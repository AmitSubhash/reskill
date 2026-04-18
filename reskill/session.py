"""`reskill session` -- walk a commit-driven quiz deck.

The killer wedge: take the last N days of git commits in this project,
detect concepts Claude (and the user) actually touched, and ask questions
from the template bank. No AI thinking time needed -- the user runs this
proactively, like Anki but automatically stocked with patterns from THEIR
recent code.
"""

from __future__ import annotations

import os
import random
import select
import sys
import termios
import time
import tty

from . import state as state_mod
from .git_diffs import CommitInfo, fetch_commits, project_root
from .inline_box import (
    render_correct_flash,
    render_question,
    render_wrong_reveal,
)
from .log_session import CACHE_ROOT, _load_cache, _project_hash
from .palette import ASH, BOLD, DARK_ASH, DIM, GOLD, SAGE, STONE, TEAL, paint
from .question import Question, detect_concepts, TEMPLATE_BANK


def _load_concept_weights(cwd: str | None) -> dict[str, int]:
    """Per-project concept tally from the Stop-hook cache.

    Returns an empty dict when nothing has been logged yet so callers
    can blindly `.get(concept, 0)`.
    """
    cache_dir = CACHE_ROOT / _project_hash(cwd)
    if not cache_dir.exists():
        return {}
    return dict(_load_cache(cache_dir).get("concepts", {}))


def _deck_from_commits(
    commits: list[CommitInfo],
    seen_ids: set[str],
    max_questions: int,
    concept_weights: dict[str, int] | None = None,
) -> list[tuple[Question, CommitInfo]]:
    """Match each commit to a relevant template question.

    When `concept_weights` is provided, concepts the user recently
    touched in Claude Code sessions are tried first per commit.
    """
    deck: list[tuple[Question, CommitInfo]] = []
    used_ids: set[str] = set(seen_ids)
    weights = concept_weights or {}

    for commit in commits:
        haystack = commit.subject + "\n" + "\n".join(commit.added_lines[:400])
        concepts = detect_concepts(haystack)
        concepts.sort(
            key=lambda c: (-weights.get(c, 0), random.random())
        )
        for concept in concepts:
            bank = TEMPLATE_BANK.get(concept, [])
            fresh = [q for q in bank if q.id not in used_ids]
            if not fresh:
                continue
            chosen = random.choice(fresh)
            deck.append((chosen, commit))
            used_ids.add(chosen.id)
            break
        if len(deck) >= max_questions:
            break

    return deck


def _set_cbreak() -> list[int]:
    """cbreak: keys read unbuffered but output newlines still become CRLF.

    Using setraw() here (as an earlier revision did) disables OPOST, which
    made every `\\n` in rendered panels render as a bare LF and staircase
    the reveal off-screen — the "stuck after skip" user complaint.
    """
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


def _wait_for_continue(max_wait: float = 8.0) -> None:
    """After a reveal, wait for any key (or auto-advance) with a visible hint.

    Without this, the user just sees the box and wonders if they're stuck.
    The cue + short max_wait eliminates the "skip feels frozen" feedback.
    """
    hint = paint(
        "  any key to continue", ASH, DIM,
    )
    sys.stdout.write("\r" + hint)
    sys.stdout.flush()
    start = time.time()
    while time.time() - start < max_wait:
        key = _read_key(timeout=0.3)
        if key is not None:
            break
    # Clear the hint line so it doesn't linger in scrollback
    sys.stdout.write("\r" + " " * (len(hint) + 10) + "\r")
    sys.stdout.flush()


def _commit_chip(commit: CommitInfo) -> str:
    """One-line 'you wrote this' chip shown above the quiz."""
    short_subject = commit.subject[:68]
    return (
        paint("  from ", ASH, DIM)
        + paint(commit.sha, TEAL, BOLD)
        + paint("  ", ASH)
        + paint(short_subject, STONE)
    )


def run_session(
    since: str = "7d",
    max_questions: int = 5,
    cwd: str | None = None,
) -> int:
    """Entry point for `reskill session`.

    Parameters
    ----------
    since : str
        Window like '7d', '24h', '2w'. Default: 7 days.
    max_questions : int
        Cap the deck; the commit-to-question mapper may yield fewer.
    cwd : str or None
        Working directory. Defaults to cwd.

    Returns
    -------
    int
        Exit code (0 = success, 1 = no git repo, 2 = no commits).
    """
    root = project_root(cwd)
    if not root:
        print(paint("  not a git repo", ASH))
        print(paint("  reskill session needs a git project", DARK_ASH, DIM))
        return 1

    print()
    print(
        paint("  reSkill", TEAL, BOLD),
        paint("session", ASH),
        paint(f"(last {since})", ASH, DIM),
    )
    print(paint("  fetching commits...", ASH, DIM))

    commits = fetch_commits(since, cwd=root)
    if not commits:
        print(paint(f"  no commits in the last {since}", ASH))
        return 2

    state = state_mod.load()
    seen = set(state.seen_questions)
    weights = _load_concept_weights(root)
    deck = _deck_from_commits(commits, seen, max_questions, concept_weights=weights)

    if not deck:
        print(paint(f"  found {len(commits)} commits but no matching templates yet.", ASH))
        print(paint("  (template bank still growing -- LLM-gen coming soon)", DARK_ASH, DIM))
        return 0

    print(
        paint(f"  {len(deck)} questions", SAGE, BOLD),
        paint(f"from {len(commits)} commits", ASH, DIM),
    )
    print()

    saved_tty = None
    if sys.stdin.isatty():
        saved_tty = _set_cbreak()

    try:
        for idx, (question, commit) in enumerate(deck, start=1):
            progress = paint(f"  {idx}/{len(deck)}", ASH, DIM)
            print(f"{progress}")
            print(_commit_chip(commit))
            sys.stdout.write(render_question(question, streak=state.streak))
            sys.stdout.flush()

            deadline = time.time() + 45.0
            label: str | None = None
            skipped = False
            while time.time() < deadline:
                key = _read_key(timeout=0.25)
                if key is None:
                    continue
                ch = key[:1]
                if ch in (b"1", b"2", b"3", b"4"):
                    label = ch.decode()
                    break
                if ch in (b"x", b"\x1b"):
                    skipped = True
                    break
                if ch == b"q":
                    return 0

            if label is not None:
                correct = label == question.correct_label
                xp = state_mod.record_answer(
                    state, question.id, question.concept, correct,
                )
                state_mod.save(state)
                if correct:
                    flash = render_correct_flash(
                        question,
                        streak=state.streak,
                        combo=state.combo,
                        xp_earned=xp,
                    )
                    sys.stdout.write(flash)
                    sys.stdout.flush()
                    time.sleep(0.9)
                else:
                    sys.stdout.write(render_wrong_reveal(question, chosen=label))
                    _wait_for_continue()
            else:
                state_mod.record_skip(state, question.concept)
                state_mod.save(state)
                if not skipped:
                    sys.stdout.write(
                        paint("  (time's up)", ASH, DIM) + "\n\n"
                    )
                sys.stdout.write(render_wrong_reveal(question, chosen=None))
                _wait_for_continue()

        state = state_mod.load()
        print()
        print(
            paint("  session complete", SAGE, BOLD),
            paint(f"· {state.correct_today}/{state.answered_today} today", ASH),
            paint(f"· day {state.streak} streak", GOLD, DIM),
        )
        print()
        return 0

    finally:
        if saved_tty is not None:
            _restore(saved_tty)
