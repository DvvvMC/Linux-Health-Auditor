"""Read-only disk and block-device audit for Linux Health Auditor."""

from dataclasses import dataclass
import json
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


@dataclass
class BlockDevice:
    """Structured information about one block device in the device tree."""

    name: str
    path: str
    device_type: str
    size_bytes: int
    read_only: bool
    transport: str | None
    filesystem: str | None
    uuid: str | None
    mountpoints: list[str]
    parent_path: str | None


def run_df() -> str:
    """Run df safely and return its output as text."""
    command = [
        "df",
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


def run_lsblk() -> str:
    """Run lsblk safely and return its JSON output as text."""
    command = [
        "lsblk",
        "--json",
        "--bytes",
        "--tree",
        "--output=NAME,PATH,TYPE,SIZE,RO,TRAN,FSTYPE,UUID,MOUNTPOINTS",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return result.stdout


def parse_lsblk_output(output: str) -> list[BlockDevice]:
    """Parse lsblk JSON and flatten its nested device tree."""
    try:
        document = json.loads(output)
    except json.JSONDecodeError as error:
        raise ValueError("The lsblk output is not valid JSON") from error

    if not isinstance(document, dict):
        raise ValueError("The lsblk JSON root must be an object")

    root_devices = document.get("blockdevices")
    if not isinstance(root_devices, list):
        raise ValueError("The lsblk JSON must contain a blockdevices list")

    devices: list[BlockDevice] = []

    def walk_devices(
        entries: list[object],
        parent_path: str | None = None,
    ) -> None:
        """Visit each device and its children, preserving parent information."""
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each lsblk device entry must be an object")

            required_fields = ("name", "path", "type", "size", "ro")
            missing_fields = [
                field for field in required_fields if field not in entry
            ]
            if missing_fields:
                missing = ", ".join(missing_fields)
                raise ValueError(f"Missing required lsblk fields: {missing}")

            name = entry["name"]
            path = entry["path"]
            device_type = entry["type"]
            size_bytes = entry["size"]
            read_only = entry["ro"]

            if not all(isinstance(value, str) and value for value in (
                name, path, device_type
            )):
                raise ValueError("lsblk name, path, and type must be non-empty strings")

            if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
                raise ValueError(f"Invalid size for block device {path}")
            if size_bytes < 0:
                raise ValueError(f"Negative size for block device {path}")

            if not isinstance(read_only, bool):
                raise ValueError(f"Invalid read-only flag for block device {path}")

            optional_fields = ("tran", "fstype", "uuid")
            for field in optional_fields:
                value = entry.get(field)
                if value is not None and not isinstance(value, str):
                    raise ValueError(f"Invalid {field} value for block device {path}")

            raw_mountpoints = entry.get("mountpoints")
            if raw_mountpoints is None:
                mountpoints = []
            elif isinstance(raw_mountpoints, list):
                if any(
                    value is not None and not isinstance(value, str)
                    for value in raw_mountpoints
                ):
                    raise ValueError(f"Invalid mountpoints for block device {path}")
                mountpoints = [
                    value for value in raw_mountpoints if isinstance(value, str)
                ]
            else:
                raise ValueError(f"Invalid mountpoints for block device {path}")

            children = entry.get("children", [])
            if not isinstance(children, list):
                raise ValueError(f"Invalid children list for block device {path}")

            devices.append(
                BlockDevice(
                    name=name,
                    path=path,
                    device_type=device_type,
                    size_bytes=size_bytes,
                    read_only=read_only,
                    transport=entry.get("tran"),
                    filesystem=entry.get("fstype"),
                    uuid=entry.get("uuid"),
                    mountpoints=mountpoints,
                    parent_path=parent_path,
                )
            )

            walk_devices(children, parent_path=path)

    walk_devices(root_devices)
    return devices


def collect_disk_info() -> list[DiskInfo]:
    """Collect capacity information for mounted filesystems."""
    return parse_df_output(run_df())


def collect_block_devices() -> list[BlockDevice]:
    """Collect block devices and partition relationships from lsblk."""
    return parse_lsblk_output(run_lsblk())
