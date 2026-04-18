"""Regression tests for the bugs the user actually hit.

These are tests that should have existed BEFORE we tried the tmux dance.
Each one reproduces a real failure mode reported from live use.
"""

from __future__ import annotations

import pytest

from reskill.wrap import (
    _detect_permission,
    _detect_turn_end,
    _is_thinking,
)


class TestSpinnerFalsePositives:
    """Claude's response body must NOT be mistaken for a spinner."""

    def test_bullet_in_response_is_not_a_spinner(self):
        """U+25CF (bullet) is Claude's list marker, not a spinner frame."""
        response_bytes = b"\xe2\x97\x8f The Mongol siege of Baghdad (1258) ended..."
        assert not _is_thinking(response_bytes, response_bytes)

    def test_circle_glyphs_in_response_are_not_spinners(self):
        """Decorative circles (◐ ◉ ○) in text should not trigger."""
        for glyph in ("\u25cb", "\u25d0", "\u25c9"):
            data = f"Some response with {glyph} in it".encode()
            assert not _is_thinking(data, data), (
                f"glyph {glyph!r} is incorrectly flagged as spinner"
            )

    def test_verb_in_response_without_braille_is_not_spinner(self):
        """Words like 'Working' appearing in response text should not fire."""
        data = b"Working on the implementation now..."
        assert not _is_thinking(data, data)

    def test_working_on_trailing_cr_without_braille_not_spinner(self):
        """Even with \\r present, we need an actual spinner glyph."""
        recent = b"\rWorking on code..."
        assert not _is_thinking(b"", recent)


class TestSpinnerTruePositives:
    """The actual Ink spinner pattern MUST be detected."""

    def test_braille_with_verb_and_cr_detected(self):
        """Canonical spinner: \\r + Braille + ' Thinking...'."""
        recent = b"\r\xe2\xa0\x8b Thinking..."  # \r ⠋ Thinking...
        assert _is_thinking(recent, recent)

    def test_sparkle_with_verb_and_cr_detected(self):
        """Sparkle frame variant."""
        recent = b"\r\xe2\x9c\xb3 Cogitating..."  # \r ✳ Cogitating...
        assert _is_thinking(recent, recent)


class TestTurnEndDetection:
    """When Claude finishes, we must see it."""

    def test_worked_for_n_seconds_detected(self):
        assert _detect_turn_end(b"Worked for 42s")

    def test_cogitated_for_detected(self):
        assert _detect_turn_end(b"Cogitated for 12s")

    def test_no_turn_end_in_streaming_text(self):
        assert not _detect_turn_end(b"The worker process has finished...")


class TestPermissionDetection:
    def test_numeric_yes_no_detected(self):
        text = b"Do you want to proceed?\n  1. Yes\n  2. No"
        assert _detect_permission(text)

    def test_yes_and_allow_detected(self):
        assert _detect_permission(b"  1. Yes, and allow")

    def test_normal_prose_is_not_a_permission(self):
        assert not _detect_permission(b"The function returns yes or no")
