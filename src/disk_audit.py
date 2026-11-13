"""Read-only filesystem capacity audit for Linux Health Auditor."""

from dataclasses import dataclass
import subprocess


@dataclass
class DiskInfo:
    """Capacity information for one mounted filesystem."""

    device: str
    filesystem: str
    total_bytes: int
    used_bytes: int
    available_bytes: int
    usage_percent: int | None
    mountpoint: str


def run_df() -> str:
    """Run df safely and return its output as text."""
    command = [
        "df",
        "-P",
        "--output=source,fstype,size,used,avail,pcent,target",
        "-B1",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return result.stdout


def parse_df_output(output: str) -> list[DiskInfo]:
    """Parse the selected columns from df output."""
    lines = output.splitlines()
    if not lines:
        raise ValueError("The df output is empty")

    filesystems: list[DiskInfo] = []

    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue

        parts = line.split(maxsplit=6)
        if len(parts) != 7:
            raise ValueError(
                f"Invalid df output on line {line_number}: expected 7 columns"
            )

        device, filesystem, size, used, available, percentage, mountpoint = parts

        try:
            total_bytes = int(size)
            used_bytes = int(used)
            available_bytes = int(available)
        except ValueError as error:
            raise ValueError(
                f"Invalid numeric capacity on df output line {line_number}"
            ) from error

        if min(total_bytes, used_bytes, available_bytes) < 0:
            raise ValueError(
                f"Negative capacity value on df output line {line_number}"
            )

        if percentage == "-":
            usage_percent = None
        else:
            try:
                usage_percent = int(percentage.removesuffix("%"))
            except ValueError as error:
                raise ValueError(
                    f"Invalid usage percentage on df output line {line_number}"
                ) from error

            if not 0 <= usage_percent <= 100:
                raise ValueError(
                    f"Usage percentage out of range on df output line {line_number}"
                )

        filesystems.append(
            DiskInfo(
                device=device,
                filesystem=filesystem,
                total_bytes=total_bytes,
                used_bytes=used_bytes,
                available_bytes=available_bytes,
                usage_percent=usage_percent,
                mountpoint=mountpoint,
            )
        )

    return filesystems


def collect_disk_info() -> list[DiskInfo]:
    """Collect capacity information for mounted filesystems."""
    return parse_df_output(run_df())
