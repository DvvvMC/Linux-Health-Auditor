"""Unit tests for the system information parsers."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.system_info import parse_cpuinfo, parse_meminfo, parse_os_release


class ParserTests(unittest.TestCase):
    """Test parsers with controlled input files."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_path = Path(self.temp_dir.name)

    def write_fixture(self, filename: str, content: str) -> Path:
        path = self.base_path / filename
        path.write_text(content, encoding="utf-8")
        return path

    def test_parse_os_release_handles_quotes_comments_and_equals(self) -> None:
        path = self.write_fixture(
            "os-release",
            '# comment\nNAME="Linux Mint"\nID=linuxmint\nURL="https://example.test/?a=b"\n',
        )

        result = parse_os_release(path)

        self.assertEqual(result["NAME"], "Linux Mint")
        self.assertEqual(result["ID"], "linuxmint")
        self.assertEqual(result["URL"], "https://example.test/?a=b")

    def test_parse_os_release_handles_empty_value(self) -> None:
        path = self.write_fixture("os-release-empty", "OPTIONAL_VALUE=\n")

        self.assertEqual(parse_os_release(path), {"OPTIONAL_VALUE": ""})

    def test_parse_meminfo_returns_required_values_as_integers(self) -> None:
        path = self.write_fixture(
            "meminfo",
            "MemTotal:       8000000 kB\n"
            "MemFree:        1000000 kB\n"
            "MemAvailable:   3500000 kB\n",
        )

        result = parse_meminfo(path)

        self.assertEqual(result, {"MemTotal": 8000000, "MemAvailable": 3500000})
        self.assertIsInstance(result["MemTotal"], int)

    def test_parse_meminfo_raises_when_required_field_is_missing(self) -> None:
        path = self.write_fixture("meminfo-missing", "MemTotal: 8000000 kB\n")

        with self.assertRaisesRegex(ValueError, "MemAvailable"):
            parse_meminfo(path)

    def test_parse_meminfo_raises_for_non_numeric_value(self) -> None:
        path = self.write_fixture(
            "meminfo-invalid",
            "MemTotal: not-a-number kB\nMemAvailable: 1000 kB\n",
        )

        with self.assertRaises(ValueError):
            parse_meminfo(path)

    def test_parse_cpuinfo_counts_unique_physical_cores(self) -> None:
        cpuinfo = (
            "processor : 0\nmodel name : Example CPU\nphysical id : 0\ncore id : 0\n\n"
            "processor : 1\nmodel name : Example CPU\nphysical id : 0\ncore id : 0\n\n"
            "processor : 2\nmodel name : Example CPU\nphysical id : 0\ncore id : 1\n\n"
            "processor : 3\nmodel name : Example CPU\nphysical id : 0\ncore id : 1\n"
        )
        path = self.write_fixture("cpuinfo", cpuinfo)

        with patch("src.system_info.os.cpu_count", return_value=4):
            result = parse_cpuinfo(path)

        self.assertEqual(result["cpu_model"], "Example CPU")
        self.assertEqual(result["logical_cpus"], 4)
        self.assertEqual(result["physical_cores"], 2)

    def test_parse_cpuinfo_leaves_physical_cores_unknown_without_topology(self) -> None:
        path = self.write_fixture(
            "cpuinfo-no-topology",
            "processor : 0\nmodel name : Example CPU\n\n"
            "processor : 1\nmodel name : Example CPU\n",
        )

        with patch("src.system_info.os.cpu_count", return_value=2):
            result = parse_cpuinfo(path)

        self.assertIsNone(result["physical_cores"])

    def test_parse_cpuinfo_raises_for_empty_file(self) -> None:
        path = self.write_fixture("cpuinfo-empty", "")

        with self.assertRaisesRegex(ValueError, "No CPU records"):
            parse_cpuinfo(path)


if __name__ == "__main__":
    unittest.main()
