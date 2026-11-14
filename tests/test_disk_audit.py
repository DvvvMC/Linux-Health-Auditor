"""Unit tests for the disk audit module."""

import subprocess
import unittest
from unittest.mock import patch

from src.disk_audit import (
    BlockDevice,
    DiskInfo,
    collect_block_devices,
    collect_disk_info,
    parse_df_output,
    parse_lsblk_output,
    run_df,
    run_lsblk,
)


SAMPLE_DF_OUTPUT = (
    "Filesystem Type 1B-blocks Used Avail Use% Mounted on\n"
    "/dev/sda2 ext4 234622398464 115774492672 106855186432 53% /\n"
    "/dev/sda1 vfat 535801856 6438912 529362944 2% /boot/efi\n"
    "tmpfs tmpfs 4115845120 0 4115845120 0% /run/qemu\n"
)

SAMPLE_LSBLK_OUTPUT = """{
  "blockdevices": [
    {
      "name": "sda",
      "path": "/dev/sda",
      "type": "disk",
      "size": 240057409536,
      "ro": false,
      "tran": "sata",
      "fstype": null,
      "uuid": null,
      "mountpoints": [null],
      "children": [
        {
          "name": "sda1",
          "path": "/dev/sda1",
          "type": "part",
          "size": 536870912,
          "ro": false,
          "tran": null,
          "fstype": "vfat",
          "uuid": "2117-6762",
          "mountpoints": ["/boot/efi"]
        },
        {
          "name": "sda2",
          "path": "/dev/sda2",
          "type": "part",
          "size": 239518875648,
          "ro": false,
          "tran": null,
          "fstype": "ext4",
          "uuid": "3ea55d2d-837c-40d5-9611-021e1271c28b",
          "mountpoints": ["/"]
        }
      ]
    }
  ]
}"""


class ParseDfOutputTests(unittest.TestCase):
    """Test df output parsing with controlled text."""

    def test_parses_multiple_filesystems(self) -> None:
        result = parse_df_output(SAMPLE_DF_OUTPUT)

        self.assertEqual(len(result), 3)
        self.assertEqual(
            result[0],
            DiskInfo(
                device="/dev/sda2",
                filesystem="ext4",
                total_bytes=234622398464,
                used_bytes=115774492672,
                available_bytes=106855186432,
                usage_percent=53,
                mountpoint="/",
            ),
        )
        self.assertEqual(result[1].mountpoint, "/boot/efi")
        self.assertEqual(result[2].filesystem, "tmpfs")

    def test_preserves_mountpoint_with_spaces(self) -> None:
        output = (
            "Filesystem Type 1B-blocks Used Avail Use% Mounted on\n"
            "/dev/example ext4 1000 400 600 40% /mnt/my drive\n"
        )

        result = parse_df_output(output)

        self.assertEqual(result[0].mountpoint, "/mnt/my drive")

    def test_supports_unknown_usage_percentage(self) -> None:
        output = (
            "Filesystem Type 1B-blocks Used Avail Use% Mounted on\n"
            "examplefs fuse 1000 100 900 - /mnt/example\n"
        )

        result = parse_df_output(output)

        self.assertIsNone(result[0].usage_percent)

    def test_raises_for_empty_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty"):
            parse_df_output("")

    def test_raises_for_invalid_column_count(self) -> None:
        output = "Filesystem Type Size Used Avail Use% Mounted on\ninvalid row\n"

        with self.assertRaisesRegex(ValueError, "7 columns"):
            parse_df_output(output)

    def test_raises_for_non_numeric_capacity(self) -> None:
        output = (
            "Filesystem Type 1B-blocks Used Avail Use% Mounted on\n"
            "/dev/sda2 ext4 not-a-number 100 200 50% /\n"
        )

        with self.assertRaisesRegex(ValueError, "numeric capacity"):
            parse_df_output(output)

    def test_raises_for_out_of_range_percentage(self) -> None:
        output = (
            "Filesystem Type 1B-blocks Used Avail Use% Mounted on\n"
            "/dev/sda2 ext4 1000 500 500 120% /\n"
        )

        with self.assertRaisesRegex(ValueError, "out of range"):
            parse_df_output(output)


