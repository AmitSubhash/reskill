"""PTY wrapper that runs a child process (like claude) with inline quizzes.

Behavior rules:
  * While the child is in a "thinking" state (spinner dominates output),
    we inject quizzes back-to-back with a short cooldown.
  * While the user is mid-answer, non-spinner output from the child is
    BUFFERED -- we don't interleave Claude's response with the quiz box.
    As soon as the user answers (or skips), we flush the buffer.
  * When the child shows a permission prompt ("Do you want to proceed?"
    with numbered options), we ENTIRELY suppress quiz injection until
    the prompt is resolved. Otherwise the user's 1/2/3 answer would go
    to the wrong thing.

The wrapper is transparent: every byte of child output reaches the terminal
in order, and every user keystroke (except those consumed by an active
quiz) reaches the child.
"""

from __future__ import annotations

import os
import pty
import re
import select
import shutil
import signal
import struct
import sys
import termios
import time
import tty
from dataclasses import dataclass

from .inline_box import render_answer_reveal, render_question
from .question import Question, generate_question
from . import state as state_mod


# ANSI escape / OSC stripper
_ANSI_RE = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)

# Braille spinner frames (used by demo.py and some older Claude Code versions)
_SPINNER_BYTES = {
    c.encode("utf-8")
    for c in "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
}

# Claude Code v2.1.x spinner glyphs (src/components/Spinner/utils.ts)
# plus status bullets and effort indicators (src/constants/figures.ts)
_SPINNER_GLYPHS = {
    c.encode("utf-8")
    for c in (
        "\u00b7\u2722\u2733\u2736\u273b\u273d"   # ·  ✢  ✳  ✶  ✻  ✽
        "\u23fa"                                  # ⏺ BLACK_CIRCLE (macOS)
        "\u25cf"                                  # ●  BLACK_CIRCLE (linux) / EFFORT_HIGH
        "\u2219"                                  # ∙ BULLET_OPERATOR
        "\u25cb\u25d0\u25c9"                      # ○ ◐ ◉ effort low/med/max
    )
}

# Past-tense verbs shown when a turn completes (src/constants/turnCompletionVerbs.ts)
# e.g. "Worked for 5s" -- means Claude has finished thinking.
_TURN_END_PATTERNS = [
    re.compile(rb"\b(baked|brewed|churned|cogitated|cooked|crunched|saut\xc3\xa9ed|worked)\s+for\s+\d", re.I),
]

# The full 170+ spinner verb list from Claude Code's leaked source.
# Source: yasasbanukaofficial/claude-code src/constants/spinnerVerbs.ts
# We match LOWERCASED keywords against the recent output window.
_SPINNER_VERB_KEYWORDS = {
    kw.lower().encode("utf-8")
    for kw in (
        "Accomplishing", "Actioning", "Actualizing", "Architecting", "Baking",
        "Beaming", "Beboppin", "Befuddling", "Billowing", "Blanching",
        "Bloviating", "Boogieing", "Boondoggling", "Booping", "Bootstrapping",
        "Brewing", "Bunning", "Burrowing", "Calculating", "Canoodling",
        "Caramelizing", "Cascading", "Catapulting", "Cerebrating", "Channeling",
        "Choreographing", "Churning", "Clauding", "Coalescing", "Cogitating",
        "Combobulating", "Composing", "Computing", "Concocting", "Considering",
        "Contemplating", "Cooking", "Crafting", "Creating", "Crunching",
        "Crystallizing", "Cultivating", "Deciphering", "Deliberating",
        "Determining", "Discombobulating", "Doodling", "Drizzling", "Ebbing",
        "Effecting", "Elucidating", "Embellishing", "Enchanting", "Envisioning",
        "Evaporating", "Fermenting", "Finagling", "Flambéing", "Flibbertigibbeting",
        "Flowing", "Flummoxing", "Fluttering", "Forging", "Forming", "Frolicking",
        "Frosting", "Gallivanting", "Galloping", "Garnishing", "Generating",
        "Gesticulating", "Germinating", "Gitifying", "Grooving", "Gusting",
        "Harmonizing", "Hashing", "Hatching", "Herding", "Honking",
        "Hullaballooing", "Hyperspacing", "Ideating", "Imagining", "Improvising",
        "Incubating", "Inferring", "Infusing", "Ionizing", "Jitterbugging",
        "Julienning", "Kneading", "Leavening", "Levitating", "Lollygagging",
        "Manifesting", "Marinating", "Meandering", "Metamorphosing", "Misting",
        "Moonwalking", "Moseying", "Mulling", "Mustering", "Musing", "Nebulizing",
        "Nesting", "Newspapering", "Noodling", "Nucleating", "Orbiting",
        "Orchestrating", "Osmosing", "Perambulating", "Percolating", "Perusing",
        "Philosophising", "Photosynthesizing", "Pollinating", "Pondering",
        "Pontificating", "Pouncing", "Precipitating", "Prestidigitating",
        "Processing", "Proofing", "Propagating", "Puttering", "Puzzling",
        "Quantumizing", "Recombobulating", "Reticulating", "Roosting", "Ruminating",
        "Sautéing", "Scampering", "Schlepping", "Scurrying", "Seasoning",
        "Shenaniganing", "Shimmying", "Simmering", "Skedaddling", "Sketching",
        "Slithering", "Smooshing", "Spelunking", "Spinning", "Sprouting",
        "Stewing", "Sublimating", "Swirling", "Swooping", "Symbioting",
        "Synthesizing", "Tempering", "Thinking", "Thundering", "Tinkering",
        "Tomfoolering", "Transfiguring", "Transmuting", "Twisting", "Undulating",
        "Unfurling", "Unravelling", "Vibing", "Waddling", "Wandering", "Warping",
        "Whirlpooling", "Whirring", "Whisking", "Wibbling", "Working", "Wrangling",
        "Zesting", "Zigzagging",
        # Status verbs used during tool execution
        "Reading", "Listing", "Searching", "Analyzing", "Planning", "Editing",
        # Effort suffix (the "(thinking with xhigh effort)" text)
        "with low effort", "with medium effort", "with high effort",
        "with xhigh effort", "with max effort",
    )
}

