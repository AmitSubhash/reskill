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
    """Full-terminal-width box with small outer padding."""
    tw = _term_width()
    # Leave 2 chars of padding on each side
    return max(50, min(tw - 4, 120))


def _indent() -> str:
    """Left padding to match the box's horizontal margin."""
    return "  "


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
    """Render options. 2-column grid if they all fit; single column otherwise.

    If answered_label is None, this is the QUESTION view (plain options).
    Otherwise it's the REVEAL view (highlight correct, mark chosen-wrong).
    """
    # Decide on layout
    max_opt_len = max(len(f"  {o.label}) {o.text}") for o in q.options)
    two_col_room = (inner_width - 2) // 2  # room per column with gap
    use_grid = (max_opt_len <= two_col_room) and len(q.options) == 4

    def _render_option(opt, column_width: int) -> str:
        label = opt.label
        text = opt.text
        if answered_label is None:
            # Question view
            label_styled = paint(f"{label})", SAGE, BOLD)
            text_styled = paint(text, INK)
            marker = ""
        elif opt.correct:
            label_styled = paint(f"{label})", SAGE, BOLD)
            text_styled = paint(text, SAGE, BOLD)
            marker = paint("  \u2713", SAGE, BOLD)
        elif answered_label == label and not opt.correct:
            label_styled = paint(f"{label})", ROSE)
            text_styled = paint(text, ROSE)
            marker = paint("  \u2717", ROSE)
        else:
            label_styled = paint(f"{label})", DARK_ASH, DIM)
            text_styled = paint(text, ASH, DIM)
            marker = ""
        piece = f" {label_styled} {text_styled}{marker}"
        return _pad_to(piece, column_width)

    lines: list[str] = []
    if use_grid:
        col_w = two_col_room
        for i in range(0, len(q.options), 2):
            left = _render_option(q.options[i], col_w)
            right = _render_option(q.options[i + 1], col_w) if i + 1 < len(q.options) else ""
            lines.append(left + right)
    else:
        col_w = inner_width
        for opt in q.options:
            lines.append(_render_option(opt, col_w))
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

    # Footer
    footer = (
        paint("press ", ASH, DIM)
        + paint("1 2 3 4", SAGE, BOLD)
        + paint(" to answer  ", ASH, DIM)
        + paint("\u00b7", DARK_ASH, DIM)
        + paint("  esc to skip", ASH, DIM)
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
