"""`reskill quiz-panel` -- standalone quiz UI for the tmux side pane.

This process owns its own PTY (it's running in a tmux pane). There is no
Ink collision, no scroll-region gymnastics. We just render a clean quiz
box and read keys normally.

Signals:
    ~/.reskill/state/thinking         empty file created by the Claude
                                      Code PreToolUse hook; removed by
                                      PostToolUse / Stop. When present we
                                      serve a question; when absent we
                                      collapse to a 'waiting for claude'
                                      view.

Quiz lifecycle:
    1. Poll the signal file every 1s.
    2. When thinking appears, generate a question from the most recent
       project transcript (via log_session cache) or fall back to a
       random template.
    3. Render the question; read 1/2/3/4, x (skip), q (quit).
    4. On answer, show reveal; wait for a key; loop.
    5. When thinking disappears, show a soft "Claude is done" card and
       wait for the next thinking event.
"""

from __future__ import annotations

import os
import random
import select
import shutil
import sys
import termios
import time
import tty
from pathlib import Path

from . import state as state_mod
from .activity import have_reskill_hooks, is_claude_active, recent_transcript_text
from .git_diffs import fetch_commits, project_root
from .inline_box import (
    render_correct_flash,
    render_question,
    render_wrong_reveal,
)
from .log_session import CACHE_ROOT, _load_cache, _project_hash
from .palette import ASH, BOLD, DARK_ASH, DIM, GOLD, SAGE, TEAL, paint
from .question import Question, TEMPLATE_BANK, detect_concepts, generate_question


STATE_DIR = Path.home() / ".reskill" / "state"
THINKING_FILE = STATE_DIR / "thinking"
CURRENT_QUIZ_FILE = STATE_DIR / "current_quiz.json"


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


def _cursor_home() -> None:
    sys.stdout.write("\x1b[H")
    sys.stdout.flush()


def _hide_cursor() -> None:
    sys.stdout.write("\x1b[?25l")
    sys.stdout.flush()


def _show_cursor() -> None:
    sys.stdout.write("\x1b[?25h")
    sys.stdout.flush()


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


_IDLE_GRACE_SECONDS = 6.0


def _is_thinking() -> bool:
    """True if Claude is actively mid-thought OR went idle very recently.

    Uses activity.is_claude_active(), which prefers the hook flag when
    available and falls back to transcript-mtime polling otherwise.
    Grace-period smooths over the flicker between tool calls.
    """
    if is_claude_active(cwd=os.getcwd()):
        _mark_active()
        return True
    last = _last_active()
    return (time.time() - last) < _IDLE_GRACE_SECONDS if last else False


def _mark_active() -> None:
    try:
        (STATE_DIR / "last_active").write_text(str(time.time()))
    except OSError:
        pass


def _last_active() -> float:
    try:
        return float((STATE_DIR / "last_active").read_text() or 0)
    except (OSError, ValueError):
        return 0.0


def _render_idle_card() -> None:
    """Shown when Claude is not currently thinking."""
    _clear_screen()
    state = state_mod.load()
    source = "hooks" if have_reskill_hooks() else "transcript poll"
    lines = [
        "",
        "  " + paint("reSkill", TEAL, BOLD),
        "  " + paint("waiting for claude to think", ASH, DIM),
        "",
        "  " + paint(f"day {state.streak}", GOLD, BOLD)
        + paint(" streak", ASH, DIM)
        + paint(f"   {state.correct_today}/{state.daily_goal} today", SAGE),
        "",
        "  " + paint(f"signal: {source}", DARK_ASH, DIM),
    ]
    if source != "hooks":
        lines.append(
            "  " + paint(
                "tip: run `reskill install` for precise timing", DARK_ASH, DIM
            )
        )
    lines.extend([
        "",
        "  " + paint("q to exit the pane", DARK_ASH, DIM),
        "",
    ])
    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()


