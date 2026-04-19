"""Persistent learning state -- streak, XP, concept mastery."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from datetime import date
from pathlib import Path

from .persist import atomic_write_json, filter_to_fields, load_json_or_quarantine

STATE_DIR = Path.home() / ".reskill"
STATE_FILE = STATE_DIR / "state.json"


@dataclass
class State:
    streak: int = 0
    last_date: str = ""
    xp_total: int = 0
    xp_today: int = 0
    correct_today: int = 0
    answered_today: int = 0
    combo: int = 0
    best_combo: int = 0
    freezes: int = 2
    seen_questions: list[str] = field(default_factory=list)
    concepts: dict[str, dict] = field(default_factory=dict)
    enabled: bool = True   # global on/off; toggled via `reskill pause`/`resume`
    daily_goal: int = 5    # questions per day to count toward streak
    history: dict[str, int] = field(default_factory=dict)  # "YYYY-MM-DD" -> answered count
    # IDs of questions answered incorrectly recently. Capped at 50 so
    # `reskill review` has a bounded drill set without drifting forever.
    recent_wrongs: list[str] = field(default_factory=list)
    # concepts[concept_key] = {"ef": 2.5, "interval": 1, "reps": 0, "last": 0.0, "correct": 0, "total": 0}

    @property
    def level(self) -> int:
        return 1 + self.xp_total // 200

    @property
    def level_title(self) -> str:
        titles = [
            "Novice", "Apprentice", "Journeyman", "Craftsman",
            "Specialist", "Expert", "Master", "Grandmaster",
        ]
        return titles[min(self.level - 1, len(titles) - 1)]


def load() -> State:
    data = load_json_or_quarantine(STATE_FILE, label="state.json")
    if data is not None:
        # Filter out unknown keys so a downgrade (or a hand-edited file
        # with a future field) doesn't TypeError us into a clean slate.
        known = {f.name for f in dataclass_fields(State)}
        s = State(**filter_to_fields(data, known))
    else:
        s = State()

    today = date.today().isoformat()
    if s.last_date != today:
        # Day rollover.
        # Streaks are kept visible because developers like the number,
        # but we removed the loss-aversion lever. Orosz et al. 2023 and
        # Self-Determination Theory both show that punitive streaks
        # reduce intrinsic motivation in adult learners even when they
        # raise short-term engagement. Rules:
        #   - Hitting the daily goal extends the streak.
        #   - Missing the goal does NOT zero the streak; we just
        #     pause it. Come back anytime -- the streak continues
        #     from where you left off.
        #   - Weekends don't count against you either way.
        if s.last_date:
            last = date.fromisoformat(s.last_date)
            if s.answered_today > 0:
                s.history[s.last_date] = s.answered_today
            gap = (date.today() - last).days
            met_goal = s.answered_today >= s.daily_goal
            was_weekend = last.weekday() >= 5
            if gap == 1 and met_goal:
                s.streak += 1
            # Implicit: no branch that zeros the streak. Pausing is the
            # only failure mode; freezes are kept for cosmetic display.
            if gap >= 2 and not was_weekend and not met_goal and s.freezes > 0:
                s.freezes -= 1
        s.xp_today = 0
        s.correct_today = 0
        s.answered_today = 0
        s.combo = 0
        s.last_date = today
        # Keep only the last ~120 days of history
        if len(s.history) > 180:
            for k in sorted(s.history.keys())[:-120]:
                del s.history[k]

    return s


def save(s: State) -> None:
    atomic_write_json(STATE_FILE, asdict(s))


def record_answer(s: State, question_id: str, concept: str, correct: bool, base_xp: int = 10) -> int:
    """Record an answer. Returns XP earned."""
    s.answered_today += 1
    if question_id not in s.seen_questions:
        s.seen_questions.append(question_id)
        # Cap history
        s.seen_questions = s.seen_questions[-500:]

    # SM-2 per concept
    c = s.concepts.setdefault(concept, {
        "ef": 2.5, "interval": 1, "reps": 0, "last": 0.0,
        "correct": 0, "total": 0,
    })
    c["total"] += 1
    c["last"] = time.time()

    if correct:
        s.correct_today += 1
        s.combo += 1
        s.best_combo = max(s.best_combo, s.combo)
        multiplier = min(s.combo, 5)
        earned = base_xp * multiplier
        s.xp_today += earned
        s.xp_total += earned
        # SM-2 update (quality ~= 4 for correct)
        c["correct"] += 1
        c["reps"] += 1
        if c["reps"] == 1:
            c["interval"] = 1
        elif c["reps"] == 2:
            c["interval"] = 6
        else:
            c["interval"] = round(c["interval"] * c["ef"])
        c["ef"] = max(1.3, c["ef"] + 0.1 - (5 - 4) * (0.08 + (5 - 4) * 0.02))
        return earned
    else:
        s.combo = 0
        c["reps"] = 0
        c["interval"] = 1
        c["ef"] = max(1.3, c["ef"] - 0.2)
        # Track for reskill review. De-dupe by moving the ID to the
        # end so the most recently-missed questions are drilled first.
        if question_id in s.recent_wrongs:
            s.recent_wrongs.remove(question_id)
        s.recent_wrongs.append(question_id)
        s.recent_wrongs = s.recent_wrongs[-50:]
        return 0


def record_skip(s: State, concept: str) -> None:
    s.answered_today += 1
    s.combo = 0
    c = s.concepts.setdefault(concept, {
        "ef": 2.5, "interval": 1, "reps": 0, "last": 0.0,
        "correct": 0, "total": 0,
    })
    c["total"] += 1
    c["last"] = time.time()
