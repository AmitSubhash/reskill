"""`reskill quiz-panel` -- the interactive quiz UI in the tmux side pane.

Design (evidence-cited, see /Users/amit/Projects/reskill/TODO.md):

  - Dynamic footer bar: always shows the keys available in the current
    state. (Posting, lazygit pattern.)
  - Arming state: 250 ms pulse + single visual bell before a new
    question renders, so the user's eye catches up.
    (fzf bell action, tmux monitor-activity.)
  - Session deck badge: `Q3 · 1✓ 1✗` always visible. (Anki deck counts.)
  - Pacing gate: at most 1 quiz / 90 s, 6 / hour, 20 / day; 3 s debounce
    after Claude starts thinking. (Iqbal & Bailey 2008.)
  - Scheduler: overdue > new > not-due, interleaved across concepts.
    (Rohrer & Taylor 2007; Bjork spacing.)
  - Tiered dismissal: x skip, b later, B bury, S suspend. (Anki.)
  - Take-a-breath empty state instead of random fallback questions.
"""

from __future__ import annotations

import os
import select
import shutil
import sys
import termios
import time
import tty
from pathlib import Path

from . import pacing
from . import scheduler
from . import state as state_mod
from .review_queue import ReviewQueue
from .activity import have_reskill_hooks, is_claude_active, recent_transcript_text
from .git_diffs import fetch_commits, project_root
from .inline_box import (
    render_correct_flash,
    render_question,
    render_wrong_reveal,
)
from .palette import (
    ASH,
    BOLD,
    DARK_ASH,
    DIM,
    GOLD,
    ROSE,
    SAGE,
    TEAL,
    paint,
)


STATE_DIR = Path.home() / ".reskill" / "state"


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _term_size() -> tuple[int, int]:
    try:
        s = shutil.get_terminal_size()
        return s.lines, s.columns
    except OSError:
        return 24, 60


def _clear_screen() -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


def _hide_cursor() -> None:
    sys.stdout.write("\x1b[?25l")
    sys.stdout.flush()


def _show_cursor() -> None:
    sys.stdout.write("\x1b[?25h")
    sys.stdout.flush()


def _bell() -> None:
    """Single visual bell. Most terminals flash; some do nothing, which is
    fine (it's the permission-less notification pattern)."""
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except OSError:
        pass


# ───────── Semantic pane-border colors (state signal at the edge) ─────────
#
# Textual's design guide + WCAG: color is a signal layer, not the only
# signal. We change the TMUX PANE BORDER to match the current state so
# peripheral vision catches it without reading the box. Glyphs inside
# the box (✓/✗, "new question incoming") remain the primary cue.
#
# Tmux colors are the 256-color palette; we approximate the Everforest
# values we use inside the pane. Falls back silently when $TMUX is unset.

_TMUX_COLORS = {
    "idle": "colour240",     # dim ash
    "arming": "colour179",   # gold
    "question": "colour108",  # teal-green
    "correct": "colour108",
    "wrong": "colour167",    # rose
}

_last_border_state: str | None = None


def _set_pane_border(state: str) -> None:
    """Color the current tmux pane's border to reflect our state.

    No-op if not inside tmux, or if the requested state is unchanged
    (so we don't thrash the terminal with escape sequences).
    """
    global _last_border_state
    if state == _last_border_state:
        return
    if not os.environ.get("TMUX"):
        _last_border_state = state
        return
    color = _TMUX_COLORS.get(state, "colour240")
    import subprocess
    try:
        subprocess.run(
            [
                "tmux", "select-pane", "-P",
                f"fg={color}",
            ],
            check=False,
            timeout=1,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    _last_border_state = state


def _set_cbreak() -> list[int]:
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    return saved  # type: ignore[return-value]


def _restore_tty(saved: list[int]) -> None:
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, saved)  # type: ignore[arg-type]


def _read_key(timeout: float) -> bytes | None:
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return None
    try:
        return os.read(sys.stdin.fileno(), 8)
    except OSError:
        return None


# ───────── Session counters (live for one quiz-panel run) ─────────


class SessionCounters:
    """Per-run ledger the user sees in the badge.

    Separate from state.py's daily counts so the badge reflects THIS
    pane's activity, not totals across reskill sessions.
    """

    def __init__(self) -> None:
        self.served: int = 0
        self.correct: int = 0
        self.wrong: int = 0
        self.skipped: int = 0

    def badge(self) -> str:
        parts: list[str] = []
        parts.append(paint(f"Q{self.served + 1}", TEAL, BOLD))
        if self.correct or self.wrong:
            parts.append(paint(f"{self.correct}\u2713", SAGE))
            parts.append(paint(f"{self.wrong}\u2717", ROSE))
        if self.skipped:
            parts.append(paint(f"{self.skipped}\u21b7", ASH, DIM))
        sep = paint(" \u00b7 ", DARK_ASH, DIM)
        return sep.join(parts)


