"""Scroll-region overlay for rendering a pinned panel at the bottom of the
terminal while content continues to scroll above.

Based on the fzf `--height` technique: use DECSTBM (`\\x1b[r`) to reserve
the bottom N lines, draw our panel there with absolute cursor positioning,
let the main application keep writing above.

Key caveats:
  - DECSTBM only bounds SCROLLING operations (LF, RI). Cursor-positioning
    escapes (CUP `\\x1b[H`) are NOT bounded. If Claude Code's Ink uses
    absolute positioning to jump into our panel rows, it will clobber.
    Mitigation: we save + restore cursor around our panel writes and hope
    Ink uses relative positioning (which it mostly does).
  - Terminal must support DECSTBM. Every serious terminal emulator does.
"""

from __future__ import annotations

import re
import shutil
import sys

# Control sequences
SAVE_CURSOR_DEC = b"\x1b7"
RESTORE_CURSOR_DEC = b"\x1b8"
RESET_REGION = b"\x1b[r"
CLEAR_LINE = b"\x1b[2K"
CLEAR_BELOW = b"\x1b[J"
CURSOR_HIDE = b"\x1b[?25l"
CURSOR_SHOW = b"\x1b[?25h"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


def term_size() -> tuple[int, int]:
    """Returns (rows, cols). Safe on non-tty."""
    try:
        s = shutil.get_terminal_size()
        return s.lines, s.columns
    except OSError:
        return 24, 80


def set_region(top: int, bottom: int) -> bytes:
    """DECSTBM: set scroll region to rows [top..bottom] (1-indexed, inclusive)."""
    return f"\x1b[{top};{bottom}r".encode()


def goto(row: int, col: int = 1) -> bytes:
    """Absolute cursor positioning (1-indexed)."""
    return f"\x1b[{row};{col}H".encode()


class Region:
    """Manages a pinned bottom region for rendering a panel.

    Usage:
        region = Region(height=10)
        region.activate(stdout_fd)
        try:
            # other process can keep writing to stdout; it scrolls above
            region.draw(panel_lines, stdout_fd)
        finally:
            region.deactivate(stdout_fd)
    """

    def __init__(self, height: int) -> None:
        self.height = max(3, height)
        self.rows: int = 0
        self.cols: int = 0
        self.main_bottom: int = 0
        self.panel_top: int = 0
        self.active: bool = False

    def _recompute(self) -> None:
        self.rows, self.cols = term_size()
        self.main_bottom = max(3, self.rows - self.height)
        self.panel_top = self.main_bottom + 1

    def activate(self, fd: int) -> None:
        """Enter region mode. Makes room for the panel, sets scroll region,
        positions cursor in the main area so subsequent prints scroll it."""
        self._recompute()
        # Force blank lines to push current content up, making panel space.
        payload = b"\n" * self.height
        # Set scroll region to exclude the panel area.
        payload += set_region(1, self.main_bottom)
        # Position cursor at the bottom of the main area so prints start there.
        payload += goto(self.main_bottom, 1)
        payload += CURSOR_HIDE
        import os
        os.write(fd, payload)
        self.active = True

    def deactivate(self, fd: int) -> None:
        """Exit region mode: reset scroll region, clear the panel area."""
        if not self.active:
            return
        import os
        # Reset scroll region to full screen.
        payload = RESET_REGION
        # Clear the panel area.
        payload += goto(self.panel_top, 1)
        payload += CLEAR_BELOW
        payload += CURSOR_SHOW
        os.write(fd, payload)
        self.active = False

    def draw(self, lines: list[str], fd: int) -> None:
        """Render `lines` in the panel area. Lines are truncated to fit and
        padded if needed. Cursor position in main area is preserved."""
        import os
        if not self.active:
            return

        # Save cursor, hide, render, restore
        out = bytearray()
        out.extend(SAVE_CURSOR_DEC)

        visible_lines: list[str] = lines[: self.height]
        while len(visible_lines) < self.height:
            visible_lines.append("")

        for i, line in enumerate(visible_lines):
            row = self.panel_top + i
            out.extend(goto(row, 1))
            out.extend(CLEAR_LINE)
            out.extend(line.encode("utf-8", errors="replace"))

        out.extend(RESTORE_CURSOR_DEC)
        os.write(fd, bytes(out))

    def handle_resize(self, fd: int) -> None:
        """Recompute on terminal resize; redraws must be triggered by caller."""
        if not self.active:
            return
        self._recompute()
        import os
        os.write(fd, set_region(1, self.main_bottom))


if __name__ == "__main__":
    # Smoke demo
    import time
    r = Region(height=8)
    r.activate(sys.stdout.fileno())
    try:
        for i in range(10):
            print(f"main-region line {i}")
            panel = [
                "─" * 60,
                f"  PANEL tick {i}  (pinned at bottom)",
                "  content above scrolls naturally",
                "",
                "  press Ctrl+C to exit early",
                "",
                "─" * 60,
                "",
            ]
            r.draw(panel, sys.stdout.fileno())
            time.sleep(0.5)
    finally:
        r.deactivate(sys.stdout.fileno())
    print("done.")
