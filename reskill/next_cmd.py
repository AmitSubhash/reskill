"""`reskill next` -- serve one context-matched question right now.

For when you want a single quick question outside the live-wrap or
session deck: e.g. waiting for CI, stuck on a problem, or just
wanting a 30-second warmup. Uses the same scheduler as everything
else (SM-2 + interleaving + 85% rule + format mix), so the
question reflects current context.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty

from . import scheduler
from . import state as state_mod
from .activity import recent_transcript_text
from .git_diffs import fetch_commits, project_root
from .inline_box import render_correct_flash, render_question, render_wrong_reveal
from .palette import ASH, BOLD, DARK_ASH, DIM, GOLD, TEAL, paint


def _set_cbreak() -> list[int]:
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    return saved  # type: ignore[return-value]


def _restore(saved: list[int]) -> None:
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, saved)  # type: ignore[arg-type]


def _read_key(timeout: float | None = None) -> bytes | None:
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return None
    try:
        return os.read(sys.stdin.fileno(), 8)
    except OSError:
        return None


def run(timeout_seconds: float = 45.0) -> int:
    """Show one question, wait for an answer, reveal, exit.

    Parameters
    ----------
    timeout_seconds : float
        How long to wait for an answer before auto-skipping.

    Returns
    -------
    int
        Exit code: 0 normal, 1 no question available.
    """
    state = state_mod.load()
    project = project_root()
    live_text = recent_transcript_text(cwd=os.getcwd() or project)
    commit_text = ""
    if project:
        commits = fetch_commits("7d", cwd=project, limit=10)
        commit_text = "\n".join(
            c.subject + "\n" + "\n".join(c.added_lines[:60]) for c in commits
        )
    pick = scheduler.choose(
        live_text=live_text or "",
        commit_text=commit_text,
        state=state,
        seen_ids=set(state.seen_questions),
    )
    if pick is None:
        print(paint("  no question available right now", ASH))
        print(paint("  template bank may be exhausted -- add more or wait", DARK_ASH, DIM))
        return 1

    print()
    print(
        paint("  reSkill", TEAL, BOLD)
        + paint("  one question", ASH, DIM)
        + paint(f"  \u00b7  {pick.concept}", ASH, DIM)
    )
    print()
    sys.stdout.write(render_question(pick.question, streak=state.streak))
    sys.stdout.write("\n  " + paint("1-4 answer  \u00b7  x skip  \u00b7  q quit", ASH, DIM) + "\n")
    sys.stdout.flush()

    saved_tty = None
    if sys.stdin.isatty():
        saved_tty = _set_cbreak()

    try:
        deadline = time.time() + timeout_seconds
        shown_at = time.time()
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
            print(paint("  (skipped)", ASH, DIM))
            state_mod.record_skip(state, pick.question.concept)
            state_mod.save(state)
            sys.stdout.write(render_wrong_reveal(pick.question, chosen=None))
            return 0

        correct = label == pick.question.correct_label
        xp = state_mod.record_answer(
            state, pick.question.id, pick.question.concept, correct,
        )
        state_mod.save(state)

        if correct:
            sys.stdout.write(
                render_correct_flash(
                    pick.question,
                    streak=state.streak,
                    combo=state.combo,
                    xp_earned=xp,
                )
            )
        else:
            sys.stdout.write(render_wrong_reveal(pick.question, chosen=label))
            if answer_time < 5.0:
                sys.stdout.write(
                    "  " + paint("\u25c9 sticky one", GOLD, BOLD)
                    + paint(" - high-confidence miss", ASH, DIM) + "\n"
                )
        return 0
    finally:
        if saved_tty is not None:
            _restore(saved_tty)
