"""Unit tests for the read-only user and sudo audit module."""

from pathlib import Path
import tempfile
import unittest

from src.user_audit import (
    collect_user_audit,
    inspect_sudoers_file,
    parse_group_text,
    parse_passwd_text,
    parse_sudoers_text,
)


PASSWD = (
    "root:x:0:0:root:/root:/bin/bash\n"
    "alice:x:1000:1000:Alice:/home/alice:/bin/bash\n"
    "service:x:998:998:Service:/nonexistent:/usr/sbin/nologin\n"
)
GROUP = (
    "root:x:0:\n"
    "users:x:1000:alice\n"
    "sudo:x:27:alice,missing-user\n"
    "service:x:998:\n"
)


class ParsePasswdTests(unittest.TestCase):
    def test_parses_valid_accounts_and_ignores_password_field(self):
        records = parse_passwd_text(PASSWD)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[1]["username"], "alice")
        self.assertEqual(records[1]["uid"], 1000)
        self.assertNotIn("password", records[1])

    def test_accepts_empty_and_comment_lines(self):
        self.assertEqual(parse_passwd_text("# comment\n\n"), [])

    def test_rejects_wrong_field_count(self):
        with self.assertRaisesRegex(ValueError, "passwd entry"):
            parse_passwd_text("alice:x:1000")

    def test_rejects_non_numeric_ids(self):
        with self.assertRaisesRegex(ValueError, "UID or GID"):
            parse_passwd_text("alice:x:bad:1000::/home/alice:/bin/bash")

    def test_rejects_negative_ids(self):
        with self.assertRaisesRegex(ValueError, "Negative"):
            parse_passwd_text("alice:x:-1:1000::/home/alice:/bin/bash")

    def test_rejects_duplicate_usernames(self):
        line = "alice:x:1000:1000::/home/alice:/bin/bash\n"
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_passwd_text(line + line)


class ParseGroupTests(unittest.TestCase):
    def test_parses_groups_and_members(self):
        records = parse_group_text(GROUP)
        sudo = next(record for record in records if record["name"] == "sudo")
        self.assertEqual(sudo["gid"], 27)
        self.assertEqual(sudo["members"], ("alice", "missing-user"))

    def test_accepts_empty_and_comment_lines(self):
        self.assertEqual(parse_group_text("# comment\n"), [])

    def test_rejects_wrong_field_count(self):
        with self.assertRaisesRegex(ValueError, "group entry"):
            parse_group_text("sudo:x:27")

    def test_rejects_non_numeric_gid(self):
        with self.assertRaisesRegex(ValueError, "Invalid GID"):
            parse_group_text("sudo:x:bad:alice")

    def test_rejects_duplicate_group_names(self):
        line = "sudo:x:27:alice\n"
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_group_text(line + line)


class ParseSudoersTests(unittest.TestCase):
    def test_detects_nopasswd_rule(self):
        result = parse_sudoers_text("alice ALL=(ALL) NOPASSWD: ALL\n")
        self.assertTrue(result[0])

    def test_does_not_match_comment(self):
        result = parse_sudoers_text("# alice ALL=(ALL) NOPASSWD: ALL\n")
        self.assertFalse(result[0])

    def test_detects_include_and_includedir(self):
        result = parse_sudoers_text(
            "#include /etc/sudoers.local\n"
            "#includedir /etc/sudoers.d\n"
        )
        self.assertEqual(
            result[1],
            ("include /etc/sudoers.local", "includedir /etc/sudoers.d"),
        )

    def test_detects_nopasswd_on_continued_line(self):
        result = parse_sudoers_text(
            "alice ALL=(ALL) \\\n    NOPASSWD: /usr/bin/id\n"
        )
        self.assertTrue(result[0])

    def test_does_not_report_rule_contents(self):
        contains, includes = parse_sudoers_text(
            "alice ALL=(ALL) NOPASSWD: /usr/bin/id\n"
        )
        self.assertIs(contains, True)
        self.assertEqual(includes, ())


class InspectSudoersTests(unittest.TestCase):
    def test_inspects_file_metadata_and_indicators(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sudoers"
            path.write_text("Defaults env_reset\nalice ALL=(ALL) NOPASSWD: ALL\n")
            result = inspect_sudoers_file(path)

        self.assertTrue(result.exists)
        self.assertTrue(result.readable)
        self.assertEqual(result.mode, "0644")
        self.assertTrue(result.contains_nopasswd)
        self.assertIsNone(result.read_error)

    def test_reports_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_sudoers_file(Path(directory) / "missing")

        self.assertFalse(result.exists)
        self.assertFalse(result.readable)
        self.assertIsNone(result.contains_nopasswd)


class CollectUserAuditTests(unittest.TestCase):
    def test_collects_users_groups_uid_zero_and_sudo_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "passwd").write_text(PASSWD)
            (root / "group").write_text(GROUP)
            (root / "sudoers").write_text("#includedir /etc/sudoers.d\n")
            sudoers_dir = root / "sudoers.d"
            sudoers_dir.mkdir()
            (sudoers_dir / "admin").write_text("alice ALL=(ALL) ALL\n")

            result = collect_user_audit(
                root / "passwd",
                root / "group",
                root / "sudoers",
                sudoers_dir,
            )

        self.assertEqual([user.username for user in result.uid_zero_users], ["root"])
        self.assertEqual(
            [user.username for user in result.sudo_group_members], ["alice"]
        )
        alice = next(user for user in result.users if user.username == "alice")
        self.assertEqual(alice.primary_group, "users")
        self.assertEqual(alice.supplementary_groups, ("sudo", "users"))
        self.assertEqual(result.unknown_sudo_members, ("missing-user",))
        self.assertEqual(len(result.sudoers_files), 2)
        self.assertEqual(
            result.sudoers_files[0].include_directives,
            ("includedir /etc/sudoers.d",),
        )

    def test_handles_missing_sudo_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "passwd").write_text(PASSWD)
            (root / "group").write_text("users:x:1000:alice\n")
            (root / "sudoers").write_text("")
            result = collect_user_audit(
                root / "passwd", root / "group", root / "sudoers", root / "absent"
            )

        self.assertEqual(result.sudo_group_members, ())
        self.assertEqual(result.unknown_sudo_members, ())

    def test_primary_sudo_group_membership_is_included(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "passwd").write_text(
                "alice:x:1000:27::/home/alice:/bin/bash\n"
            )
            (root / "group").write_text("sudo:x:27:\n")
            (root / "sudoers").write_text("")
            result = collect_user_audit(
                root / "passwd", root / "group", root / "sudoers", root / "absent"
            )

        self.assertEqual([user.username for user in result.sudo_group_members], ["alice"])


if __name__ == "__main__":
    unittest.main()
