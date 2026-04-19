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
# tool calls AND long model-inference gaps between tool calls (which
# can be 15-30s on xhigh effort), tight enough to go idle soon after Stop.
TRANSCRIPT_FRESH_SECONDS = 15.0


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


def latest_transcript_path(cwd: str | None = None) -> Path | None:
    """Return the path to the most recently-written transcript.

    Used by the quiz picker to read the live conversation context --
    the last thing Claude wrote or read -- so questions match what
    the user is actually working on RIGHT NOW, not the cumulative
    cache from past sessions.
    """
    if not TRANSCRIPTS_ROOT.exists():
        return None
    best_path: Path | None = None
    best_mtime = 0.0
    try:
        if cwd:
            slug = cwd.replace("/", "-")
            project_dir = TRANSCRIPTS_ROOT / slug
            if project_dir.is_dir():
                for path in project_dir.glob("*.jsonl"):
                    try:
                        m = path.stat().st_mtime
                        if m > best_mtime:
                            best_mtime = m
                            best_path = path
                    except OSError:
                        continue
                if best_path is not None:
                    return best_path

        for project_dir in TRANSCRIPTS_ROOT.iterdir():
            if not project_dir.is_dir():
                continue
            try:
                for path in project_dir.glob("*.jsonl"):
                    try:
                        m = path.stat().st_mtime
                        if m > best_mtime:
                            best_mtime = m
                            best_path = path
                    except OSError:
                        continue
            except OSError:
                continue
    except OSError:
        return None
    return best_path


def recent_transcript_text(cwd: str | None = None, max_chars: int = 8000) -> str:
    """Read the tail of the most recent transcript as plain text.

    Strips the JSONL structure and pulls assistant text, tool inputs,
    and tool results -- whatever Claude is chewing on. This gives the
    question picker real signal about the live turn.
    """
    import json

    path = latest_transcript_path(cwd)
    if path is None:
        return ""
    try:
        raw = path.read_text(errors="replace")
    except OSError:
        return ""

    lines = raw.splitlines()[-80:]
    chunks: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = evt.get("message") if isinstance(evt, dict) else None
        msg = msg if isinstance(msg, dict) else evt
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                t = block.get("type")
                if t == "text":
                    v = block.get("text", "")
                    if isinstance(v, str):
                        chunks.append(v)
                elif t == "tool_use":
                    ti = block.get("input") or {}
                    for k in ("command", "content", "new_string", "code", "pattern"):
                        v = ti.get(k)
                        if isinstance(v, str):
                            chunks.append(v)
                elif t == "tool_result":
                    r = block.get("content")
                    if isinstance(r, str):
                        chunks.append(r[:1000])
                    elif isinstance(r, list):
                        for it in r:
                            if isinstance(it, dict) and isinstance(it.get("text"), str):
                                chunks.append(it["text"][:1000])

    joined = "\n".join(chunks)
    return joined[-max_chars:] if len(joined) > max_chars else joined


def have_reskill_hooks() -> bool:
    """Report whether `reskill install` has been run (best-effort check).

    Claude Code reads hooks from settings.hooks.* (nested). We also
    check the settings root for legacy installs.
    """
    import json

    settings = Path.home() / ".claude" / "settings.json"
    if not settings.exists():
        return False
    try:
        data = json.loads(settings.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    events = ("Stop", "PreToolUse", "PostToolUse", "UserPromptSubmit")
    locations = []
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        locations.append(hooks)
    locations.append(data)  # legacy root-level
    for loc in locations:
        for event in events:
            for entry in loc.get(event, []) if isinstance(loc.get(event), list) else []:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    if "reskill" in cmd or "reskill-thinking-flag" in cmd:
                        return True
    return False