# Permission prompt detection patterns.
# Source: yasasbanukaofficial/claude-code src/components/permissions/*.tsx
# Claude Code uses select-menu prompts with 'Yes' / 'Yes, and ...' / 'No' labels.
_PERMISSION_MARKERS = [
    re.compile(rb"do you want to (proceed|continue|allow)", re.I),
    re.compile(rb"\(y/n\)|\(y/N\)|\(Y/n\)", re.I),
    # Numbered option lists with "Yes" or "No" as option 1
    re.compile(rb"^\s*1[\.\)]\s*Yes", re.I | re.M),
    # Claude Code's specific option labels
    re.compile(rb"Yes, and allow", re.I),
    re.compile(rb"Yes, during this session", re.I),
    re.compile(rb"Yes, don't ask again", re.I),
    re.compile(rb"No, and tell Claude", re.I),
]

# When we see these, the permission prompt has been resolved
_PERMISSION_RESOLVED_MARKERS = [
    re.compile(rb"permission denied", re.I),
    re.compile(rb"operation cancelled", re.I),
]


@dataclass
class Config:
    # Brief warm-up before the first quiz so the user sees Claude started
    submit_to_quiz_ms: int = 300
    # Cooldown between consecutive quizzes within the same thinking window
    min_seconds_between_quizzes: float = 2.5
    # How long the answer reveal stays on the alt screen before we switch back
    reveal_duration_ms: int = 3000
    # Minimum chars typed before Enter counts as a prompt submission
    min_prompt_chars: int = 6
    # How long after seeing a permission prompt to stay suppressed
    permission_cooldown_ms: int = 8000


# ANSI escape sequences for alternate screen buffer (what vim/htop use).
ALT_SCREEN_ENTER = b"\x1b[?1049h\x1b[H"
ALT_SCREEN_EXIT = b"\x1b[?1049l"
CURSOR_HIDE = b"\x1b[?25l"
CURSOR_SHOW = b"\x1b[?25h"


def _set_raw() -> list[int]:
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setraw(fd)
    return saved  # type: ignore[return-value]


def _restore(saved: list[int]) -> None:
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSADRAIN, saved)  # type: ignore[arg-type]


def _get_winsize() -> tuple[int, int]:
    size = shutil.get_terminal_size()
    return size.lines, size.columns


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    TIOCSWINSZ = getattr(termios, "TIOCSWINSZ", 0x5414)
    size = struct.pack("HHHH", rows, cols, 0, 0)
    try:
        import fcntl
        fcntl.ioctl(fd, TIOCSWINSZ, size)
    except Exception:
        pass


