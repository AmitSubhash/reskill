"""Inline quiz box -- renders full-terminal-width in the flow of output."""

from __future__ import annotations

import shutil

from .palette import (
    BOLD, DIM, RESET,
    INK, STONE, ASH, DARK_ASH, SAGE, TEAL, GOLD, VIOLET, ROSE,
    bg_rgb, paint, rgb,
)
from .panel import visible_len
from .question import Question


# Box drawing characters
TL, TR, BL, BR = "\u256d", "\u256e", "\u2570", "\u256f"
HZ, VT = "\u2500", "\u2502"
LT, RT = "\u251c", "\u2524"
THICK_VT = "\u2503"  # ┃  used for the left accent bar


def _term_width() -> int:
    try:
        return shutil.get_terminal_size().columns
    except OSError:
        return 80


def _box_width() -> int:
    """Fixed-size centered card. Feels like a popover, not a takeover."""
    tw = _term_width()
    # Target width: 64 chars; fall back to terminal width if narrow
    return min(64, max(40, tw - 6))


def _indent() -> str:
    """Left padding that centers the box in the terminal."""
    tw = _term_width()
    pad = max(2, (tw - _box_width()) // 2)
    return " " * pad


def _pad_to(line: str, width: int) -> str:
    """Pad to width using visible length (ignoring ANSI)."""
    vl = visible_len(line)
    if vl >= width:
        return line
    return line + " " * (width - vl)


def _row(
    content: str,
    inner_width: int,
    border_color: str,
    border_dim: bool = False,
    left_accent: str | None = None,
) -> str:
    """Render a single content row inside the box."""
    left_border = paint(VT, border_color, DIM if border_dim else "")
    right_border = paint(VT, border_color, DIM if border_dim else "")
    if left_accent:
        # Replace first char with thick accent VT
        left_border = paint(THICK_VT, left_accent, BOLD)
    padded = _pad_to(content, inner_width)
    return f"{_indent()}{left_border} {padded} {right_border}"


def _wrap_text(text: str, width: int) -> list[str]:
    """Greedy word wrap, respects paragraph breaks on '\\n'."""
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


def _render_options_grid(
    q: Question,
    inner_width: int,
    answered_label: str | None = None,
) -> list[str]:
    """Render options in a single stacked column with wrapping.

    Each option may span multiple lines. The label (1/2/3/4) stays on
    the first line; continuation lines are indented to align with the
    option text.
    """
    # Style chooser per option -- answered_label is None for question view
    def _colors(opt) -> tuple[str, str, str]:
        """Returns (label_color, text_color, marker_string)."""
        if answered_label is None:
            return SAGE, INK, ""
        if opt.correct:
            return SAGE, SAGE, paint("  \u2713", SAGE, BOLD)
        if answered_label == opt.label and not opt.correct:
            return ROSE, ROSE, paint("  \u2717", ROSE)
        return DARK_ASH, ASH, ""

    lines: list[str] = []
    # " 1) " = 4 visible chars. Leave that gap on continuation lines.
    label_prefix_visible = 4
    indent_cont = " " * (label_prefix_visible + 1)
    text_room = inner_width - label_prefix_visible - 2  # -2 for leading space + marker padding

    for opt in q.options:
        label_color, text_color, marker = _colors(opt)
        wrapped = _wrap_text(opt.text, text_room)
        bold_label = BOLD if (answered_label is None or opt.correct) else ""
        bold_text = BOLD if (answered_label is not None and opt.correct) else ""
        for i, line in enumerate(wrapped):
            if i == 0:
                label_part = paint(f" {opt.label}) ", label_color, bold_label)
                text_part = paint(line, text_color, bold_text)
                full = f"{label_part}{text_part}"
                if marker and i == len(wrapped) - 1:
                    full += marker
                lines.append(full)
            else:
                text_part = paint(line, text_color, bold_text)
                full = indent_cont + text_part
                if marker and i == len(wrapped) - 1:
                    full += marker
                lines.append(full)
    return lines


def render_question(q: Question, streak: int = 0) -> str:
    """Render the question panel. Full width, left-accent bar, Everforest."""
    width = _box_width()
    inner = width - 4  # accounting for "| " and " |"
    bar = HZ * (width - 2)
    border_color = DARK_ASH
    accent = TEAL

    out: list[str] = [""]  # blank line above

    # Top border with tight label
    title = " think about this "
    title_vis = len(title)
    side_left = 2
    side_right = width - 2 - side_left - title_vis
    top = (
        paint(TL, border_color)
        + paint(HZ * side_left, border_color)
        + paint(title, accent, BOLD)
        + paint(HZ * side_right, border_color)
        + paint(TR, border_color)
    )
    out.append(_indent() + top)

    # Small streak/xp hint row if the streak is meaningful
    if streak > 0:
        hint = paint(f"day {streak} streak", GOLD, DIM)
        out.append(_row(hint, inner, border_color, left_accent=accent))
        out.append(_indent() + paint(LT + HZ * (width - 2) + RT, border_color, DIM))

    # Spacer
    out.append(_row("", inner, border_color, left_accent=accent))

    # Question prompt
    prompt_lines = _wrap_text(q.prompt, inner - 2)
    for pl in prompt_lines:
        styled = paint(pl, INK, BOLD)
        out.append(_row(styled, inner, border_color, left_accent=accent))

    # Optional code snippet
    if q.code:
        out.append(_row("", inner, border_color, left_accent=accent))
        for code_line in q.code.split("\n"):
            # Pad code to a consistent column, render in teal
            truncated = code_line[: inner - 4]
            styled = paint("  " + truncated, TEAL)
            out.append(_row(styled, inner, border_color, left_accent=accent))

    out.append(_row("", inner, border_color, left_accent=accent))

    # Options grid
    for row in _render_options_grid(q, inner, answered_label=None):
        out.append(_row(row, inner, border_color, left_accent=accent))

    # Spacer
    out.append(_row("", inner, border_color, left_accent=accent))

    # Footer: answer options + escape hatches
    footer = (
        paint("press ", ASH, DIM)
        + paint("1 2 3 4", SAGE, BOLD)
        + paint(" to answer  ", ASH, DIM)
        + paint("\u00b7", DARK_ASH, DIM)
        + paint("  ", ASH, DIM)
        + paint("x", SAGE)
        + paint(" skip  ", ASH, DIM)
        + paint("\u00b7", DARK_ASH, DIM)
        + paint("  ", ASH, DIM)
        + paint("X", SAGE)
        + paint(" mute session", ASH, DIM)
    )
    out.append(_row(footer, inner, border_color, left_accent=accent))

    # Bottom border
    out.append(_indent() + paint(BL + bar + BR, border_color))
    out.append("")

    return "\n".join(out) + "\n"


def render_answer_reveal(q: Question, chosen: str | None, xp_earned: int) -> str:
    """Render the answer reveal. Full width, colored border by result."""
    width = _box_width()
    inner = width - 4
    bar = HZ * (width - 2)

    if chosen is None:
        border_color = GOLD
        title_text = " skipped "
        title_color = ASH
        accent = GOLD
    elif chosen == q.correct_label:
        border_color = SAGE
        title_text = " exactly right "
        title_color = SAGE
        accent = SAGE
    else:
        border_color = GOLD
        title_text = " good to know "
        title_color = GOLD
        accent = GOLD

    out: list[str] = [""]

    # Top border
    title_vis = len(title_text)
    side_left = 2
    side_right = width - 2 - side_left - title_vis
    top = (
        paint(TL, border_color)
        + paint(HZ * side_left, border_color)
        + paint(title_text, title_color, BOLD)
        + paint(HZ * side_right, border_color)
        + paint(TR, border_color)
    )
    out.append(_indent() + top)

    out.append(_row("", inner, border_color, left_accent=accent))

    # Show the code again on reveal so the reader can re-check
    if q.code:
        for code_line in q.code.split("\n"):
            truncated = code_line[: inner - 4]
            out.append(_row(paint("  " + truncated, TEAL, DIM), inner, border_color, left_accent=accent))
        out.append(_row("", inner, border_color, left_accent=accent))

    # Options with reveal marks
    for row in _render_options_grid(q, inner, answered_label=chosen or ""):
        out.append(_row(row, inner, border_color, left_accent=accent))

    out.append(_row("", inner, border_color, left_accent=accent))

    # Explanation
    expl_lines = _wrap_text(q.explanation, inner - 2)
    for el in expl_lines:
        out.append(_row(paint(el, STONE), inner, border_color, left_accent=accent))

    out.append(_row("", inner, border_color, left_accent=accent))

    # Footer: XP or context message
    if chosen is None:
        footer = paint("noted -- you'll see it again", ASH, DIM)
    elif chosen == q.correct_label:
        footer = paint(f"+{xp_earned} xp", VIOLET, BOLD)
    else:
        footer = paint("we'll surface this again soon", STONE, DIM)
    out.append(_row(footer, inner, border_color, left_accent=accent))

    # Bottom
    out.append(_indent() + paint(BL + bar + BR, border_color))
    out.append("")

    return "\n".join(out) + "\n"
