"""
Showcase all reSkill content formats in a simulated session.
Run: python -m reskill.showcase
"""

from __future__ import annotations

import itertools
import os
import sys
import time

from .palette import (
    BOLD, DIM,
    INK, STONE, ASH, DARK_ASH, SAGE, TEAL, ROSE, VIOLET, GOLD,
    paint,
)
from .panel import render_panel, HZ, TERM_W
from .quiz import (
    SessionState, SAMPLE_QUESTIONS,
    render_quiz, render_answer, render_session_summary,
)
from .cards import (
    SAMPLE_TILS, SAMPLE_PATTERNS, SAMPLE_DOCS, SAMPLE_REFLECTS,
    render_til, render_pattern, render_doc, render_reflect,
)

SPINNER = list("\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")
VERBS = ["Cogitating", "Ruminating", "Deliberating", "Pondering",
         "Cerebrating", "Noodling", "Percolating", "Machinating"]


def print_lines(lines: list[str]) -> None:
    for l in lines:
        print(l)


def cursor_up(n: int) -> None:
    sys.stdout.write(f"\033[{n}A")
    sys.stdout.flush()


def clear_n(n: int) -> None:
    for _ in range(n):
        sys.stdout.write("\033[2K\n")
    cursor_up(n)


def spin(duration: float, msg: str = "") -> None:
    spinner = itertools.cycle(SPINNER)
    for i in range(int(duration / 0.1)):
        s = next(spinner)
        v = VERBS[i % len(VERBS)]
        extra = f"  {paint(msg, DARK_ASH, DIM)}" if msg else ""
        sys.stdout.write(f"\r  {paint(s, TEAL)} {paint(f'{v}...', ASH)}{extra}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r\033[2K")


def show_card(lines: list[str], duration: float = 3.0) -> None:
    """Show a card panel during thinking, then clean up."""
    print()
    print_lines(lines)
    height = len(lines) + 1
    spin(duration)
    cursor_up(height)
    clear_n(height)


def user_prompt(text: str) -> None:
    print()
    print(f"  {paint(chr(0x276f), SAGE, BOLD)} {paint(text, INK, BOLD)}")


def tool_call(name: str, arg: str = "") -> None:
    print(f"  {paint(chr(0x2699), GOLD)} {paint(name, GOLD, BOLD)} {paint(arg, ASH)}")


def success_msg(text: str) -> None:
    print(f"  {paint(chr(0x2713), SAGE, BOLD)} {paint(text, ASH)}")


def assistant(text: str) -> None:
    print()
    for line in text.split("\n"):
        print(f"  {paint(line, INK)}")


def section_banner(num: int, title: str, desc: str) -> None:
    """Show what content type is coming next."""
    print()
    print(paint(f"  {'─' * (TERM_W - 4)}", DARK_ASH, DIM))
    print(f"  {paint(f'Format {num}:', TEAL, BOLD)} {paint(title, INK, BOLD)}")
    print(f"  {paint(desc, ASH)}")
    print(paint(f"  {'─' * (TERM_W - 4)}", DARK_ASH, DIM))
    time.sleep(1.5)


