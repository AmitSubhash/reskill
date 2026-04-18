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
from .palette import ASH, BOLD, DARK_ASH, DIM, GOLD, ROSE, SAGE, STONE, TEAL, paint
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
    state: state_mod.State | None = None,
) -> list[tuple[Question, CommitInfo]]:
    """Match each commit to an SM-2 + interleaving-aware question.

    Delegates to `scheduler.choose` so `reskill session` and the live
    tmux quiz pane share the same evidence-based selection logic:
    overdue > new > not-due within the pool, interleaved across
    concepts, format-diverse.
    """
    from . import scheduler as sched

    deck: list[tuple[Question, CommitInfo]] = []
    used_ids: set[str] = set(seen_ids)
    weights = concept_weights or {}
    active_state = state or state_mod.load()
    last_concept: str | None = None
    recent_formats: list[str] = []

    for commit in commits:
        if len(deck) >= max_questions:
            break
        live_text = commit.subject + "\n" + "\n".join(commit.added_lines[:400])
        # Apply the Stop-hook cache as a weak bias: if a concept is
        # both mentioned here AND recently touched globally, bump it.
        biased = live_text
        for concept, score in weights.items():
            if score > 0:
                biased += "\n" + (concept.replace("_", " ") + " ") * min(score, 3)
        pick = sched.choose(
            live_text=biased,
            commit_text="",
            state=active_state,
            seen_ids=used_ids,
            last_concept=last_concept,
            recent_formats=recent_formats,
        )
        if pick is None:
            continue
        deck.append((pick.question, commit))
        used_ids.add(pick.question.id)
        last_concept = pick.concept
        recent_formats.append(pick.question.format)
        recent_formats = recent_formats[-4:]

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

    # Per-question outcomes for the end-of-session summary.
    outcomes: list[dict] = []

    try:
        for idx, (question, commit) in enumerate(deck, start=1):
            progress = paint(f"  {idx}/{len(deck)}", ASH, DIM)
            print(f"{progress}")
            print(_commit_chip(commit))
            sys.stdout.write(render_question(question, streak=state.streak))
            sys.stdout.flush()

            shown_at = time.time()
            deadline = shown_at + 45.0
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
                    _render_summary(outcomes, commits_count=len(commits))
                    return 0

            answer_time = time.time() - shown_at

            if label is not None:
                correct = label == question.correct_label
                xp = state_mod.record_answer(
                    state, question.id, question.concept, correct,
                )
                state_mod.save(state)
                outcomes.append({
                    "question": question,
                    "commit": commit,
                    "outcome": "correct" if correct else "wrong",
                    "chosen": label,
                    "answer_time": answer_time,
                })
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
                    if answer_time < 5.0:
                        # High-confidence miss (Butterfield & Metcalfe 2001
                        # hypercorrection effect): make the reveal stand out
                        # so the user tags it mentally.
                        sys.stdout.write(
                            "  " + paint("\u25c9 sticky one", GOLD, BOLD)
                            + paint(
                                " - high-confidence miss, stays with you",
                                ASH, DIM,
                            )
                            + "\n"
                        )
                    _wait_for_continue()
            else:
                state_mod.record_skip(state, question.concept)
                state_mod.save(state)
                outcomes.append({
                    "question": question,
                    "commit": commit,
                    "outcome": "timeout" if not skipped else "skipped",
                    "chosen": None,
                    "answer_time": answer_time,
                })
                if not skipped:
                    sys.stdout.write(
                        paint("  (time's up)", ASH, DIM) + "\n\n"
                    )
                sys.stdout.write(render_wrong_reveal(question, chosen=None))
                _wait_for_continue()

        _render_summary(outcomes, commits_count=len(commits))
        return 0

    finally:
        if saved_tty is not None:
            _restore(saved_tty)


