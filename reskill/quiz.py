"""Quiz data models, rendering, and gamification state."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .palette import (
    BOLD, DIM, RESET,
    INK, STONE, ASH, DARK_ASH, SAGE, TEAL, ROSE, VIOLET, GOLD,
    paint,
)
from .panel import render_panel, visible_len, HZ, TERM_W


# ── Data models ──────────────────────────────────────────────


@dataclass
class QuizOption:
    label: str
    text: str
    correct: bool


@dataclass
class QuizQuestion:
    format: str  # what_is_output, spot_the_bug, true_false, multiple_choice
    language: str
    tags: list[str]
    difficulty: int  # 1=easy, 2=medium, 3=hard
    prompt: str
    options: list[QuizOption]
    explanation: str
    code: str | None = None
    xp: int = 10

    @property
    def correct_label(self) -> str:
        for o in self.options:
            if o.correct:
                return o.label
        return "?"


# ── State persistence ────────────────────────────────────────


STATE_DIR = Path.home() / ".reskill"


@dataclass
class SessionState:
    streak: int = 0
    last_date: str = ""
    xp_total: int = 0
    xp_today: int = 0
    level: int = 1
    correct_today: int = 0
    total_today: int = 0
    combo: int = 0
    best_combo: int = 0
    freezes: int = 2

    def load(self) -> None:
        path = STATE_DIR / "state.json"
        if path.exists():
            data = json.loads(path.read_text())
            for k, v in data.items():
                if hasattr(self, k):
                    setattr(self, k, v)
        # Check streak
        today = date.today().isoformat()
        if self.last_date == today:
            pass  # same day, continue
        elif self.last_date == str(date.today().replace(day=date.today().day - 1)):
            self.streak += 1
            self.xp_today = 0
            self.correct_today = 0
            self.total_today = 0
            self.combo = 0
        else:
            if self.freezes > 0 and self.last_date:
                self.freezes -= 1
            else:
                self.streak = 0
            self.xp_today = 0
            self.correct_today = 0
            self.total_today = 0
            self.combo = 0
        self.last_date = today

    def save(self) -> None:
        STATE_DIR.mkdir(exist_ok=True)
        path = STATE_DIR / "state.json"
        path.write_text(json.dumps({
            "streak": self.streak,
            "last_date": self.last_date,
            "xp_total": self.xp_total,
            "xp_today": self.xp_today,
            "level": self.level,
            "correct_today": self.correct_today,
            "total_today": self.total_today,
            "combo": self.combo,
            "best_combo": self.best_combo,
            "freezes": self.freezes,
        }, indent=2))

    def record_answer(self, correct: bool, xp: int) -> int:
        """Record an answer. Returns XP earned (with combo multiplier)."""
        self.total_today += 1
        if correct:
            self.combo += 1
            self.best_combo = max(self.best_combo, self.combo)
            self.correct_today += 1
            multiplier = min(self.combo, 5)  # max 5x combo
            earned = xp * multiplier
            self.xp_today += earned
            self.xp_total += earned
            # Level up every 200 XP
            self.level = 1 + self.xp_total // 200
            return earned
        else:
            self.combo = 0
            return 0

    @property
    def level_title(self) -> str:
        titles = [
            "Novice", "Apprentice", "Journeyman", "Craftsman",
            "Specialist", "Expert", "Master", "Grandmaster",
        ]
        idx = min(self.level - 1, len(titles) - 1)
        return titles[idx]

    @property
    def daily_goal(self) -> int:
        return 5

    @property
    def daily_progress_str(self) -> str:
        return f"{self.correct_today}/{self.daily_goal}"


# ── Rendering ────────────────────────────────────────────────


def render_quiz(q: QuizQuestion, state: SessionState) -> list[str]:
    """Render a quiz question panel."""
    lines: list[str] = []
    lines.append("")

    # Code block if present
    if q.code:
        for code_line in q.code.split("\n"):
            lines.append(paint(f"  {code_line}", TEAL))
        lines.append("")

    # Question prompt
    lines.append(paint(f"  {q.prompt}", INK))
    lines.append("")

    # Options
    for opt in q.options:
        lines.append(
            paint(f"    {opt.label}) ", SAGE, BOLD)
            + paint(opt.text, INK)
        )
    lines.append("")

    # Footer: instructions + timer + xp
    lines.append(
        paint(f"  Press {'/'.join(o.label.lower() for o in q.options)} to answer", ASH)
        + paint(f"    +{q.xp} XP", VIOLET)
    )

    # Build title
    lang_label = q.language.title()
    progress = state.daily_progress_str
    title = f"{lang_label} Quiz"
    subtitle = f"{progress} today"
    if state.combo >= 2:
        subtitle += f"  {state.combo}x combo"
    if state.streak > 0:
        subtitle += f"  {state.streak}d streak"

    return render_panel(
        title,
        lines,
        border_color=DARK_ASH,
        title_color=TEAL,
        subtitle=subtitle,
    )


def render_answer(
    q: QuizQuestion,
    chosen: str,
    state: SessionState,
    xp_earned: int,
) -> list[str]:
    """Render the answer reveal panel."""
    correct = chosen.upper() == q.correct_label.upper()
    lines: list[str] = []
    lines.append("")

    for opt in q.options:
        if opt.correct:
            marker = paint(" \u2713", SAGE, BOLD)
            lines.append(
                paint(f"    {opt.label}) ", SAGE, BOLD)
                + paint(opt.text, SAGE)
                + marker
            )
        elif opt.label.upper() == chosen.upper() and not opt.correct:
            marker = paint(" \u2717", ROSE, BOLD)
            lines.append(
                paint(f"    {opt.label}) ", ROSE)
                + paint(opt.text, ROSE)
                + marker
            )
        else:
            lines.append(
                paint(f"    {opt.label}) ", ASH)
                + paint(opt.text, ASH)
            )
    lines.append("")

    # Explanation
    for expl_line in q.explanation.split("\n"):
        lines.append(paint(f"  {expl_line}", STONE))
    lines.append("")

    # Title
    if correct:
        title = paint("Correct!", SAGE, BOLD)
        xp_text = f"+{xp_earned} XP"
        if state.combo >= 2:
            xp_text += f" ({state.combo}x combo!)"
    else:
        title = paint("Not quite", ROSE)
        xp_text = ""

    return render_panel(
        title,
        lines,
        border_color=SAGE if correct else ROSE,
        title_color=SAGE if correct else ROSE,
        subtitle=xp_text,
    )


def render_session_summary(state: SessionState) -> list[str]:
    """Render end-of-session summary."""
    pct = (state.correct_today / max(1, state.total_today)) * 100
    bar_filled = int(pct / 5)  # 20 chars wide
    bar_empty = 20 - bar_filled
    bar = paint("\u2588" * bar_filled, TEAL) + paint("\u2591" * bar_empty, DARK_ASH)

    lines: list[str] = []
    lines.append("")
    lines.append(
        paint(f"  Score: {state.correct_today}/{state.total_today}  ", INK)
        + bar
        + paint(f"  {pct:.0f}%", SAGE)
    )
    lines.append("")
    lines.append(
        paint(f"  XP earned: ", STONE)
        + paint(f"+{state.xp_today}", GOLD, BOLD)
        + paint(f"  (total: {state.xp_total})", ASH)
    )
    lines.append(
        paint(f"  Level: ", STONE)
        + paint(f"{state.level} ({state.level_title})", VIOLET)
    )
    lines.append(
        paint(f"  Streak: ", STONE)
        + paint(f"{state.streak} days", GOLD)
        + paint(f"  Best combo: {state.best_combo}x", ASH)
    )
    lines.append("")

    return render_panel(
        "Session Summary",
        lines,
        border_color=TEAL,
        title_color=TEAL,
    )


# ── Sample questions ─────────────────────────────────────────

SAMPLE_QUESTIONS: list[QuizQuestion] = [
    QuizQuestion(
        format="what_is_output",
        language="python",
        tags=["references", "lists"],
        difficulty=1,
        prompt="What does this code output?",
        code="x = [1, 2, 3]\ny = x\ny.append(4)\nprint(len(x))",
        options=[
            QuizOption("A", "3", False),
            QuizOption("B", "4", True),
            QuizOption("C", "TypeError", False),
            QuizOption("D", "None", False),
        ],
        explanation="Lists are mutable reference types. y = x creates\nan alias, not a copy. Both point to the same object.",
        xp=10,
    ),
    QuizQuestion(
        format="spot_the_bug",
        language="python",
        tags=["algorithms", "binary_search"],
        difficulty=2,
        prompt="Which line has the bug?",
        code=(
            "def binary_search(arr, target):\n"
            "    low, high = 0, len(arr)\n"
            "    while low <= high:\n"
            "        mid = (low + high) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            low = mid + 1\n"
            "        else:\n"
            "            high = mid - 1\n"
            "    return -1"
        ),
        options=[
            QuizOption("A", "Line 2: should be len(arr) - 1", True),
            QuizOption("B", "Line 4: integer overflow risk", False),
            QuizOption("C", "Line 3: should be low < high", False),
            QuizOption("D", "Line 10: should be high = mid", False),
        ],
        explanation="high should be len(arr) - 1. With len(arr),\narr[mid] can index out of bounds on the last element.",
        xp=25,
    ),
    QuizQuestion(
        format="multiple_choice",
        language="python",
        tags=["fastapi", "http"],
        difficulty=1,
        prompt="What HTTP status code means 'Created'?",
        code=None,
        options=[
            QuizOption("A", "200", False),
            QuizOption("B", "201", True),
            QuizOption("C", "204", False),
            QuizOption("D", "301", False),
        ],
        explanation="201 Created indicates a new resource was\nsuccessfully created. 200 is OK, 204 is No Content.",
        xp=10,
    ),
    QuizQuestion(
        format="what_is_output",
        language="python",
        tags=["scope", "closures"],
        difficulty=2,
        prompt="What does this code output?",
        code=(
            "funcs = []\n"
            "for i in range(3):\n"
            "    funcs.append(lambda: i)\n"
            "print([f() for f in funcs])"
        ),
        options=[
            QuizOption("A", "[0, 1, 2]", False),
            QuizOption("B", "[2, 2, 2]", True),
            QuizOption("C", "[3, 3, 3]", False),
            QuizOption("D", "Error", False),
        ],
        explanation="The lambda captures the variable i by reference,\nnot by value. After the loop, i is 2 for all closures.",
        xp=25,
    ),
    QuizQuestion(
        format="true_false",
        language="python",
        tags=["types"],
        difficulty=1,
        prompt="True or False: In Python, tuples are mutable.",
        code=None,
        options=[
            QuizOption("A", "True", False),
            QuizOption("B", "False", True),
        ],
        explanation="Tuples are immutable. Once created, their elements\ncannot be changed, added, or removed.",
        xp=10,
    ),
]
