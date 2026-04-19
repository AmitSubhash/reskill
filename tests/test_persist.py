"""Tests for reskill/persist.py, the crash-safe JSON helpers.

Covers:
  - atomic_write_json writes via tmp + replace (no partial files)
  - atomic_write_json cleans up tmp on write failure
  - load_json_or_quarantine returns None for absent files
  - load_json_or_quarantine quarantines corrupt files + returns None
  - load_json_or_quarantine survives non-dict JSON roots
  - filter_to_fields discards unknown keys
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from reskill.persist import (
    atomic_write_json,
    filter_to_fields,
    load_json_or_quarantine,
)


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    atomic_write_json(target, {"streak": 3})
    assert json.loads(target.read_text()) == {"streak": 3}


def test_atomic_write_makes_parent_dirs(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c.json"
    atomic_write_json(nested, {"k": "v"})
    assert nested.exists()


def test_atomic_write_leaves_no_tmp(tmp_path: Path) -> None:
    target = tmp_path / "p.json"
    atomic_write_json(target, {"n": 1})
    leftover = [p.name for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert leftover == []


def test_atomic_write_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / "p.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 2}


def test_atomic_write_cleans_tmp_on_failure(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "p.json"

    original_replace = os.replace

    def boom(*a, **kw):
        raise OSError("replace failed")

    monkeypatch.setattr("reskill.persist.os.replace", boom)
    with pytest.raises(OSError):
        atomic_write_json(target, {"v": 1})
    # No stray tmp file.
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr("reskill.persist.os.replace", original_replace)


def test_load_absent_returns_none(tmp_path: Path) -> None:
    assert load_json_or_quarantine(tmp_path / "nope.json") is None


def test_load_valid_returns_dict(tmp_path: Path) -> None:
    target = tmp_path / "p.json"
    target.write_text('{"x": 42}')
    assert load_json_or_quarantine(target) == {"x": 42}


def test_load_corrupt_quarantines(tmp_path: Path, capsys) -> None:
    target = tmp_path / "p.json"
    target.write_text("{ not valid json ")
    result = load_json_or_quarantine(target, label="test")
    assert result is None
    # Original is gone.
    assert not target.exists()
    # Quarantine sibling exists.
    quarantined = list(tmp_path.glob("p.json.corrupt-*"))
    assert len(quarantined) == 1
    # Stderr notice mentions the label and the new path.
    err = capsys.readouterr().err
    assert "test" in err
    assert "unreadable" in err


def test_load_non_dict_root_quarantines(tmp_path: Path) -> None:
    target = tmp_path / "p.json"
    target.write_text("[1, 2, 3]")
    assert load_json_or_quarantine(target) is None
    assert list(tmp_path.glob("p.json.corrupt-*"))


def test_filter_to_fields_drops_unknown() -> None:
    got = filter_to_fields(
        {"streak": 1, "future_field": "mystery", "xp_total": 100},
        {"streak", "xp_total"},
    )
    assert got == {"streak": 1, "xp_total": 100}


def test_state_survives_unknown_key(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: a state.json with a future-version key still loads.

    Before the filter, this raised TypeError and the user silently
    started from zero.
    """
    from reskill import state as state_mod

    monkeypatch.setattr(state_mod, "STATE_FILE", tmp_path / "state.json")
    # A state file from a hypothetical future version with an unknown
    # `achievements` field.
    (tmp_path / "state.json").write_text(
        json.dumps({"streak": 7, "xp_total": 1400, "achievements": ["x"]})
    )
    s = state_mod.load()
    assert s.streak == 7
    assert s.xp_total == 1400
