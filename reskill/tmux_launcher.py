"""`reskill claude` -- tmux split-pane launcher.

Why this, and not a PTY wrap:
    Earlier revisions PTY-wrapped `claude` and tried to overlay the quiz
    panel in the same terminal using a DECSTBM scroll region. That cannot
    work with Claude Code, because its renderer (Ink/React) repaints
    absolute rows via `CUU + EL` (cursor-up + erase-in-line) and
    periodically issues `\\x1b[2J\\x1b[3J\\x1b[H` (full clear + scrollback
    wipe). DECSTBM only constrains newline-driven scrolling; neither of
    those sequences are bounded. There is no public Ink API to reserve
    rows (Ink issues #263, #182, #442, #78 all rejected or unresolved).

    The only robust pattern is to give the quiz its own PTY. Tmux hands
    us two for free: pane 0 runs `claude`, pane 1 runs our quiz panel.
    No escape-sequence collision is possible because the two panes have
    independent terminal emulations.

Inspired by sokojh/claude-code-tmux-hud.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid

from .palette import ASH, BOLD, DARK_ASH, DIM, SAGE, TEAL, paint


DEFAULT_PANEL_COLS = 52


def _have_tmux() -> bool:
    return shutil.which("tmux") is not None


def _have_claude() -> bool:
    return shutil.which("claude") is not None


def _inside_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def _print_install_hint() -> None:
    print(paint("  tmux is required for `reskill claude`", ASH))
    print(paint("  install it once:", ASH, DIM))
    print(paint("    brew install tmux", TEAL))
    print(paint("  or use the git-log deck which works anywhere:", ASH, DIM))
    print(paint("    reskill session", TEAL))


def launch(claude_args: list[str]) -> int:
    """Spawn `claude` in a tmux split with a reskill quiz pane alongside.

    Parameters
    ----------
    claude_args : list[str]
        Arguments forwarded to the `claude` CLI.

    Returns
    -------
    int
        Exit code of `tmux attach` (0 = clean exit).
    """
    if not _have_claude():
        print(paint("  `claude` not found on PATH", ASH))
        print(paint("  install Claude Code first:", ASH, DIM))
        print(paint("    https://docs.claude.com/en/docs/claude-code/overview", TEAL))
        return 127

    if not _have_tmux():
        _print_install_hint()
        return 127

    session = f"reskill-{uuid.uuid4().hex[:8]}"
    panel_cols = _panel_cols_from_term()

    quoted_args = " ".join(_shell_quote(a) for a in claude_args)
    claude_cmd = f"claude {quoted_args}".rstrip()

    # Use -lc so the login shell finds reskill on PATH.
    panel_cmd = "reskill quiz-panel"

    try:
        if _inside_tmux():
            # Already in tmux: split the current window rather than nest.
            subprocess.run(
                [
                    "tmux", "split-window", "-h", "-l", str(panel_cols), "-d",
                    panel_cmd,
                ],
                check=True,
            )
            # Claude runs in the current pane; replace this shell with it.
            os.execvp("claude", ["claude", *claude_args])

        # Fresh nested session path.
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, claude_cmd],
            check=True,
        )
        subprocess.run(
            [
                "tmux", "split-window", "-h", "-l", str(panel_cols),
                "-t", f"{session}:0.0", panel_cmd,
            ],
            check=True,
        )
        subprocess.run(
            ["tmux", "select-pane", "-t", f"{session}:0.0"],
            check=True,
        )
        # Attach; user exits by exiting claude.
        result = subprocess.run(["tmux", "attach", "-t", session])
        return result.returncode
    except subprocess.CalledProcessError as exc:
        print(paint(f"  tmux failed: {exc}", ASH))
        return 1
    except FileNotFoundError:
        _print_install_hint()
        return 127


def _panel_cols_from_term() -> int:
    """Pick a quiz pane width proportional to the terminal."""
    try:
        cols = shutil.get_terminal_size().columns
    except OSError:
        cols = 160
    if cols < 120:
        return max(38, cols // 3)
    if cols < 180:
        return DEFAULT_PANEL_COLS
    return 60


def _shell_quote(arg: str) -> str:
    """Quote a shell argument conservatively."""
    safe = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_./=:"
    )
    if arg and all(ch in safe for ch in arg):
        return arg
    escaped = arg.replace("'", "'\"'\"'")
    return f"'{escaped}'"


def ensure_banner() -> None:
    """Print a one-line 'reSkill is live' banner before attaching.

    Useful when a user runs `reskill claude` directly and wants a visible
    signal that our wrapper is in play.
    """
    print()
    print(
        paint("  reSkill", TEAL, BOLD),
        paint("launching claude with a quiz pane alongside", ASH),
    )
    print(
        paint(
            "  exit claude (Ctrl+C or /exit) to leave the session",
            DARK_ASH,
            DIM,
        )
    )
    print()
