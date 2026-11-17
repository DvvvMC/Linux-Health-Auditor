"""Read-only local user, group, and sudo configuration audit."""

from dataclasses import dataclass
from pathlib import Path
import re
import stat


@dataclass(frozen=True)
class UserInfo:
    """A user account parsed from /etc/passwd."""

    username: str
    uid: int
    primary_gid: int
    gecos: str
    home: str
    shell: str
    primary_group: str | None
    supplementary_groups: tuple[str, ...]

    @property
    def is_uid_zero(self) -> bool:
        """Whether this account has root's numeric user ID."""
        return self.uid == 0


@dataclass(frozen=True)
class GroupInfo:
    """A group parsed from /etc/group."""

    name: str
    gid: int
    members: tuple[str, ...]


@dataclass(frozen=True)
class SudoersFileInfo:
    """Non-sensitive metadata and simple indicators for one sudoers file."""

    path: str
    exists: bool
    readable: bool
    owner_uid: int | None
    mode: str | None
    contains_nopasswd: bool | None
    include_directives: tuple[str, ...]
    read_error: str | None


@dataclass(frozen=True)
class UserAuditResult:
    """Structured results from the user and sudo audit."""

    users: tuple[UserInfo, ...]
    groups: tuple[GroupInfo, ...]
    sudoers_files: tuple[SudoersFileInfo, ...]
    unknown_sudo_members: tuple[str, ...]

    @property
    def uid_zero_users(self) -> tuple[UserInfo, ...]:
        """Return every account whose UID is zero."""
        return tuple(user for user in self.users if user.is_uid_zero)

    @property
    def sudo_group_members(self) -> tuple[UserInfo, ...]:
        """Return accounts belonging to the group named sudo."""
        sudo_group = next((group for group in self.groups if group.name == "sudo"), None)
        if sudo_group is None:
            return ()

        names = set(sudo_group.members)
        return tuple(
            user for user in self.users
            if user.username in names or user.primary_gid == sudo_group.gid
        )


def parse_passwd_text(output: str) -> list[dict[str, str | int]]:
    """Parse /etc/passwd text without retaining password placeholders."""
    records: list[dict[str, str | int]] = []
    seen_names: set[str] = set()

    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue

        fields = line.split(":")
        if len(fields) != 7 or not fields[0]:
            raise ValueError(f"Invalid passwd entry on line {line_number}")

        username, _password_placeholder, uid_text, gid_text, gecos, home, shell = fields
        try:
            uid = int(uid_text)
            gid = int(gid_text)
        except ValueError as error:
            raise ValueError(f"Invalid UID or GID on passwd line {line_number}") from error

        if uid < 0 or gid < 0:
            raise ValueError(f"Negative UID or GID on passwd line {line_number}")
        if username in seen_names:
            raise ValueError(f"Duplicate username on passwd line {line_number}")

        seen_names.add(username)
        records.append({
            "username": username,
            "uid": uid,
            "primary_gid": gid,
            "gecos": gecos,
            "home": home,
            "shell": shell,
        })

    return records


def parse_group_text(output: str) -> list[dict[str, str | int | tuple[str, ...]]]:
    """Parse /etc/group entries into structured records."""
    records: list[dict[str, str | int | tuple[str, ...]]] = []
    seen_names: set[str] = set()

    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue

        fields = line.split(":")
        if len(fields) != 4 or not fields[0]:
            raise ValueError(f"Invalid group entry on line {line_number}")

        name, _password_placeholder, gid_text, members_text = fields
        try:
            gid = int(gid_text)
        except ValueError as error:
            raise ValueError(f"Invalid GID on group line {line_number}") from error

        if gid < 0:
            raise ValueError(f"Negative GID on group line {line_number}")
        if name in seen_names:
            raise ValueError(f"Duplicate group name on line {line_number}")

        members = tuple(member for member in members_text.split(",") if member)
        seen_names.add(name)
        records.append({"name": name, "gid": gid, "members": members})

    return records


