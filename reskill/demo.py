"""Interactive demo: simulates a Claude Code session with inline quizzes.

This lets you experience the product without needing Claude Code installed.
The demo streams fake Claude output, shows a quiz during each 'thinking'
phase, captures your keypress, and continues.

For wrapping real Claude Code, see reskill.wrap.
"""

from __future__ import annotations

import itertools
import os
import random
import select
import sys
import termios
import time
import tty

from . import state as state_mod
from .inline_box import render_correct_flash, render_question, render_wrong_reveal
from .palette import (
    ASH,
    BOLD,
    DARK_ASH,
    DIM,
    GOLD,
    INK,
    SAGE,
    STONE,
    TEAL,
    VIOLET,
    paint,
)
from .question import Question, generate_question

HR = "\u2500" * 60
SPINNER = list("\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")


# ── Scenario script ─────────────────────────────────────────

SCENARIOS = [
    {
        "user": "add error handling to the JWT validation in src/auth.py",
        "context_hint": "jwt error handling try except",
        "thinking_seconds": 12.0,  # long thinking -> multiple quizzes
        "tools": [("Read", "src/auth.py")],
        "response": (
            "\n  I'll add error handling to the JWT validation. Looking at "
            "the current code, expired tokens aren't being caught properly -- "
            "they return a 500 instead of 401.\n\n"
            "  I'll wrap the decode call in a try/except block and catch "
            "specific exceptions instead of using a bare except clause.\n\n"
            "  Here's the fix:\n"
        ),
        "code": (
            "try:\n"
            "    payload = jwt.decode(token, SECRET, algorithms=['HS256'])\n"
            "except jwt.ExpiredSignatureError:\n"
            "    raise HTTPException(401, detail='Token expired')\n"
            "except jwt.InvalidTokenError:\n"
            "    raise HTTPException(401, detail='Invalid token')"
        ),
        "after_tools": [("Edit", "src/auth.py")],
        "after_done": ["Applied edit to src/auth.py"],
    },
    {
        "user": "memoize the expensive lookup in helpers.py with lru_cache",
        "context_hint": "lru_cache memoization",
        "thinking_seconds": 10.0,
        "tools": [("Read", "src/helpers.py")],
        "response": (
            "\n  I'll add @lru_cache to the lookup. Repeated calls with "
            "the same email will return instantly from cache.\n\n"
            "  Using maxsize=128 keeps memory bounded.\n"
        ),
        "code": (
            "from functools import lru_cache\n\n"
            "@lru_cache(maxsize=128)\n"
            "def get_user_by_email(email: str) -> User | None:\n"
            "    return db.query(User).filter_by(email=email).first()"
        ),
        "after_tools": [("Edit", "src/helpers.py")],
        "after_done": ["Applied edit to src/helpers.py"],
    },
    {
        "user": "what status code should I return for POST /users?",
        "context_hint": "HTTP POST creates a resource 201 Created",
        "thinking_seconds": 6.0,
        "tools": [],
        "response": (
            "\n  Return `201 Created` for a successful POST that creates a "
            "new resource. Include the created resource in the body and a "
            "`Location` header pointing to its URL.\n"
        ),
        "code": None,
        "after_tools": [],
        "after_done": [],
    },
]


# ── Terminal I/O helpers ───────────────────────────────────


def _stdout_write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _read_answer(
    q: Question, timeout: float, state: state_mod.State
) -> tuple[str | None, int]:
    """Wait for 1/2/3/4 or ESC or timeout. Returns (label_or_None, xp)."""
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                state_mod.record_skip(state, q.concept)
                return None, 0
            r, _, _ = select.select([sys.stdin], [], [], min(0.25, remaining))
            if not r:
                continue
            try:
                ch = os.read(fd, 1)
            except OSError:
                continue
            if not ch:
                continue
            if ch in (b"1", b"2", b"3", b"4"):
                label = ch.decode()
                correct = label == q.correct_label
                xp = state_mod.record_answer(
                    state, q.id, q.concept, correct
                )
                return label, xp
            if ch in (b"\x1b", b"x", b"X"):
                state_mod.record_skip(state, q.concept)
                return None, 0
            # other keys: ignore, keep waiting
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def _thinking_spinner_until(deadline: float) -> None:
    """Animate a spinner until `deadline`. Same line, no scrolling."""
    spinner = itertools.cycle(SPINNER)
    verbs = ["Thinking", "Cogitating", "Pondering", "Ruminating"]
    start = time.time()
    while time.time() < deadline:
        s = next(spinner)
        v = verbs[int(time.time() - start) % len(verbs)]
        _stdout_write(f"\r  {paint(s, TEAL)} {paint(v + '...', ASH)}")
        time.sleep(0.08)
    _stdout_write("\r" + " " * 40 + "\r")


def _stream_text(text: str, wpm: int = 650) -> None:
    base = 60.0 / (wpm * 5)
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(base * random.uniform(0.3, 1.6))


def _tool_call(name: str, arg: str) -> None:
    print()
    print(f"  {paint('*', GOLD)} {paint(name, GOLD, BOLD)} {paint(arg, ASH)}")
    time.sleep(0.4)


def _done(text: str) -> None:
    print(f"  {paint(chr(0x2713), SAGE, BOLD)} {paint(text, ASH)}")