def _pick_question(seen_ids: set[str]) -> Question | None:
    """Source a question that matches what Claude is WORKING ON NOW.

    Priority (highest to lowest):
      1. Concepts detected in the live Claude transcript (this turn's
         assistant text + tool inputs). This is the "you asked about X,
         here's a quiz about X" path.
      2. Concepts detected in recent git commits in this project.
      3. Cumulative per-project concept tally from past sessions.
      4. Any fresh question at all.
    """
    project = project_root()

    # 1. Live context from the current Claude transcript.
    live_text = recent_transcript_text(cwd=os.getcwd() or project)
    if live_text:
        live_concepts = detect_concepts(live_text)
        random.shuffle(live_concepts)
        for concept in live_concepts:
            bank = TEMPLATE_BANK.get(concept, [])
            fresh = [q for q in bank if q.id not in seen_ids]
            if fresh:
                return random.choice(fresh)

    # 2. Recent commit diffs.
    if project:
        commits = fetch_commits("7d", cwd=project, limit=15)
        for commit in commits:
            haystack = commit.subject + "\n" + "\n".join(commit.added_lines[:200])
            for concept in detect_concepts(haystack):
                bank = TEMPLATE_BANK.get(concept, [])
                fresh = [q for q in bank if q.id not in seen_ids]
                if fresh:
                    return random.choice(fresh)

    # 3. Cumulative tally (only if the live signal was empty).
    weights: dict[str, int] = {}
    if project:
        cache_dir = CACHE_ROOT / _project_hash(project)
        if cache_dir.exists():
            weights = dict(_load_cache(cache_dir).get("concepts", {}))
    for concept in sorted(weights.keys(), key=lambda c: -weights[c]):
        bank = TEMPLATE_BANK.get(concept, [])
        fresh = [q for q in bank if q.id not in seen_ids]
        if fresh:
            return random.choice(fresh)

    # 4. Anything fresh.
    return generate_question("", seen_ids=seen_ids)


def _render_question_view(question: Question, state: state_mod.State) -> None:
    _clear_screen()
    sys.stdout.write("\n")
    sys.stdout.write(render_question(question, streak=state.streak, compact=True))
    # The user's keystrokes go to whichever tmux pane has focus -- by default
    # that's Claude's pane. Show a clear hint that answering requires a pane
    # switch, otherwise the user types "1" and it gets sent to Claude.
    hint1 = paint(
        "  click here ", ASH, DIM,
    ) + paint("or ", ASH, DIM) + paint(
        "ctrl-b \u2192", TEAL, BOLD,
    ) + paint("  to focus this pane", ASH, DIM)
    hint2 = paint("  then press 1 / 2 / 3 / 4", ASH, DIM)
    sys.stdout.write("\n" + hint1 + "\n" + hint2 + "\n")
    sys.stdout.flush()


def _quiz_loop_once(state: state_mod.State) -> None:
    """Handle a single question while Claude is thinking.

    Exits early if Claude stops thinking -- we don't want to make the user
    finish a question that's already served its purpose.
    """
    seen = set(state.seen_questions)
    question = _pick_question(seen)
    if question is None:
        _render_idle_card()
        return

    _render_question_view(question, state)

    deadline = time.time() + 45.0
    label: str | None = None
    skipped = False
    while time.time() < deadline and _is_thinking():
        key = _read_key(timeout=0.5)
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
            raise KeyboardInterrupt

    if label is not None:
        correct = label == question.correct_label
        xp = state_mod.record_answer(state, question.id, question.concept, correct)
        state_mod.save(state)
        _clear_screen()
        if correct:
            sys.stdout.write(
                render_correct_flash(
                    question,
                    streak=state.streak,
                    combo=state.combo,
                    xp_earned=xp,
                )
            )
            sys.stdout.flush()
            time.sleep(1.2)
        else:
            sys.stdout.write(render_wrong_reveal(question, chosen=label))
            sys.stdout.flush()
            _wait_for_continue()
    else:
        state_mod.record_skip(state, question.concept)
        state_mod.save(state)
        if skipped:
            _clear_screen()
            sys.stdout.write(render_wrong_reveal(question, chosen=None))
            sys.stdout.flush()
            _wait_for_continue()


def _wait_for_continue(max_wait: float = 8.0) -> None:
    hint = paint("  press any key to continue", ASH, DIM)
    sys.stdout.write("\n" + hint + "\n")
    sys.stdout.flush()
    start = time.time()
    while time.time() - start < max_wait:
        if _read_key(timeout=0.3) is not None:
            break


def run() -> int:
    """Entry point for `reskill quiz-panel`."""
    _ensure_state_dir()

    saved_tty = None
    if sys.stdin.isatty():
        saved_tty = _set_cbreak()
    _hide_cursor()

    last_state = None
    try:
        while True:
            thinking = _is_thinking()
            if thinking:
                state = state_mod.load()
                _quiz_loop_once(state)
            else:
                if last_state != "idle":
                    _render_idle_card()
                    last_state = "idle"
                # Poll for thinking start OR quit key.
                key = _read_key(timeout=1.0)
                if key and key[:1] == b"q":
                    return 0
    except KeyboardInterrupt:
        return 0
    finally:
        _show_cursor()
        if saved_tty is not None:
            _restore_tty(saved_tty)
        _clear_screen()
