"""Read-only system information collection for Linux Health Auditor.

This module reads operating-system metadata and Linux procfs files.
It does not execute shell commands or modify the host system.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shlex
import socket


@dataclass
class SystemInfo:
    """Structured snapshot of selected system information."""

    hostname: str
    os_name: str
    os_version: str
    os_id: str
    kernel_release: str
    architecture: str
    cpu_model: str
    logical_cpus: int
    physical_cores: int | None
    memory_total_kib: int
    memory_available_kib: int


def parse_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    """Parse the KEY=VALUE entries in an os-release file."""
    values: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, raw_value = line.split("=", maxsplit=1)
        parsed_parts = shlex.split(raw_value, comments=False, posix=True)
        values[key] = parsed_parts[0] if parsed_parts else ""

    return values


def parse_meminfo(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    """Return selected /proc/meminfo values in KiB."""
    wanted_keys = {"MemTotal", "MemAvailable"}
    memory: dict[str, int] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition(":")

        if not separator or key not in wanted_keys:
            continue

        parts = value.split()
        if not parts:
            continue

        memory[key] = int(parts[0])

    missing_keys = wanted_keys - memory.keys()
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"Missing required memory fields: {missing}")

    return memory


def parse_cpuinfo(path: Path = Path("/proc/cpuinfo")) -> dict[str, str | int | None]:
    """Extract the CPU model, logical CPU count, and physical core count."""
    text = path.read_text(encoding="utf-8")
    records: list[dict[str, str]] = []

    for block in text.strip().split("\n\n"):
        record: dict[str, str] = {}

        for line in block.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                record[key.strip()] = value.strip()

        if record:
            records.append(record)

    if not records:
        raise ValueError("No CPU records found in /proc/cpuinfo")

    first_record = records[0]
    cpu_model = (
        first_record.get("model name")
        or first_record.get("Hardware")
        or first_record.get("Processor")
        or platform.processor()
        or "Unknown"
    )

    core_pairs = {
        (record["physical id"], record["core id"])
        for record in records
        if "physical id" in record and "core id" in record
    }
    physical_cores = len(core_pairs) if core_pairs else None

    return {
        "cpu_model": cpu_model,
        "logical_cpus": os.cpu_count() or len(records),
        "physical_cores": physical_cores,
    }


def collect_system_info() -> SystemInfo:
    """Collect a read-only snapshot of basic system information."""
    os_release = parse_os_release()
    memory = parse_meminfo()
    cpu = parse_cpuinfo()

    return SystemInfo(
        hostname=socket.gethostname(),
        os_name=os_release.get("NAME", "Unknown"),
        os_version=os_release.get("VERSION_ID", "Unknown"),
        os_id=os_release.get("ID", "Unknown"),
        kernel_release=platform.release(),
        architecture=platform.machine(),
        cpu_model=str(cpu["cpu_model"]),
        logical_cpus=int(cpu["logical_cpus"]),
        physical_cores=cpu["physical_cores"],
        memory_total_kib=memory["MemTotal"],
        memory_available_kib=memory["MemAvailable"],
    )
