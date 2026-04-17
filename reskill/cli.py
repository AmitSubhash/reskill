"""reskill CLI.

Usage:
  reskill run <command> [args...]   # wrap a command (e.g. claude) with inline quizzes
  reskill demo                      # run a demo (simulated claude, inline quizzes)
  reskill stats                     # show your learning stats
  reskill question                  # render a sample question (for UI testing)
"""

from __future__ import annotations

import os
import sys

from .palette import BOLD, DIM, INK, STONE, ASH, DARK_ASH, SAGE, TEAL, GOLD, VIOLET, paint


def cmd_run(argv: list[str]) -> int:
    from . import wrap
    return wrap.wrap(argv)


def cmd_demo() -> int:
    """Run the interactive inline-quiz demo (no Claude Code required)."""
    from . import demo as demo_mod
    demo_mod.run()
    return 0


def cmd_stats() -> int:
    from . import state as state_mod
    s = state_mod.load()

    HR = "\u2500" * 50

    print()
    print(f"  {paint('reSkill', TEAL, BOLD)} {paint('stats', ASH)}")
    print(paint(f"  {HR}", DARK_ASH, DIM))
    print()

    level_bar_total = 200
    xp_into_level = s.xp_total - ((s.level - 1) * 200)
    filled = int(xp_into_level / level_bar_total * 20)
    empty = 20 - filled
    bar = paint("\u2588" * filled, TEAL) + paint("\u2591" * empty, DARK_ASH)

    print(f"  {paint('level', STONE)}       {paint(str(s.level), VIOLET, BOLD)} {paint('(' + s.level_title + ')', ASH)}")
    print(f"              {bar} {paint(f'{xp_into_level}/{level_bar_total} xp', ASH)}")
    print()
    print(f"  {paint('streak', STONE)}      {paint(f'{s.streak} days', GOLD, BOLD)}  {paint(f'({s.freezes} freezes left)', ASH, DIM)}")
    print(f"  {paint('today', STONE)}       {paint(f'{s.correct_today}/{s.answered_today} correct', SAGE)}  {paint(f'+{s.xp_today} xp', VIOLET)}")
    print(f"  {paint('best combo', STONE)}  {paint(f'{s.best_combo}x', GOLD)}")
    print(f"  {paint('total xp', STONE)}    {paint(str(s.xp_total), ASH)}")
    print()

    if s.concepts:
        print(f"  {paint('concepts', STONE)}")
        for concept, data in sorted(s.concepts.items(), key=lambda kv: -kv[1]["total"])[:10]:
            pct = data["correct"] / max(1, data["total"]) * 100
            pct_color = SAGE if pct >= 80 else (GOLD if pct >= 50 else STONE)
            fill = int(pct / 10)
            mini_bar = paint("\u2588" * fill, pct_color) + paint("\u2591" * (10 - fill), DARK_ASH)
            counts = f"({data['correct']}/{data['total']})"
            print(
                f"    {paint(concept.ljust(20), INK)} {mini_bar} "
                f"{paint(f'{pct:.0f}%', pct_color)} "
                f"{paint(counts, ASH, DIM)}"
            )
    print()
    return 0


def cmd_question() -> int:
    """Render a sample question for testing."""
    from .question import TEMPLATE_BANK
    from .inline_box import render_question, render_answer_reveal

    # Pick one question from each concept
    for concept, questions in list(TEMPLATE_BANK.items())[:3]:
        q = questions[0]
        sys.stdout.write(render_question(q, streak=7))
        sys.stdout.write(render_answer_reveal(q, q.correct_label, 50))
    return 0


def cmd_help() -> int:
    print(__doc__)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        return cmd_help()

    cmd = argv[0]
    rest = argv[1:]

    if cmd in ("-h", "--help", "help"):
        return cmd_help()
    if cmd == "run":
        return cmd_run(rest)
    if cmd == "demo":
        return cmd_demo()
    if cmd == "stats":
        return cmd_stats()
    if cmd == "question":
        return cmd_question()

    print(f"reskill: unknown command '{cmd}'", file=sys.stderr)
    return cmd_help()


if __name__ == "__main__":
    raise SystemExit(main())
