"""Terse status output for shell prompts, tmux status-right, and heatmaps."""

from __future__ import annotations

from datetime import date, timedelta

from . import state as state_mod
from .palette import ASH, BOLD, DARK_ASH, DIM, GOLD, INK, SAGE, STONE, paint


def render_status(plain: bool = False) -> str:
    """One-line summary: streak + today's progress.

    Parameters
    ----------
    plain : bool
        If True, emit ASCII-only without ANSI colors (for $PS1 safety).

    Returns
    -------
    str
        Single line, no trailing newline.
    """
    s = state_mod.load()
    fire = "*" if plain else "\U0001f525"
    sep = "  " if plain else "  \u00b7  "
    streak_bit = f"{fire} {s.streak}" if s.streak > 0 else f"{fire} --"
    today_bit = f"{s.correct_today}/{s.daily_goal} today"

    if plain:
        return f"{streak_bit}{sep}{today_bit}"

    return (
        paint(streak_bit, GOLD, BOLD)
        + paint(sep, DARK_ASH, DIM)
        + paint(today_bit, SAGE if s.correct_today >= s.daily_goal else STONE)
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
    summary = (
        paint(f"  total answered: ", ASH, DIM)
        + paint(str(totals), INK, BOLD)
        + paint(f"    goal: {s.daily_goal}/day", ASH, DIM)
        + paint(f"    streak: ", ASH, DIM)
        + paint(f"{s.streak}", GOLD, BOLD)
        + paint(f"    freezes: {s.freezes}", ASH, DIM)
    )
    lines.append("")
    lines.append(summary)
    lines.append("")
    return "\n".join(lines)
