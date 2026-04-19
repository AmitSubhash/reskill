"""`reskill gen` -- generate + serve an LLM-made question from a real diff.

When the template bank feels generic, this is the escape hatch:
point it at a specific commit (or the most recent one) and it asks
Claude to write a quiz grounded in that exact code. Cached so the
same commit never re-queries.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty

from . import state as state_mod
from .git_diffs import fetch_commits, project_root
from .inline_box import render_correct_flash, render_question, render_wrong_reveal
from .llm_gen import generate_from_commit
from .palette import ASH, BOLD, DARK_ASH, DIM, GOLD, SAGE, TEAL, paint


def _set_cbreak() -> list[int]:
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    return saved  # type: ignore[return-value]


def _restore(saved: list[int]) -> None:
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, saved)  # type: ignore[arg-type]


def _read_key(timeout: float) -> bytes | None:
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return None
    try:
        return os.read(sys.stdin.fileno(), 8)
    except OSError:
        return None


def run(commit: str | None = None, timeout_seconds: float = 45.0) -> int:
    """Generate one question from a specific commit (or latest) + run it.

    Parameters
    ----------
    commit : str or None
        Git ref. If None, use the most recent commit in the cwd.
    timeout_seconds : float
        How long to wait for the user to answer.
    """
    root = project_root()
    if not root:
        print(paint("  not a git repo -- nothing to generate from", ASH))
        return 1

    if commit is None:
        recent = fetch_commits("14d", cwd=root, limit=1)
        if not recent:
            print(paint("  no commits in the last 14 days", ASH))
            return 2
        commit = recent[0].sha

    print()
    print(
        paint("  reSkill", TEAL, BOLD)
        + paint("  generating from commit ", ASH, DIM)
        + paint(commit[:8], TEAL)
    )
    print(paint("  asking claude -- this can take a few seconds...", ASH, DIM))
    print()

    result = generate_from_commit(commit, cwd=root, timeout_seconds=timeout_seconds)
    if result.question is None:
        print(paint(f"  generation failed: {result.error}", ASH))
        if result.raw:
            print(paint(f"  raw response: {result.raw[:200]}", DARK_ASH, DIM))
        return 3

    state = state_mod.load()
    q = result.question

    sys.stdout.write(render_question(q, streak=state.streak))
    sys.stdout.write("\n  " + paint(
        "1-4 answer  \u00b7  x skip  \u00b7  q quit", ASH, DIM,
    ) + "\n")
    sys.stdout.flush()

    saved_tty = None
    if sys.stdin.isatty():
        saved_tty = _set_cbreak()

    try:
        shown_at = time.time()
        deadline = shown_at + timeout_seconds
        label: str | None = None
        while time.time() < deadline:
            key = _read_key(timeout=0.25)
            if key is None:
                continue
            ch = key[:1]
            if ch in (b"1", b"2", b"3", b"4"):
                label = ch.decode()
                break
            if ch in (b"x", b"\x1b", b"q"):
                break

        answer_time = time.time() - shown_at

        if label is None:
            state_mod.record_skip(state, q.concept)
            state_mod.save(state)
            sys.stdout.write(render_wrong_reveal(q, chosen=None))
            return 0

        correct = label == q.correct_label
        xp = state_mod.record_answer(state, q.id, q.concept, correct)
        state_mod.save(state)

        if correct:
            sys.stdout.write(
                render_correct_flash(
                    q, streak=state.streak, combo=state.combo, xp_earned=xp,
                )
            )
        else:
            sys.stdout.write(render_wrong_reveal(q, chosen=label))
            if answer_time < 5.0:
                sys.stdout.write(
                    "  " + paint("\u25c9 sticky one", GOLD, BOLD)
                    + paint(" - high-confidence miss", ASH, DIM) + "\n"
                )
        return 0
    finally:
        if saved_tty is not None:
            _restore(saved_tty)
