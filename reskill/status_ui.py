"""Terse status output for shell prompts, tmux status-right, and heatmaps."""

from __future__ import annotations

from datetime import date, timedelta

from . import state as state_mod
from .palette import ASH, BOLD, DARK_ASH, DIM, GOLD, SAGE, STONE, paint


def _concepts_mastered(s: state_mod.State, threshold: float = 0.75) -> int:
    """Count concepts with mastery >= threshold.

    Promoted as the primary metric over streak to align with
    Self-Determination Theory: competence > compliance. An item counts
    as "mastered" when the running correct/total ratio is high enough
    and it has been answered at least twice.
    """
    n = 0
    for data in s.concepts.values():
        total = data.get("total", 0)
        correct = data.get("correct", 0)
        if total >= 2 and (correct / total) >= threshold:
            n += 1
    return n


def render_status(plain: bool = False) -> str:
    """One-line summary: concepts mastered + today's progress + streak.

    Concept mastery is first because it's the retention-aligned metric;
    streak is kept but demoted.
    """
    s = state_mod.load()
    mastered = _concepts_mastered(s)
    fire = "*" if plain else "\U0001f525"
    tilde = "~" if plain else "\u223c"
    sep = "  " if plain else "  \u00b7  "

    mastered_bit = f"{mastered} mastered"
    today_bit = f"{s.correct_today}/{s.daily_goal} today"
    # Use a different character when the streak is "paused" (today has
    # no answers yet and we've already missed the goal window). Never
    # show a zero that looks punitive; the literature says that anxiety
    # doesn't help adult learners.
    if s.streak > 0 and s.correct_today == 0:
        streak_bit = f"{tilde} {s.streak}"   # paused
    elif s.streak > 0:
        streak_bit = f"{fire} {s.streak}"
    else:
        streak_bit = f"{fire} --"

    if plain:
        return f"{mastered_bit}{sep}{today_bit}{sep}{streak_bit}"

    return (
        paint(mastered_bit, SAGE, BOLD)
        + paint(sep, DARK_ASH, DIM)
        + paint(today_bit, SAGE if s.correct_today >= s.daily_goal else STONE)
        + paint(sep, DARK_ASH, DIM)
        + paint(streak_bit, GOLD)
    )


def render_heatmap(weeks: int = 12) -> str:
    """Github-style heatmap of the last N weeks.

    We render 7 rows (Sun..Sat) x `weeks` columns; each cell is shaded by
    answered-count bucket. Uses state.history and today's in-progress counter.
    """
    s = state_mod.load()
    today = date.today()
    start = today - timedelta(days=weeks * 7 - 1)
    start -= timedelta(days=start.weekday() + 1 if start.weekday() < 6 else 0)

    def cell(count: int) -> str:
        if count <= 0:
            return paint("\u2591", DARK_ASH, DIM)
        if count < s.daily_goal // 2:
            return paint("\u2592", STONE)
        if count < s.daily_goal:
            return paint("\u2593", GOLD)
        return paint("\u2588", SAGE, BOLD)

    lines = [""]
    for weekday in range(7):
        row_date = start + timedelta(days=weekday)
        row: list[str] = []
        while row_date <= today:
            key = row_date.isoformat()
            count = s.history.get(key, 0)
            if key == today.isoformat():
                count = max(count, s.answered_today)
            row.append(cell(count))
            row_date += timedelta(days=7)
        label = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][weekday]
        lines.append(
            paint(f"  {label}  ", ASH, DIM) + " ".join(row)
        )

    totals = sum(s.history.values()) + s.answered_today
    mastered = _concepts_mastered(s)
    summary = (
        paint("  ", ASH)
        + paint(f"{mastered} concepts mastered", SAGE, BOLD)
        + paint(f"    {totals} answered", ASH)
        + paint(f"    streak {s.streak}", GOLD, DIM)
        + paint(f"    goal {s.daily_goal}/day", ASH, DIM)
    )
    lines.append("")
    lines.append(summary)
    lines.append("")
    return "\n".join(lines)
