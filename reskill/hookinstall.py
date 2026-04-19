"""Install / uninstall reskill hooks into ~/.claude/settings.json.

Claude Code currently expects hook events under the top-level ``hooks``
object. reskill keeps its entries isolated there and removes only the
reskill-owned handlers on uninstall, leaving unrelated hooks untouched.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .palette import ASH, BOLD, DARK_ASH, DIM, ROSE, SAGE, TEAL, paint

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
HOOK_MARKER = "reskill log-session"
THINKING_MARKER = "reskill-thinking-flag"
STATE_DIR = Path.home() / ".reskill" / "state"
THINKING_FILE = STATE_DIR / "thinking"
THINKING_ON_COMMAND = f"mkdir -p {STATE_DIR} && touch {THINKING_FILE}"
THINKING_OFF_COMMAND = f"rm -f {THINKING_FILE}"
HOOK_EVENTS = ("Stop", "PreToolUse", "PostToolUse", "UserPromptSubmit")


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
    """Signal Claude is mid-thought."""
    return {
        "type": "command",
        "command": THINKING_ON_COMMAND,
        "timeout": 2,
        "async": True,
    }


def _build_thinking_off_hook() -> dict:
    """Stop hook + PostToolUse: clear the thinking signal."""
    return {
        "type": "command",
        "command": THINKING_OFF_COMMAND,
        "timeout": 2,
        "async": True,
    }


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except json.JSONDecodeError as exc:
        backup = SETTINGS_PATH.with_suffix(".json.reskill-bak")
        print(
            paint(
                f"  reskill: can't parse {SETTINGS_PATH}", ROSE, BOLD,
            ),
            file=sys.stderr,
        )
        print(
            paint(f"    {exc.__class__.__name__}: {exc}", ASH),
            file=sys.stderr,
        )
        if backup.exists():
            print(
                paint(
                    f"  a reskill backup exists at {backup}",
                    ASH, DIM,
                ),
                file=sys.stderr,
            )
            print(
                paint(
                    "  to restore it:  ", ASH, DIM,
                )
                + paint(
                    f"cp {backup} {SETTINGS_PATH}", TEAL, BOLD,
                ),
                file=sys.stderr,
            )
        else:
            print(
                paint(
                    "  fix the JSON manually, then re-run `reskill install`.",
                    ASH, DIM,
                ),
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
    return (
        HOOK_MARKER in cmd
        or THINKING_MARKER in cmd
        or cmd.startswith(THINKING_ON_COMMAND)
        or cmd.startswith(THINKING_OFF_COMMAND)
    )


def _has_any_reskill_hook(settings: dict) -> bool:
    for event in HOOK_EVENTS:
        for entry in _iter_event_entries(settings, event):
            if any(_is_reskill_hook(hook) for hook in entry.get("hooks", [])):
                return True
    return False


def _hooks_root(settings: dict) -> dict:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        print(
            paint('  reskill: ~/.claude/settings.json has a non-object "hooks" field', ASH),
            file=sys.stderr,
        )
        sys.exit(1)
    return hooks


def _iter_event_entries(settings: dict, event: str) -> list[dict]:
    entries: list[dict] = []

    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        nested = hooks.get(event, [])
        if isinstance(nested, list):
            entries.extend(nested)

    legacy = settings.get(event, [])
    if isinstance(legacy, list):
        entries.extend(legacy)

    return entries


def _append_hook(settings: dict, event: str, hook: dict, matcher: str | None = None) -> None:
    arr = _hooks_root(settings).setdefault(event, [])
    entry = {"hooks": [hook]}
    if matcher is not None:
        entry["matcher"] = matcher
    arr.append(entry)


def _remove_reskill_hooks(settings: dict) -> bool:
    removed = False

    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event in HOOK_EVENTS:
            arr = hooks.get(event, [])
            if not isinstance(arr, list):
                continue

            cleaned: list[dict] = []
            any_removed_here = False
            for entry in arr:
                orig = entry.get("hooks", [])
                kept = [hook for hook in orig if not _is_reskill_hook(hook)]
                if len(kept) != len(orig):
                    any_removed_here = True
                if kept:
                    cleaned_entry = dict(entry)
                    cleaned_entry["hooks"] = kept
                    cleaned.append(cleaned_entry)

            if any_removed_here:
                removed = True
                if cleaned:
                    hooks[event] = cleaned
                else:
                    hooks.pop(event, None)

        if not hooks:
            settings.pop("hooks", None)

    for event in HOOK_EVENTS:
        arr = settings.get(event)
        if not isinstance(arr, list):
            continue

        cleaned: list[dict] = []
        any_removed_here = False
        for entry in arr:
            orig = entry.get("hooks", [])
            kept = [hook for hook in orig if not _is_reskill_hook(hook)]
            if len(kept) != len(orig):
                any_removed_here = True
            if kept:
                cleaned_entry = dict(entry)
                cleaned_entry["hooks"] = kept
                cleaned.append(cleaned_entry)

        if any_removed_here:
            removed = True
            if cleaned:
                settings[event] = cleaned
            else:
                settings.pop(event, None)

    return removed


WRAPPER_SCRIPT_PATH = Path.home() / ".claude" / "reskill-statusline-wrapper.sh"
WRAPPER_MARKER = "reskill-statusline-wrapper"


def _write_compose_wrapper(existing_command: str) -> None:
    """Create a wrapper script that runs BOTH the user's existing
    statusLine command and `reskill statusline`, concatenating with \\n.

    Claude Code calls statusLine with JSON on stdin. The wrapper reads
    stdin once, then pipes the same payload to both commands so neither
    starves for input.
    """
    reskill_bin = _find_reskill_binary()
    content = f"""#!/usr/bin/env bash
