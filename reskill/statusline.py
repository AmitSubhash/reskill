"""`reskill statusline` -- Claude Code statusLine command.

Claude Code reserves the bottom row(s) of its own render viewport for
whatever this script writes to stdout. That reservation happens INSIDE
Ink, which is the only place it can possibly work -- external scroll
regions can't reserve rows because Ink's viewport size is always the
full terminal height.

Install it in ~/.claude/settings.json:

    "statusLine": {
        "type": "command",
        "command": "reskill statusline",
        "refreshInterval": 2,
        "padding": 2
    }

Contract (from Claude Code docs):
  - stdin:  JSON object with session_id, transcript_path, model, cwd
  - stdout: rendered verbatim; each \\n = one row
  - ANSI:   colors and OSC-8 links supported
  - rerun:  after each assistant message, on mode change, every N seconds
            if refreshInterval is set

The statusline is NOT interactive. For answering quizzes, users run
`reskill claude` (tmux split) or `reskill session` after a coding run.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import state as state_mod
from .palette import ASH, BOLD, DARK_ASH, DIM, GOLD, SAGE, STONE, TEAL, paint


STATE_DIR = Path.home() / ".reskill" / "state"
THINKING_FILE = STATE_DIR / "thinking"


def _read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _is_thinking() -> bool:
    if not THINKING_FILE.exists():
        return False
    try:
        # Stale protection: flag older than 15 minutes is probably orphaned.
        age = time.time() - THINKING_FILE.stat().st_mtime
        return age < 15 * 60
    except OSError:
        return False


def _render_idle(state: state_mod.State) -> str:
    parts = [
        paint("reskill", TEAL, BOLD),
        paint(f"\u00b7 day {state.streak}", GOLD, DIM),
        paint(f"\u00b7 {state.correct_today}/{state.daily_goal} today", SAGE if state.correct_today >= state.daily_goal else STONE),
        paint(f"\u00b7 {state.xp_total} xp", ASH, DIM),
    ]
    return " ".join(parts)


def _render_thinking(state: state_mod.State) -> str:
    line1 = paint("reskill", TEAL, BOLD) + paint("  quiz pane is live", ASH, DIM)
    line2 = (
        paint(f"\U0001f525 {state.streak}", GOLD, BOLD)
        + paint("  \u00b7  ", DARK_ASH, DIM)
        + paint(f"{state.correct_today}/{state.daily_goal} today", SAGE)
        + paint("  \u00b7  ", DARK_ASH, DIM)
        + paint("quiz this turn", TEAL)
    )
    return line1 + "\n" + line2


def run() -> int:
    """Entry point for `reskill statusline`.

    Reads hook JSON from stdin, prints one or two colored lines, exits fast.
    Claude Code debounces our invocation; we must return in < 300ms.
    """
    _read_hook_input()  # We don't need the fields yet, but draining is polite.
    state = state_mod.load()
    if _is_thinking():
        sys.stdout.write(_render_thinking(state))
    else:
        sys.stdout.write(_render_idle(state))
    return 0
