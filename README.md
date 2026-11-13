# Linux Health Auditor

A read-only Linux system health auditing tool built with Python, featuring both a command-line interface (CLI) and a graphical user interface (GUI).

## Project Overview

Linux Health Auditor collects selected system information, checks common
health indicators, and produces a human-readable Markdown report.

The project is developed incrementally, with an emphasis on safe system
inspection, clear error handling, modular design, and testability.

The planned desktop interface follows a **Dark Professional** design direction.
The CLI will remain a first-class interface; the GUI will complement it rather
than replace it.

## Planned Features

- [x] Project foundation and development environment
- [x] System information audit
- [ ] Disk capacity and block-device/partition inventory
- [ ] Service status audit
- [ ] User and sudo configuration audit
- [ ] Network listening-port audit
- [ ] Login history audit
- [ ] Failed systemd services audit
- [ ] Shared Markdown report generation
- [ ] CLI and GUI integration
- [ ] Dark Professional desktop dashboard
- [ ] Automated tests and release preparation

## Architecture

The application will use a shared Python core with two independent interfaces:

```text
                    Linux Health Auditor
                             |
                    Shared Python Core
             (collection, parsing, analysis, reports)
                       /           \
                      /             \
               CLI Interface     GUI Interface
                                (Dark Professional)
```

The core contains the auditing logic and must not depend on either interface.
The CLI and GUI call the same core functions so that results and safety
behavior remain consistent.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the architecture,
design principles, and planned implementation structure.

## Technology Stack

- Python 3.12+
- Linux
- Python standard library for the audit core wherever practical
- PySide6 (planned) for the graphical interface
- Git and GitHub

PySide6 will be introduced when GUI implementation begins. The current audit
modules do not require third-party packages.

## Security Philosophy

The initial version is strictly read-only.

The tool is designed to inspect and report. It must not modify system
configurations, users, permissions, files, packages, or running services.

The GUI must follow the same read-only policy as the CLI. A graphical control
must never silently perform a system-changing action.

Collected reports may contain sensitive system information. Generated
reports are therefore excluded from version control by `.gitignore`.

## Project Structure

The project is being expanded incrementally. The intended structure is:

```text
Linux-Health-Auditor/
├── src/
│   ├── core/       # Shared collection, parsing, and analysis logic
│   ├── cli/        # Command-line interface
│   ├── gui/        # PySide6 graphical interface
│   └── main.py     # Current CLI entry point during development
├── tests/
├── docs/
│   └── ARCHITECTURE.md
├── reports/
├── README.md
├── requirements.txt
└── .gitignore
```

This is the target structure, not a claim that all directories have already
been implemented.

## Development

The current audit modules use the Python standard library, so no third-party
packages are needed for the CLI work completed so far.

On Linux, create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
```

Run the current application entry point from the repository root:

```bash
python src/main.py
```

PySide6 installation and GUI launch instructions will be added when the GUI
implementation begins.

Deactivate the virtual environment when finished:

```bash
deactivate
```

## Project Status

Under development. The project foundation and system information audit are
complete. The filesystem capacity audit is implemented; block-device and
partition inventory is the next part of the disk audit.

The final application is planned to provide both CLI and GUI interfaces over
one shared, read-only Python core.
