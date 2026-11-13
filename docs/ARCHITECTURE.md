# Linux Health Auditor — Architecture

## 1. Product Direction

Linux Health Auditor is a read-only Linux system auditing application.

The final product will provide two interfaces:

- **CLI:** a practical command-line interface for terminal workflows,
  automation-friendly execution, and troubleshooting.
- **GUI:** a desktop interface using **PySide6**, following a
  **Dark Professional** visual direction.

Both interfaces must use the same Python core. The GUI is an additional
presentation layer, not a separate implementation of the auditing logic.

## 2. High-Level Architecture

```text
                    Linux Health Auditor
                             |
                 Application / Interface Layer
                       /           \
                      /             \
               CLI Interface     GUI Interface
                                  PySide6
                       \           /
                        \         /
                     Shared Python Core
              /             |              \
       Collectors         Analysis       Report Engine
              |
       Linux system sources
       (/proc, /etc, df, lsblk,
        systemd tools, etc.)
```

### Layer responsibilities

| Layer | Responsibility |
|---|---|
| CLI | Parse arguments, invoke core operations, display text output |
| GUI | Present dashboards, audit results, status, and report actions |
| Core collectors | Gather system data using read-only operations |
| Parsers | Convert command output and system files into structured data |
| Analysis | Derive transparent health indicators from collected facts |
| Report engine | Produce Markdown reports from core audit results |

The core must not import GUI or CLI modules. Interface modules may import
core modules; the reverse dependency is not allowed.

## 3. Design Rules

1. **Read-only by default:** no configuration changes, file deletion,
   permission changes, package installation, user changes, or service
   restarts.
2. **One source of audit logic:** CLI and GUI call the same core functions.
3. **Structured data:** collectors return dataclasses or other explicit
   data structures rather than printing directly.
4. **Separation of concerns:** collection, parsing, analysis, presentation,
   and reporting remain distinct responsibilities.
5. **Safe subprocess use:** pass argument lists to `subprocess.run`;
   do not build shell command strings or use `shell=True`.
6. **Bounded execution:** external commands should use sensible timeouts and
   explicit error handling.
7. **Honest results:** distinguish unavailable data, permission errors,
   missing tools, and actual unhealthy states. Never silently invent values.
8. **Testability:** parsers and analysis functions should be testable with
   fixture data and mocked subprocess calls.
9. **Sensitive output:** generated reports may contain hostnames, usernames,
   addresses, UUIDs, and other system details. Keep generated reports out of
   Git commits by default.
10. **No duplicated business logic:** GUI widgets must not parse raw system
    command output independently from the core.

## 4. Planned Source Layout

The repository will move toward this structure as implementation grows:

```text
src/
├── core/
│   ├── system_info.py
│   ├── disk_audit.py
│   ├── service_audit.py
│   ├── user_audit.py
│   ├── network_audit.py
│   ├── login_audit.py
│   └── report.py
├── cli/
│   └── ...
├── gui/
│   ├── ...
│   └── styles/
└── main.py
```

This is a target layout. Existing modules currently live directly under
`src/`; they will be moved only as a deliberate refactoring step with tests
updated and passing.

## 5. GUI Direction — Dark Professional

The planned GUI should feel like a focused system-administration dashboard.

### Main dashboard

- Overview cards for CPU, memory, storage, and system identity.
- Clear audit status and timestamps.
- Navigation to individual audit sections.
- Tables for filesystems, block devices, partitions, services, and findings.
- A readable details panel for errors and unavailable data.
- Markdown report preview and export.

### Visual principles

- Dark neutral base with restrained accent colors.
- Strong contrast and readable typography.
- Consistent spacing and clear information hierarchy.
- Color must not be the only way to communicate severity or status.
- Avoid decorative charts that imply precision not present in the source data.

### GUI safety

The GUI will initially be an inspection and reporting interface only.
Buttons such as “Run Audit” and “Export Report” may collect or export data,
but must not make system changes. Any future feature that could change the
host requires a separate design and explicit safety review; it is outside
the current project scope.

## 6. Technology Choices

- **Python 3.12+:** application language.
- **Python standard library:** preferred for core collection, parsing,
  subprocess handling, and tests.
- **PySide6:** planned GUI toolkit.
- **unittest:** current test framework.
- **Git/GitHub:** source control and project documentation.

PySide6 is not required for the current CLI and audit lessons. It will be
added to project dependencies when GUI development starts.

## 7. Implementation Roadmap

1. Project foundation and environment setup — complete.
2. System information audit — complete.
3. Disk audit:
   - filesystem capacity — implemented;
   - block-device and partition inventory — next.
4. Service audit.
5. User and sudo audit.
6. Network audit.
7. Login history audit.
8. Failed systemd services audit.
9. Shared Markdown report engine.
10. CLI integration and stabilization.
11. GUI foundation with PySide6.
12. Dark Professional dashboard and audit views.
13. Connect GUI to the shared core and report engine.
14. Testing, documentation, packaging, and first release.

The CLI remains supported after the GUI is introduced.

## 8. Definition of Done for GUI Integration

- GUI imports and calls shared core functions; it does not duplicate audit
  collection or parsing.
- CLI behavior remains available and tested.
- Both interfaces report errors and missing data clearly.
- Long-running audit tasks do not freeze the GUI.
- GUI actions remain read-only.
- Report generation is shared by both interfaces.
- Tests cover core behavior independently of the GUI.
