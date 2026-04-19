"""`reskill log-session <transcript>` -- ingest a Claude Code JSONL transcript.

Runs from the Stop hook. Reads the transcript, extracts assistant text +
code-touching tool calls, detects concepts with the existing matcher,
and appends candidate questions into the project cache. Non-blocking:
prints at most a single friendly line, never crashes the hook.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from .question import detect_concepts

CACHE_ROOT = Path.home() / ".reskill" / "project_cache"


def _project_hash(cwd: str | None) -> str:
    """Stable hash of the project directory for cache partitioning."""
    base = (cwd or os.getcwd()).rstrip("/")
    return hashlib.sha256(base.encode()).hexdigest()[:12]


def _read_transcript(path: Path) -> list[dict]:
    """Read a Claude Code session JSONL transcript.

    Parameters
    ----------
    path : Path
        Absolute path to the JSONL file.

    Returns
    -------
    list[dict]
        Parsed events. Empty list if unreadable.
    """
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def _extract_text(events: list[dict]) -> str:
    """Collect everything text-ish: assistant messages + tool input code."""
    chunks: list[str] = []
    for evt in events:
        if not isinstance(evt, dict):
            continue
        msg = evt.get("message") or evt
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    t = block.get("text", "")
                    if isinstance(t, str):
                        chunks.append(t)
                elif btype == "tool_use":
                    tool_input = block.get("input") or {}
                    for key in ("command", "content", "new_string", "old_string", "code"):
                        val = tool_input.get(key)
                        if isinstance(val, str):
                            chunks.append(val)
                elif btype == "tool_result":
                    result = block.get("content")
                    if isinstance(result, str):
                        chunks.append(result[:2000])
                    elif isinstance(result, list):
                        for item in result:
                            if isinstance(item, dict) and isinstance(item.get("text"), str):
                                chunks.append(item["text"][:2000])
    return "\n".join(chunks)


def _load_cache(cache_dir: Path) -> dict:
    """Load the concept tally. Creates an empty dict on first run."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "concepts.json"
    if not path.exists():
        return {"concepts": {}, "sessions": 0, "last_session": 0}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"concepts": {}, "sessions": 0, "last_session": 0}


def _save_cache(cache_dir: Path, data: dict) -> None:
    path = cache_dir / "concepts.json"
    try:
        path.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def log_session(transcript_path: str, cwd: str | None = None) -> int:
    """Ingest a transcript; update the per-project concept tally.

    Parameters
    ----------
    transcript_path : str
        Path to the Claude Code session JSONL file.
    cwd : str or None
        Project directory the session ran in.

    Returns
    -------
    int
        Exit code. 0 = success (or silently skipped). Never raises.
    """
    try:
        if not transcript_path:
            return 0
        path = Path(transcript_path).expanduser()
        events = _read_transcript(path)
        if not events:
            return 0
        text = _extract_text(events)
        if not text.strip():
            return 0

        concepts = detect_concepts(text)
        project_id = _project_hash(cwd)
        cache_dir = CACHE_ROOT / project_id
        cache = _load_cache(cache_dir)

        tally: dict[str, int] = cache.setdefault("concepts", {})
        for concept in concepts:
            tally[concept] = tally.get(concept, 0) + 1
        cache["sessions"] = cache.get("sessions", 0) + 1
        cache["last_session"] = int(time.time())
        cache["cwd"] = cwd or os.getcwd()

        _save_cache(cache_dir, cache)

        unique = sorted(set(concepts))
        if unique:
            head = ", ".join(unique[:4])
            more = f" (+{len(unique) - 4})" if len(unique) > 4 else ""
            print(f"reskill: queued {head}{more}", file=sys.stderr)
        return 0
    except Exception:
        return 0