def _is_thinking(data: bytes, recent_raw: bytes) -> bool:
    """Heuristic: is the child currently in a 'thinking' state?

    True if any of:
      - braille spinner frame (demo / older CC)
      - Claude Code v2.1.x glyph (· ✢ ✳ ✶ ✻ ✽)
      - one of the 170+ known spinner verbs appears in recent output
    AND the new chunk is small (not a burst of real response tokens).
    """
    stripped = _ANSI_RE.sub(b"", data)
    if len(stripped) > 400:
        return False

    if any(s in data for s in _SPINNER_BYTES):
        return True
    if any(g in data for g in _SPINNER_GLYPHS):
        return True

    # Check the recent window for any spinner verb, case-insensitive.
    window = recent_raw[-1500:].lower()
    return any(kw in window for kw in _SPINNER_VERB_KEYWORDS)


def _detect_permission_prompt(recent_text: bytes) -> bool:
    """Check the recent output for hints of an interactive permission prompt."""
    return any(pat.search(recent_text) for pat in _PERMISSION_MARKERS)


def _detect_permission_resolved(recent_text: bytes) -> bool:
    return any(pat.search(recent_text) for pat in _PERMISSION_RESOLVED_MARKERS)


def _detect_turn_end(recent_text: bytes) -> bool:
    """True when Claude's past-tense completion verb appears ('Worked for 5s')."""
    return any(pat.search(recent_text[-500:]) for pat in _TURN_END_PATTERNS)


def _build_context_window(buffer: bytearray, limit: int = 2000) -> str:
    recent = bytes(buffer[-limit:])
    return recent.decode("utf-8", errors="ignore")


