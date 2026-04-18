"""Terminal color palette with readable defaults across backgrounds.

Themes:
  - `everforest` (default): true-color palette with readable contrast
    tweaked so ASH/STONE/DARK_ASH are visible on both light AND dark
    terminals (old values were too close to middle gray).
  - `mono`: only BOLD / DIM / terminal-default foreground. Set
    `RESKILL_THEME=mono` to enable. Useful for light terminals, low-
    vision setups, or tmux configs that mangle RGB.

Also respects the standard `NO_COLOR` env var (https://no-color.org):
if it's set to anything, we fall back to mono automatically.
"""

from __future__ import annotations

import os


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _theme() -> str:
    if os.environ.get("NO_COLOR"):
        return "mono"
    return os.environ.get("RESKILL_THEME", "everforest").lower()


def rgb(r: int, g: int, b: int) -> str:
    """Foreground true-color."""
    return f"\033[38;2;{r};{g};{b}m"


def bg_rgb(r: int, g: int, b: int) -> str:
    """Background true-color."""
    return f"\033[48;2;{r};{g};{b}m"


if _theme() == "mono":
    # In mono mode, body text uses the terminal's default foreground
    # (no color escape at all) so it always matches the user's scheme.
    # Accents collapse to BOLD / DIM variations to stay legible.
    _MONO = ""
    INK      = _MONO
    STONE    = _MONO
    ASH      = DIM
    DARK_ASH = DIM
    SAGE     = BOLD            # "correct" signal via weight, not hue
    TEAL     = BOLD            # headers via bold
    ROSE     = BOLD            # "wrong" -- bold + the ✗ glyph carries the signal
    VIOLET   = BOLD
    GOLD     = BOLD
    BLUE     = BOLD
else:
    # Everforest-tuned true-color. Compared to the previous palette,
    # ASH and STONE are pulled brighter so they're readable on both
    # light terminals and dark ones. Don't drop below 160 on any
    # channel for "body dim" roles.
    INK      = rgb(211, 198, 170)   # #d3c6aa  primary text
    STONE    = rgb(186, 196, 189)   # #bac4bd  muted text (was too dark)
    ASH      = rgb(168, 181, 174)   # #a8b5ae  dim text (was too dark)
    DARK_ASH = rgb(130, 144, 137)   # #829089  borders only
    SAGE     = rgb(167, 192, 128)   # #a7c080  accent / success
    TEAL     = rgb(127, 187, 179)   # #7fbbb3  links / headers
    ROSE     = rgb(230, 126, 128)   # #e67e80  errors
    VIOLET   = rgb(214, 153, 182)   # #d699b6  highlight
    GOLD     = rgb(219, 188, 127)   # #dbbc7f  warm accent
    BLUE     = rgb(115, 174, 213)   # #73aed5  cool accent


def paint(text: str, *codes: str) -> str:
    """Wrap text in ANSI codes and reset. De-duplicates codes so mono
    mode (where multiple slots collapse to BOLD) doesn't emit redundant
    escape sequences."""
    seen: set[str] = set()
    unique: list[str] = []
    for c in codes:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    if not unique:
        return text
    return f"{''.join(unique)}{text}{RESET}"
