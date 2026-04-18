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
import uuid

from .palette import ASH, BOLD, DARK_ASH, DIM, TEAL, paint


DEFAULT_PANEL_COLS = 52


def _have_tmux() -> bool:
    return shutil.which("tmux") is not None


def _have_claude() -> bool:
    return shutil.which("claude") is not None


def _inside_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def _print_install_hint() -> None:
    print(paint("  tmux is required for `reskill claude --tmux`", ASH))
    print(paint("  either install tmux (`brew install tmux`) or", ASH, DIM))
    print(paint("  just open a second terminal and run:", ASH, DIM))
    print(paint("    reskill quiz-panel", TEAL))


def _macos_spawn_quiz_window() -> bool:
    """Open a second terminal WINDOW running `reskill quiz-panel`.

    No tmux, no split-pane. The user's current terminal keeps running
    whatever they like (usually `claude`), and the quiz pane lives in
    its own window. Both processes coordinate via the thinking-flag file.

    Returns True if a window was spawned, False if we couldn't figure
    out how.
    """
    import platform

    if platform.system() != "Darwin":
        return False

    term = os.environ.get("TERM_PROGRAM", "")
    reskill_bin = shutil.which("reskill") or "reskill"

    if term == "iTerm.app":
        script = f'''
            tell application "iTerm"
                create window with default profile
                tell current session of current window
                    write text "{reskill_bin} quiz-panel"
                end tell
            end tell
        '''
    else:
        # Default to Terminal.app -- works whether the user is there or
        # running bare ssh/kitty/wezterm (osascript targets Terminal).
        script = f'''
            tell application "Terminal"
                activate
                do script "{reskill_bin} quiz-panel"
            end tell
        '''
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            timeout=5,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


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
        # No tmux? On macOS we can still give the user the split-window
        # experience by opening a second Terminal.app / iTerm2 window
        # with the quiz pane.
        if _macos_spawn_quiz_window():
            print(
                paint("  reSkill", TEAL, BOLD),
                paint("quiz pane opened in a new window", ASH),
            )
            print(paint("  starting claude here now...", ASH, DIM))
            print()
            os.execvp("claude", ["claude", *claude_args])
        _print_install_hint()
        return 127

    session = f"reskill-{uuid.uuid4().hex[:8]}"
    panel_cols = _panel_cols_from_term()

    quoted_args = " ".join(_shell_quote(a) for a in claude_args)
    # Wrap claude so that when it exits, the whole tmux session tears down.
    # Without this, the quiz pane keeps the session alive and the user
    # is left staring at an orphaned quiz after finishing their Claude
    # work -- the "return to terminal is super poor" complaint.
    claude_cmd = (
        f"claude {quoted_args}".rstrip()
        + f"; tmux kill-session -t {session}"
    )
    panel_cmd = "reskill quiz-panel"

    try:
        if _inside_tmux():
            # Already in tmux: split current window for the quiz pane.
            # Mouse mode so the user can click to focus (idempotent).
            subprocess.run(
                ["tmux", "set-option", "-g", "mouse", "on"],
                check=False,
            )
            # Heavy borders + "both" indicators make focus unmistakable
            # on tmux >= 3.3. Graceful no-op on older versions.
            subprocess.run(
                ["tmux", "set-option", "-g", "pane-border-lines", "heavy"],
                check=False,
            )
            subprocess.run(
                ["tmux", "set-option", "-g", "pane-border-indicators", "both"],
                check=False,
            )
            # `prefix + r` -> jump focus to the quiz pane. Single keybind
            # beats remembering which arrow direction.
            subprocess.run(
                [
                    "tmux", "bind-key", "r",
                    "select-pane", "-t", "{right-of}",
                ],
                check=False,
            )
            subprocess.run(
                [
                    "tmux", "split-window", "-h", "-l", str(panel_cols), "-d",
                    panel_cmd,
                ],
                check=True,
            )
            # Wrap claude so exiting kills the whole window (tears down the
            # now-orphaned quiz pane). Without this the user is left with
            # just a quiz pane after finishing their Claude work.
            wrapper = f"claude {quoted_args}; tmux kill-window"
            os.execvp("bash", ["bash", "-lc", wrapper])

        # Fresh nested session path. Use new-session with the claude command
        # so the session auto-terminates when claude exits.
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session,
             f"bash -c {_shell_quote(claude_cmd)}"],
            check=True,
        )
        # Session-local: mouse click to focus, heavy border indicators,
        # and `prefix + r` = select right-pane.
        for opt_cmd in (
            ["set-option", "-t", session, "mouse", "on"],
            ["set-option", "-t", session, "pane-border-lines", "heavy"],
            ["set-option", "-t", session, "pane-border-indicators", "both"],
            ["bind-key", "-T", "prefix", "r", "select-pane", "-t", "{right-of}"],
        ):
            subprocess.run(["tmux", *opt_cmd], check=False)
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

    Also nudges the user if the hooks aren't installed, since the quiz
    pane works better with them (it still falls back to transcript
    polling, but the hook signal is faster and cleaner).
    """
    from .activity import have_reskill_hooks

    print()
    print(
        paint("  reSkill", TEAL, BOLD),
        paint("launching claude with a quiz pane alongside", ASH),
    )
    if not have_reskill_hooks():
        print(
            paint(
                "  heads up: `reskill install` not run yet -- quiz pane "
                "will use transcript polling as a fallback signal",
                DARK_ASH,
                DIM,
            )
        )
    print(
        paint(
            "  exit claude (Ctrl+C or /exit) to leave the session",
            DARK_ASH,
            DIM,
        )
    )
    print()
