"""Detect whether Claude Code is currently active (thinking/streaming).

Two signals, in order of preference:

  1. `~/.reskill/state/thinking` flag file, toggled by our hooks.
     Preferred because it's precise: set on UserPromptSubmit/PreToolUse,
     cleared on PostToolUse/Stop. Requires `reskill install` to have run.

  2. Transcript-file mtime poll. Claude Code appends every assistant
     token, tool call, and tool result to a JSONL at
     `~/.claude/projects/<slug>/<uuid>.jsonl`. If any of those files
     was modified in the last few seconds, Claude is doing something
     right now. Works without any hook install -- just observation.

The quiz pane prefers signal 1 when available, falls back to signal 2.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


STATE_DIR = Path.home() / ".reskill" / "state"
THINKING_FILE = STATE_DIR / "thinking"
TRANSCRIPTS_ROOT = Path.home() / ".claude" / "projects"

# Claude Code appends on every token. If a transcript mtime is this recent,
# we treat Claude as active. Wide enough to cover brief pauses between
# tool calls; tight enough to go idle within a few seconds of Stop.
TRANSCRIPT_FRESH_SECONDS = 3.0


def _flag_is_set() -> bool:
    if not THINKING_FILE.exists():
        return False
    try:
        age = time.time() - THINKING_FILE.stat().st_mtime
        return age < 15 * 60  # stale protection
    except OSError:
        return False


def _latest_transcript_mtime(cwd: str | None = None) -> float:
    """Most recent mtime across plausible transcript files.

    If `cwd` is given, we prefer files in the slug that matches that
    directory; otherwise we scan the whole projects tree but cap the
    walk for speed.
    """
    if not TRANSCRIPTS_ROOT.exists():
        return 0.0

    best = 0.0
    cutoff = time.time() - 60.0  # no point looking at stale files
    try:
        if cwd:
            slug = cwd.replace("/", "-")
            project_dir = TRANSCRIPTS_ROOT / slug
            if project_dir.is_dir():
                for path in project_dir.glob("*.jsonl"):
                    try:
                        m = path.stat().st_mtime
                        if m > best and m > cutoff:
                            best = m
                    except OSError:
                        continue
                if best:
                    return best

        # Global fallback: walk all project dirs.
        for project_dir in TRANSCRIPTS_ROOT.iterdir():
            if not project_dir.is_dir():
                continue
            try:
                for path in project_dir.glob("*.jsonl"):
                    try:
                        m = path.stat().st_mtime
                        if m > best:
                            best = m
                    except OSError:
                        continue
            except OSError:
                continue
    except OSError:
        return 0.0
    return best


def is_claude_active(cwd: str | None = None) -> bool:
    """True if Claude is currently thinking or streaming a response."""
    if _flag_is_set():
        return True
    mtime = _latest_transcript_mtime(cwd)
    if mtime == 0.0:
        return False
    return (time.time() - mtime) < TRANSCRIPT_FRESH_SECONDS


def have_reskill_hooks() -> bool:
    """Report whether `reskill install` has been run (best-effort check)."""
    import json

    settings = Path.home() / ".claude" / "settings.json"
    if not settings.exists():
        return False
    try:
        data = json.loads(settings.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    for event in ("Stop", "PreToolUse", "PostToolUse", "UserPromptSubmit"):
        for entry in data.get(event, []):
            for hook in entry.get("hooks", []):
                if "reskill" in hook.get("command", ""):
                    return True
    return False
