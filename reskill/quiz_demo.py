"""
Full Claude Code session simulation with interactive quizzes during thinking.
Run: python -m reskill.quiz_demo
"""

from __future__ import annotations

import itertools
import os
import select
import sys
import termios
import time
import tty

from .palette import (
    BOLD, DIM, RESET,
    INK, STONE, ASH, DARK_ASH, SAGE, TEAL, ROSE, VIOLET, GOLD,
    paint,
)
from .panel import render_panel, visible_len, HZ, TERM_W
from .quiz import (
    QuizQuestion, SessionState,
    render_quiz, render_answer, render_session_summary,
    SAMPLE_QUESTIONS,
)


# ── Terminal input helpers ───────────────────────────────────


def getch_nonblocking(timeout: float = 0.1) -> str | None:
    """Read a single character with timeout. Returns None if no input."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            return sys.stdin.read(1)
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── Rendering helpers ────────────────────────────────────────


SPINNER = list("\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")
VERBS = [
    "Cogitating", "Ruminating", "Deliberating", "Pondering",
    "Cerebrating", "Noodling", "Percolating", "Machinating",
]


def print_lines(lines: list[str]) -> None:
    for line in lines:
        print(line)


def cursor_up(n: int) -> None:
    sys.stdout.write(f"\033[{n}A")
    sys.stdout.flush()


def clear_n_lines(n: int) -> None:
    for _ in range(n):
        sys.stdout.write("\033[2K\n")
    cursor_up(n)


def user_prompt(text: str) -> None:
    print()
    print(f"  {paint(chr(0x276f), SAGE, BOLD)} {paint(text, INK, BOLD)}")


def tool_call(name: str, arg: str = "") -> None:
    print(f"  {paint(chr(0x2699), GOLD)} {paint(name, GOLD, BOLD)} {paint(arg, ASH)}")


def success(text: str) -> None:
    print(f"  {paint(chr(0x2713), SAGE, BOLD)} {paint(text, ASH)}")


def assistant_text(text: str) -> None:
    print()
    for line in text.split("\n"):
        print(f"  {paint(line, INK)}")


def code_block(code: str) -> None:
    lines: list[str] = []
    for i, line in enumerate(code.strip().split("\n"), 1):
        num = paint(f"{i:>3} ", DARK_ASH)
        lines.append(num + paint(line, INK))
    panel = render_panel(
        paint("  python", STONE),
        lines,
        border_color=STONE,
        title_color=STONE,
    )
    print()
    print_lines(panel)


# ── Quiz during thinking ────────────────────────────────────


def show_thinking_with_quiz(
    q: QuizQuestion,
    state: SessionState,
    max_time: float = 8.0,
) -> tuple[str | None, float]:
    """Show quiz during thinking time. Returns (answer, time_taken)."""
    # Render quiz panel
    quiz_lines = render_quiz(q, state)
    print()
    print_lines(quiz_lines)

    quiz_height = len(quiz_lines) + 1

    # Wait for answer or timeout
    spinner = itertools.cycle(SPINNER)
    start = time.time()
    answer = None

    while time.time() - start < max_time:
        # Check for keypress
        ch = getch_nonblocking(0.1)
        if ch and ch.lower() in [o.label.lower() for o in q.options]:
            answer = ch.upper()
            break

        # Update spinner
        elapsed = time.time() - start
        remaining = max(0, max_time - elapsed)
        s = next(spinner)
        v = VERBS[int(elapsed) % len(VERBS)]
        sys.stdout.write(
            f"\r  {paint(s, TEAL)} {paint(f'{v}...', ASH)}"
            f"  {paint(f'{remaining:.0f}s remaining', DARK_ASH)}"
            f"{' ' * 20}"
        )
        sys.stdout.flush()

    time_taken = time.time() - start

    # Clear spinner line
    sys.stdout.write("\r\033[2K")

    # Show answer
    if answer:
        correct = answer == q.correct_label
        xp_earned = state.record_answer(correct, q.xp)
    else:
        # Timed out -- treat as skip
        state.total_today += 1
        xp_earned = 0
        answer = "?"

    answer_lines = render_answer(q, answer, state, xp_earned)

    # Clear quiz panel
    cursor_up(quiz_height)
    clear_n_lines(quiz_height)

    # Show answer panel
    print_lines(answer_lines)
    time.sleep(2.0)

    # Clear answer panel
    answer_height = len(answer_lines)
    cursor_up(answer_height)
    clear_n_lines(answer_height)

    return answer, time_taken


# ── Main session simulation ─────────────────────────────────


def run() -> None:
    os.system("clear")

    state = SessionState()
    # Don't load from disk for demo -- start fresh
    state.streak = 7
    state.xp_total = 1060
    state.level = 6
    state.last_date = "2026-04-16"

    # Header
    print()
    hr = HZ * (TERM_W - 4)
    print(f"  {paint('claude code', TEAL, BOLD)}  {paint('v2.1.88', DARK_ASH)}")
    print(paint(f"  {hr}", DARK_ASH, DIM))
    streak_info = (
        paint(f"  reSkill: ", ASH)
        + paint(f"Day {state.streak} streak", GOLD)
        + paint(f"  |  Level {state.level} ({state.level_title})", VIOLET)
        + paint(f"  |  {state.xp_total} XP", ASH)
    )
    print(streak_info)
    print()
    time.sleep(1.0)

    # ── Turn 1 ───────────────────────────────────────────
    user_prompt("add a /health endpoint to the FastAPI app")
    time.sleep(0.5)

    show_thinking_with_quiz(SAMPLE_QUESTIONS[0], state, max_time=10.0)

    tool_call("Read", "src/main.py")
    time.sleep(0.3)
    assistant_text("I'll add a health check endpoint to your FastAPI app.")

    code_block('''@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for load balancer."""
    return {"status": "ok", "version": app.version}''')

    tool_call("Edit", "src/main.py")
    time.sleep(0.2)
    success("Applied edit to src/main.py")
    time.sleep(1.0)

    # ── Turn 2 ───────────────────────────────────────────
    user_prompt("write tests for it")
    time.sleep(0.5)

    show_thinking_with_quiz(SAMPLE_QUESTIONS[1], state, max_time=15.0)

    tool_call("Read", "tests/test_api.py")
    time.sleep(0.2)
    assistant_text("Added tests for the health endpoint:")

    code_block('''@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"''')

    tool_call("Edit", "tests/test_api.py")
    time.sleep(0.2)
    success("Applied edit to tests/test_api.py")
    time.sleep(1.0)

    # ── Turn 3 ───────────────────────────────────────────
    user_prompt("what status code should I use for POST /users?")
    time.sleep(0.5)

    show_thinking_with_quiz(SAMPLE_QUESTIONS[2], state, max_time=8.0)

    assistant_text(
        "Use 201 Created for successful POST /users.\n"
        "Return the created user object in the response body\n"
        "with a Location header pointing to the new resource."
    )
    time.sleep(1.0)

    # ── Turn 4 ───────────────────────────────────────────
    user_prompt("refactor the auth middleware to use dependency injection")
    time.sleep(0.5)

    show_thinking_with_quiz(SAMPLE_QUESTIONS[3], state, max_time=12.0)

    tool_call("Read", "src/auth.py")
    time.sleep(0.2)
    tool_call("Read", "src/dependencies.py")
    time.sleep(0.2)
    assistant_text("I'll refactor the auth to use FastAPI's Depends():")

    code_block('''from fastapi import Depends, HTTPException

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, decode_token(token).sub)
    if not user:
        raise HTTPException(401)
    return user''')

    tool_call("Edit", "src/auth.py")
    time.sleep(0.2)
    success("Applied edit to src/auth.py")
    time.sleep(1.0)

    # ── Session end ──────────────────────────────────────
    print()
    print(paint(f"  {hr}", DARK_ASH, DIM))
    print()

    summary_lines = render_session_summary(state)
    print_lines(summary_lines)

    print()
    print(paint("  end of simulation", TEAL, BOLD))
    print()
    print(paint("  The quizzes were interactive -- press a/b/c/d to answer.", ASH))
    print(paint("  Context-aware: Python + FastAPI questions for a Python project.", ASH))
    print(paint("  Streaks, XP, combos, and session summary persist across sessions.", ASH))
    print()


if __name__ == "__main__":
    run()