# {WRAPPER_MARKER}
# Composes the user's existing statusLine with reSkill's one-liner.
# Both get the same JSON payload on stdin.
set -e
input=$(cat)
printf '%s' "$input" | {existing_command}
printf '\\n'
printf '%s' "$input" | {reskill_bin} statusline
"""
    WRAPPER_SCRIPT_PATH.write_text(content)
    WRAPPER_SCRIPT_PATH.chmod(0o755)


def install(with_statusline: bool = True, compose_statusline: bool = True) -> int:
    """Install all reskill hooks + (optionally) the statusLine. Idempotent.

    Hooks:
      - UserPromptSubmit: sets the thinking flag (user just submitted)
      - PreToolUse:       keeps it set as Claude starts tools
      - PostToolUse:      clears it when tool completes
      - Stop:             clears it + logs the transcript into cache

    statusLine:
      - If no statusLine is configured: point it at `reskill statusline`.
      - If one IS configured and compose_statusline=True: write a
        wrapper script that runs both commands and concatenates output,
        preserving the user's existing line.
      - Otherwise: leave the existing statusLine alone.
    """
    settings = _load_settings()
    already = _has_any_reskill_hook(settings)
    if already:
        _remove_reskill_hooks(settings)
        print(paint("  reskill hooks refreshed", ASH, DIM))

    _append_hook(settings, "Stop", _build_log_hook())
    _append_hook(settings, "Stop", _build_thinking_off_hook())
    _append_hook(settings, "UserPromptSubmit", _build_thinking_on_hook())
    _append_hook(settings, "PreToolUse", _build_thinking_on_hook(), matcher="*")
    _append_hook(settings, "PostToolUse", _build_thinking_off_hook(), matcher="*")

    existing_sl = settings.get("statusLine", {}) if with_statusline else {}
    existing_cmd = existing_sl.get("command", "") if isinstance(existing_sl, dict) else ""
    reskill_cmd = f"{_find_reskill_binary()} statusline"

    if with_statusline:
        if not existing_sl:
            settings["statusLine"] = {
                "type": "command",
                "command": reskill_cmd,
                "refreshInterval": 2,
                "padding": 2,
                # Explicit ownership marker -- uninstall checks this
                # before deleting so a user's custom line that happens
                # to mention "reskill statusline" (e.g. in a comment)
                # is never wiped.
                "_reskill_owned": True,
            }
            print(paint("  statusLine configured (reskill only)", SAGE, BOLD))
        elif (
            existing_sl.get("_reskill_owned") is True
            or WRAPPER_MARKER in existing_cmd
            or existing_cmd.strip() == reskill_cmd
        ):
            # Already wrapped or already us.
            pass
        elif compose_statusline:
            _write_compose_wrapper(existing_cmd)
            settings["statusLine"] = {
                "type": "command",
                "command": f"bash {WRAPPER_SCRIPT_PATH}",
                "refreshInterval": 2,
                "padding": 2,
                "_reskill_owned": True,
            }
            print(
                paint("  statusLine composed", SAGE, BOLD),
                paint("(your existing line + reskill's)", ASH, DIM),
            )

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
    if not already:
        print()
        print(paint("  try it now:  ", ASH, DIM) + paint("reskill demo", TEAL, BOLD))
        print(
            paint("  then start a real session with:  ", ASH, DIM)
            + paint("reskill claude", TEAL, BOLD)
        )
        print()
        print(
            paint("  shipped on PyPI as ", ASH, DIM)
            + paint("reskill-claude", TEAL)
            + paint(" (the CLI stays `reskill`)", ASH, DIM)
        )
    return 0


def uninstall() -> int:
    """Remove every reskill hook entry and the statusLine. Safe if absent."""
    settings = _load_settings()
    removed = _remove_reskill_hooks(settings)

    sl = settings.get("statusLine", {})
    if isinstance(sl, dict):
        cmd = sl.get("command", "")
        # Only delete statusLine entries we know we own. The
        # `_reskill_owned` marker is our explicit consent flag; the
        # exact-match check is for older installs (pre-marker) that
        # had nothing else but our command.
        reskill_cmd = f"{_find_reskill_binary()} statusline"
        owned = sl.get("_reskill_owned") is True
        legacy_owned = cmd.strip() == reskill_cmd
        if owned or legacy_owned:
            del settings["statusLine"]
            removed = True
        elif WRAPPER_MARKER in cmd or str(WRAPPER_SCRIPT_PATH) in cmd:
            # Try to restore the composed-underneath command.
            if WRAPPER_SCRIPT_PATH.exists():
                try:
                    for line in WRAPPER_SCRIPT_PATH.read_text().splitlines():
                        if line.startswith('printf \'%s\' "$input" | ') and "reskill" not in line:
                            original = line.split(" | ", 1)[1]
                            settings["statusLine"] = {
                                "type": "command",
                                "command": original,
                            }
                            break
                except OSError:
                    pass
                try:
                    WRAPPER_SCRIPT_PATH.unlink()
                except OSError:
                    pass
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
