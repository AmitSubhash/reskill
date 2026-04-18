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

# Braille spinner frames Claude Code emits while thinking
_SPINNER_BYTES = {
    c.encode("utf-8")
    for c in "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
}

# Permission prompt detection patterns
_PERMISSION_MARKERS = [
    re.compile(rb"do you want to proceed", re.I),
    re.compile(rb"do you want to continue", re.I),
    re.compile(rb"\(y/n\)|\(y/N\)|\(Y/n\)", re.I),
    re.compile(rb"1\.\s*yes", re.I),
    re.compile(rb"press\s+\d\s+to", re.I),
]

# When we see these, the permission prompt has been resolved
_PERMISSION_RESOLVED_MARKERS = [
    re.compile(rb"proceeding", re.I),
    re.compile(rb"permission denied", re.I),
    re.compile(rb"cancelled", re.I),
]


@dataclass
class Config:
    # Brief warm-up before the first quiz so the user sees Claude started
    submit_to_quiz_ms: int = 300
    # Cooldown between consecutive quizzes within the same thinking window
    min_seconds_between_quizzes: float = 2.5
    # How long the answer reveal stays before we consider the next quiz
    reveal_duration_ms: int = 3000
    # Minimum chars typed before Enter counts as a prompt submission
    min_prompt_chars: int = 6
    # How long after seeing a permission prompt to stay suppressed
    permission_cooldown_ms: int = 8000


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
    """True if `data` is mostly spinner frames (low content churn)."""
    has_spinner = any(s in data for s in _SPINNER_BYTES)
    stripped = _ANSI_RE.sub(b"", data)
    return has_spinner and len(stripped) < 80


def _detect_permission_prompt(recent_text: bytes) -> bool:
    """Check the recent output for hints of an interactive permission prompt."""
    return any(pat.search(recent_text) for pat in _PERMISSION_MARKERS)


def _detect_permission_resolved(recent_text: bytes) -> bool:
    return any(pat.search(recent_text) for pat in _PERMISSION_RESOLVED_MARKERS)


def _build_context_window(buffer: bytearray, limit: int = 2000) -> str:
    recent = bytes(buffer[-limit:])
    return recent.decode("utf-8", errors="ignore")


def wrap(argv: list[str]) -> int:
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

    content_buffer = bytearray()   # stripped text for question gen
    recent_raw = bytearray()       # raw recent output for permission detection

    # User typing state
    typed_chars: int = 0
    prompt_submitted_at: float = 0  # timestamp, 0 == not currently thinking

    # Quiz state
    pending_q: Question | None = None
    awaiting_answer = False
    last_quiz_at: float = 0.0
    reveal_until: float = 0.0      # during this window don't show another quiz
    suppress_quizzes_until: float = 0.0  # permission prompt cooldown

    # Output buffering while a quiz is on screen
    pending_output = bytearray()

    exit_status = 0

    def flush_pending_output() -> None:
        if pending_output:
            os.write(sys.stdout.fileno(), bytes(pending_output))
            pending_output.clear()

    try:
        while True:
            now = time.time()
            if reveal_until and now > reveal_until:
                reveal_until = 0.0

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

                # Detect permission prompt
                if _detect_permission_prompt(bytes(recent_raw[-2000:])):
                    suppress_quizzes_until = now + cfg.permission_cooldown_ms / 1000.0
                    # If a quiz is live, abort it so keys reach Claude
                    if awaiting_answer and pending_q is not None:
                        state_mod.record_skip(state, pending_q.concept)
                        state_mod.save(state)
                        pending_q = None
                        awaiting_answer = False
                        flush_pending_output()
                elif _detect_permission_resolved(bytes(recent_raw[-2000:])):
                    suppress_quizzes_until = min(
                        suppress_quizzes_until, now + 0.5
                    )

                # If we're waiting for an answer, buffer real content
                # (let spinner frames through to the user still sees Claude alive)
                if awaiting_answer and not _looks_like_spinner(data):
                    pending_output.extend(data)
                else:
                    os.write(sys.stdout.fileno(), data)

                # Accumulate stripped content for question generation
                stripped = _ANSI_RE.sub(b"", data)
                content_buffer.extend(stripped)
                if len(content_buffer) > 20000:
                    del content_buffer[:-10000]

                # Quiz trigger: in a thinking window, not in permission,
                # not mid-quiz, not in reveal cooldown
                if (
                    prompt_submitted_at > 0
                    and (now - prompt_submitted_at) * 1000 > cfg.submit_to_quiz_ms
                    and now > suppress_quizzes_until
                    and not awaiting_answer
                    and now > reveal_until
                    and (now - last_quiz_at) > cfg.min_seconds_between_quizzes
                    and _looks_like_spinner(data)
                ):
                    window = _build_context_window(content_buffer)
                    seen = set(state.seen_questions)
                    q = generate_question(window, seen_ids=seen)
                    if q is not None:
                        pending_q = q
                        awaiting_answer = True
                        last_quiz_at = now
                        # Clear the current spinner line so the box sits cleanly
                        os.write(sys.stdout.fileno(), b"\r\x1b[2K")
                        rendered = render_question(q, streak=state.streak)
                        os.write(sys.stdout.fileno(), rendered.encode())

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
                        reveal_until = time.time() + cfg.reveal_duration_ms / 1000.0
                        flush_pending_output()
                        consumed = True
                    elif ch == b"\x1b":
                        state_mod.record_skip(state, pending_q.concept)
                        state_mod.save(state)
                        rendered = render_answer_reveal(pending_q, None, 0)
                        os.write(sys.stdout.fileno(), rendered.encode())
                        pending_q = None
                        awaiting_answer = False
                        reveal_until = time.time() + cfg.reveal_duration_ms / 1000.0
                        flush_pending_output()
                        consumed = True

                    if consumed:
                        data = data[1:]
                        if not data:
                            continue

                # Track typing toward prompt submission
                for b in data:
                    if b in (0x0d, 0x0a):
                        if typed_chars >= cfg.min_prompt_chars:
                            prompt_submitted_at = time.time()
                            last_quiz_at = 0.0  # reset cooldown for new turn
                        typed_chars = 0
                    elif b == 0x7f or b == 0x08:
                        typed_chars = max(0, typed_chars - 1)
                    elif 0x20 <= b < 0x7f:
                        typed_chars += 1

                os.write(master, data)

    except KeyboardInterrupt:
        pass
    finally:
        # Flush any buffered output and clean up
        flush_pending_output()
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
