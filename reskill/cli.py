"""
CLI entry points for Claude Code hook integration.

Usage:
  reskill start    # Called by PreToolUse hook -- show quiz
  reskill stop     # Called by PostToolUse hook -- dismiss quiz
  reskill init     # Called by SessionStart hook -- detect stack, load tips
  reskill status   # Show current streak/XP/level
  reskill setup    # Write hooks to ~/.claude/settings.json
  reskill demo     # Run the interactive demo simulation
"""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

from .palette import paint, TEAL, SAGE, ASH, GOLD, VIOLET, BOLD
from .detect import detect_languages, detect_frameworks, get_quiz_topics, detect_summary
from .quiz import SessionState, SAMPLE_QUESTIONS, render_quiz, render_answer

PIDFILE = Path("/tmp/.reskill.pid")
STOPFILE = Path("/tmp/.reskill-stop")

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"


def cmd_setup() -> None:
    """Write reSkill hooks into Claude Code settings."""
    reskill_bin = "python3 -m reskill.cli"

    hooks_config = {
        "PreToolUse": [{
            "matcher": "",
            "hooks": [{"type": "command", "command": f"{reskill_bin} start"}],
        }],
        "PostToolUse": [{
            "matcher": "",
            "hooks": [{"type": "command", "command": f"{reskill_bin} stop"}],
        }],
        "Stop": [{
            "matcher": "",
            "hooks": [{"type": "command", "command": f"{reskill_bin} stop"}],
        }],
    }

    if CLAUDE_SETTINGS.exists():
        settings = json.loads(CLAUDE_SETTINGS.read_text())
    else:
        settings = {}

    existing_hooks = settings.get("hooks", {})
    # Merge (don't overwrite existing hooks for other events)
    for event, hook_list in hooks_config.items():
        existing_hooks[event] = hook_list
    settings["hooks"] = existing_hooks

    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2))
    print(paint("reSkill hooks installed.", SAGE, BOLD))
    print(paint(f"  Written to {CLAUDE_SETTINGS}", ASH))
    print(paint("  Restart Claude Code for hooks to take effect.", ASH))


def cmd_init() -> None:
    """Detect project stack and prepare quiz content."""
    cwd = os.getcwd()
    summary = detect_summary(cwd)
    topics = get_quiz_topics(cwd)

    state = SessionState()
    state.load()

    print(paint("reSkill initialized.", TEAL, BOLD))
    print(paint(f"  {summary}", ASH))
    print(paint(f"  Streak: {state.streak} days | Level {state.level} ({state.level_title}) | {state.xp_total} XP", ASH))

    # Write context-aware tips to spinnerTipsOverride
    tips = _generate_tips(topics)
    if tips:
        _update_spinner_tips(tips)
        print(paint(f"  Loaded {len(tips)} learning tips into spinner.", ASH))


def cmd_start() -> None:
    """Show quiz during tool execution. Called by PreToolUse hook."""
    # Clean up any previous stop signal
    STOPFILE.unlink(missing_ok=True)

    state = SessionState()
    state.load()

    # Pick a question (simple round-robin for now)
    q_idx = state.total_today % len(SAMPLE_QUESTIONS)
    q = SAMPLE_QUESTIONS[q_idx]

    # Fork to show quiz without blocking the hook
    pid = os.fork()
    if pid > 0:
        # Parent: write pidfile and return (hook completes)
        PIDFILE.write_text(str(pid))
        return

    # Child: show interactive quiz
    os.setsid()
    try:
        tty = open("/dev/tty", "r+")
        os.dup2(tty.fileno(), 0)
        os.dup2(tty.fileno(), 1)
        os.dup2(tty.fileno(), 2)
    except OSError:
        os._exit(0)

    # Enter alternate screen
    sys.stdout.write("\033[?1049h")
    sys.stdout.flush()

    import select
    import termios
    import tty as tty_mod
    import itertools

    spinner = itertools.cycle("\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")
    verbs = ["Cogitating", "Ruminating", "Deliberating", "Pondering"]

    # Render quiz
    quiz_lines = render_quiz(q, state)
    for line in quiz_lines:
        print(line)

    # Wait for answer or stop signal
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty_mod.setraw(fd)

    answer = None
    start_time = __import__("time").time()
    try:
        while not STOPFILE.exists():
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)
            if ready:
                ch = sys.stdin.read(1)
                valid = [o.label.lower() for o in q.options]
                if ch.lower() in valid:
                    answer = ch.upper()
                    break

            elapsed = __import__("time").time() - start_time
            remaining = max(0, 30 - elapsed)
            s = next(spinner)
            v = verbs[int(elapsed) % len(verbs)]
            sys.stdout.write(
                f"\r  {paint(s, TEAL)} {paint(f'{v}...', ASH)}"
                f"  {paint(f'{remaining:.0f}s', ASH)}"
            )
            sys.stdout.flush()

            if elapsed > 30:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # Record answer
    if answer:
        correct = answer == q.correct_label
        xp_earned = state.record_answer(correct, q.xp)
        answer_lines = render_answer(q, answer, state, xp_earned)
        sys.stdout.write("\033[2J\033[H")  # clear screen
        for line in answer_lines:
            print(line)
        __import__("time").sleep(1.5)
    else:
        state.total_today += 1

    state.save()

    # Leave alternate screen
    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()

    os._exit(0)


