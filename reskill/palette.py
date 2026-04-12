"""Feynman Everforest-inspired true-color palette for terminal rendering."""

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def rgb(r: int, g: int, b: int) -> str:
    """Foreground true-color."""
    return f"\033[38;2;{r};{g};{b}m"


def bg_rgb(r: int, g: int, b: int) -> str:
    """Background true-color."""
    return f"\033[48;2;{r};{g};{b}m"


# ── Everforest Dark palette ──────────────────────────────────
INK      = rgb(211, 198, 170)   # #d3c6aa  primary text
STONE    = rgb(157, 169, 160)   # #9da9a0  muted text
ASH      = rgb(133, 146, 137)   # #859289  dim text
DARK_ASH = rgb(92, 106, 114)    # #5c6a72  borders
SAGE     = rgb(167, 192, 128)   # #a7c080  accent / success
TEAL     = rgb(127, 187, 179)   # #7fbbb3  links / headers
ROSE     = rgb(230, 126, 128)   # #e67e80  errors
VIOLET   = rgb(214, 153, 182)   # #d699b6  highlight
GOLD     = rgb(219, 188, 127)   # #dbbc7f  warm accent
BLUE     = rgb(115, 174, 213)   # #73aed5  cool accent


def paint(text: str, *codes: str) -> str:
    """Wrap text in ANSI codes and reset."""
    return f"{''.join(codes)}{text}{RESET}"