def _render_summary(outcomes: list[dict], commits_count: int) -> None:
    """Rich end-of-session summary. Shows:

      - Score + time + sticky-wrong count
      - Concepts touched (with ✓/✗ markers)
      - Missed questions with the right answer quoted
      - Suggested next move (review queue, more session, rest)

    Research note: Butler & Roediger 2008 delayed-feedback preference
    is already satisfied by showing the correct answer during the
    quiz; this summary is about *recall cueing* and closure, not
    additional teaching content.
    """
    from collections import OrderedDict

    state = state_mod.load()
    print()
    print(paint("  session complete", SAGE, BOLD))
    if not outcomes:
        print(paint(f"  no questions answered from {commits_count} commits", ASH, DIM))
        print()
        return

    correct = sum(1 for o in outcomes if o["outcome"] == "correct")
    wrong = sum(1 for o in outcomes if o["outcome"] == "wrong")
    skipped = sum(1 for o in outcomes if o["outcome"] == "skipped")
    timeouts = sum(1 for o in outcomes if o["outcome"] == "timeout")
    sticky = sum(
        1 for o in outcomes
        if o["outcome"] == "wrong" and o.get("answer_time", 999) < 5.0
    )
    total_time = sum(o.get("answer_time", 0.0) for o in outcomes)
    accuracy = correct / len(outcomes) * 100

    print(
        paint(f"  {correct} correct", SAGE, BOLD)
        + paint(f"   {wrong} wrong", ROSE if wrong else ASH, BOLD if wrong else DIM)
        + (paint(f"   {skipped} skipped", ASH, DIM) if skipped else "")
        + (paint(f"   {timeouts} timeouts", ASH, DIM) if timeouts else "")
        + paint(f"   {accuracy:.0f}% accuracy", ASH, DIM)
    )
    mins = total_time / 60
    print(
        paint(f"  took {mins:.1f} min", ASH, DIM)
        + (paint(f"   {sticky} sticky \u25c9", GOLD, DIM) if sticky else "")
    )

    # Concepts touched with pass/fail markers.
    concepts_hit: OrderedDict[str, dict] = OrderedDict()
    for o in outcomes:
        concept = o["question"].concept
        concepts_hit.setdefault(concept, {"ok": 0, "miss": 0})
        if o["outcome"] == "correct":
            concepts_hit[concept]["ok"] += 1
        else:
            concepts_hit[concept]["miss"] += 1
    if concepts_hit:
        print()
        print(paint("  concepts this session", ASH))
        for concept, data in concepts_hit.items():
            marks = paint("\u2713" * data["ok"], SAGE)
            marks += paint("\u2717" * data["miss"], ROSE) if data["miss"] else ""
            print(f"    {paint(concept.ljust(28), STONE)} {marks}")

    # Missed questions with the correct answer pointed out.
    misses = [o for o in outcomes if o["outcome"] in ("wrong", "timeout", "skipped")]
    if misses:
        print()
        print(paint(f"  revisit later ({len(misses)})", ROSE if any(m['outcome']=='wrong' for m in misses) else GOLD))
        for m in misses[:5]:
            q = m["question"]
            correct_opt = next((o for o in q.options if o.correct), None)
            prompt_short = q.prompt[:60] + ("..." if len(q.prompt) > 60 else "")
            print(f"    {paint('·', ASH, DIM)} {paint(prompt_short, STONE)}")
            if correct_opt:
                ans_short = correct_opt.text[:55] + (
                    "..." if len(correct_opt.text) > 55 else ""
                )
                print(
                    "      "
                    + paint("\u2192 ", SAGE)
                    + paint(ans_short, ASH, DIM)
                )
        if len(misses) > 5:
            print(paint(f"    ...and {len(misses) - 5} more", ASH, DIM))

    # Next-step hint.
    print()
    if wrong >= 3:
        hint = "take five, then `reskill session --since 3d` to rebuild streaks"
    elif correct >= 4 and wrong == 0:
        hint = "crushed it. try `reskill session --max 10` next"
    elif skipped + timeouts >= 2:
        hint = "skipped a lot? the `reskill claude` pane shows context-matched ones"
    else:
        hint = f"day {state.streak} streak · {state.correct_today}/{state.daily_goal} today"
    print(paint(f"  {hint}", ASH, DIM))
    print()
