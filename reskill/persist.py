"""Atomic, crash-safe JSON persistence helpers.

Every write-to-disk call in reskill funnels through here so we survive:
  - ^C or laptop-sleep mid-write (no truncated state.json)
  - downgrades that inject unknown fields (bad data is renamed, not lost)
  - partial JSON from an earlier crash (ditto)

Two public helpers:

  atomic_write_json(path, payload)   -- write via tmp + os.replace
  load_json_or_quarantine(path)      -- read, rename-aside on parse fail
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    """Write JSON to `path` atomically.

    Uses a same-directory tmp file + os.replace so we never leave a
    half-written file around. Parent directories are created lazily.

    No fsync: the goal is crash-safety for "power off / lid close / ^C"
    at the filesystem API level, not durability across hard reboots.
    Adding fsync would slow `pacing.save()` which runs on every quiz.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(payload, indent=indent))
        os.replace(tmp, path)
    except Exception:
        # Best-effort cleanup; don't mask the original error.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def load_json_or_quarantine(path: Path, *, label: str = "state") -> dict | None:
    """Read JSON from `path`, returning parsed dict or None.

    If the file is unreadable or not valid JSON, rename it aside to
    `<path>.corrupt-<ts>` and print a one-line stderr notice so the
    user knows their data moved. Returns None in that case (callers
    should treat as "no data yet"), never raises.

    Returns None for "file absent" as well, so callers handle both
    uniformly.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"{label} root is not a JSON object")
        return data
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        ts = time.strftime("%Y%m%d-%H%M%S")
        quarantine = path.with_suffix(path.suffix + f".corrupt-{ts}")
        try:
            os.replace(path, quarantine)
            print(
                f"reskill: {label} at {path} was unreadable ({exc}).",
                file=sys.stderr,
            )
            print(
                f"reskill: moved aside to {quarantine}. "
                "Starting from a clean slate.",
                file=sys.stderr,
            )
        except OSError:
            # Can't even rename. Best we can do is leave the file and
            # return None so the caller starts fresh in memory.
            print(
                f"reskill: {label} at {path} unreadable and unmovable. "
                f"Delete it manually to clear. ({exc})",
                file=sys.stderr,
            )
        return None


def filter_to_fields(data: dict, fields: set[str]) -> dict:
    """Keep only keys that `fields` recognizes.

    Lets callers survive unknown-key injection (e.g. downgrades, hand
    edits) by discarding foreign keys rather than raising TypeError
    when constructing a dataclass.
    """
    return {k: v for k, v in data.items() if k in fields}