def cmd_stop() -> None:
    """Dismiss quiz. Called by PostToolUse hook."""
    STOPFILE.touch()
    if PIDFILE.exists():
        try:
            pid = int(PIDFILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
        PIDFILE.unlink(missing_ok=True)
    STOPFILE.unlink(missing_ok=True)


def cmd_status() -> None:
    """Show current gamification state."""
    state = SessionState()
    state.load()

    print()
    print(paint("  reSkill Status", TEAL, BOLD))
    print(paint(f"  {'─' * 40}", ASH))
    print(f"  {paint('Streak:', STONE)} {paint(f'{state.streak} days', GOLD, BOLD)}")
    print(f"  {paint('Level:', STONE)} {paint(f'{state.level} ({state.level_title})', VIOLET)}")
    print(f"  {paint('XP:', STONE)} {paint(f'{state.xp_total} total, {state.xp_today} today', ASH)}")
    print(f"  {paint('Today:', STONE)} {paint(f'{state.correct_today}/{state.total_today} correct', SAGE)}")
    print(f"  {paint('Best combo:', STONE)} {paint(f'{state.best_combo}x', GOLD)}")
    print(f"  {paint('Freezes:', STONE)} {paint(f'{state.freezes} remaining', ASH)}")
    print()

    # Mini heatmap placeholder
    cwd = os.getcwd()
    summary = detect_summary(cwd)
    if summary:
        print(paint(f"  Project: {summary}", ASH))
    print()


def _generate_tips(topics: list[str]) -> list[str]:
    """Generate learning tips for spinnerTipsOverride."""
    tip_bank: dict[str, list[str]] = {
        "python": [
            "Python: list.copy() is shallow. Use copy.deepcopy() for nested structures.",
            "Python: Use enumerate() instead of range(len()) for cleaner loops.",
            "Python: f-strings are faster than .format() and % formatting.",
            "Python: defaultdict(list) avoids KeyError when appending to dict values.",
            "Python: := (walrus operator) assigns and returns in one expression.",
        ],
        "git": [
            "Git: git stash -u includes untracked files. git stash only gets tracked.",
            "Git: git rebase -i lets you squash, reorder, and edit commits.",
            "Git: git bisect uses binary search to find the commit that introduced a bug.",
            "Git: git reflog shows ALL ref changes, even after reset --hard.",
        ],
        "fastapi": [
            "FastAPI: Use Depends() for dependency injection. It's testable and composable.",
            "FastAPI: BackgroundTasks run after the response is sent. Use for emails, logs.",
            "FastAPI: Path parameters are required. Query parameters are optional by default.",
        ],
        "react": [
            "React: useMemo() caches computed values. useCallback() caches functions.",
            "React: Keys should be stable IDs, not array indices (unless list is static).",
            "React: useEffect cleanup runs before re-run AND on unmount.",
        ],
        "algorithms": [
            "Big-O: O(log n) means halving the problem each step (binary search).",
            "Big-O: O(n log n) is the theoretical minimum for comparison-based sorting.",
            "Data structures: HashMap average O(1) lookup, worst case O(n) with collisions.",
        ],
        "http-status": [
            "HTTP: 200 OK, 201 Created, 204 No Content, 301 Moved, 400 Bad Request.",
            "HTTP: 401 Unauthorized means not authenticated. 403 Forbidden means not authorized.",
            "HTTP: 429 Too Many Requests. Include Retry-After header in the response.",
        ],
    }

    tips: list[str] = []
    for topic in topics:
        if topic in tip_bank:
            tips.extend(tip_bank[topic])

    return tips[:20]  # Cap at 20 tips


def _update_spinner_tips(tips: list[str]) -> None:
    """Write tips to Claude Code's spinnerTipsOverride setting."""
    if not CLAUDE_SETTINGS.exists():
        return

    try:
        settings = json.loads(CLAUDE_SETTINGS.read_text())
        settings["spinnerTipsOverride"] = {
            "excludeDefault": False,
            "tips": tips,
        }
        CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2))
    except (json.JSONDecodeError, OSError):
        pass


STONE = __import__("reskill.palette", fromlist=["STONE"]).STONE


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: reskill <start|stop|init|status|setup|demo>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "init":
        cmd_init()
    elif cmd == "status":
        cmd_status()
    elif cmd == "setup":
        cmd_setup()
    elif cmd == "demo":
        from .quiz_demo import run
        run()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
