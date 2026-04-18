"""Quiz + reveal rendering.

The box is a fixed-width centered card. Render functions return byte
strings so the wrapper can write them atomically with os.write().

Key rendering principles (learned the hard way):
  1. The box renders on a FULLY CLEARED terminal. The wrapper does the
     clear; the renderer just produces a compact self-contained block.
  2. Every output line is padded to the box width so partial overwrites
     can't leak through.
  3. Cursor is hidden during rendering, restored on exit.
"""

from __future__ import annotations

import re
import shutil

from .palette import (
    BOLD, DIM,
    INK, STONE, ASH, DARK_ASH, SAGE, TEAL, GOLD, VIOLET, ROSE,
    paint,
)
from .question import Question


# Box drawing
TL, TR, BL, BR = "\u256d", "\u256e", "\u2570", "\u256f"
HZ, VT = "\u2500", "\u2502"
LT, RT = "\u251c", "\u2524"
THICK_VT = "\u2503"  # ┃ left accent

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def _term_size() -> tuple[int, int]:
    try:
        s = shutil.get_terminal_size()
        return s.columns, s.lines
    except OSError:
        return 80, 24


def _box_width() -> int:
    cols, _ = _term_size()
    return min(64, max(40, cols - 6))


def _indent() -> str:
    cols, _ = _term_size()
    pad = max(2, (cols - _box_width()) // 2)
    return " " * pad


def _wrap(text: str, width: int) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        words = para.split()
        line = ""
        for w in words:
            if not line:
                line = w
            elif len(line) + 1 + len(w) <= width:
                line += " " + w
            else:
                out.append(line)
                line = w
        if line:
            out.append(line)
    return out


def _row(content: str, inner_width: int, border_color: str, accent_color: str) -> str:
    """A single content row: accent bar + space + content + padding + right border."""
    vl = _visible_len(content)
    pad = max(0, inner_width - vl)
    return (
        f"{_indent()}"
        f"{paint(THICK_VT, accent_color, BOLD)} "
        f"{content}{' ' * pad} "
        f"{paint(VT, border_color)}"
    )


def _empty_row(inner_width: int, border_color: str, accent_color: str) -> str:
    return _row("", inner_width, border_color, accent_color)


def _render_options(
    q: Question,
    inner_width: int,
    answered_label: str | None = None,
) -> list[str]:
    """Render options, wrapped to fit. One option may span multiple lines."""
    text_room = inner_width - 5  # room for " N) " + 1 space

    def colors(opt) -> tuple[str, str, str]:
        if answered_label is None:
            return SAGE, INK, ""
        if opt.correct:
            return SAGE, SAGE, paint("  \u2713", SAGE, BOLD)
        if answered_label == opt.label and not opt.correct:
            return ROSE, ROSE, paint("  \u2717", ROSE)
        return DARK_ASH, ASH, ""

    lines: list[str] = []
    for opt in q.options:
        lab_color, txt_color, marker = colors(opt)
        bold_lab = BOLD if (answered_label is None or opt.correct) else ""
        bold_txt = BOLD if (answered_label is not None and opt.correct) else ""
        wrapped = _wrap(opt.text, text_room)
        for i, line in enumerate(wrapped):
            if i == 0:
                part = (
                    paint(f" {opt.label}) ", lab_color, bold_lab)
                    + paint(line, txt_color, bold_txt)
                )
            else:
                part = "    " + paint(line, txt_color, bold_txt)
            if marker and i == len(wrapped) - 1:
                part += marker
            lines.append(part)
    return lines


def _progress_bar(seconds_left: float, total: float, inner_width: int) -> str:
    """A thin progress bar showing time remaining. Sage at first, gold, then rose."""
    if seconds_left < 0:
        seconds_left = 0
    if total <= 0:
        total = 1
    frac = seconds_left / total
    bar_w = inner_width - 6   # reserve room for label "  Ns  "
    filled = int(round(frac * bar_w))
    empty = bar_w - filled
    if frac > 0.5:
        color = SAGE
    elif frac > 0.2:
        color = GOLD
    else:
        color = ROSE
    bar = paint("\u2588" * filled, color) + paint("\u2591" * empty, DARK_ASH, DIM)
    label = paint(f"{seconds_left:>3.0f}s", color, DIM)
    return f"{bar}  {label}"


def render_question(
    q: Question,
    streak: int,
    seconds_left: float | None = None,
    total_seconds: float = 15.0,
) -> str:
    """Render the whole question card. If seconds_left is given, include a
    progress bar at the bottom. The wrapper calls this repeatedly to
    animate the countdown.
    """
    width = _box_width()
    inner = width - 4
    bar_h = HZ * (width - 2)
    border = DARK_ASH
    accent = TEAL

    out: list[str] = []

    # Top with tight title
    title = " think about this "
    t_vis = len(title)
    side_l = 2
    side_r = width - 2 - side_l - t_vis
    top = (
        paint(TL, border)
        + paint(HZ * side_l, border)
        + paint(title, accent, BOLD)
        + paint(HZ * side_r, border)
        + paint(TR, border)
    )
    out.append(_indent() + top)

    # Optional streak row
    if streak > 0:
        out.append(_row(paint(f"day {streak} streak", GOLD, DIM), inner, border, accent))
        out.append(_indent() + paint(LT + HZ * (width - 2) + RT, border, DIM))

    out.append(_empty_row(inner, border, accent))

    for line in _wrap(q.prompt, inner - 1):
        out.append(_row(paint(line, INK, BOLD), inner, border, accent))

    # Code snippet if present
    if q.code:
        out.append(_empty_row(inner, border, accent))
        for code_line in q.code.split("\n"):
            truncated = code_line[: inner - 3]
            out.append(_row(paint("  " + truncated, TEAL), inner, border, accent))

    out.append(_empty_row(inner, border, accent))

    for line in _render_options(q, inner):
        out.append(_row(line, inner, border, accent))

    out.append(_empty_row(inner, border, accent))

    # Countdown (if provided) ABOVE the key hints, separated by an implicit blank
    if seconds_left is not None:
        out.append(_row(_progress_bar(seconds_left, total_seconds, inner), inner, border, accent))

    # Key hints
    hints = (
        paint("press ", ASH, DIM)
        + paint("1 2 3 4", SAGE, BOLD)
        + paint("  ", ASH, DIM)
        + paint("\u00b7", DARK_ASH, DIM)
        + paint("  ", ASH, DIM)
        + paint("x", SAGE) + paint(" skip  ", ASH, DIM)
        + paint("\u00b7", DARK_ASH, DIM)
        + paint("  ", ASH, DIM)
        + paint("X", SAGE) + paint(" mute", ASH, DIM)
    )
    out.append(_row(hints, inner, border, accent))

    out.append(_indent() + paint(BL + bar_h + BR, border))
    return "\n".join(out) + "\n"


def render_correct_flash(q: Question, streak: int, combo: int, xp_earned: int) -> str:
    """A minimal 1-line flash shown for correct answers so you move on fast."""
    bits: list[str] = []
    bits.append(paint("\u2713 exactly right", SAGE, BOLD))
    if combo >= 2:
        bits.append(paint(f"{combo}x combo", GOLD, BOLD))
    bits.append(paint(f"+{xp_earned} xp", VIOLET))
    if streak > 0:
        bits.append(paint(f"day {streak}", GOLD, DIM))
    joiner = paint("  \u00b7  ", DARK_ASH, DIM)
    content = joiner.join(bits)
    # Center it like the box
    width = _box_width()
    return _indent() + content + "\n"


def render_wrong_reveal(q: Question, chosen: str | None) -> str:
    """Full teaching reveal -- only shown when the user was wrong or skipped."""
    width = _box_width()
    inner = width - 4
    bar_h = HZ * (width - 2)

    if chosen is None:
        border, accent = GOLD, GOLD
        title = " skipped "
    else:
        border, accent = GOLD, GOLD
        title = " good to know "

    out: list[str] = []
    t_vis = len(title)
    side_l = 2
    side_r = width - 2 - side_l - t_vis
    out.append(
        _indent()
        + paint(TL, border)
        + paint(HZ * side_l, border)
        + paint(title, accent, BOLD)
        + paint(HZ * side_r, border)
        + paint(TR, border)
    )

    out.append(_empty_row(inner, border, accent))

    if q.code:
        for code_line in q.code.split("\n"):
            truncated = code_line[: inner - 3]
            out.append(_row(paint("  " + truncated, TEAL, DIM), inner, border, accent))
        out.append(_empty_row(inner, border, accent))

    for line in _render_options(q, inner, answered_label=chosen or ""):
        out.append(_row(line, inner, border, accent))

    out.append(_empty_row(inner, border, accent))

    for line in _wrap(q.explanation, inner - 1):
        out.append(_row(paint(line, STONE), inner, border, accent))

    out.append(_empty_row(inner, border, accent))

    if chosen is None:
        footer = paint("we'll surface this again later", ASH, DIM)
    else:
        footer = paint("we'll surface this again soon", ASH, DIM)
    out.append(_row(footer, inner, border, accent))

    out.append(_indent() + paint(BL + bar_h + BR, border))
    return "\n".join(out) + "\n"
