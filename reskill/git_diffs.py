"""Pull commits + diffs from the project's git history.

Used by `reskill session --from-commits 7d` to turn recent work into a
studyable deck. We keep parsing lightweight: shell out to git, grab the
patch text, and extract signal without touching a real diff parser.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    subject: str
    author_time: str
    diff: str
    added_lines: tuple[str, ...] = field(default_factory=tuple)
    files: tuple[str, ...] = field(default_factory=tuple)


_SINCE_RE = re.compile(r"^(\d+)([dhwm])$", re.I)


def parse_since(spec: str) -> str:
    """Turn '7d' / '24h' / '2w' into a git --since value.

    Parameters
    ----------
    spec : str
        Compact duration like '7d', '24h', '2w', '1m'.

    Returns
    -------
    str
        Value suitable for `git log --since="..."`.
    """
    match = _SINCE_RE.match(spec.strip())
    if not match:
        return spec
    n, unit = match.groups()
    unit_map = {
        "d": "days",
        "h": "hours",
        "w": "weeks",
        "m": "months",
    }
    return f"{n} {unit_map[unit.lower()]} ago"


def _run_git(args: list[str], cwd: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def project_root(cwd: str | None = None) -> str | None:
    out = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd).strip()
    return out or None


def fetch_commits(since: str, cwd: str | None = None, limit: int = 40) -> list[CommitInfo]:
    """Fetch commits since the given window, each with its patch text.

    Parameters
    ----------
    since : str
        Compact duration ('7d') or git-native value.
    cwd : str or None
        Directory to run git from. Defaults to current.
    limit : int
        Max commits to return (newest first).

    Returns
    -------
    list[CommitInfo]
    """
    since_val = parse_since(since)
    sep = "\x1e\x1e\x1e"
    field_sep = "\x1f"
    fmt = f"%H{field_sep}%s{field_sep}%ai"
    log_out = _run_git(
        [
            "log",
            f"--since={since_val}",
            f"-n{limit}",
            f"--pretty=format:{sep}{fmt}",
            "--patch",
            "--no-color",
            "--unified=3",
        ],
        cwd=cwd,
    )
    if not log_out:
        return []

    commits: list[CommitInfo] = []
    for block in log_out.split(sep):
        block = block.strip("\n")
        if not block:
            continue
        header, _, patch = block.partition("\n")
        parts = header.split(field_sep)
        if len(parts) < 3:
            continue
        sha, subject, author_time = parts[0], parts[1], parts[2]
        added = tuple(
            line[1:].strip()
            for line in patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        files = tuple(
            re.findall(r"^diff --git a/.* b/(.*)$", patch, flags=re.M)
        )
        commits.append(
            CommitInfo(
                sha=sha[:12],
                subject=subject,
                author_time=author_time,
                diff=patch,
                added_lines=added,
                files=files,
            )
        )
    return commits
