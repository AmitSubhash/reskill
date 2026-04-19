"""LLM-generated questions from real diffs.

Uses the `claude -p` non-interactive CLI (which the user already has
configured) to generate a reSkill-shaped Question from a specific
patch or code snippet. No API key required; it piggybacks on the
user's existing Claude Code subscription.

Caches results at `~/.reskill/generated/<sha>.json` so a given commit
is never re-queried.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .question import Option, Question


GEN_CACHE_DIR = Path.home() / ".reskill" / "generated"
_PROMPT_TEMPLATE = """\
You are a senior engineer helping a coworker level up through short quizzes.

A developer just shipped this code. Produce ONE reSkill-shaped quiz
question about a real pitfall, trade-off, or non-obvious consequence
of THIS specific code. Do not repeat textbook trivia.

STRICT RULES:
  - The question must reference something concrete in the code (a
    function name, a call, a flag, a type) so the quiz feels
    personal and earned.
  - All four options must be plausible -- every option should be a
    thing someone could genuinely believe. No obvious throwaways.
  - Exactly ONE option is correct.
  - The explanation teaches something non-obvious (a mental model,
    a runtime gotcha, a scaling concern) -- NOT just a restatement
    of the right answer.
  - 2-4 sentence explanation max.

FORMAT: respond with ONLY a single JSON object, no prose before or
after, no markdown fences. Schema:

{{
  "concept": "short-slug",
  "format": "one of: output, bug, tradeoff, scenario, why, gotcha, refactor, idiom",
  "prompt": "the question text, one or two sentences",
  "code": "the code snippet to show (optional, keep it short)",
  "options": [
    {{"text": "...", "correct": false}},
    {{"text": "...", "correct": true}},
    {{"text": "...", "correct": false}},
    {{"text": "...", "correct": false}}
  ],
  "explanation": "what they learn by getting this right"
}}

CODE TO QUIZ ABOUT:
```
{code}
```

CONTEXT (optional commit message / file path):
{context}
"""


@dataclass
class GenResult:
    question: Question | None
    error: str | None = None
    raw: str | None = None


def _cache_key(code: str, context: str) -> str:
    h = hashlib.sha256()
    h.update(code.encode("utf-8"))
    h.update(b"|")
    h.update(context.encode("utf-8"))
    return h.hexdigest()[:16]


def _cached(cache_file: Path) -> Question | None:
    if not cache_file.exists():
        return None
    try:
        raw = json.loads(cache_file.read_text())
        return _parse_question(raw)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _save(cache_file: Path, payload: dict) -> None:
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def _parse_question(raw: dict) -> Question:
    """Validate and construct a Question from a parsed JSON payload."""
    if not isinstance(raw, dict):
        raise ValueError("top-level JSON must be an object")
    concept = str(raw.get("concept") or "generated").strip() or "generated"
    fmt = str(raw.get("format") or "gotcha").strip() or "gotcha"
    prompt = str(raw.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is empty")
    code = raw.get("code")
    code_str = str(code).strip() if code else None
    explanation = str(raw.get("explanation") or "").strip()
    if not explanation:
        raise ValueError("explanation is empty")

    options_raw = raw.get("options") or []
    if not isinstance(options_raw, list) or len(options_raw) != 4:
        raise ValueError("need exactly 4 options")
    correct_count = 0
    options: list[Option] = []
    for i, opt in enumerate(options_raw):
        if not isinstance(opt, dict):
            raise ValueError(f"option {i} is not an object")
        text = str(opt.get("text") or "").strip()
        correct = bool(opt.get("correct", False))
        if not text:
            raise ValueError(f"option {i} has empty text")
        if correct:
            correct_count += 1
        options.append(Option(label=str(i + 1), text=text, correct=correct))
    if correct_count != 1:
        raise ValueError(f"need exactly 1 correct option, got {correct_count}")

    return Question(
        prompt=prompt,
        options=options,
        explanation=explanation,
        concept=concept,
        format=fmt,
        code=code_str,
        source="llm",
    )


def _extract_json(text: str) -> str | None:
    """Pull the first {...} block from a model response.

    Claude is usually obedient with "respond with only JSON" but we
    stay defensive: strip fenced blocks, pick the outermost balanced
    object.
    """
    # Drop ```json ... ``` fences if present
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    # Find first balanced {...}
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def generate_from_code(
    code: str,
    context: str = "",
    timeout_seconds: float = 45.0,
    model: str | None = None,
) -> GenResult:
    """Ask Claude for a question about this code. Cached.

    Parameters
    ----------
    code : str
        The code snippet to quiz about.
    context : str
        Optional commit message, file path, etc.
    timeout_seconds : float
        Seconds to wait for the Claude CLI to respond.
    model : str or None
        Forwarded to `claude -p --model MODEL` if given.

    Returns
    -------
    GenResult
        .question on success, .error with a reason on failure.
    """
    if not shutil.which("claude"):
        return GenResult(None, "claude CLI not on PATH")

    cache_file = GEN_CACHE_DIR / f"{_cache_key(code, context)}.json"
    cached = _cached(cache_file)
    if cached is not None:
        return GenResult(question=cached)

    prompt = _PROMPT_TEMPLATE.format(code=code[:4000], context=context[:500] or "(none)")

    cmd = ["claude", "-p", prompt]
    if model:
        cmd.extend(["--model", model])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return GenResult(None, f"claude -p timed out after {timeout_seconds}s")
    except (OSError, FileNotFoundError) as exc:
        return GenResult(None, f"failed to spawn claude: {exc}")

    if proc.returncode != 0:
        return GenResult(
            None,
            f"claude exited {proc.returncode}: {proc.stderr[:200]}",
            raw=proc.stdout,
        )

    body = proc.stdout
    payload_str = _extract_json(body)
    if payload_str is None:
        return GenResult(None, "model returned no JSON block", raw=body[:500])
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        return GenResult(None, f"invalid JSON from model: {exc}", raw=body[:500])

    try:
        question = _parse_question(payload)
    except ValueError as exc:
        return GenResult(None, f"schema violation: {exc}", raw=body[:500])

    _save(cache_file, payload)
    return GenResult(question=question)


def generate_from_commit(
    commit_sha: str,
    cwd: str | None = None,
    timeout_seconds: float = 45.0,
) -> GenResult:
    """Pull a commit's diff and generate one question from it."""
    try:
        diff_proc = subprocess.run(
            ["git", "show", "--format=%s%n%n", "--no-color", commit_sha],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return GenResult(None, f"git show failed: {exc}")
    diff_text = diff_proc.stdout
    # Separate subject line from the patch
    lines = diff_text.splitlines()
    subject = lines[0] if lines else ""
    body = "\n".join(lines[1:])
    return generate_from_code(
        code=body[:6000],
        context=f"commit {commit_sha[:8]}: {subject}",
        timeout_seconds=timeout_seconds,
    )


def clear_cache() -> int:
    """Remove every cached generated question. Returns count removed."""
    if not GEN_CACHE_DIR.exists():
        return 0
    n = 0
    for p in GEN_CACHE_DIR.glob("*.json"):
        try:
            p.unlink()
            n += 1
        except OSError:
            continue
    return n
