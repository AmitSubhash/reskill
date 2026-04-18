"""`reskill review` -- drill your recently-missed questions.

The forgetting curve is steepest in the first 24 hours. If you answered
something wrong today, re-encountering it is the single highest-leverage
practice you can do (Butler & Roediger 2008 delayed-feedback studies;
Karpicke & Blunt 2011 retrieval practice is a bigger lever than any
amount of re-reading).

This command:
  - pulls state.recent_wrongs (maintained by record_answer)
  - resolves IDs back to Question objects from TEMPLATE_BANK
  - walks them one by one with the normal quiz box
  - drops from the wrong-list on correct, keeps on wrong
  - shows a summary at the end
"""

from __future__ import annotations

import os
import select
import sys
import termios
import time
import tty

from . import state as state_mod
from .inline_box import render_correct_flash, render_question, render_wrong_reveal
from .palette import ASH, BOLD, DIM, GOLD, ROSE, SAGE, TEAL, paint
from .question import Question, TEMPLATE_BANK


def _all_questions_by_id() -> dict[str, Question]:
    out: dict[str, Question] = {}
    for bank in TEMPLATE_BANK.values():
        for q in bank:
            out[q.id] = q
    return out


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


def _wait_for_continue(max_wait: float = 8.0) -> None:
    start = time.time()
    last_shown = -1
    while True:
        remaining = int(max_wait - (time.time() - start))
        if remaining <= 0:
            break
        if remaining != last_shown:
            sys.stdout.write(
                "\r\x1b[K"
                + paint(
                    f"  any key to continue  \u00b7  auto in {remaining}s",
                    ASH, DIM,
                )
            )
            sys.stdout.flush()
            last_shown = remaining
        if _read_key(timeout=0.3) is not None:
            break
    sys.stdout.write("\r\x1b[K")
    sys.stdout.flush()


def run(max_questions: int = 10) -> int:
    """Walk the user through their recent-wrongs queue.

    Parameters
    ----------
    max_questions : int
        Cap on how many to drill in one session.

    Returns
    -------
    int
        0 normal, 2 if there are no wrongs to review.
    """
    state = state_mod.load()
    wrongs = list(reversed(state.recent_wrongs))  # most-recent-first
    if not wrongs:
        print()
        print(paint("  nothing to review", SAGE, BOLD))
        print(paint("  your recent answers are all correct (or you haven't", ASH, DIM))
        print(paint("  answered many yet). try `reskill next` for fresh quizzes.", ASH, DIM))
        print()
        return 2

    by_id = _all_questions_by_id()
    queue: list[Question] = []
    for qid in wrongs:
        q = by_id.get(qid)
        if q is not None:
            queue.append(q)
        if len(queue) >= max_questions:
            break

    if not queue:
        print(paint("  no questions to review (IDs drifted)", ASH, DIM))
        return 2

    print()
    print(
        paint("  reSkill", TEAL, BOLD)
        + paint("  review", ASH)
        + paint(f"  ({len(queue)} recent misses)", ASH, DIM)
    )
    print(paint("  nail these and they drop off the list.", ASH, DIM))
    print()

    saved_tty = None
    if sys.stdin.isatty():
        saved_tty = _set_cbreak()

    correct = 0
    still_wrong = 0
    skipped = 0

    try:
        for idx, q in enumerate(queue, start=1):
            print(paint(f"  {idx}/{len(queue)}", ASH, DIM))
            sys.stdout.write(render_question(q, streak=state.streak))
            sys.stdout.write("\n  " + paint(
                "1-4 answer  \u00b7  x skip  \u00b7  q quit", ASH, DIM,
            ) + "\n")
            sys.stdout.flush()

            shown_at = time.time()
            deadline = shown_at + 45.0
            label: str | None = None
            skipped_this = False
            while time.time() < deadline:
                key = _read_key(timeout=0.3)
                if key is None:
                    continue
                ch = key[:1]
                if ch in (b"1", b"2", b"3", b"4"):
                    label = ch.decode()
                    break
                if ch in (b"x", b"\x1b"):
                    skipped_this = True
                    break
                if ch == b"q":
                    _summary(correct, still_wrong, skipped, len(queue))
                    return 0

            answer_time = time.time() - shown_at

            if label is None:
                if skipped_this:
                    skipped += 1
                    state_mod.record_skip(state, q.concept)
                    state_mod.save(state)
                    sys.stdout.write(render_wrong_reveal(q, chosen=None))
                    _wait_for_continue()
                else:
                    still_wrong += 1
                    sys.stdout.write(
                        paint("  (time's up)", ASH, DIM) + "\n\n"
                    )
                    sys.stdout.write(render_wrong_reveal(q, chosen=None))
                    _wait_for_continue()
                continue

            is_correct = label == q.correct_label
            xp = state_mod.record_answer(state, q.id, q.concept, is_correct)
            state_mod.save(state)
            if is_correct:
                correct += 1
                # Drop this one from recent_wrongs on success.
                if q.id in state.recent_wrongs:
                    state.recent_wrongs.remove(q.id)
                    state_mod.save(state)
                sys.stdout.write(
                    render_correct_flash(
                        q,
                        streak=state.streak,
                        combo=state.combo,
                        xp_earned=xp,
                    )
                )
                sys.stdout.flush()
                time.sleep(0.9)
            else:
                still_wrong += 1
                sys.stdout.write(render_wrong_reveal(q, chosen=label))
                if answer_time < 5.0:
                    sys.stdout.write(
                        "  " + paint("\u25c9 sticky one", GOLD, BOLD)
                        + paint(" - still tripping you up", ASH, DIM) + "\n"
                    )
                _wait_for_continue()

        _summary(correct, still_wrong, skipped, len(queue))
        return 0
    finally:
        if saved_tty is not None:
            _restore(saved_tty)


def _summary(correct: int, still_wrong: int, skipped: int, total: int) -> None:
    print()
    print(paint("  review complete", SAGE, BOLD))
    parts = [
        paint(f"  {correct} nailed", SAGE, BOLD),
    ]
    if still_wrong:
        parts.append(paint(f"{still_wrong} still tricky", ROSE, BOLD))
    if skipped:
        parts.append(paint(f"{skipped} skipped", ASH, DIM))
    parts.append(paint(f"of {total}", ASH, DIM))
    print("   ".join(parts))
    if correct == total and total > 0:
        print()
        print(paint("  wrong-list is now smaller. nice.", ASH, DIM))
    elif still_wrong:
        print()
        print(paint("  the tricky ones stay on the list -- try again tomorrow.", ASH, DIM))
    print()
