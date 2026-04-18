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
THINKING_MARKER = "reskill-thinking-flag"
STATE_DIR = Path.home() / ".reskill" / "state"
THINKING_FILE = STATE_DIR / "thinking"


def _find_reskill_binary() -> str:
    """Locate the reskill executable -- prefer the one on PATH, fall back
    to the one from argv0 (when running from source via python -m)."""
    found = shutil.which("reskill")
    if found:
        return found
    return "reskill"


def _build_log_hook() -> dict:
    """Stop-event hook: ingest the transcript into the concept cache."""
    return {
        "type": "command",
        "command": f"{_find_reskill_binary()} log-session 2>>/tmp/reskill-hook.log",
        "timeout": 10,
        "async": True,
    }


def _build_thinking_on_hook() -> dict:
    """PreToolUse hook: signal Claude is mid-thought. Marker lets us find
    and remove this entry on uninstall."""
    return {
        "type": "command",
        "command": (
            f"mkdir -p {STATE_DIR} && touch {THINKING_FILE} "
            f"# {THINKING_MARKER}"
        ),
        "timeout": 2,
        "async": True,
    }


def _build_thinking_off_hook() -> dict:
    """Stop hook + PostToolUse: clear the thinking signal."""
    return {
        "type": "command",
        "command": f"rm -f {THINKING_FILE} # {THINKING_MARKER}",
        "timeout": 2,
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


def _is_reskill_hook(hook: dict) -> bool:
    cmd = hook.get("command", "")
    return HOOK_MARKER in cmd or THINKING_MARKER in cmd


def _has_any_reskill_hook(settings: dict) -> bool:
    for event in ("Stop", "PreToolUse", "PostToolUse"):
        for entry in settings.get(event, []):
            if any(_is_reskill_hook(h) for h in entry.get("hooks", [])):
                return True
    return False


def _append_hook(settings: dict, event: str, hook: dict) -> None:
    arr = settings.setdefault(event, [])
    arr.append({"matcher": "*", "hooks": [hook]})


def install(with_statusline: bool = True) -> int:
    """Install all reskill hooks + (optionally) the statusLine. Idempotent.

    Hooks:
      - UserPromptSubmit: sets the thinking flag (user just submitted)
      - PreToolUse:       keeps it set as Claude starts tools
      - PostToolUse:      clears it when tool completes
      - Stop:             clears it + logs the transcript into cache
    """
    settings = _load_settings()
    already = _has_any_reskill_hook(settings)
    if already:
        print(paint("  reskill hooks already installed", ASH, DIM))
    else:
        _append_hook(settings, "Stop", _build_log_hook())
        _append_hook(settings, "Stop", _build_thinking_off_hook())
        _append_hook(settings, "UserPromptSubmit", _build_thinking_on_hook())
        _append_hook(settings, "PreToolUse", _build_thinking_on_hook())
        _append_hook(settings, "PostToolUse", _build_thinking_off_hook())

    if with_statusline and "statusLine" not in settings:
        settings["statusLine"] = {
            "type": "command",
            "command": f"{_find_reskill_binary()} statusline",
            "refreshInterval": 2,
            "padding": 2,
        }
        print(paint("  statusLine configured", SAGE, BOLD))

    if already and (not with_statusline or "statusLine" in settings and settings["statusLine"].get("command", "").endswith("reskill statusline")):
        return 0

    _save_settings(settings)
    if not already:
        print(paint("  reskill hooks installed", SAGE, BOLD))
        print(
            paint(
                "  UserPromptSubmit / PreToolUse / PostToolUse / Stop -- "
                "the quiz pane + statusline know when Claude is mid-thought",
                ASH,
                DIM,
            )
        )
    print(paint(f"  backup saved to {SETTINGS_PATH}.reskill-bak", DARK_ASH, DIM))
    return 0


def uninstall() -> int:
    """Remove every reskill hook entry and the statusLine. Safe if absent."""
    settings = _load_settings()
    removed = False
    for event in ("Stop", "PreToolUse", "PostToolUse", "UserPromptSubmit"):
        arr = settings.get(event, [])
        cleaned: list[dict] = []
        any_removed_here = False
        for entry in arr:
            orig = entry.get("hooks", [])
            kept = [h for h in orig if not _is_reskill_hook(h)]
            if len(kept) != len(orig):
                any_removed_here = True
            if kept:
                entry["hooks"] = kept
                cleaned.append(entry)
        if any_removed_here:
            removed = True
            settings[event] = cleaned

    sl = settings.get("statusLine", {})
    if isinstance(sl, dict) and "reskill statusline" in sl.get("command", ""):
        del settings["statusLine"]
        removed = True

    if not removed:
        print(paint("  reskill hooks were not installed; nothing to do", ASH, DIM))
        return 0

    _save_settings(settings)
    print(paint("  reskill hooks + statusline removed", SAGE, BOLD))
    return 0


def status() -> int:
    """Report whether the hooks are installed."""
    settings = _load_settings()
    if _has_any_reskill_hook(settings):
        print(paint("  installed", SAGE, BOLD), paint(f"in {SETTINGS_PATH}", ASH, DIM))
    else:
        print(paint("  not installed", ASH))
        print(paint("  run `reskill install` to enable session ingestion", DARK_ASH, DIM))
    return 0
