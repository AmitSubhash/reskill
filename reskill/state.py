"""Persistent learning state -- streak, XP, concept mastery."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path


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
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            s = State(**data)
        except (json.JSONDecodeError, TypeError):
            s = State()
    else:
        s = State()

    today = date.today().isoformat()
    if s.last_date != today:
        # Day rollover
        if s.last_date:
            last = date.fromisoformat(s.last_date)
            if s.answered_today > 0:
                s.history[s.last_date] = s.answered_today
            gap = (date.today() - last).days
            met_goal = s.answered_today >= s.daily_goal
            if gap == 1 and met_goal:
                s.streak += 1
            elif gap >= 1 and not met_goal:
                if s.freezes > 0:
                    s.freezes -= 1
                else:
                    s.streak = 0
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
    STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(asdict(s), indent=2))


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