# ───────── Footer (always-visible keymap hint) ─────────

FOOTER_IDLE = [
    ("F", "focus"),
    ("q", "quit"),
]
FOOTER_ARMING = [
    ("F", "focus"),
    ("...", "incoming"),
]
FOOTER_QUESTION_UNFOCUSED = [
    ("click or ctrl-b \u2192", "focus to answer"),
]
FOOTER_QUESTION_FOCUSED = [
    ("1-4", "answer"),
    ("b", "later"),
    ("B", "bury"),
    ("x", "skip"),
]
FOOTER_REVEAL_CORRECT = [
    ("", "continuing..."),
]
FOOTER_REVEAL_WRONG = [
    ("any key", "continue"),
]


def _render_footer(items: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    for key, label in items:
        if key:
            parts.append(paint(f"[{key}]", TEAL, BOLD) + paint(f" {label}", ASH, DIM))
        else:
            parts.append(paint(label, ASH, DIM))
    sep = paint("   ", DARK_ASH, DIM)
    return "  " + sep.join(parts)


# ───────── Cards ─────────


def _render_idle_card(session: SessionCounters, paced: pacing.PacingState) -> None:
    """Shown when Claude is not currently thinking."""
    _set_pane_border("idle")
    _clear_screen()
    state = state_mod.load()
    source = "hooks" if have_reskill_hooks() else "transcript poll"

    # Show how many concepts are ready.
    live_text = recent_transcript_text(cwd=os.getcwd() or project_root())
    due_n, new_n = scheduler.concepts_ready(
        live_text or "", state, set(state.seen_questions)
    )

    next_in = int(pacing.seconds_until_next_allowed(paced))
    wait_line = (
        paint(f"next allowed in {next_in}s", ASH, DIM)
        if next_in > 0
        else paint("ready when claude thinks", ASH, DIM)
    )

    lines = [
        "",
        "  " + paint("reSkill", TEAL, BOLD) + "   " + session.badge(),
        "  " + paint("standby", ASH, DIM),
        "",
        "  "
        + paint(f"day {state.streak}", GOLD, BOLD)
        + paint(" streak", ASH, DIM)
        + "   "
        + paint(f"{state.correct_today}/{state.daily_goal} today", SAGE if state.correct_today >= state.daily_goal else ASH),
        "  " + paint(f"{due_n} due \u00b7 {new_n} new", ASH, DIM),
        "",
        "  " + wait_line,
        "  " + paint(f"signal: {source}", DARK_ASH, DIM),
    ]
    if source != "hooks":
        lines.append(
            "  " + paint("tip: `reskill install` for tighter timing", DARK_ASH, DIM)
        )
    lines.append("")
    sys.stdout.write("\n".join(lines))
    sys.stdout.write("\n\n")
    sys.stdout.write(_render_footer(FOOTER_IDLE))
    sys.stdout.flush()


def _render_take_a_breath() -> None:
    """Take-a-breath card shown when there are no matching questions.

    Based on fzf's empty-results convention: never fake content.
    """
    _clear_screen()
    tips = [
        (
            "f-string debug",
            "In 3.8+: `print(f'{user=}')` prints BOTH the name and the repr.",
        ),
        (
            "dict order",
            "Python dict is insertion-ordered since 3.7 -- no need for OrderedDict.",
        ),
        (
            "pathlib",
            "Path('x.json').read_text(encoding='utf-8') beats open() + os.path.",
        ),
        (
            "timing-safe compare",
            "`hmac.compare_digest(a, b)` for tokens -- `==` short-circuits.",
        ),
    ]
    import random
    tag, tip = random.choice(tips)
    lines = [
        "",
        "  " + paint("TIL", GOLD, BOLD) + paint(f"  {tag}", ASH),
        "",
        "  " + paint(tip, ASH),
        "",
        "  " + paint("no matching questions for the current context", DARK_ASH, DIM),
        "",
    ]
    sys.stdout.write("\n".join(lines))
    sys.stdout.write("\n\n")
    sys.stdout.write(_render_footer(FOOTER_IDLE))
    sys.stdout.flush()


def _render_question_view(question, state: state_mod.State, session: SessionCounters) -> None:
    _set_pane_border("question")
    _clear_screen()
    sys.stdout.write("  " + session.badge() + "\n")
    sys.stdout.write(render_question(question, streak=state.streak, compact=True))
    sys.stdout.write("\n")
    sys.stdout.write(_render_footer(FOOTER_QUESTION_UNFOCUSED))
    sys.stdout.write("\n\n")
    sys.stdout.write(_render_footer(FOOTER_QUESTION_FOCUSED))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _arming_pulse() -> None:
    """250 ms border flash + bell before the real question renders.

    Gives peripheral vision a chance to catch up instead of the box
    appearing mid-keystroke.
    """
    _set_pane_border("arming")
    _clear_screen()
    bar = paint("\u2502 ", GOLD, BOLD) * 4
    lines = [
        "",
        "  " + bar,
        "  " + paint("new question incoming...", GOLD, BOLD),
        "  " + bar,
        "",
    ]
    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()
    _bell()
    time.sleep(0.25)


def _wait_for_continue(max_wait: float = 8.0) -> None:
    """Poll for any key with a visible countdown so the user knows the
    reveal isn't frozen. Anki's equivalent: the 60 s "you walked away"
    timeout. 8 s keeps the reveal readable without forcing engagement.
    """
    start = time.time()
    last_shown = -1
    while True:
        remaining = int(max_wait - (time.time() - start))
        if remaining <= 0:
            break
        if remaining != last_shown:
            # Overwrite the footer's last-line "any key continue" hint
            # with a live countdown. \r + \x1b[K clears the line.
            line = paint(
                f"  any key to continue  \u00b7  auto in {remaining}s",
                ASH, DIM,
            )
            sys.stdout.write("\r\x1b[K" + line)
            sys.stdout.flush()
            last_shown = remaining
        if _read_key(timeout=0.3) is not None:
            break
    # Clear the countdown line so nothing lingers on the next render.
    sys.stdout.write("\r\x1b[K")
    sys.stdout.flush()


# ───────── Main loop ─────────


def _quiz_loop_once(
    state: state_mod.State,
    session: SessionCounters,
    paced: pacing.PacingState,
    review: ReviewQueue,
    last_concept: str | None,
    recent_formats: list[str],
) -> str | None:
    """Serve one question (if pacing allows). Returns the concept served
    so the next call can interleave away from it."""
    seen = set(state.seen_questions)
    project = project_root()

    # The review queue gets first crack: any wrong/skipped question that
    # has waited out its countdown re-appears here. Butler & Roediger 2008:
    # same-session relearning strongly improves retention of the item.
    question_from_review = review.ready()
    if question_from_review is not None:
        pick = scheduler.Pick(
            question=question_from_review,
            concept=question_from_review.concept,
            source="review",
        )
    else:
        live_text = recent_transcript_text(cwd=os.getcwd() or project)
        commit_text = ""
        if project:
            commits = fetch_commits("7d", cwd=project, limit=10)
            commit_text = "\n".join(
                c.subject + "\n" + "\n".join(c.added_lines[:60]) for c in commits
            )
        pick = scheduler.choose(
            live_text=live_text,
            commit_text=commit_text,
            state=state,
            seen_ids=seen,
            last_concept=last_concept,
            recent_formats=recent_formats,
        )
        if pick is None:
            _render_take_a_breath()
            return last_concept

    # Pacing gate (review items still obey the rate limit).
    gate = pacing.can_fire_now(paced, candidate_concept=pick.concept)
    if not gate.allowed:
        _render_idle_card(session, paced)
        return last_concept

    # Arming state: brief pulse + bell, then render.
    _arming_pulse()

    pacing.note_quiz_served(paced, pick.concept)
    pacing.save(paced)
    session.served += 1
    recent_formats.append(pick.question.format)
    while len(recent_formats) > 4:
        recent_formats.pop(0)
    # Tick AFTER choosing so the newly-served item doesn't immediately
    # decrement its own countdown.
    review.tick()
    _render_question_view(pick.question, state, session)

    deadline = time.time() + 45.0
    label: str | None = None
    dismissal: str | None = None
    while time.time() < deadline and _is_thinking_with_grace():
        key = _read_key(timeout=0.5)
        if key is None:
            continue
        ch = key[:1]
        if ch in (b"1", b"2", b"3", b"4"):
            label = ch.decode()
            break
        if ch == b"x":
            dismissal = "skip"
            break
        if ch == b"\x1b":
            dismissal = "skip"
            break
        if ch == b"b":
            dismissal = "later"
            break
        if ch == b"B":
            dismissal = "bury"
            break
        if ch == b"q":
            raise KeyboardInterrupt

    pacing.note_quiz_finished(paced)
    pacing.save(paced)

    if label is not None:
        correct = label == pick.question.correct_label
        xp = state_mod.record_answer(
            state, pick.question.id, pick.question.concept, correct
        )
        state_mod.save(state)
        _clear_screen()
        if correct:
            session.correct += 1
            _set_pane_border("correct")
            sys.stdout.write(
                render_correct_flash(
                    pick.question,
                    streak=state.streak,
                    combo=state.combo,
                    xp_earned=xp,
                )
            )
            sys.stdout.write("\n")
            sys.stdout.write(_render_footer(FOOTER_REVEAL_CORRECT))
            sys.stdout.flush()
            time.sleep(1.2)
        else:
            session.wrong += 1
            # Re-queue the missed question for this session. The
            # forgetting curve shows the first few minutes are when
            # retention drops fastest -- re-asking 3 questions later
            # locks in the correction. First-time misses only; if this
            # was ALREADY a re-asked review, don't loop it forever.
            if pick.source != "review":
                review.enqueue(pick.question)
            _set_pane_border("wrong")
            sys.stdout.write(render_wrong_reveal(pick.question, chosen=label))
            sys.stdout.write("\n")
            sys.stdout.write(_render_footer(FOOTER_REVEAL_WRONG))
            sys.stdout.flush()
            _wait_for_continue()
    elif dismissal:
        session.skipped += 1
        state_mod.record_skip(state, pick.question.concept)
        state_mod.save(state)
        if dismissal == "bury":
            # Keep seen_questions so the ID won't recur today.
            state.seen_questions.append(pick.question.id)
            state_mod.save(state)
        elif dismissal == "later" and pick.source != "review":
            # 'later' = push back in this session; come around again.
            review.enqueue(pick.question, priority=5)
        # 'skip' just rolls forward.
        if dismissal in ("skip", "bury"):
            _clear_screen()
            sys.stdout.write(render_wrong_reveal(pick.question, chosen=None))
            sys.stdout.write("\n")
            sys.stdout.write(_render_footer(FOOTER_REVEAL_WRONG))
            sys.stdout.flush()
            _wait_for_continue()

    return pick.concept


# ───────── Thinking-flag gating with grace ─────────

_IDLE_GRACE_SECONDS = 6.0


def _is_thinking_with_grace() -> bool:
    if is_claude_active(cwd=os.getcwd()):
        try:
            (STATE_DIR / "last_active").write_text(str(time.time()))
        except OSError:
            pass
        return True
    try:
        last = float((STATE_DIR / "last_active").read_text() or 0)
    except (OSError, ValueError):
        last = 0.0
    return (time.time() - last) < _IDLE_GRACE_SECONDS if last else False


def run() -> int:
    """Entry point for `reskill quiz-panel`."""
    _ensure_state_dir()

    session = SessionCounters()
    paced = pacing.load()
    review = ReviewQueue()

    saved_tty = None
    if sys.stdin.isatty():
        saved_tty = _set_cbreak()
    _hide_cursor()

    last_render = ""   # 'idle' | 'question' | 'reveal'
    last_concept: str | None = None
    recent_formats: list[str] = []

    try:
        was_thinking = False
        while True:
            thinking = _is_thinking_with_grace()
            if thinking and not was_thinking:
                pacing.note_thinking_started(paced)
                pacing.save(paced)
            was_thinking = thinking

            if thinking:
                state = state_mod.load()
                last_concept = _quiz_loop_once(
                    state, session, paced, review,
                    last_concept, recent_formats,
                )
            else:
                if last_render != "idle":
                    _render_idle_card(session, paced)
                    last_render = "idle"
                key = _read_key(timeout=1.0)
                if key and key[:1] == b"q":
                    return 0
                # Re-render periodically so counters + "next in Ns" update.
                if key is None and int(time.time()) % 3 == 0:
                    _render_idle_card(session, paced)
    except KeyboardInterrupt:
        return 0
    finally:
        # Restore tmux pane border to the default color so the user
        # doesn't see a weird color on whatever pane replaces this one.
        if os.environ.get("TMUX"):
            import subprocess
            try:
                subprocess.run(
                    ["tmux", "select-pane", "-P", "fg=default"],
                    check=False,
                    timeout=1,
                )
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                pass
        _show_cursor()
        if saved_tty is not None:
            _restore_tty(saved_tty)
        _clear_screen()
