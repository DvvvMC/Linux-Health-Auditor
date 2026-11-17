"""Read-only systemd service audit for Linux Health Auditor."""

from dataclasses import dataclass
import json
import subprocess


@dataclass
class ServiceInfo:
    """Structured runtime and unit-file information for one service."""

    name: str
    description: str
    load_state: str
    active_state: str
    sub_state: str
    unit_file_state: str
    unit_file_preset: str | None
    fragment_path: str | None

    @property
    def is_failed(self) -> bool:
        """Return whether systemd currently marks the service as failed."""
        return self.active_state == "failed"


def run_systemctl_list_units() -> str:
    """Return systemd service runtime information as JSON."""
    command = [
        "systemctl",
        "list-units",
        "--type=service",
        "--all",
        "--output=json",
        "--no-pager",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return result.stdout


def run_systemctl_list_unit_files() -> str:
    """Return installed service unit-file states as a text table."""
    command = [
        "systemctl",
        "list-unit-files",
        "--type=service",
        "--no-legend",
        "--no-pager",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return result.stdout


def parse_systemctl_units_json(output: str) -> dict[str, dict[str, str | None]]:
    """Parse systemctl list-units JSON into records keyed by unit name."""
    try:
        document = json.loads(output)
    except json.JSONDecodeError as error:
        raise ValueError("The systemctl list-units output is not valid JSON") from error

    if not isinstance(document, list):
        raise ValueError("The systemctl JSON root must be a list")

    units: dict[str, dict[str, str | None]] = {}

    for index, entry in enumerate(document):
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid systemctl unit entry at index {index}")

        name = entry.get("unit")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Missing or invalid unit name at index {index}")

        fields = {
            "description": entry.get("description"),
            "load_state": entry.get("load"),
            "active_state": entry.get("active"),
            "sub_state": entry.get("sub"),
            "fragment_path": entry.get("unit_path"),
        }

        for field, value in fields.items():
            if value is not None and not isinstance(value, str):
                raise ValueError(f"Invalid {field} for systemd unit {name}")

        units[name] = fields

    return units


def parse_unit_files_output(output: str) -> dict[str, tuple[str, str | None]]:
    """Parse list-unit-files rows into name -> (state, preset)."""
    unit_files: dict[str, tuple[str, str | None]] = {}

    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue

        parts = line.split(maxsplit=2)

        # Be tolerant if a systemctl version or environment still emits a header.
        if parts[0] in {"UNIT", "UNIT FILE"}:
            continue

        if len(parts) not in {2, 3}:
            raise ValueError(
                f"Invalid systemctl list-unit-files output on line {line_number}"
            )

        name, state = parts[0], parts[1]
        preset = parts[2] if len(parts) == 3 else None

        if not name.endswith(".service"):
            raise ValueError(
                f"Unexpected non-service unit on line {line_number}: {name}"
            )

        unit_files[name] = (state, preset)

    return unit_files


def collect_services() -> list[ServiceInfo]:
    """Collect and merge runtime service states with unit-file states."""
    runtime_units = parse_systemctl_units_json(run_systemctl_list_units())
    unit_files = parse_unit_files_output(run_systemctl_list_unit_files())

    service_names = sorted(set(runtime_units) | set(unit_files))
    services: list[ServiceInfo] = []

    for name in service_names:
        runtime = runtime_units.get(name, {})
        file_state, preset = unit_files.get(name, ("unknown", None))

        services.append(
            ServiceInfo(
                name=name,
                description=runtime.get("description") or "",
                load_state=runtime.get("load_state") or "not-loaded",
                active_state=runtime.get("active_state") or "unknown",
                sub_state=runtime.get("sub_state") or "unknown",
                unit_file_state=file_state,
                unit_file_preset=preset,
                fragment_path=runtime.get("fragment_path") or None,
            )
        )

    return services
