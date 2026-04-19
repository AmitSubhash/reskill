"""Smoke tests for the newer CLI commands: doctor, topics, next --concept.

These don't assert on the exact UI bytes -- they just make sure the
modules import, the entry points don't crash on common state, and
the core logic produces sensible output.
"""

from __future__ import annotations


def test_doctor_runs_without_crash(capsys):
    from reskill import doctor
    code = doctor.run()
    out = capsys.readouterr().out
    # 12 integration checks
    assert "reSkill doctor" in out
    assert "claude binary" in out
    assert "hook schema" in out
    assert "pacing" in out
    # Exit code 0 (no FAILs) or 1 (some FAILs) -- both acceptable
    assert code in (0, 1)


def test_topics_renders_all_clusters(capsys):
    from reskill import topics_cmd
    code = topics_cmd.run()
    out = capsys.readouterr().out
    assert code == 0
    # At least one cluster name should appear
    assert "caching" in out or "python" in out or "frontend" in out
    # Summary footer
    assert "mastered" in out
    assert "of" in out  # "X mastered ... of 50"


def test_next_concept_filter_finds_real_concept(monkeypatch, capsys):
    """next --concept torch should pick a pytorch question.

    We patch the interactive read to skip immediately so the test
    doesn't hang on stdin.
    """
    from reskill import next_cmd

    # Patch _read_key to always return None so the timeout path fires
    # quickly.
    monkeypatch.setattr(next_cmd, "_read_key", lambda timeout=None: None)
    # Patch sleep-y bits to no-op
    monkeypatch.setattr(next_cmd, "_set_cbreak", lambda: None)
    monkeypatch.setattr(next_cmd, "_restore", lambda saved: None)
    # Force non-tty so we skip raw-mode entirely
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    # 1s timeout so the test completes quickly
    code = next_cmd.run(timeout_seconds=1.0, concept="torch")
    out = capsys.readouterr().out
    assert code in (0, 1)
    # Should mention torch-y concept in the header
    assert "pytorch" in out.lower() or "torch" in out.lower()


def test_next_concept_no_match_reports_error(capsys):
    from reskill import next_cmd
    code = next_cmd.run(timeout_seconds=1.0, concept="thisdoesnotexist12345")
    out = capsys.readouterr().out
    assert code == 1
    assert "no concept" in out.lower() or "topics" in out.lower()


def test_review_queue_pipes_into_state(tmp_path, monkeypatch):
    """record_answer on a wrong answer adds to state.recent_wrongs."""
    from reskill import state as state_mod
    # Redirect STATE_FILE to a tmp path so this test doesn't touch user state
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)

    s = state_mod.State()
    state_mod.record_answer(s, "q_abc123", "caching", correct=False)
    assert "q_abc123" in s.recent_wrongs
    # Second wrong: same ID gets moved to end (de-dupe behavior)
    state_mod.record_answer(s, "q_abc123", "caching", correct=False)
    assert s.recent_wrongs.count("q_abc123") == 1


def test_review_queue_dropped_on_correct(tmp_path, monkeypatch):
    from reskill import state as state_mod
    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)

    s = state_mod.State()
    # Wrong first
    state_mod.record_answer(s, "q_abc", "caching", correct=False)
    assert "q_abc" in s.recent_wrongs
    # Correct second -- state doesn't auto-drop from recent_wrongs,
    # that's the review_cmd's job. But the correct count should update.
    state_mod.record_answer(s, "q_abc", "caching", correct=True)
    cs = s.concepts["caching"]
    assert cs["correct"] == 1
    assert cs["total"] == 2


def test_activity_mtime_cache_returns_consistent_value():
    from reskill.activity import _latest_transcript_mtime, _mtime_cache

    _mtime_cache.clear()
    a = _latest_transcript_mtime("/tmp")
    b = _latest_transcript_mtime("/tmp")
    # Cache hit should return exactly the same value
    assert a == b
