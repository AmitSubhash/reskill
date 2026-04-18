"""Quiz box rendering.

Design rules (learned from v1..v5):
  - We print the box inline. No screen clears. No cursor positioning.
    Every render is a plain append to the terminal output stream.
  - Lines are separated by \\n and the box scrolls naturally into
    scrollback when Claude's output follows.
  - The countdown lives on a SINGLE line below the box. We update it
    in place with \\r (carriage return) so it doesn't scroll.
  - No re-rendering of the whole box mid-quiz. The box is written
    once as one atomic os.write().
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


TL, TR, BL, BR = "\u256d", "\u256e", "\u2570", "\u256f"
HZ, VT = "\u2500", "\u2502"
THICK_VT = "\u2503"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def _term_cols() -> int:
    try:
        return shutil.get_terminal_size().columns
    except OSError:
        return 80


def _box_width() -> int:
    """Prefer 58 chars; fall back if terminal is narrower."""
    return min(58, max(38, _term_cols() - 10))


def _indent() -> str:
    """Left pad so the box sits centered in the terminal."""
    pad = max(0, (_term_cols() - _box_width()) // 2)
    return " " * pad


def _wrap(text: str, width: int) -> list[str]:
    """Greedy word-wrap. If a single word is longer than the width, hard-break it."""
    out: list[str] = []
    if width <= 0:
        return [text]
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        words = para.split()
        line = ""
        for w in words:
            # Hard-break words that are too long on their own
            while len(w) > width:
                if line:
                    out.append(line)
                    line = ""
                out.append(w[:width])
                w = w[width:]
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


def _row(content: str, inner: int, border_color: str, accent_color: str) -> str:
    """| content | row with a thick left accent bar."""
    vis = _visible_len(content)
    pad = max(0, inner - vis)
    return (
        f"{_indent()}"
        f"{paint(THICK_VT, accent_color, BOLD)} "
        f"{content}{' ' * pad} "
        f"{paint(VT, border_color)}"
    )


def _empty(inner: int, border: str, accent: str) -> str:
    return _row("", inner, border, accent)


def _options(q: Question, inner: int, chosen: str | None = None) -> list[str]:
    text_room = inner - 5

    def colors(opt):
        if chosen is None:
            return SAGE, INK, ""
        if opt.correct:
            return SAGE, SAGE, paint("  \u2713", SAGE, BOLD)
        if chosen == opt.label and not opt.correct:
            return ROSE, ROSE, paint("  \u2717", ROSE)
        return DARK_ASH, ASH, ""

    lines: list[str] = []
    for opt in q.options:
        lab_c, txt_c, marker = colors(opt)
        lab_b = BOLD if (chosen is None or opt.correct) else ""
        txt_b = BOLD if (chosen is not None and opt.correct) else ""
        wrapped = _wrap(opt.text, text_room)
        for i, line in enumerate(wrapped):
            if i == 0:
                piece = (
                    paint(f" {opt.label}) ", lab_c, lab_b)
                    + paint(line, txt_c, txt_b)
                )
            else:
                piece = "    " + paint(line, txt_c, txt_b)
            if marker and i == len(wrapped) - 1:
                piece += marker
            lines.append(piece)
    return lines


def render_question(q: Question, streak: int) -> str:
    """Render the full question box. One atomic write (no re-renders)."""
    width = _box_width()
    inner = width - 4
    bar = HZ * (width - 2)
    border = DARK_ASH
    accent = TEAL
    ind = _indent()

    out: list[str] = []
    out.append("")  # blank line of separation above

    # Top with centered tight title
    title = " think about this "
    t_vis = len(title)
    side_l = 2
    side_r = width - 2 - side_l - t_vis
    out.append(
        ind
        + paint(TL, border)
        + paint(HZ * side_l, border)
        + paint(title, accent, BOLD)
        + paint(HZ * side_r, border)
        + paint(TR, border)
    )

    # Streak chip (no divider; tight layout)
    if streak > 0:
        streak_line = paint(f"day {streak} streak", GOLD, DIM)
        out.append(_row(streak_line, inner, border, accent))
        out.append(_empty(inner, border, accent))

    # Question
    for line in _wrap(q.prompt, inner - 1):
        out.append(_row(paint(line, INK, BOLD), inner, border, accent))

    # Code
    if q.code:
        out.append(_empty(inner, border, accent))
        for code_line in q.code.split("\n"):
            out.append(_row(paint("  " + code_line[: inner - 3], TEAL), inner, border, accent))

    out.append(_empty(inner, border, accent))

    # Options
    for line in _options(q, inner):
        out.append(_row(line, inner, border, accent))

    out.append(_empty(inner, border, accent))

    # Key hints inside the box
    hints = (
        paint("press ", ASH, DIM)
        + paint("1 2 3 4", SAGE, BOLD)
        + paint("  \u00b7  ", DARK_ASH, DIM)
        + paint("x", SAGE)
        + paint(" skip  ", ASH, DIM)
        + paint("\u00b7  ", DARK_ASH, DIM)
        + paint("X", SAGE)
        + paint(" mute", ASH, DIM)
    )
    out.append(_row(hints, inner, border, accent))

    # Bottom
    out.append(ind + paint(BL + bar + BR, border))
    out.append("")  # blank line below

    return "\n".join(out) + "\n"


def render_countdown_line(seconds_left: float, total: float) -> str:
    """A single line to be written with leading \\r to update the countdown
    without scrolling. Returns bytes-safe text with no trailing newline.
    """
    if seconds_left < 0:
        seconds_left = 0
    if total <= 0:
        total = 1
    width = _box_width()
    inner = width - 4
    bar_w = inner - 10  # room for " XXs left"

    frac = seconds_left / total
    filled = int(round(frac * bar_w))
    empty = bar_w - filled
    if frac > 0.5:
        color = SAGE
    elif frac > 0.25:
        color = GOLD
    else:
        color = ROSE

    bar = paint("\u2588" * filled, color) + paint("\u2591" * empty, DARK_ASH, DIM)
    label = paint(f"{seconds_left:>3.0f}s", color, DIM)
    hint = paint("claude is still thinking", ASH, DIM)
    # Clear to end of line with \x1b[K so old content doesn't linger
    return f"\r\x1b[2K{_indent()}  {bar}  {label}  {hint}"


def render_correct_flash(
    q: Question, streak: int, combo: int, xp_earned: int
) -> str:
    """One-line positive acknowledgement. Compact, moves on fast."""
    bits = [paint("\u2713 exactly right", SAGE, BOLD)]
    if combo >= 2:
        bits.append(paint(f"{combo}x combo", GOLD, BOLD))
    bits.append(paint(f"+{xp_earned} xp", VIOLET))
    if streak > 0:
        bits.append(paint(f"day {streak}", GOLD, DIM))
    joiner = paint("  \u00b7  ", DARK_ASH, DIM)
    return "\n" + _indent() + joiner.join(bits) + "\n\n"


def render_wrong_reveal(q: Question, chosen: str | None) -> str:
    """Teaching reveal -- shown on wrong/skipped only. Inline, atomic."""
    width = _box_width()
    inner = width - 4
    bar = HZ * (width - 2)
    ind = _indent()

    border = GOLD
    accent = GOLD
    title = " good to know " if chosen is not None else " skipped "

    out: list[str] = []
    out.append("")

    t_vis = len(title)
    side_l = 2
    side_r = width - 2 - side_l - t_vis
    out.append(
        ind
        + paint(TL, border)
        + paint(HZ * side_l, border)
        + paint(title, accent, BOLD)
        + paint(HZ * side_r, border)
        + paint(TR, border)
    )

    if q.code:
        out.append(_empty(inner, border, accent))
        for code_line in q.code.split("\n"):
            out.append(_row(paint("  " + code_line[: inner - 3], TEAL, DIM), inner, border, accent))

    out.append(_empty(inner, border, accent))

    for line in _options(q, inner, chosen=chosen or ""):
        out.append(_row(line, inner, border, accent))

    out.append(_empty(inner, border, accent))

    for line in _wrap(q.explanation, inner - 1):
        out.append(_row(paint(line, STONE), inner, border, accent))

    out.append(ind + paint(BL + bar + BR, border))
    out.append("")

    return "\n".join(out) + "\n"
