"""Guardrails against the specific bugs the user hit in live use.

These are boring tests. They exist so a future refactor doesn't quietly
re-introduce one of the regressions we already paid to fix.
"""

from __future__ import annotations

import inspect

from reskill import quiz_panel, session


def test_session_uses_cbreak_not_raw():
    """tty.setraw disables OPOST -- newlines became LF-only and staircased
    the reveal off-screen ("stuck after skip"). Must use cbreak."""
    src = inspect.getsource(session)
    assert "tty.setcbreak" in src, "session must enter cbreak mode"
    assert "tty.setraw(" not in src, (
        "tty.setraw disables OPOST; newlines won't render as CRLF. "
        "Use tty.setcbreak instead -- this caused the stuck-after-skip bug."
    )


def test_quiz_panel_uses_cbreak_not_raw():
    src = inspect.getsource(quiz_panel)
    assert "tty.setcbreak" in src
    assert "tty.setraw(" not in src


def test_session_has_continue_hint():
    """After a reveal, user must see an explicit hint, not just sit
    staring at the box wondering if they're stuck."""
    src = inspect.getsource(session)
    assert "_wait_for_continue" in src


def test_wrap_spinner_glyphs_exclude_bullet():
    """U+25CF (●) is Claude's response bullet. Putting it in spinner
    glyphs caused quizzes to fire on every response list item."""
    from reskill import wrap
    bullet = "\u25cf".encode("utf-8")
    assert bullet not in wrap._SPINNER_GLYPHS, (
        "bullet U+25CF must not be a spinner glyph; it's a response marker"
    )


def test_wrap_spinner_requires_cr_or_returns_false():
    """Without a carriage return in recent data, we must not fire.
    Ink's spinner updates in place via \\r; pure streaming response text
    never has \\r, so absence is a hard negative signal."""
    from reskill.wrap import _is_thinking
    # A response that LOOKS spinner-ish (has Braille + verb) but no \r.
    data = b"\xe2\xa0\x8b Working on the plan"
    assert not _is_thinking(data, data)


def test_wrap_one_quiz_per_turn_semantics():
    """After a quiz runs, prompt_submitted_at must be cleared so the
    same turn can't trigger another. This is enforced in wrap.py by
    setting it to 0 after run_quiz returns."""
    from reskill import wrap
    src = inspect.getsource(wrap)
    # The only place run_quiz() is called in the main loop should be
    # immediately followed by `prompt_submitted_at = 0`.
    post = src.split("run_quiz(q)", 1)[1]
    assert "prompt_submitted_at = 0" in post[:500], (
        "Main loop must clear prompt_submitted_at after a quiz "
        "runs to prevent the same turn triggering another."
    )
