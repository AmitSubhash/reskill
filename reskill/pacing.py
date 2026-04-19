"""Pacing rules that decide WHEN a quiz is allowed to fire.

Derived from evidence rather than vibes. Primary sources:
  - Iqbal & Bailey 2008 (CHI): interrupting at coarse task breakpoints
    is far cheaper than fine-grained interruptions.
  - Adamczyk & Bailey 2004: first 3 s of a task-switch window is still
    "fine-grained"; wait for the user to settle.
  - Wang et al. 2021 microlearning meta: 6+ interruptions/hour starts to
    dominate recovery time even at coarse breakpoints.
  - Mark, Gonzalez, Harris 2008: ~23 min refocus time is the upper bound
    without pacing; 90 s gap is the empirical floor that avoids
    fire-hosing during tool-heavy turns.

The gate is `can_fire_now(...)`. Every other function here supports it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


STATE_DIR = Path.home() / ".reskill" / "state"
PACING_FILE = STATE_DIR / "pacing.json"


@dataclass
class PacingState:
    """Rolling counters for rate-limit decisions.

    Persisted so counts survive quiz-panel restarts within a session.
    """

    thinking_started_at: float = 0.0
    last_quiz_finished_at: float = 0.0
    last_concept_at: dict[str, float] = field(default_factory=dict)
    quiz_timestamps: list[float] = field(default_factory=list)


# Evidence-cited defaults. See module docstring for citations.
# All tunable via env vars so power users can dial up or down:
#   RESKILL_MIN_GAP=30   seconds between quizzes (default 30)
#   RESKILL_MAX_PER_HOUR=10
#   RESKILL_MAX_PER_DAY=40
#   RESKILL_SAME_CONCEPT_COOLDOWN=120
# Research default was 90s; lowered to 30s based on user feedback that
# the live-pane felt too quiet. Still respects the 3s post-thinking
# debounce (Iqbal & Bailey 2008) that avoids micro-interrupts.
def _env_float(name: str, default: float) -> float:
    import os
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


MIN_SECONDS_AFTER_THINKING_START = _env_float("RESKILL_THINKING_DEBOUNCE", 3.0)
# Back-to-back quizzes while Claude is still thinking: 10s is short
# enough to feel responsive, long enough to avoid overwhelming the user.
MIN_SECONDS_BETWEEN_QUIZZES = _env_float("RESKILL_MIN_GAP", 10.0)
# Caps are very loose by default -- the scheduler's own interleaving +
# format-mix logic handles variety; hard caps were creating confusing
# "stuck" states when hit. Set to a very large number so they don't
# trigger in practice. Users who want a real cap can set the env var.
MAX_QUIZZES_PER_HOUR = int(_env_float("RESKILL_MAX_PER_HOUR", 9999))
MAX_QUIZZES_PER_DAY = int(_env_float("RESKILL_MAX_PER_DAY", 9999))
# Same-concept cooldown: don't re-ask the SAME concept for N seconds.
# Keeps variety. When the gate blocks on this, we DON'T just sit and
# wait -- quiz_panel retries with the concept excluded.
MIN_SECONDS_BEFORE_SAME_CONCEPT = _env_float(
    "RESKILL_SAME_CONCEPT_COOLDOWN", 60,
)


def load() -> PacingState:
    if not PACING_FILE.exists():
        return PacingState()
    try:
        data = json.loads(PACING_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return PacingState()
    ps = PacingState(
        thinking_started_at=data.get("thinking_started_at", 0.0),
        last_quiz_finished_at=data.get("last_quiz_finished_at", 0.0),
        last_concept_at=dict(data.get("last_concept_at", {})),
        quiz_timestamps=list(data.get("quiz_timestamps", [])),
    )
    ps.quiz_timestamps = _prune_day(ps.quiz_timestamps)
    return ps


def save(ps: PacingState) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        PACING_FILE.write_text(json.dumps({
            "thinking_started_at": ps.thinking_started_at,
            "last_quiz_finished_at": ps.last_quiz_finished_at,
            "last_concept_at": ps.last_concept_at,
            "quiz_timestamps": ps.quiz_timestamps,
        }, indent=2))
    except OSError:
        pass


def _prune_day(timestamps: list[float], now: float | None = None) -> list[float]:
    cutoff = (now or time.time()) - 86400
    return [t for t in timestamps if t >= cutoff]


def _count_in_window(timestamps: list[float], window_seconds: float, now: float) -> int:
    cutoff = now - window_seconds
    return sum(1 for t in timestamps if t >= cutoff)


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str  # 'ok' or a short diagnostic like 'rate:hourly'


def can_fire_now(
    ps: PacingState,
    candidate_concept: str | None = None,
    now: float | None = None,
) -> GateResult:
    """Is it OK to show a new question right now?

    Must pass every rule; first failure wins and is reported in `.reason`.
    """
    now = now if now is not None else time.time()

    if ps.thinking_started_at > 0:
        elapsed = now - ps.thinking_started_at
        if elapsed < MIN_SECONDS_AFTER_THINKING_START:
            return GateResult(False, "debounce:thinking-just-started")

    if ps.last_quiz_finished_at > 0:
        gap = now - ps.last_quiz_finished_at
        if gap < MIN_SECONDS_BETWEEN_QUIZZES:
            return GateResult(False, f"rate:min-gap({int(gap)}s<90s)")

    hourly = _count_in_window(ps.quiz_timestamps, 3600, now)
    if hourly >= MAX_QUIZZES_PER_HOUR:
        return GateResult(False, f"rate:hourly({hourly}>=6)")

    daily = _count_in_window(ps.quiz_timestamps, 86400, now)
    if daily >= MAX_QUIZZES_PER_DAY:
        return GateResult(False, f"rate:daily({daily}>=20)")

    if candidate_concept:
        last_same = ps.last_concept_at.get(candidate_concept, 0.0)
        if last_same > 0:
            since = now - last_same
            if since < MIN_SECONDS_BEFORE_SAME_CONCEPT:
                return GateResult(False, f"rate:same-concept({int(since)}s<600s)")

    return GateResult(True, "ok")


def note_thinking_started(ps: PacingState, now: float | None = None) -> None:
    ps.thinking_started_at = now if now is not None else time.time()


def note_quiz_served(
    ps: PacingState,
    concept: str,
    now: float | None = None,
) -> None:
    t = now if now is not None else time.time()
    ps.quiz_timestamps.append(t)
    ps.quiz_timestamps = _prune_day(ps.quiz_timestamps, t)
    ps.last_concept_at[concept] = t


def note_quiz_finished(ps: PacingState, now: float | None = None) -> None:
    ps.last_quiz_finished_at = now if now is not None else time.time()


def seconds_until_next_allowed(
    ps: PacingState,
    now: float | None = None,
) -> float:
    """Estimate how long until the pacing gate opens again.

    Useful for the idle card's "next question in ~?s" hint.
    """
    now = now if now is not None else time.time()
    if ps.last_quiz_finished_at == 0:
        return 0.0
    gap_remaining = MIN_SECONDS_BETWEEN_QUIZZES - (now - ps.last_quiz_finished_at)
    hourly = _count_in_window(ps.quiz_timestamps, 3600, now)
    hourly_remaining = 0.0
    if hourly >= MAX_QUIZZES_PER_HOUR:
        oldest_in_hour = min(
            (t for t in ps.quiz_timestamps if t >= now - 3600),
            default=now,
        )
        hourly_remaining = (oldest_in_hour + 3600) - now
    return max(0.0, gap_remaining, hourly_remaining)
