"""Tests for the LLM-gen pipeline.

We mock the subprocess call to `claude -p` so these tests don't
actually talk to Claude. The real integration test is
`reskill gen` run manually.
"""

from __future__ import annotations

import json
from unittest import mock

from reskill import llm_gen
from reskill.llm_gen import (
    GenResult,
    _extract_json,
    _parse_question,
    generate_from_code,
)


GOOD_PAYLOAD = {
    "concept": "async-pitfall",
    "format": "gotcha",
    "prompt": "Why is this function serial even though it uses await?",
    "code": "async def f():\n    for u in urls:\n        r = await fetch(u)",
    "options": [
        {"text": "`async for` is required", "correct": False},
        {"text": "await in a loop runs sequentially; use gather", "correct": True},
        {"text": "httpx is sync-only", "correct": False},
        {"text": "need asyncio.run() wrapper", "correct": False},
    ],
    "explanation": "await suspends until the call completes; next iteration waits. asyncio.gather runs concurrently.",
}


def test_parse_question_accepts_valid_payload():
    q = _parse_question(GOOD_PAYLOAD)
    assert q.prompt.startswith("Why is this function")
    assert len(q.options) == 4
    assert sum(1 for o in q.options if o.correct) == 1
    assert q.correct_label == "2"
    assert q.source == "llm"


def test_parse_question_rejects_zero_correct():
    bad = dict(GOOD_PAYLOAD)
    bad["options"] = [
        {"text": o["text"], "correct": False}
        for o in GOOD_PAYLOAD["options"]
    ]
    try:
        _parse_question(bad)
    except ValueError as exc:
        assert "correct" in str(exc)
    else:
        raise AssertionError("should have raised")


def test_parse_question_rejects_wrong_option_count():
    bad = dict(GOOD_PAYLOAD)
    bad["options"] = GOOD_PAYLOAD["options"][:3]
    try:
        _parse_question(bad)
    except ValueError as exc:
        assert "4 options" in str(exc)
    else:
        raise AssertionError("should have raised")


def test_extract_json_handles_bare_object():
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_json_handles_fenced_block():
    fenced = '```json\n{"a": 1}\n```'
    assert _extract_json(fenced) == '{"a": 1}'


def test_extract_json_handles_prose_preamble():
    wrapped = 'Sure! Here is the quiz:\n\n{"a": 1}\n\nHope that helps!'
    assert _extract_json(wrapped) == '{"a": 1}'


def test_extract_json_handles_nested_braces():
    nested = 'before\n{"a": {"b": {"c": 1}}}\nafter'
    assert _extract_json(nested) == '{"a": {"b": {"c": 1}}}'


def test_generate_from_code_mocked_claude(tmp_path, monkeypatch):
    """End-to-end through subprocess mocking."""
    monkeypatch.setattr(llm_gen, "GEN_CACHE_DIR", tmp_path / "gen")

    class FakeProc:
        returncode = 0
        stdout = json.dumps(GOOD_PAYLOAD)
        stderr = ""

    monkeypatch.setattr(llm_gen.shutil, "which", lambda _: "/fake/claude")
    with mock.patch.object(llm_gen.subprocess, "run", return_value=FakeProc()):
        result = generate_from_code("def f(): pass", context="test")
    assert result.error is None
    assert result.question is not None
    assert result.question.source == "llm"


def test_generate_from_code_no_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_gen, "GEN_CACHE_DIR", tmp_path / "gen")
    monkeypatch.setattr(llm_gen.shutil, "which", lambda _: None)
    result = generate_from_code("def f(): pass")
    assert result.question is None
    assert "PATH" in (result.error or "")


def test_generate_from_code_bad_json(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_gen, "GEN_CACHE_DIR", tmp_path / "gen")

    class FakeProc:
        returncode = 0
        stdout = "I cannot generate a quiz about this, sorry!"
        stderr = ""

    monkeypatch.setattr(llm_gen.shutil, "which", lambda _: "/fake/claude")
    with mock.patch.object(llm_gen.subprocess, "run", return_value=FakeProc()):
        result = generate_from_code("def f(): pass")
    assert result.question is None
    assert "JSON" in (result.error or "") or "block" in (result.error or "")


def test_generate_from_code_cache_hit_skips_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_gen, "GEN_CACHE_DIR", tmp_path / "gen")
    monkeypatch.setattr(llm_gen.shutil, "which", lambda _: "/fake/claude")

    class FakeProc:
        returncode = 0
        stdout = json.dumps(GOOD_PAYLOAD)
        stderr = ""

    # First call: hits subprocess
    with mock.patch.object(llm_gen.subprocess, "run", return_value=FakeProc()) as run_mock:
        r1 = generate_from_code("def f(): pass", context="same")
        assert r1.question is not None
        # Second call: should be served from cache, subprocess NOT called again
        r2 = generate_from_code("def f(): pass", context="same")
        assert r2.question is not None
        assert run_mock.call_count == 1