def wrap(argv: list[str], quizzes_enabled: bool = True) -> int:
    if not argv:
        print("reskill: no command given", file=sys.stderr)
        return 2

    pid, master = pty.fork()
    if pid == 0:
        os.execvp(argv[0], argv)
        os._exit(1)

    rows, cols = _get_winsize()
    _set_winsize(master, rows, cols)

    saved_tty = None
    if sys.stdin.isatty():
        saved_tty = _set_raw()

    def on_resize(signum, frame):
        r, c = _get_winsize()
        _set_winsize(master, r, c)

    signal.signal(signal.SIGWINCH, on_resize)

    cfg = Config()
    state = state_mod.load()

    # Combined enablement:
    #  - quizzes_enabled: CLI flag (--no-quiz) for this invocation
    #  - state.enabled:    persistent global toggle (`reskill pause`/`resume`)
    #  - session_muted:    keyboard shortcut `X` during session mutes for rest of run
    session_muted = (not quizzes_enabled) or (not state.enabled)

    content_buffer = bytearray()   # stripped text for question gen
    recent_raw = bytearray()       # raw recent output for permission detection

    # User typing state
    typed_chars: int = 0
    prompt_submitted_at: float = 0  # timestamp, 0 == not currently thinking

    # Quiz state
    pending_q: Question | None = None
    awaiting_answer = False
    last_quiz_at: float = 0.0
    reveal_until: float = 0.0           # during this window don't show another quiz
    suppress_quizzes_until: float = 0.0  # permission prompt cooldown

    # When a quiz is visible, we HOLD Claude's new output (so Ink's repaints
    # don't scramble our box). After the reveal, we flush the most recent state.
    held_output = bytearray()

    exit_status = 0

    def flush_held_output() -> None:
        if not held_output:
            return
        # Don't replay the whole buffer -- just write a screen clear + cursor home
        # so Ink can re-paint fresh on its next frame.
        # But CC's Ink cursor accounting is line-relative, so we just discard
        # and let its next cycle redraw.
        held_output.clear()

    try:
        while True:
            now = time.time()
            if reveal_until and now > reveal_until:
                reveal_until = 0.0
                # Reveal window ended -- flush any held output and let Ink repaint
                flush_held_output()

            r, _, _ = select.select([sys.stdin, master], [], [], 0.05)

            if master in r:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                if not data:
                    break

                # Keep a rolling window of raw output for permission detection
                recent_raw.extend(data)
                if len(recent_raw) > 4000:
                    del recent_raw[:-2000]

                # Permission prompt takes priority -- exit any in-flight quiz
                if _detect_permission_prompt(bytes(recent_raw[-2000:])):
                    suppress_quizzes_until = now + cfg.permission_cooldown_ms / 1000.0
                    if awaiting_answer and pending_q is not None:
                        state_mod.record_skip(state, pending_q.concept)
                        state_mod.save(state)
                        pending_q = None
                        awaiting_answer = False
                        flush_held_output()
                elif _detect_permission_resolved(bytes(recent_raw[-2000:])):
                    suppress_quizzes_until = min(
                        suppress_quizzes_until, now + 0.5
                    )

                # Turn completion: stop popping new quizzes for this turn
                if _detect_turn_end(bytes(recent_raw[-1000:])):
                    prompt_submitted_at = 0

                # While a quiz/reveal is visible, HOLD Claude's new bytes so
                # Ink's repaints don't scramble our box. We'll discard them
                # when the reveal ends -- Ink redraws fresh on its next frame.
                if awaiting_answer or reveal_until > now:
                    held_output.extend(data)
                    if len(held_output) > 50000:
                        del held_output[:-25000]
                else:
                    os.write(sys.stdout.fileno(), data)

                # Accumulate stripped content for question generation
                stripped = _ANSI_RE.sub(b"", data)
                content_buffer.extend(stripped)
                if len(content_buffer) > 20000:
                    del content_buffer[:-10000]

                # Quiz trigger
                if (
                    not session_muted
                    and prompt_submitted_at > 0
                    and (now - prompt_submitted_at) * 1000 > cfg.submit_to_quiz_ms
                    and now > suppress_quizzes_until
                    and not awaiting_answer
                    and now > reveal_until
                    and (now - last_quiz_at) > cfg.min_seconds_between_quizzes
                    and _is_thinking(data, bytes(recent_raw))
                ):
                    window = _build_context_window(content_buffer)
                    seen = set(state.seen_questions)
                    q = generate_question(window, seen_ids=seen)
                    if q is not None:
                        pending_q = q
                        awaiting_answer = True
                        last_quiz_at = now
                        # Render the quiz as one atomic write so Ink can't
                        # interleave its repaints into the middle of our box.
                        rendered = render_question(q, streak=state.streak).encode()
                        # Prefix with a clear of the current line (where the
                        # spinner is) so the box has a clean starting point.
                        os.write(sys.stdout.fileno(), b"\r\x1b[2K" + rendered)

            if sys.stdin in r:
                try:
                    data = os.read(sys.stdin.fileno(), 1024)
                except OSError:
                    break
                if not data:
                    break

                # If a quiz is active, intercept answer keys
                if awaiting_answer and pending_q is not None:
                    ch = data[:1]
                    consumed = False
                    label: str | None = None
                    skip_reason: str | None = None

                    if ch in (b"1", b"2", b"3", b"4"):
                        label = ch.decode()
                        consumed = True
                    elif ch in (b"\x1b", b"x"):
                        skip_reason = "skip"
                        consumed = True
                    elif ch == b"X":
                        skip_reason = "mute"
                        consumed = True

                    if consumed:
                        if label is not None:
                            correct = label == pending_q.correct_label
                            xp = state_mod.record_answer(
                                state, pending_q.id, pending_q.concept, correct,
                            )
                            rendered = render_answer_reveal(pending_q, label, xp).encode()
                        else:
                            state_mod.record_skip(state, pending_q.concept)
                            rendered = render_answer_reveal(pending_q, None, 0).encode()
                            if skip_reason == "mute":
                                session_muted = True
                        state_mod.save(state)

                        # Render the reveal inline, single atomic write
                        os.write(sys.stdout.fileno(), rendered)
                        if skip_reason == "mute":
                            from .palette import paint, ASH, DIM
                            notice = paint(
                                "  reskill muted for this session -- run `reskill resume` to re-enable\n",
                                ASH, DIM,
                            )
                            os.write(sys.stdout.fileno(), notice.encode())

                        pending_q = None
                        awaiting_answer = False
                        # Keep holding Claude's output until reveal window ends
                        reveal_until = time.time() + cfg.reveal_duration_ms / 1000.0

                        data = data[1:]
                        if not data:
                            continue

                # Track typing toward prompt submission
                for b in data:
                    if b in (0x0d, 0x0a):
                        if typed_chars >= cfg.min_prompt_chars:
                            prompt_submitted_at = time.time()
                            last_quiz_at = 0.0
                        typed_chars = 0
                    elif b == 0x7f or b == 0x08:
                        typed_chars = max(0, typed_chars - 1)
                    elif 0x20 <= b < 0x7f:
                        typed_chars += 1

                # Pass keystrokes to Claude (but not while quiz is showing)
                if not awaiting_answer:
                    os.write(master, data)

    except KeyboardInterrupt:
        pass
    finally:
        # Ensure cursor is visible (in case we somehow stranded it hidden)
        try:
            os.write(sys.stdout.fileno(), CURSOR_SHOW)
        except OSError:
            pass
        if saved_tty is not None:
            _restore(saved_tty)
        try:
            os.close(master)
        except OSError:
            pass
        try:
            _, status = os.waitpid(pid, 0)
            exit_status = os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1
        except ChildProcessError:
            pass

    return exit_status
