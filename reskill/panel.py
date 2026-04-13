"""Feynman-style panel rendering with box-drawing characters."""

import re
import shutil

from .palette import BOLD, DIM, DARK_ASH, TEAL, ASH, paint

# Box-drawing characters
TL = "\u256d"  # ╭
TR = "\u256e"  # ╮
BL = "\u2570"  # ╰
BR = "\u256f"  # ╯
HZ = "\u2500"  # ─
VT = "\u2502"  # │
LT = "\u251c"  # ├
RT = "\u2524"  # ┤

TERM_W = min(shutil.get_terminal_size().columns, 90)

_ANSI_RE = re.compile(r'\033\[[0-9;]*m')


def visible_len(text: str) -> int:
    """Length of text after stripping ANSI escape codes."""
    return len(_ANSI_RE.sub('', text))


def render_panel(
    title: str,
    lines: list[str],
    *,
    width: int | None = None,
    border_color: str = DARK_ASH,
    title_color: str = TEAL,
    centered: bool = False,
    subtitle: str = "",
) -> list[str]:
    """Render a bordered panel. Returns list of printable strings."""
    w = width or TERM_W
    inner = w - 4  # VT + space + content + space + VT

    out: list[str] = []
    b = border_color
    bar = HZ * (inner + 2)

    # top
    out.append(paint(f"  {TL}{bar}{TR}", b, BOLD))

    # title row
    t_content = paint(title, title_color, BOLD)
    t_pad = max(0, inner - visible_len(title))
    vt_l = paint(f"  {VT} ", b, BOLD)
    vt_r = paint(f" {VT}", b, BOLD)
    out.append(f"{vt_l}{t_content}{' ' * t_pad}{vt_r}")

    # subtitle row
    if subtitle:
        s_content = paint(subtitle, ASH)
        s_pad = max(0, inner - visible_len(subtitle))
        out.append(f"{vt_l}{s_content}{' ' * s_pad}{vt_r}")

    # divider
    if lines:
        out.append(paint(f"  {LT}{bar}{RT}", b, DIM))

    # content
    for line in lines:
        vl = visible_len(line)
        if centered:
            pad_l = max(0, (inner - vl) // 2)
            pad_r = max(0, inner - vl - pad_l)
        else:
            pad_l = 0
            pad_r = max(0, inner - vl)
        out.append(f"{vt_l}{' ' * pad_l}{line}{' ' * pad_r}{vt_r}")

    # bottom
    out.append(paint(f"  {BL}{bar}{BR}", b, BOLD))
    return out
