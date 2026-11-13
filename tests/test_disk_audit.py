"""Unit tests for the disk audit module."""

import subprocess
import unittest
from unittest.mock import patch

from src.disk_audit import (
    DiskInfo,
    collect_disk_info,
    parse_df_output,
    run_df,
)


SAMPLE_DF_OUTPUT = (
    "Filesystem Type 1B-blocks Used Avail Use% Mounted on\n"
    "/dev/sda2 ext4 234622398464 115774492672 106855186432 53% /\n"
    "/dev/sda1 vfat 535801856 6438912 529362944 2% /boot/efi\n"
    "tmpfs tmpfs 4115845120 0 4115845120 0% /run/qemu\n"
)


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


if __name__ == "__main__":
    unittest.main()
