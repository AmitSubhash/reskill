"""PTY wrapper that runs a child process (claude) with inline quizzes.

Design choices that survived iteration:

  1. The quiz is inline in the same terminal (no alt-screen switching --
     that was jarring and left artifacts on exit).
  2. When a quiz appears we CLEAR THE VISIBLE SCREEN (ESC [2J H) and
     render the quiz on a clean canvas. Scrollback is preserved, so the
     user can scroll up to see Claude's earlier output.
  3. While the quiz is on screen we HOLD Claude's new bytes in a buffer
     instead of forwarding them -- otherwise Ink repaints scramble the
     quiz. When the quiz ends, we discard the buffer; Ink repaints cleanly
     on its next frame.
  4. If the answer is CORRECT, we show a brief one-line flash and move on
     (no reveal). If the answer is WRONG or SKIPPED, we show the full
     teaching reveal with the explanation.
  5. A countdown bar at the bottom of the quiz ticks down; if it expires
     the quiz auto-skips.
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

from . import state as state_mod
from .inline_box import (
    render_correct_flash,
    render_countdown_line,
    render_question,
    render_wrong_reveal,
)
from .question import Question, generate_question


# ───────── ANSI helpers ─────────

CURSOR_SHOW = b"\x1b[?25h"
CURSOR_HIDE = b"\x1b[?25l"

_ANSI_RE = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)


# ───────── Thinking / permission detection ─────────

_SPINNER_BYTES = {
    c.encode("utf-8")
    for c in "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
}
_SPINNER_GLYPHS = {
    c.encode("utf-8")
    for c in (
        "\u00b7\u2722\u2733\u2736\u273b\u273d"
        "\u23fa\u25cf\u2219"
        "\u25cb\u25d0\u25c9"
    )
}
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
        "Evaporating", "Fermenting", "Finagling", "Flamb", "Flibbertigibbeting",
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
        "Saut", "Scampering", "Schlepping", "Scurrying", "Seasoning",
        "Shenaniganing", "Shimmying", "Simmering", "Skedaddling", "Sketching",
        "Slithering", "Smooshing", "Spelunking", "Spinning", "Sprouting",
        "Stewing", "Sublimating", "Swirling", "Swooping", "Symbioting",
        "Synthesizing", "Tempering", "Thinking", "Thundering", "Tinkering",
        "Tomfoolering", "Transfiguring", "Transmuting", "Twisting", "Undulating",
        "Unfurling", "Unravelling", "Vibing", "Vibing\u2026", "Waddling",
        "Wandering", "Warping",
        "Whirlpooling", "Whirring", "Whisking", "Wibbling", "Working", "Wrangling",
        "Zesting", "Zigzagging",
        "Reading", "Listing", "Searching", "Analyzing", "Planning", "Editing",
        "Frosting", "Hmm",
        "with low effort", "with medium effort", "with high effort",
        "with xhigh effort", "with max effort",
    )
}

_PERMISSION_MARKERS = [
    re.compile(rb"do you want to (proceed|continue|allow)", re.I),
    re.compile(rb"\(y/n\)|\(y/N\)|\(Y/n\)", re.I),
    re.compile(rb"^\s*1[\.\)]\s*Yes", re.I | re.M),
    re.compile(rb"Yes, and allow", re.I),
    re.compile(rb"Yes, during this session", re.I),
    re.compile(rb"Yes, don't ask again", re.I),
    re.compile(rb"No, and tell Claude", re.I),
]
_PERMISSION_RESOLVED_MARKERS = [
    re.compile(rb"permission denied", re.I),
    re.compile(rb"operation cancelled", re.I),
]
_TURN_END_PATTERNS = [
    re.compile(rb"\b(baked|brewed|churned|cogitated|cooked|crunched|saut\xc3\xa9ed|worked)\s+for\s+\d", re.I),
]


def _is_thinking(data: bytes, recent_raw: bytes) -> bool:
    stripped = _ANSI_RE.sub(b"", data)
    if len(stripped) > 400:
        return False
    if any(s in data for s in _SPINNER_BYTES):
        return True
    if any(g in data for g in _SPINNER_GLYPHS):
        return True
    window = recent_raw[-1500:].lower()
    return any(kw in window for kw in _SPINNER_VERB_KEYWORDS)


def _detect_permission(recent: bytes) -> bool:
    return any(p.search(recent) for p in _PERMISSION_MARKERS)


def _detect_permission_resolved(recent: bytes) -> bool:
    return any(p.search(recent) for p in _PERMISSION_RESOLVED_MARKERS)


def _detect_turn_end(recent: bytes) -> bool:
    return any(p.search(recent[-500:]) for p in _TURN_END_PATTERNS)


# ───────── Config / terminal helpers ─────────


@dataclass
class Config:
    submit_to_quiz_ms: int = 400
    min_seconds_between_quizzes: float = 3.0   # a bit more breathing room
    quiz_time_limit: float = 20.0              # seconds to answer before auto-skip
    correct_flash_ms: int = 1400               # enough time to read "+N xp"
    wrong_reveal_ms: int = 5000                # longer read time on wrong/skipped
    min_prompt_chars: int = 6
    permission_cooldown_ms: int = 8000
    countdown_tick_ms: int = 250               # how often we update countdown


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


# ───────── Main wrapper ─────────


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
    session_muted = (not quizzes_enabled) or (not state.enabled)

    content_buffer = bytearray()
    recent_raw = bytearray()
    typed_chars = 0
    prompt_submitted_at: float = 0
    last_quiz_at: float = 0.0
    suppress_until: float = 0.0
    held_output = bytearray()
    exit_status = 0

    def stdout_write(b: bytes) -> None:
        os.write(sys.stdout.fileno(), b)

    def _build_panel_lines(
        q: Question, st: state_mod.State, seconds_left: float
    ) -> list[str]:
        """Render the quiz as a list of lines that fit in the pinned region.

        We use a compact inline_box layout but return raw lines rather than a
        single string with newlines, so the region can draw them at absolute
        rows without cursor math.
        """
        rendered = render_question(q, streak=st.streak)
        # The render output includes newlines; split and drop the trailing
        # empty line if any.
        lines = rendered.split("\n")
        # Append countdown line
        lines.append(
            render_countdown_line(seconds_left, cfg.quiz_time_limit).replace(
                "\r\x1b[2K", "").strip()
        )
        return lines

    def reset_ink_state() -> None:
        """Make Claude Code's Ink forget its previous render position.

        Why: Ink tracks `previousOutput` and uses cursor-up/erase to repaint
        in place. When we inject a quiz box between Ink's frames, Ink's next
        render reaches up into our box and clobbers it.

        Claude Code's Ink calls `log.reset()` on the SIGCONT signal
        (see src/ink/ink.tsx: `handleResume`). It explicitly says:
          'Physical cursor position is unknown after external terminal
           corruption. Clear displayCursor...'

        We exploit this by sending SIGSTOP+SIGCONT to the child, which fires
        Ink's reset handler. Next Ink render starts fresh from current cursor.
        """
        try:
            os.kill(pid, signal.SIGSTOP)
            # Tiny pause so the signal is delivered before we resume
            time.sleep(0.02)
            os.kill(pid, signal.SIGCONT)
        except (OSError, ProcessLookupError):
            pass

    def run_quiz(q: Question) -> None:
        """Show quiz in a pinned bottom region while Claude's output keeps
        scrolling above. No screen clears. No Ink collision (Ink writes in
        the main region, we own the panel area at the bottom).
        """
        from .region import Region, term_size
        # Render full quiz into lines, figure out height needed.
        initial_panel = _build_panel_lines(q, state, seconds_left=cfg.quiz_time_limit)
        # Reserve enough rows for the whole quiz; cap at ~60% of terminal
        rows, _ = term_size()
        panel_height = min(len(initial_panel) + 1, max(8, rows * 6 // 10))

        region = Region(height=panel_height)
        region.activate(sys.stdout.fileno())

        deadline = time.time() + cfg.quiz_time_limit
        last_draw = 0.0
        label: str | None = None
        skip_reason: str | None = None

        # Initial draw
        region.draw(initial_panel, sys.stdout.fileno())

        while True:
            now = time.time()
            remaining = max(0.0, deadline - now)

            if now - last_draw >= cfg.countdown_tick_ms / 1000.0:
                panel = _build_panel_lines(q, state, seconds_left=remaining)
                region.draw(panel, sys.stdout.fileno())
                last_draw = now

            if remaining <= 0:
                skip_reason = "timeout"
                break

            r, _, _ = select.select(
                [sys.stdin, master], [], [], cfg.countdown_tick_ms / 1000.0
            )
            if master in r:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                if data:
                    recent_raw.extend(data)
                    # Claude's bytes flow through to the main region naturally.
                    stdout_write(data)
                    stripped = _ANSI_RE.sub(b"", data)
                    content_buffer.extend(stripped)
                    if _detect_permission(bytes(recent_raw[-2000:])):
                        skip_reason = "permission"
                        break
                    if _detect_turn_end(bytes(recent_raw[-1000:])):
                        skip_reason = "turn_end"
                        break
            if sys.stdin in r:
                try:
                    data = os.read(sys.stdin.fileno(), 16)
                except OSError:
                    break
                if not data:
                    continue
                ch = data[:1]
                if ch in (b"1", b"2", b"3", b"4"):
                    label = ch.decode()
                    break
                if ch in (b"\x1b", b"x"):
                    skip_reason = "skip"
                    break
                if ch == b"X":
                    skip_reason = "mute"
                    break

        region.deactivate(sys.stdout.fileno())

        if label is not None:
            correct = label == q.correct_label
            xp = state_mod.record_answer(
                state, q.id, q.concept, correct,
            )
            state_mod.save(state)

            if correct:
                flash = render_correct_flash(
                    q, streak=state.streak, combo=state.combo, xp_earned=xp,
                ).encode()
                stdout_write(flash)
                time.sleep(cfg.correct_flash_ms / 1000.0)
            else:
                reveal = render_wrong_reveal(q, chosen=label).encode()
                stdout_write(reveal)
                time.sleep(cfg.wrong_reveal_ms / 1000.0)
        else:
            state_mod.record_skip(state, q.concept)
            state_mod.save(state)
            if skip_reason == "mute":
                nonlocal_set_mute()
            if skip_reason != "permission":
                reveal = render_wrong_reveal(q, chosen=None).encode()
                stdout_write(reveal)
                time.sleep(cfg.wrong_reveal_ms / 1000.0)

        # Flush or discard held bytes depending on what happened
        if skip_reason in ("permission", "turn_end"):
            if held_output:
                stdout_write(bytes(held_output))
        held_output.clear()

        # Reset Ink once more: its next render won't try to reach up into
        # the quiz/reveal we just drew.
        reset_ink_state()

    def nonlocal_set_mute() -> None:
        nonlocal session_muted
        session_muted = True

    try:
        while True:
            now = time.time()

            r, _, _ = select.select([sys.stdin, master], [], [], 0.05)

            if master in r:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                if not data:
                    break

                recent_raw.extend(data)
                if len(recent_raw) > 4000:
                    del recent_raw[:-2000]

                if _detect_permission(bytes(recent_raw[-2000:])):
                    suppress_until = now + cfg.permission_cooldown_ms / 1000.0
                elif _detect_permission_resolved(bytes(recent_raw[-2000:])):
                    suppress_until = min(suppress_until, now + 0.3)

                if _detect_turn_end(bytes(recent_raw[-1000:])):
                    prompt_submitted_at = 0

                # Forward to user's terminal
                stdout_write(data)

                # Accumulate stripped content for question gen
                stripped = _ANSI_RE.sub(b"", data)
                content_buffer.extend(stripped)
                if len(content_buffer) > 20000:
                    del content_buffer[:-10000]

                # Maybe trigger a quiz
                if (
                    not session_muted
                    and prompt_submitted_at > 0
                    and (now - prompt_submitted_at) * 1000 > cfg.submit_to_quiz_ms
                    and now > suppress_until
                    and (now - last_quiz_at) > cfg.min_seconds_between_quizzes
                    and _is_thinking(data, bytes(recent_raw))
                ):
                    seen = set(state.seen_questions)
                    window = content_buffer[-2000:].decode("utf-8", errors="ignore")
                    q = generate_question(window, seen_ids=seen)
                    if q is not None:
                        last_quiz_at = time.time()
                        run_quiz(q)
                        # After quiz ends: loop continues normally.
                        # Reset prompt_submitted_at only if turn is ending.

            if sys.stdin in r:
                try:
                    data = os.read(sys.stdin.fileno(), 1024)
                except OSError:
                    break
                if not data:
                    break

                # Track typed chars / prompt submission
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

                os.write(master, data)

    except KeyboardInterrupt:
        pass
    finally:
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