def parse_sudoers_text(output: str) -> tuple[bool, tuple[str, ...]]:
    """Detect NOPASSWD and include directives without exposing sudoers rules."""
    contains_nopasswd = False
    include_directives: list[str] = []
    logical_lines: list[str] = []
    pending = ""

    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        include_match = re.match(r"^#(include|includedir)\s+(\S+)", stripped)
        if include_match:
            include_directives.append(
                f"{include_match.group(1)} {include_match.group(2)}"
            )
            continue

        # A backslash at the end continues a sudoers logical line.
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue

        logical_lines.append(pending + stripped)
        pending = ""

    if pending:
        logical_lines.append(pending)

    for line in logical_lines:
        rule = line.split("#", maxsplit=1)[0]
        if re.search(r"\bNOPASSWD\b", rule):
            contains_nopasswd = True
            break

    return contains_nopasswd, tuple(include_directives)


def inspect_sudoers_file(path: Path) -> SudoersFileInfo:
    """Inspect file metadata and safe indicators; never return rule contents."""
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return SudoersFileInfo(
            str(path), False, False, None, None, None, (), "File not found"
        )
    except OSError as error:
        return SudoersFileInfo(
            str(path), True, False, None, None, None, (), str(error)
        )

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return SudoersFileInfo(
            str(path),
            True,
            False,
            metadata.st_uid,
            f"{stat.S_IMODE(metadata.st_mode):04o}",
            None,
            (),
            str(error),
        )

    contains_nopasswd, includes = parse_sudoers_text(content)
    return SudoersFileInfo(
        path=str(path),
        exists=True,
        readable=True,
        owner_uid=metadata.st_uid,
        mode=f"{stat.S_IMODE(metadata.st_mode):04o}",
        contains_nopasswd=contains_nopasswd,
        include_directives=includes,
        read_error=None,
    )


def collect_user_audit(
    passwd_path: Path = Path("/etc/passwd"),
    group_path: Path = Path("/etc/group"),
    sudoers_path: Path = Path("/etc/sudoers"),
    sudoers_dir: Path = Path("/etc/sudoers.d"),
) -> UserAuditResult:
    """Collect local account/group data and inspect sudoers files read-only."""
    passwd_records = parse_passwd_text(passwd_path.read_text(encoding="utf-8"))
    group_records = parse_group_text(group_path.read_text(encoding="utf-8"))

    groups = tuple(
        GroupInfo(
            name=str(record["name"]),
            gid=int(record["gid"]),
            members=tuple(record["members"]),
        )
        for record in group_records
    )
    group_names_by_gid: dict[int, str] = {}
    for group in groups:
        group_names_by_gid.setdefault(group.gid, group.name)

    supplementary_by_user: dict[str, list[str]] = {}
    for group in groups:
        for username in group.members:
            supplementary_by_user.setdefault(username, []).append(group.name)

    users = tuple(
        UserInfo(
            username=str(record["username"]),
            uid=int(record["uid"]),
            primary_gid=int(record["primary_gid"]),
            gecos=str(record["gecos"]),
            home=str(record["home"]),
            shell=str(record["shell"]),
            primary_group=group_names_by_gid.get(int(record["primary_gid"])),
            supplementary_groups=tuple(
                sorted(supplementary_by_user.get(str(record["username"]), []))
            ),
        )
        for record in passwd_records
    )

    sudoers_paths = [sudoers_path]
    if sudoers_dir.is_dir():
        sudoers_paths.extend(
            sorted(path for path in sudoers_dir.iterdir() if path.is_file())
        )

    sudoers_files = tuple(inspect_sudoers_file(path) for path in sudoers_paths)

    sudo_group = next((group for group in groups if group.name == "sudo"), None)
    known_users = {user.username for user in users}
    unknown_sudo_members = (
        tuple(sorted(set(sudo_group.members) - known_users))
        if sudo_group is not None
        else ()
    )

    return UserAuditResult(
        users=users,
        groups=groups,
        sudoers_files=sudoers_files,
        unknown_sudo_members=unknown_sudo_members,
    )
