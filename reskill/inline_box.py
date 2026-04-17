"""Inline quiz box that renders in the flow of terminal output.

Approach: we write the question to the terminal AS PART of the output stream.
Because we're in a PTY wrapper, we can choose when to inject our content.
The box is centered horizontally, appears between Claude's output chunks.
"""

from __future__ import annotations

import shutil
import sys

from .palette import (
    BOLD, DIM, RESET,
    INK, STONE, ASH, DARK_ASH, SAGE, TEAL, GOLD, VIOLET, ROSE,
    paint,
)
from .panel import visible_len
from .question import Question


# Box drawing characters
TL, TR, BL, BR = "\u256d", "\u256e", "\u2570", "\u256f"
HZ, VT = "\u2500", "\u2502"
LT, RT = "\u251c", "\u2524"

BOX_WIDTH = 60  # Fixed width that centers nicely in most terminals


def _term_width() -> int:
    try:
        return shutil.get_terminal_size().columns
    except OSError:
        return 80


def _center_indent(width: int) -> str:
    """Left padding to center a box of given width in the terminal."""
    term_w = _term_width()
    pad = max(0, (term_w - width) // 2)
    return " " * pad


def _pad_to(line: str, width: int) -> str:
    """Pad visible text to width with trailing spaces."""
    vl = visible_len(line)
    if vl >= width:
        return line
    return line + " " * (width - vl)


def render_question(q: Question, streak: int = 0) -> str:
    """Render a question as a centered inline box. Returns the full string to print.

    Includes a blank line above and below for visual separation.
    """
    indent = _center_indent(BOX_WIDTH)
    inner = BOX_WIDTH - 4  # account for "| " and " |"

    bar = HZ * (BOX_WIDTH - 2)

    lines: list[str] = []
    lines.append("")  # blank line above

    # Top border with label
    label = paint(" think about this ", TEAL, BOLD)
    label_visible = visible_len(label)
    side = (BOX_WIDTH - 2 - label_visible) // 2
    top = (
        paint(TL, DARK_ASH)
        + paint(HZ * side, DARK_ASH)
        + label
        + paint(HZ * (BOX_WIDTH - 2 - side - label_visible), DARK_ASH)
        + paint(TR, DARK_ASH)
    )
    lines.append(indent + top)

    # Optional streak/xp subtitle
    if streak > 0:
        subtitle = paint(f"day {streak} streak", GOLD, DIM)
        sub_pad = (inner - visible_len(subtitle)) // 2
        sub_line = (
            paint(VT, DARK_ASH)
            + " "
            + " " * sub_pad
            + subtitle
            + " " * (inner - sub_pad - visible_len(subtitle))
            + " "
            + paint(VT, DARK_ASH)
        )
        lines.append(indent + sub_line)
        # Divider
        lines.append(indent + paint(LT + HZ * (BOX_WIDTH - 2) + RT, DARK_ASH, DIM))

    # Spacer
    lines.append(indent + paint(VT, DARK_ASH) + " " * (BOX_WIDTH - 2) + paint(VT, DARK_ASH))

    # Question prompt -- wrap if needed
    prompt_lines = _wrap_text(q.prompt, inner - 2)
    for pline in prompt_lines:
        colored = paint(pline, INK, BOLD)
        padded = _pad_to(colored, inner)
        lines.append(
            indent + paint(VT, DARK_ASH) + "  " + padded + paint(VT, DARK_ASH)
        )

    # Spacer
    lines.append(indent + paint(VT, DARK_ASH) + " " * (BOX_WIDTH - 2) + paint(VT, DARK_ASH))

    # Options
    for opt in q.options:
        label_txt = paint(f"  {opt.label}) ", SAGE, BOLD)
        opt_text = paint(opt.text, INK)
        line = label_txt + opt_text
        padded = _pad_to(line, inner)
        lines.append(
            indent + paint(VT, DARK_ASH) + " " + padded + " " + paint(VT, DARK_ASH)
        )

    # Spacer
    lines.append(indent + paint(VT, DARK_ASH) + " " * (BOX_WIDTH - 2) + paint(VT, DARK_ASH))

    # Footer: press 1-4
    footer = paint("press 1-4 to answer  ", ASH, DIM) + paint("esc to skip", ASH, DIM)
    footer_pad = (inner - visible_len(footer)) // 2
    footer_line = (
        " " * footer_pad + footer + " " * (inner - footer_pad - visible_len(footer))
    )
    lines.append(
        indent + paint(VT, DARK_ASH) + " " + footer_line + " " + paint(VT, DARK_ASH)
    )

    # Bottom border
    lines.append(indent + paint(BL + bar + BR, DARK_ASH))
    lines.append("")  # blank line below

    return "\n".join(lines) + "\n"


def render_answer_reveal(q: Question, chosen: str | None, xp_earned: int) -> str:
    """Render the answer reveal, same width as the question box."""
    correct = chosen == q.correct_label if chosen else False
    indent = _center_indent(BOX_WIDTH)
    inner = BOX_WIDTH - 4

    border_color = SAGE if correct else GOLD
    bar = HZ * (BOX_WIDTH - 2)

    lines: list[str] = []
    lines.append("")

    # Top with title
    if chosen is None:
        title = paint(" answer ", ASH, BOLD)
    elif correct:
        title = paint(" exactly right ", SAGE, BOLD)
    else:
        title = paint(" good to know ", GOLD, BOLD)

    title_vis = visible_len(title)
    side = (BOX_WIDTH - 2 - title_vis) // 2
    top = (
        paint(TL + HZ * side, border_color)
        + title
        + paint(HZ * (BOX_WIDTH - 2 - side - title_vis) + TR, border_color)
    )
    lines.append(indent + top)

    # Spacer
    lines.append(indent + paint(VT, border_color) + " " * (BOX_WIDTH - 2) + paint(VT, border_color))

    # Show each option with marker
    for opt in q.options:
        if opt.correct:
            marker = paint(" \u2713", SAGE, BOLD)
            text_color = SAGE
            label_bold = True
        elif chosen == opt.label and not opt.correct:
            marker = paint(" \u2717", ROSE)
            text_color = ROSE
            label_bold = False
        else:
            marker = "  "
            text_color = ASH
            label_bold = False

        label_styled = paint(
            f"  {opt.label}) ",
            SAGE if opt.correct else (ROSE if chosen == opt.label else ASH),
            BOLD if label_bold else "",
        )
        opt_text = paint(opt.text, text_color)
        line = label_styled + opt_text + marker
        padded = _pad_to(line, inner)
        lines.append(
            indent + paint(VT, border_color) + " " + padded + " " + paint(VT, border_color)
        )

    # Spacer
    lines.append(indent + paint(VT, border_color) + " " * (BOX_WIDTH - 2) + paint(VT, border_color))

    # Explanation, wrapped
    expl_lines = _wrap_text(q.explanation, inner - 2)
    for line in expl_lines:
        colored = paint(line, STONE)
        padded = _pad_to(colored, inner)
        lines.append(
            indent + paint(VT, border_color) + "  " + padded + paint(VT, border_color)
        )

    # Spacer
    lines.append(indent + paint(VT, border_color) + " " * (BOX_WIDTH - 2) + paint(VT, border_color))

    # Footer: xp
    if chosen is None:
        footer = paint("skipped -- noted for later", ASH, DIM)
    elif correct:
        footer = paint(f"+{xp_earned} xp", VIOLET, BOLD)
    else:
        footer = paint("you'll see this again soon", STONE, DIM)
    footer_pad = (inner - visible_len(footer)) // 2
    footer_line = (
        " " * footer_pad + footer + " " * (inner - footer_pad - visible_len(footer))
    )
    lines.append(
        indent + paint(VT, border_color) + " " + footer_line + " " + paint(VT, border_color)
    )

    # Bottom
    lines.append(indent + paint(BL + bar + BR, border_color))
    lines.append("")

    return "\n".join(lines) + "\n"


def _wrap_text(text: str, width: int) -> list[str]:
    """Simple word-wrap, respecting paragraph breaks."""
    result: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            result.append("")
            continue
        words = para.split()
        line = ""
        for word in words:
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                result.append(line)
                line = word
        if line:
            result.append(line)
    return result
