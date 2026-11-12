# Linux Health Auditor

A read-only Linux system health auditing tool built with Python.

## Project Overview

Linux Health Auditor collects selected system information, checks common
health indicators, and produces a human-readable Markdown report.

The project is being developed incrementally, with an emphasis on safe
system inspection, clear error handling, modular design, and testability.

## Planned Features

- [ ] System information audit
- [ ] Disk usage audit
- [ ] Service status audit
- [ ] User and sudo configuration audit
- [ ] Network listening-port audit
- [ ] Login history audit
- [ ] Failed systemd services audit
- [ ] Markdown report generation
- [ ] Automated tests and release preparation

## Technology Stack

- Python 3.12+
- Linux
- Python standard library
- Git and GitHub

## Security Philosophy

The initial version is strictly read-only.

The tool is designed to inspect and report. It must not modify system
configurations, users, permissions, files, packages, or running services.

Collected reports may contain sensitive system information. Generated
reports are therefore excluded from version control by `.gitignore`.

## Project Structure

```text
Linux-Health-Auditor/
├── src/
│   └── main.py
├── tests/
├── docs/
├── reports/
├── README.md
├── requirements.txt
└── .gitignore
```

## Development

The project currently uses only the Python standard library, so no
third-party packages need to be installed.

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

Deactivate the virtual environment when finished:

```bash
deactivate
```

## Project Status

Under development — project foundation in progress.