def run() -> None:
    os.system("clear")

    state = SessionState()
    state.streak = 12
    state.xp_total = 2340
    state.level = 12

    # Header
    print()
    print(f"  {paint('reSkill', TEAL, BOLD)} {paint('Content Format Showcase', INK)}")
    print(f"  {paint('5 ways to learn during AI thinking time', ASH)}")
    hr = HZ * (TERM_W - 4)
    print(paint(f"  {hr}", DARK_ASH, DIM))
    print()
    print(f"  {paint('Detected stack:', STONE)} {paint('Python + FastAPI + pytest', TEAL)}")
    print(f"  {paint('Streak:', STONE)} {paint(f'{state.streak} days', GOLD)} {paint('|', DARK_ASH)} {paint(f'Level {state.level} ({state.level_title})', VIOLET)} {paint('|', DARK_ASH)} {paint(f'{state.xp_total} XP', ASH)}")
    print()
    time.sleep(2.0)

    # ═══════════════════════════════════════════════════
    # FORMAT 1: Interactive Quiz (longer tool calls)
    # ═══════════════════════════════════════════════════
    section_banner(1, "Interactive Quiz",
                   "During longer tool calls (Bash, multi-file edits). Press a/b/c/d to answer.")

    user_prompt("run the full test suite with coverage")
    time.sleep(0.5)

    # Show quiz (non-interactive in showcase mode)
    q = SAMPLE_QUESTIONS[0]
    quiz_lines = render_quiz(q, state)
    print()
    print_lines(quiz_lines)
    height = len(quiz_lines) + 1
    spin(3.0)

    # Simulate answer
    xp = state.record_answer(True, q.xp)
    cursor_up(height)
    clear_n(height)
    answer_lines = render_answer(q, "B", state, xp)
    print_lines(answer_lines)
    time.sleep(2.5)
    a_height = len(answer_lines)
    cursor_up(a_height)
    clear_n(a_height)

    tool_call("Bash", "pytest --cov=src -v")
    time.sleep(0.3)
    success_msg("All 23 tests passed. Coverage: 87%")
    time.sleep(1.0)

    # ═══════════════════════════════════════════════════
    # FORMAT 2: TIL Card (short thinking times)
    # ═══════════════════════════════════════════════════
    section_banner(2, "Today I Learned",
                   "During short thinks (<5s). Passive -- just read. No interaction needed.")

    user_prompt("explain what lru_cache does")
    time.sleep(0.5)

    til_lines = render_til(SAMPLE_TILS[3])
    show_card(til_lines, 3.5)

    assistant(
        "functools.lru_cache is a decorator that memoizes function results.\n"
        "It stores the return value for each set of arguments and returns\n"
        "the cached result on subsequent calls with the same arguments."
    )
    time.sleep(1.0)

    # ═══════════════════════════════════════════════════
    # FORMAT 3: Pattern Card (during reads/edits)
    # ═══════════════════════════════════════════════════
    section_banner(3, "Pattern Comparison",
                   "Shows a common anti-pattern vs the better way. Teaches through contrast.")

    user_prompt("optimize the data processing pipeline")
    time.sleep(0.5)

    pattern_lines = render_pattern(SAMPLE_PATTERNS[0])
    show_card(pattern_lines, 4.0)

    tool_call("Read", "src/pipeline.py")
    time.sleep(0.2)
    tool_call("Edit", "src/pipeline.py")
    time.sleep(0.2)
    success_msg("Replaced string concatenation with join()")
    time.sleep(1.0)

    # ═══════════════════════════════════════════════════
    # FORMAT 4: Doc Card (just-in-time documentation)
    # ═══════════════════════════════════════════════════
    section_banner(4, "Just-in-Time Docs",
                   "Shows relevant docs for what you're building. Context-aware.")

    user_prompt("add background email sending after user signup")
    time.sleep(0.5)

    doc_lines = render_doc(SAMPLE_DOCS[0])
    show_card(doc_lines, 4.0)

    assistant(
        "I'll use FastAPI's BackgroundTasks to send the welcome email\n"
        "after the response is returned, so signup stays fast."
    )
    tool_call("Edit", "src/routes/users.py")
    time.sleep(0.2)
    success_msg("Added background task for welcome email")
    time.sleep(1.0)

    # ═══════════════════════════════════════════════════
    # FORMAT 5: Reflection Card (your own code)
    # ═══════════════════════════════════════════════════
    section_banner(5, "Code Reflection",
                   "Shows YOUR code and prompts you to think about improvements.")

    user_prompt("refactor the auth module")
    time.sleep(0.5)

    reflect_lines = render_reflect(SAMPLE_REFLECTS[0])
    show_card(reflect_lines, 5.0)

    tool_call("Read", "src/auth.py")
    time.sleep(0.2)
    assistant(
        "I extracted a reusable get_or_404 helper and applied it\n"
        "across all endpoints that fetch resources by ID."
    )
    tool_call("Edit", "src/auth.py")
    time.sleep(0.2)
    success_msg("Refactored with get_or_404 helper")
    time.sleep(1.0)

    # ═══════════════════════════════════════════════════
    # SESSION SUMMARY
    # ═══════════════════════════════════════════════════
    print()
    print(paint(f"  {hr}", DARK_ASH, DIM))
    print()

    # Fake a few more answers for a better summary
    state.record_answer(True, 25)
    state.record_answer(False, 10)
    state.record_answer(True, 10)

    summary_lines = render_session_summary(state)
    print_lines(summary_lines)

    # Contribution heatmap
    print()
    heatmap_lines = _render_heatmap()
    print_lines(heatmap_lines)

    print()
    print(paint("  end of showcase", TEAL, BOLD))
    print()
    print(paint("  5 content formats, all context-aware, all non-disruptive:", ASH))
    print(paint("  1. Interactive Quiz    -- longer waits, press a/b/c/d", ASH))
    print(paint("  2. TIL Card            -- short waits, just read", ASH))
    print(paint("  3. Pattern Comparison  -- learn by contrast", ASH))
    print(paint("  4. Just-in-Time Docs   -- relevant docs for what you're building", ASH))
    print(paint("  5. Code Reflection     -- your own code, think critically", ASH))
    print()


def _render_heatmap() -> list[str]:
    """Render a GitHub-style contribution heatmap for quiz activity."""
    # Simulate 28 days of activity
    import random
    random.seed(42)
    activity = [random.choice([0, 0, 1, 2, 3, 4, 5, 0, 1, 2]) for _ in range(28)]
    # Make recent days more active
    for i in range(21, 28):
        activity[i] = random.randint(2, 6)

    def block(count: int) -> str:
        if count == 0:
            return paint("\u2591", DARK_ASH, DIM)
        elif count <= 2:
            return paint("\u2593", SAGE, DIM)
        elif count <= 4:
            return paint("\u2593", SAGE)
        else:
            return paint("\u2588", SAGE, BOLD)

    lines: list[str] = []
    lines.append("")

    # Build weekly columns (4 weeks)
    days = ["Mon", "   ", "Wed", "   ", "Fri", "   ", "Sun"]
    for row_idx, day_label in enumerate(days):
        row = paint(f"  {day_label} ", ASH)
        for week in range(4):
            day = week * 7 + row_idx
            if day < len(activity):
                row += block(activity[day]) + " "
            else:
                row += "  "
        lines.append(row)

    lines.append("")
    lines.append(
        paint("  ", ASH)
        + paint("\u2591", DARK_ASH, DIM) + paint("=0 ", ASH)
        + paint("\u2593", SAGE, DIM) + paint("=1-2 ", ASH)
        + paint("\u2593", SAGE) + paint("=3-4 ", ASH)
        + paint("\u2588", SAGE, BOLD) + paint("=5+ ", ASH)
        + paint(f"  Streak: {12} days", GOLD)
    )
    lines.append("")

    return render_panel(
        "Activity (last 4 weeks)",
        lines,
        border_color=DARK_ASH,
        title_color=TEAL,
    )


if __name__ == "__main__":
    run()