def _code_block(code: str) -> None:
    print()
    inner_width = 58
    top = "\u250c" + "\u2500" * inner_width + "\u2510"
    bot = "\u2514" + "\u2500" * inner_width + "\u2518"
    print(paint(f"  {top}", STONE, DIM))
    for line in code.strip("\n").split("\n"):
        padded = line + " " * max(0, inner_width - len(line))
        print(
            paint("  \u2502", STONE, DIM)
            + paint(padded, TEAL)
            + paint("\u2502", STONE, DIM)
        )
    print(paint(f"  {bot}", STONE, DIM))


def _banner(state: state_mod.State) -> None:
    print()
    title = paint("claude", TEAL, BOLD) + "  " + paint("sonnet 4.6", DARK_ASH)
    streak = ""
    if state.streak > 0:
        streak = "  " + paint(f"reskill: day {state.streak}", GOLD, DIM)
    print(f"  {title}{streak}")
    print(paint(f"  {HR}", DARK_ASH, DIM))


def _user_prompt(text: str) -> None:
    print()
    prefix = paint(">", SAGE, BOLD)
    # Type the prompt character by character for realism
    sys.stdout.write(f"  {prefix} ")
    sys.stdout.flush()
    for ch in text:
        sys.stdout.write(paint(ch, INK, BOLD))
        sys.stdout.flush()
        time.sleep(random.uniform(0.015, 0.045))
    sys.stdout.write("\n")


def _end_of_turn_footer(state: state_mod.State) -> None:
    """Tiny footer after each response showing reskill progress."""
    if state.answered_today == 0:
        return
    score = f"{state.correct_today}/{state.answered_today}"
    xp = f"+{state.xp_today} xp"
    combo = f"{state.combo}x combo" if state.combo >= 2 else ""
    parts = [
        paint("reskill", TEAL, DIM),
        paint(score, SAGE, DIM),
        paint(xp, VIOLET, DIM),
    ]
    if combo:
        parts.append(paint(combo, GOLD, DIM))
    print()
    print("  " + paint(" | ", DARK_ASH, DIM).join(parts))


# ── Main demo loop ─────────────────────────────────────────


def run() -> None:
    state = state_mod.load()

    os.system("clear")
    _banner(state)
    time.sleep(0.6)

    for scenario in SCENARIOS:
        _user_prompt(scenario["user"])
        time.sleep(0.4)

        # --- Thinking phase: keep popping quizzes until Claude is done,
        #     then wait for the user to finish the last one before showing
        #     the response. ---
        thinking_deadline = time.time() + scenario["thinking_seconds"]

        # Brief warm-up so the user sees Claude started
        _thinking_spinner_until(time.time() + 0.6)

        still_time = True
        while still_time:
            seen = set(state.seen_questions)
            q = generate_question(scenario["context_hint"], seen_ids=seen)
            if q is None:
                break

            _stdout_write(render_question(q, streak=state.streak))

            # User may take their time; if thinking deadline has passed,
            # we let them finish -- response is held until they answer.
            remaining = thinking_deadline - time.time()
            answer_timeout = max(6.0, remaining + 30.0)  # generous grace period
            label, xp = _read_answer(q, answer_timeout, state)
            state_mod.save(state)

            # Mirror wrap.py behavior: correct -> flash, wrong -> reveal
            if label is not None and label == q.correct_label:
                _stdout_write(render_correct_flash(
                    q, streak=state.streak, combo=state.combo, xp_earned=xp,
                ))
            else:
                _stdout_write(render_wrong_reveal(q, chosen=label))

            # Short reveal pause so the explanation registers
            time.sleep(1.0)

            remaining = thinking_deadline - time.time()
            if remaining <= 0:
                # Claude is done -- if user wants the response, exit loop
                still_time = False
            else:
                # Still thinking; give a small spinner gap before next question
                gap = min(1.5, remaining)
                _thinking_spinner_until(time.time() + gap)
                # Decide whether to pop another: only if we still have some
                # thinking room and a fresh question exists.
                remaining = thinking_deadline - time.time()
                if remaining < 2.0:
                    still_time = False
        # If we broke out because of no-more-questions but still had time,
        # burn the rest with the spinner.
        if time.time() < thinking_deadline:
            _thinking_spinner_until(thinking_deadline)

        # --- Claude's response ---
        for tool in scenario["tools"]:
            _tool_call(tool[0], tool[1])
            time.sleep(0.3)

        _stream_text(scenario["response"])

        if scenario["code"]:
            _code_block(scenario["code"])

        for tool in scenario["after_tools"]:
            _tool_call(tool[0], tool[1])
            time.sleep(0.2)
        for msg in scenario["after_done"]:
            _done(msg)
            time.sleep(0.2)

        _end_of_turn_footer(state)
        time.sleep(1.2)

    print()
    print(paint(f"  {HR}", DARK_ASH, DIM))
    print()
    print(
        "  "
        + paint("session ended", ASH)
        + "  "
        + paint("|", DARK_ASH, DIM)
        + "  "
        + paint(f"+{state.xp_today} xp today", VIOLET)
        + "  "
        + paint("|", DARK_ASH, DIM)
        + "  "
        + paint(f"level {state.level}", TEAL)
    )
    print()
    print(paint("  run `reskill stats` to see your growth", ASH, DIM))
    print()


if __name__ == "__main__":
    run()
