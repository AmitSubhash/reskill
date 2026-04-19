"""Terminal color palette with readable defaults across backgrounds.

Themes:
  - `everforest` (default on truecolor terminals): readable contrast
    tuned so ASH/STONE/DARK_ASH remain visible on both light and dark
    backgrounds.
  - `mono`: only BOLD / DIM / terminal-default foreground. Auto-selected
    when COLORTERM isn't `truecolor`/`24bit` (Apple Terminal.app, many
    ssh contexts, tmux without RGB passthrough), since the everforest
    24-bit values collapse to an unreadable gray on 256-color terminals.
    Also set manually via `RESKILL_THEME=mono`.

Also respects the standard `NO_COLOR` env var (https://no-color.org):
if it's set to anything, we fall back to mono automatically.
"""

from __future__ import annotations

import os

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def _supports_truecolor() -> bool:
    """Does this terminal render 24-bit color?

    We trust COLORTERM when set ("truecolor" / "24bit" are the two
    values in the wild). When it's absent, be conservative and answer
    no -- Apple Terminal.app, mosh, and many SSH jumphosts don't set
    it, and our Everforest values collapse to a near-invisible gray
    on 256-color terminals.
    """
    colorterm = (os.environ.get("COLORTERM") or "").lower()
    return colorterm in ("truecolor", "24bit")


def _theme() -> str:
    explicit = os.environ.get("RESKILL_THEME")
    if explicit:
        return explicit.lower()
    if os.environ.get("NO_COLOR"):
        return "mono"
    if not _supports_truecolor():
        return "mono"
    return "everforest"


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
    # Everforest-tuned true-color. ASH and STONE are pulled brighter
    # still than v2 -- the user couldn't see the ~a8 gray on common
    # backgrounds. New floor is #c8 (200) for "dim body" roles so
    # readability wins across terminal themes.
    INK      = rgb(211, 198, 170)   # #d3c6aa  primary text
    STONE    = rgb(208, 215, 208)   # #d0d7d0  muted text (bright)
    ASH      = rgb(196, 204, 198)   # #c4ccc6  dim text (bright)
    DARK_ASH = rgb(156, 170, 164)   # #9caaa4  borders only
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