class ParseLsblkOutputTests(unittest.TestCase):
    """Test recursive lsblk JSON parsing."""

    def test_parses_device_tree_and_parent_relationships(self) -> None:
        result = parse_lsblk_output(SAMPLE_LSBLK_OUTPUT)

        self.assertEqual(len(result), 3)
        self.assertEqual(
            result[0],
            BlockDevice(
                name="sda",
                path="/dev/sda",
                device_type="disk",
                size_bytes=240057409536,
                read_only=False,
                transport="sata",
                filesystem=None,
                uuid=None,
                mountpoints=[],
                parent_path=None,
            ),
        )
        self.assertEqual(result[1].parent_path, "/dev/sda")
        self.assertEqual(result[1].mountpoints, ["/boot/efi"])
        self.assertEqual(result[2].filesystem, "ext4")
        self.assertEqual(result[2].mountpoints, ["/"])

    def test_supports_missing_children_and_null_mountpoints(self) -> None:
        output = """{
          "blockdevices": [{
            "name": "loop0",
            "path": "/dev/loop0",
            "type": "loop",
            "size": 1024,
            "ro": true,
            "tran": null,
            "fstype": null,
            "uuid": null,
            "mountpoints": [null]
          }]
        }"""

        result = parse_lsblk_output(output)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].mountpoints, [])
        self.assertTrue(result[0].read_only)
        self.assertIsNone(result[0].parent_path)

    def test_raises_for_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            parse_lsblk_output("{not-json}")

    def test_raises_when_blockdevices_is_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "blockdevices list"):
            parse_lsblk_output("{}")

    def test_raises_for_invalid_size(self) -> None:
        output = """{
          "blockdevices": [{
            "name": "sda",
            "path": "/dev/sda",
            "type": "disk",
            "size": "large",
            "ro": false
          }]
        }"""

        with self.assertRaisesRegex(ValueError, "Invalid size"):
            parse_lsblk_output(output)

    def test_raises_for_invalid_children(self) -> None:
        output = """{
          "blockdevices": [{
            "name": "sda",
            "path": "/dev/sda",
            "type": "disk",
            "size": 1000,
            "ro": false,
            "children": {}
          }]
        }"""

        with self.assertRaisesRegex(ValueError, "Invalid children"):
            parse_lsblk_output(output)


class CollectDiskInfoTests(unittest.TestCase):
    """Test command execution and collection orchestration."""

    @patch("src.disk_audit.subprocess.run")
    def test_run_df_uses_argument_list_without_shell(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["df"], returncode=0, stdout=SAMPLE_DF_OUTPUT, stderr=""
        )

        output = run_df()

        self.assertEqual(output, SAMPLE_DF_OUTPUT)
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0][0], "df")
        self.assertIn("--output=source,fstype,size,used,avail,pcent,target", args[0])
        self.assertNotIn("-P", args[0])
        self.assertNotIn("shell", kwargs)
        self.assertTrue(kwargs["check"])
        self.assertTrue(kwargs["capture_output"])

    @patch("src.disk_audit.run_df", return_value=SAMPLE_DF_OUTPUT)
    def test_collect_disk_info_returns_parsed_records(self, mock_run_df) -> None:
        result = collect_disk_info()

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].device, "/dev/sda2")
        mock_run_df.assert_called_once_with()

    @patch("src.disk_audit.subprocess.run")
    def test_run_lsblk_uses_safe_json_command(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["lsblk"], returncode=0, stdout=SAMPLE_LSBLK_OUTPUT, stderr=""
        )

        output = run_lsblk()

        self.assertEqual(output, SAMPLE_LSBLK_OUTPUT)
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0][0], "lsblk")
        self.assertIn("--json", args[0])
        self.assertIn("--bytes", args[0])
        self.assertIn("--tree", args[0])
        self.assertTrue(kwargs["check"])
        self.assertTrue(kwargs["capture_output"])
        self.assertNotIn("shell", kwargs)

    @patch("src.disk_audit.run_lsblk", return_value=SAMPLE_LSBLK_OUTPUT)
    def test_collect_block_devices_returns_parsed_records(self, mock_run_lsblk) -> None:
        result = collect_block_devices()

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].path, "/dev/sda")
        mock_run_lsblk.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
