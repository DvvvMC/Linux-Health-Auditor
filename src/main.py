"""Command-line entry point for Linux Health Auditor.

The first version is intentionally read-only. Audit modules are added
incrementally and collect information without modifying the host system.
"""

import subprocess

from disk_audit import collect_disk_info
from system_info import collect_system_info


def kib_to_gib(value: int) -> float:
    """Convert a memory value from KiB to GiB."""
    return value / (1024 ** 2)


def bytes_to_gib(value: int) -> float:
    """Convert a byte value to GiB."""
    return value / (1024 ** 3)


def main() -> None:
    """Collect and display system and filesystem information."""
    try:
        info = collect_system_info()
        filesystems = collect_disk_info()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"System audit failed: {error}")
        return

    print("=" * 52)
    print("             LINUX HEALTH AUDITOR")
    print("              SYSTEM INFORMATION")
    print("=" * 52)

    print("\n[Operating System]")
    print(f"Hostname:          {info.hostname}")
    print(f"Distribution:      {info.os_name}")
    print(f"Version:           {info.os_version}")
    print(f"Distribution ID:   {info.os_id}")
    print(f"Kernel:            {info.kernel_release}")
    print(f"Architecture:      {info.architecture}")

    print("\n[CPU]")
    print(f"Model:             {info.cpu_model}")
    print(f"Logical CPUs:      {info.logical_cpus}")
    physical_cores = (
        str(info.physical_cores)
        if info.physical_cores is not None
        else "Unknown"
    )
    print(f"Physical cores:    {physical_cores}")

    print("\n[Memory]")
    print(
        f"Total:             {info.memory_total_kib:,} KiB "
        f"({kib_to_gib(info.memory_total_kib):.2f} GiB)"
    )
    print(
        f"Available:         {info.memory_available_kib:,} KiB "
        f"({kib_to_gib(info.memory_available_kib):.2f} GiB)"
    )

    print("\n[Disk / Filesystem]")
    for filesystem in filesystems:
        usage = (
            f"{filesystem.usage_percent}%"
            if filesystem.usage_percent is not None
            else "Unknown"
        )
        print(f"Device:            {filesystem.device}")
        print(f"Filesystem:        {filesystem.filesystem}")
        print(f"Mount point:       {filesystem.mountpoint}")
        print(
            f"Total:             {filesystem.total_bytes:,} bytes "
            f"({bytes_to_gib(filesystem.total_bytes):.2f} GiB)"
        )
        print(
            f"Used:              {filesystem.used_bytes:,} bytes "
            f"({bytes_to_gib(filesystem.used_bytes):.2f} GiB)"
        )
        print(
            f"Available:         {filesystem.available_bytes:,} bytes "
            f"({bytes_to_gib(filesystem.available_bytes):.2f} GiB)"
        )
        print(f"Usage:             {usage}")
        print("-" * 52)

    print("\n" + "=" * 52)
    print("Audit mode: READ-ONLY")
    print("=" * 52)


if __name__ == "__main__":
    main()
