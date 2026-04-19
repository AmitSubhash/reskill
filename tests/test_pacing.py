"""Pacing-gate tests. Each asserts one evidence-cited rule."""

from __future__ import annotations

from reskill.pacing import (
    MAX_QUIZZES_PER_DAY,
    MAX_QUIZZES_PER_HOUR,
    MIN_SECONDS_AFTER_THINKING_START,
    MIN_SECONDS_BEFORE_SAME_CONCEPT,
    MIN_SECONDS_BETWEEN_QUIZZES,
    PacingState,
    can_fire_now,
    note_quiz_finished,
    note_quiz_served,
    note_thinking_started,
    seconds_until_next_allowed,
)


NOW = 1_000_000.0


def test_gate_closed_in_first_3s_of_thinking():
    ps = PacingState()
    note_thinking_started(ps, now=NOW)
    r = can_fire_now(ps, now=NOW + 1.0)
    assert not r.allowed
    assert "debounce" in r.reason


def test_gate_opens_after_debounce():
    ps = PacingState()
    note_thinking_started(ps, now=NOW)
    r = can_fire_now(ps, now=NOW + MIN_SECONDS_AFTER_THINKING_START + 0.1)
    assert r.allowed, r


def test_min_gap_between_quizzes():
    ps = PacingState()
    note_quiz_served(ps, "caching", now=NOW)
    note_quiz_finished(ps, now=NOW + 30)
    # 1 second after finish: should still be blocked regardless of
    # the configured min-gap (as long as it's >1s, which it always is).
    r = can_fire_now(ps, now=NOW + 30 + 1)
    assert not r.allowed
    assert "min-gap" in r.reason


def test_gate_opens_after_min_gap():
    ps = PacingState()
    note_quiz_served(ps, "caching", now=NOW)
    note_quiz_finished(ps, now=NOW + 30)
    r = can_fire_now(ps, now=NOW + 30 + MIN_SECONDS_BETWEEN_QUIZZES + 1)
    assert r.allowed, r


def test_hourly_cap():
    # With the env-tunable defaults raised to effectively-unlimited,
    # exercise the cap logic by overriding the env var inside the test.
    import os
    os.environ["RESKILL_MAX_PER_HOUR"] = "5"
    # Reload the module so the constant picks up the override.
    import importlib
    import reskill.pacing as pm
    importlib.reload(pm)
    try:
        ps = pm.PacingState()
        for i in range(pm.MAX_QUIZZES_PER_HOUR):
            pm.note_quiz_served(ps, f"c{i}", now=NOW + i * 120)
        pm.note_quiz_finished(ps, now=NOW + pm.MAX_QUIZZES_PER_HOUR * 120)
        r = pm.can_fire_now(
            ps, now=NOW + pm.MAX_QUIZZES_PER_HOUR * 120 + 91,
        )
        assert not r.allowed
        assert "hourly" in r.reason
    finally:
        del os.environ["RESKILL_MAX_PER_HOUR"]
        importlib.reload(pm)


def test_daily_cap():
    import os
    import importlib
    os.environ["RESKILL_MAX_PER_HOUR"] = "9999"  # get out of the way
    os.environ["RESKILL_MAX_PER_DAY"] = "5"
    import reskill.pacing as pm
    importlib.reload(pm)
    try:
        ps = pm.PacingState()
        spacing = 86400 // (pm.MAX_QUIZZES_PER_DAY + 1)
        for i in range(pm.MAX_QUIZZES_PER_DAY):
            pm.note_quiz_served(ps, f"c{i}", now=NOW + i * spacing)
        pm.note_quiz_finished(ps, now=NOW + pm.MAX_QUIZZES_PER_DAY * spacing)
        r = pm.can_fire_now(
            ps,
            now=NOW
            + pm.MAX_QUIZZES_PER_DAY * spacing
            + pm.MIN_SECONDS_BETWEEN_QUIZZES
            + 5,
        )
        assert not r.allowed
        assert "daily" in r.reason or "hourly" in r.reason
    finally:
        del os.environ["RESKILL_MAX_PER_HOUR"]
        del os.environ["RESKILL_MAX_PER_DAY"]
        importlib.reload(pm)


def test_same_concept_cooldown():
    ps = PacingState()
    note_quiz_served(ps, "caching", now=NOW)
    note_quiz_finished(ps, now=NOW + 30)
    # Wait long enough to pass the 90s min-gap so we're testing the
    # per-concept cooldown specifically, not the global gap.
    future = NOW + 30 + MIN_SECONDS_BETWEEN_QUIZZES + 5
    r = can_fire_now(ps, candidate_concept="caching", now=future)
    assert not r.allowed
    assert "same-concept" in r.reason
    # A different concept is allowed at the same moment.
    r2 = can_fire_now(ps, candidate_concept="async", now=future)
    assert r2.allowed, r2


def test_same_concept_opens_after_10_min():
    ps = PacingState()
    note_quiz_served(ps, "caching", now=NOW)
    note_quiz_finished(ps, now=NOW + 30)
    r = can_fire_now(
        ps,
        candidate_concept="caching",
        now=NOW + MIN_SECONDS_BEFORE_SAME_CONCEPT + 1,
    )
    assert r.allowed


def test_seconds_until_next_allowed_zero_on_fresh_state():
    assert seconds_until_next_allowed(PacingState(), now=NOW) == 0.0


def test_seconds_until_next_reports_remaining_gap():
    ps = PacingState()
    note_quiz_served(ps, "caching", now=NOW)
    note_quiz_finished(ps, now=NOW + 30)
    # Check the reported remaining is (min_gap - elapsed), regardless of
    # what min_gap is configured to (env-tunable since v0.2).
    elapsed_since_finish = 1.0
    remaining = seconds_until_next_allowed(
        ps, now=NOW + 30 + elapsed_since_finish,
    )
    expected = MIN_SECONDS_BETWEEN_QUIZZES - elapsed_since_finish
    assert abs(remaining - expected) < 2
