"""reskill -- learn during AI thinking time.

Usage:
  reskill claude [args...]     launch claude in a tmux split with a quiz pane
  reskill quiz-panel           the pane itself (usually spawned by `claude`)
  reskill session [--since 7d] quiz deck built from your recent commits
  reskill next                 serve one context-matched quiz right now
  reskill review               drill your recently-missed questions
  reskill doctor               diagnose why reskill isn't behaving
  reskill topics               see every concept + your mastery progress
  reskill install              install the Claude Code hooks (PreToolUse,
                               PostToolUse, Stop) that signal the quiz pane
  reskill uninstall            remove the hooks
  reskill hook-status          are the hooks installed?
  reskill log-session <path>   ingest a transcript (called by the Stop hook)
  reskill status [--plain]     terse one-line status (for $PS1, tmux, etc.)
  reskill streak               12-week heatmap of your answered days
  reskill demo                 interactive demo (no Claude Code required)
  reskill stats                show streak, XP, concept mastery
  reskill pause                turn quizzes OFF globally
  reskill resume               turn quizzes back ON
  reskill question             render a sample quiz box (UI sanity check)
  reskill wrap <cmd> [args]    legacy PTY-wrap (DECSTBM; DEPRECATED -- does
                               not cooperate with Ink/Claude Code; kept
                               only for non-Ink programs)

Flags:
  --no-quiz                    disable quizzes for this invocation only
                               e.g. `reskill claude --no-quiz /plan "..."

During a wrapped session:
  1-4   answer the quiz
  x     skip this quiz (tracked; you'll see related concepts again)
  X     mute quizzes for the rest of THIS session
  esc   alias for x

Quizzes also pause automatically during Claude permission prompts
(y/n or numbered options), so your keys always reach the right place.
"""

from __future__ import annotations

import os
import sys

from .palette import BOLD, DIM, INK, STONE, ASH, DARK_ASH, SAGE, TEAL, GOLD, VIOLET, paint


def cmd_run(argv: list[str]) -> int:
    from . import wrap
    quizzes_enabled = True
    # Allow `--no-quiz` as the FIRST arg before the wrapped command
    # (so `reskill run --no-quiz claude` works, but also
    # `reskill claude --no-quiz` because we intercept it in main()).
    if argv and argv[0] == "--no-quiz":
        quizzes_enabled = False
        argv = argv[1:]
    return wrap.wrap(argv, quizzes_enabled=quizzes_enabled)


def cmd_pause() -> int:
    from . import state as state_mod
    s = state_mod.load()
    s.enabled = False
    state_mod.save(s)
    print(
        paint("  reskill paused", ASH, BOLD),
        paint("-- run `reskill resume` when you want questions back", ASH, DIM),
    )
    return 0


def cmd_resume() -> int:
    from . import state as state_mod
    s = state_mod.load()
    s.enabled = True
    state_mod.save(s)
    print(
        paint("  reskill resumed", SAGE, BOLD),
        paint("-- quizzes will appear during thinking time", ASH, DIM),
    )
    return 0


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
    from .inline_box import render_question, render_wrong_reveal

    # Pick one question from each concept
    for _concept, questions in list(TEMPLATE_BANK.items())[:3]:
        q = questions[0]
        sys.stdout.write(render_question(q, streak=7))
        sys.stdout.write(render_wrong_reveal(q, chosen=None))
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
    if cmd == "wrap":
        # Legacy PTY-wrap. Does NOT work with Claude Code's Ink renderer --
        # kept only for non-Ink programs.
        return cmd_run(rest)
    if cmd == "run":
        # Legacy alias.
        return cmd_run(rest)
    if cmd == "claude":
        from . import tmux_launcher
        tmux_launcher.ensure_banner()
        return tmux_launcher.launch(rest)
    if cmd == "quiz-panel":
        from . import quiz_panel
        return quiz_panel.run()
    if cmd == "statusline":
        from . import statusline
        return statusline.run()
    if cmd == "demo":
        return cmd_demo()
    if cmd == "stats":
        return cmd_stats()
    if cmd == "pause":
        return cmd_pause()
    if cmd == "resume":
        return cmd_resume()
    if cmd == "question":
        return cmd_question()
    if cmd == "session":
        return cmd_session(rest)
    if cmd == "next":
        from . import next_cmd
        # Accept --concept X or --concept=X
        concept: str | None = None
        i = 0
        while i < len(rest):
            if rest[i] == "--concept" and i + 1 < len(rest):
                concept = rest[i + 1]
                i += 2
                continue
            if rest[i].startswith("--concept="):
                concept = rest[i].split("=", 1)[1]
                i += 1
                continue
            i += 1
        return next_cmd.run(concept=concept)
    if cmd == "review":
        from . import review_cmd
        return review_cmd.run()
    if cmd == "doctor":
        from . import doctor
        return doctor.run()
    if cmd == "topics":
        from . import topics_cmd
        return topics_cmd.run()
    if cmd == "install":
        from . import hookinstall
        return hookinstall.install()
    if cmd == "uninstall":
        from . import hookinstall
        return hookinstall.uninstall()
    if cmd == "hook-status":
        from . import hookinstall
        return hookinstall.status()
    if cmd == "log-session":
        from . import log_session
        return log_session.log_session(
            transcript_path=(rest[0] if rest else _read_hook_stdin()),
            cwd=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(),
        )
    if cmd == "status":
        from .status_ui import render_status
        plain = "--plain" in rest
        print(render_status(plain=plain))
        return 0
    if cmd == "streak":
        from .status_ui import render_heatmap
        print(render_heatmap())
        return 0

    print(f"reskill: unknown command '{cmd}'", file=sys.stderr)
    return cmd_help()


def _read_hook_stdin() -> str:
    """Claude Code hooks pass JSON via stdin with transcript_path. Parse it."""
    import json
    try:
        data = json.loads(sys.stdin.read() or "{}")
        return str(data.get("transcript_path") or "")
    except (json.JSONDecodeError, OSError):
        return ""


def cmd_session(argv: list[str]) -> int:
    """`reskill session --since 7d` -- quiz deck from recent commits."""
    since = "7d"
    max_questions = 5
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--since", "--from-commits") and i + 1 < len(argv):
            since = argv[i + 1]
            i += 2
            continue
        if arg in ("-n", "--max") and i + 1 < len(argv):
            try:
                max_questions = max(1, int(argv[i + 1]))
            except ValueError:
                pass
            i += 2
            continue
        i += 1
    from . import session as session_mod
    return session_mod.run_session(since=since, max_questions=max_questions)


if __name__ == "__main__":
    raise SystemExit(main())
