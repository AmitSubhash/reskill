"""PTY wrapper that runs a child process (like claude) with inline quizzes.

UX philosophy: the quiz appears WHILE the model is thinking, not after.

Trigger strategy:
  1. Detect that the user has submitted a prompt (Enter on a non-empty line).
  2. Start a "thinking window": let the child print its spinner briefly.
  3. If the child is still producing low-content output (spinner frames),
     that's our chance to inject the quiz box inline.
  4. The user answers (or skips) while the model keeps thinking in the
     background. When the model's real content starts flowing, we have
     already shown the answer reveal and we stay out of the way.

Spinner/low-content detection:
  Claude Code's spinner emits braille dots (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏) plus a verb.
  These repaints contain lots of ANSI control sequences but very few
  "new textual characters" (after we strip ANSI and dedupe repeated runs).
  If we see sustained output with low NEW-content ratio, we're in thinking.

The same logic works for the simulator which emits the same braille frames.
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

from .inline_box import render_question, render_answer_reveal
from .question import Question, generate_question
from . import state as state_mod


# Strip ANSI escapes to measure "content bytes" vs spinner churn
_ANSI_RE = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)

# Braille spinner characters Claude Code / the simulator emit during thinking
_SPINNER_BYTES = {
    c.encode("utf-8")
    for c in "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
}


@dataclass
class Config:
    # How long after the user submits before we try to pop a quiz
    submit_to_quiz_ms: int = 250
    # Minimum time between consecutive quizzes
    min_seconds_between_quizzes: float = 8.0
    # How long the reveal stays before we remove the block flag
    reveal_duration_ms: int = 3500
    # Minimum chars typed before Enter counts as "submitted a prompt"
    min_prompt_chars: int = 6


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


def _looks_like_spinner(data: bytes) -> bool:
    """True if `data` is mostly spinner frames and redraw escapes."""
    has_spinner = any(s in data for s in _SPINNER_BYTES)
    stripped = _ANSI_RE.sub(b"", data)
    # Few visible chars and contains a spinner glyph
    return has_spinner and len(stripped) < 80


def _build_context_window(buffer: bytearray, limit: int = 2000) -> str:
    """Build a text window for template matching from the recent buffer."""
    recent = bytes(buffer[-limit:])
    return recent.decode("utf-8", errors="ignore")


def wrap(argv: list[str]) -> int:
    if not argv:
        print("reskill: no command given", file=sys.stderr)
        return 2

    pid, master = pty.fork()
    if pid == 0:
        # Child
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

    content_buffer = bytearray()   # stripped text only, for question gen

    # User-input state: are they typing a prompt?
    typed_chars: int = 0           # chars typed since last Enter
    prompt_submitted_at: float = 0  # time the user submitted a prompt

    # Quiz state
    pending_q: Question | None = None
    awaiting_answer = False
    last_quiz_at: float = 0.0
    suppress_until: float = 0.0    # don't pop a quiz until this time

    exit_status = 0

    try:
        while True:
            # Remove suppress when reveal elapsed
            now = time.time()
            if suppress_until and now > suppress_until:
                suppress_until = 0.0

            r, _, _ = select.select([sys.stdin, master], [], [], 0.05)

            if master in r:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                if not data:
                    break

                # Always forward to the terminal
                os.write(sys.stdout.fileno(), data)

                # Accumulate stripped content
                stripped = _ANSI_RE.sub(b"", data)
                content_buffer.extend(stripped)

                # Trim buffer
                if len(content_buffer) > 20000:
                    del content_buffer[:-10000]

                # If we saw a user submission recently AND this chunk is
                # spinner-like, this is the moment to inject a quiz.
                now = time.time()
                if (
                    prompt_submitted_at > 0
                    and (now - prompt_submitted_at) * 1000 > cfg.submit_to_quiz_ms
                    and (now - last_quiz_at) > cfg.min_seconds_between_quizzes
                    and not awaiting_answer
                    and not suppress_until
                    and _looks_like_spinner(data)
                ):
                    window = _build_context_window(content_buffer)
                    seen = set(state.seen_questions)
                    q = generate_question(window, seen_ids=seen)
                    if q is not None:
                        pending_q = q
                        awaiting_answer = True
                        last_quiz_at = now
                        # Clear the spinner line so the box sits cleanly
                        os.write(sys.stdout.fileno(), b"\r\x1b[2K")
                        rendered = render_question(q, streak=state.streak)
                        os.write(sys.stdout.fileno(), rendered.encode())
                        # Don't re-pop while answering this one
                        prompt_submitted_at = 0

            if sys.stdin in r:
                try:
                    data = os.read(sys.stdin.fileno(), 1024)
                except OSError:
                    break
                if not data:
                    break

                # If a quiz is showing, intercept answer keys
                if awaiting_answer and pending_q is not None:
                    ch = data[:1]
                    consumed = False
                    if ch in (b"1", b"2", b"3", b"4"):
                        label = ch.decode()
                        correct = label == pending_q.correct_label
                        xp = state_mod.record_answer(
                            state, pending_q.id, pending_q.concept, correct,
                        )
                        state_mod.save(state)
                        rendered = render_answer_reveal(pending_q, label, xp)
                        os.write(sys.stdout.fileno(), rendered.encode())
                        pending_q = None
                        awaiting_answer = False
                        suppress_until = time.time() + cfg.reveal_duration_ms / 1000.0
                        consumed = True
                    elif ch == b"\x1b":
                        state_mod.record_skip(state, pending_q.concept)
                        state_mod.save(state)
                        rendered = render_answer_reveal(pending_q, None, 0)
                        os.write(sys.stdout.fileno(), rendered.encode())
                        pending_q = None
                        awaiting_answer = False
                        suppress_until = time.time() + cfg.reveal_duration_ms / 1000.0
                        consumed = True

                    if consumed:
                        data = data[1:]
                        if not data:
                            continue

                # Track user typing toward a prompt
                for b in data:
                    if b in (0x0d, 0x0a):  # CR or LF
                        if typed_chars >= cfg.min_prompt_chars:
                            prompt_submitted_at = time.time()
                        typed_chars = 0
                    elif b == 0x7f or b == 0x08:  # backspace
                        typed_chars = max(0, typed_chars - 1)
                    elif b >= 0x20 and b < 0x7f:
                        typed_chars += 1
                    # ignore other control chars

                # Forward the keystrokes to the child
                os.write(master, data)

    except KeyboardInterrupt:
        pass
    finally:
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
