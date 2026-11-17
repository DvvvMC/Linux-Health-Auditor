"""Unit tests for the systemd service audit module."""

import subprocess
import unittest
from unittest.mock import patch

from src.service_audit import (
    ServiceInfo,
    collect_services,
    parse_systemctl_units_json,
    parse_unit_files_output,
    run_systemctl_list_unit_files,
    run_systemctl_list_units,
)


SAMPLE_UNITS_JSON = """[
  {
    "unit": "cron.service",
    "description": "Regular background program processing daemon",
    "load": "loaded",
    "active": "active",
    "sub": "running",
    "unit_path": "/usr/lib/systemd/system/cron.service"
  },
  {
    "unit": "casper-md5check.service",
    "description": "Verify Live ISO checksums",
    "load": "loaded",
    "active": "failed",
    "sub": "failed",
    "unit_path": "/usr/lib/systemd/system/casper-md5check.service"
  }
]"""

SAMPLE_UNIT_FILES = (
    "cron.service enabled enabled\n"
    "casper-md5check.service enabled enabled\n"
    "example-static.service static -\n"
    "example-masked.service masked enabled\n"
)


class ParseSystemctlUnitsJsonTests(unittest.TestCase):
    """Test parsing of systemctl's JSON runtime output."""

    def test_parses_runtime_properties(self) -> None:
        result = parse_systemctl_units_json(SAMPLE_UNITS_JSON)

        self.assertEqual(result["cron.service"]["active_state"], "active")
        self.assertEqual(result["cron.service"]["sub_state"], "running")
        self.assertEqual(
            result["cron.service"]["fragment_path"],
            "/usr/lib/systemd/system/cron.service",
        )
        self.assertEqual(result["casper-md5check.service"]["active_state"], "failed")

    def test_accepts_empty_unit_list(self) -> None:
        self.assertEqual(parse_systemctl_units_json("[]"), {})

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            parse_systemctl_units_json("{not-json}")

    def test_rejects_non_list_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "root must be a list"):
            parse_systemctl_units_json("{}")

    def test_rejects_entry_without_unit_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "unit name"):
            parse_systemctl_units_json('[{"active": "active"}]')

    def test_rejects_non_string_property(self) -> None:
        output = '[{"unit": "bad.service", "active": false}]'
        with self.assertRaisesRegex(ValueError, "active_state"):
            parse_systemctl_units_json(output)


class ParseUnitFilesOutputTests(unittest.TestCase):
    """Test parsing of unit-file installation states."""

    def test_parses_enabled_static_and_masked_states(self) -> None:
        result = parse_unit_files_output(SAMPLE_UNIT_FILES)

        self.assertEqual(result["cron.service"], ("enabled", "enabled"))
        self.assertEqual(result["example-static.service"], ("static", "-"))
        self.assertEqual(result["example-masked.service"], ("masked", "enabled"))

    def test_skips_optional_header(self) -> None:
        output = "UNIT FILE STATE PRESET\ncron.service enabled enabled\n"
        self.assertEqual(
            parse_unit_files_output(output),
            {"cron.service": ("enabled", "enabled")},
        )

    def test_accepts_empty_output(self) -> None:
        self.assertEqual(parse_unit_files_output(""), {})

    def test_rejects_malformed_row(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid systemctl"):
            parse_unit_files_output("cron.service")

    def test_rejects_non_service_unit(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-service"):
            parse_unit_files_output("multi-user.target enabled enabled")


class ServiceCollectionTests(unittest.TestCase):
    """Test safe command execution and merging of service data."""

    @patch("src.service_audit.subprocess.run")
    def test_runtime_command_uses_json_and_safe_subprocess(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["systemctl"], returncode=0, stdout=SAMPLE_UNITS_JSON, stderr=""
        )

        output = run_systemctl_list_units()

        self.assertEqual(output, SAMPLE_UNITS_JSON)
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0][0], "systemctl")
        self.assertIn("--output=json", args[0])
        self.assertIn("--type=service", args[0])
        self.assertTrue(kwargs["check"])
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["timeout"], 15)
        self.assertNotIn("shell", kwargs)

    @patch("src.service_audit.subprocess.run")
    def test_unit_file_command_uses_safe_subprocess(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["systemctl"], returncode=0, stdout=SAMPLE_UNIT_FILES, stderr=""
        )

        output = run_systemctl_list_unit_files()

        self.assertEqual(output, SAMPLE_UNIT_FILES)
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0][0], "systemctl")
        self.assertIn("list-unit-files", args[0])
        self.assertIn("--no-legend", args[0])
        self.assertTrue(kwargs["check"])
        self.assertTrue(kwargs["capture_output"])
        self.assertNotIn("shell", kwargs)

    @patch(
        "src.service_audit.run_systemctl_list_unit_files",
        return_value=SAMPLE_UNIT_FILES,
    )
    @patch(
        "src.service_audit.run_systemctl_list_units",
        return_value=SAMPLE_UNITS_JSON,
    )
    def test_collect_services_merges_runtime_and_file_data(
        self, mock_runtime, mock_files
    ) -> None:
        result = collect_services()

        self.assertEqual(len(result), 4)
        cron = next(item for item in result if item.name == "cron.service")
        failed = next(
            item for item in result if item.name == "casper-md5check.service"
        )
        static = next(
            item for item in result if item.name == "example-static.service"
        )

        self.assertEqual(cron.description, "Regular background program processing daemon")
        self.assertEqual(cron.active_state, "active")
        self.assertEqual(cron.unit_file_state, "enabled")
        self.assertFalse(cron.is_failed)

        self.assertEqual(failed.active_state, "failed")
        self.assertTrue(failed.is_failed)

        self.assertEqual(static.load_state, "not-loaded")
        self.assertEqual(static.active_state, "unknown")
        self.assertEqual(static.unit_file_state, "static")

        mock_runtime.assert_called_once_with()
        mock_files.assert_called_once_with()

    def test_service_info_failed_property(self) -> None:
        service = ServiceInfo(
            name="example.service",
            description="Example",
            load_state="loaded",
            active_state="failed",
            sub_state="failed",
            unit_file_state="enabled",
            unit_file_preset="enabled",
            fragment_path=None,
        )

        self.assertTrue(service.is_failed)


if __name__ == "__main__":
    unittest.main()
