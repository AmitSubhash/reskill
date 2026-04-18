"""Install / uninstall reskill's Stop hook into ~/.claude/settings.json.

Idempotent: detects reskill's hook by the literal marker string
"reskill log-session" and won't double-install. Uninstall removes only
the reskill entry, leaving other Stop hooks untouched.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .palette import ASH, BOLD, DARK_ASH, DIM, SAGE, paint


SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
HOOK_MARKER = "reskill log-session"


def _find_reskill_binary() -> str:
    """Locate the reskill executable -- prefer the one on PATH, fall back
    to the one from argv0 (when running from source via python -m)."""
    found = shutil.which("reskill")
    if found:
        return found
    return "reskill"


def _build_hook_entry() -> dict:
    """Return the JSON object that goes in Stop[].hooks[].

    Claude Code pipes a JSON object with `transcript_path` via stdin,
    so we let `reskill log-session` read it from stdin rather than env.
    """
    return {
        "type": "command",
        "command": f"{_find_reskill_binary()} log-session 2>>/tmp/reskill-hook.log",
        "timeout": 10,
        "async": True,
    }


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except json.JSONDecodeError:
        print(
            paint("  reskill: ~/.claude/settings.json is not valid JSON", ASH),
            file=sys.stderr,
        )
        sys.exit(1)


def _save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup = SETTINGS_PATH.with_suffix(".json.reskill-bak")
    if SETTINGS_PATH.exists():
        shutil.copy2(SETTINGS_PATH, backup)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")


def _has_reskill_hook(stop_array: list) -> bool:
    for entry in stop_array:
        for hook in entry.get("hooks", []):
            if HOOK_MARKER in hook.get("command", ""):
                return True
    return False


def install() -> int:
    """Install the Stop hook. Idempotent."""
    settings = _load_settings()
    stop = settings.setdefault("Stop", [])

    if _has_reskill_hook(stop):
        print(paint("  reskill hook already installed", ASH, DIM))
        return 0

    stop.append(
        {
            "matcher": "*",
            "hooks": [_build_hook_entry()],
        }
    )
    _save_settings(settings)
    print(paint("  reskill Stop hook installed", SAGE, BOLD))
    print(
        paint(
            "  every Claude Code session end will now enqueue question candidates",
            ASH,
            DIM,
        )
    )
    print(paint(f"  backup saved to {SETTINGS_PATH}.reskill-bak", DARK_ASH, DIM))
    return 0


def uninstall() -> int:
    """Remove reskill's Stop hook. Safe if not installed."""
    settings = _load_settings()
    stop = settings.get("Stop", [])
    before = len(stop)

    cleaned: list[dict] = []
    for entry in stop:
        hooks = [h for h in entry.get("hooks", []) if HOOK_MARKER not in h.get("command", "")]
        if hooks:
            entry["hooks"] = hooks
            cleaned.append(entry)

    if len(cleaned) == before and not any(
        HOOK_MARKER in h.get("command", "")
        for entry in stop
        for h in entry.get("hooks", [])
    ):
        print(paint("  reskill hook was not installed; nothing to do", ASH, DIM))
        return 0

    settings["Stop"] = cleaned
    _save_settings(settings)
    print(paint("  reskill Stop hook removed", SAGE, BOLD))
    return 0


def status() -> int:
    """Report whether the hook is installed."""
    settings = _load_settings()
    stop = settings.get("Stop", [])
    if _has_reskill_hook(stop):
        print(paint("  installed", SAGE, BOLD), paint(f"in {SETTINGS_PATH}", ASH, DIM))
    else:
        print(paint("  not installed", ASH))
        print(paint("  run `reskill install` to enable session ingestion", DARK_ASH, DIM))
    return 0
