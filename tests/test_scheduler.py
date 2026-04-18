"""Scheduler unit tests -- make sure SM-2 + interleaving logic hold."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from reskill.scheduler import choose, concepts_ready
from reskill.state import State


def make_state_with_concepts(**overrides) -> State:
    s = State()
    for concept, cs in overrides.items():
        s.concepts[concept] = cs
    return s


def test_new_concept_wins_over_not_due():
    """A never-answered concept should beat one that was just answered."""
    live = "this code uses @lru_cache(maxsize=128) and try/except"
    just_answered = {
        "ef": 2.5,
        "interval": 30,     # long interval -> not due
        "reps": 3,
        "last": time.time(),  # just answered, so not due
        "correct": 3,
        "total": 3,
    }
    state = make_state_with_concepts(caching=just_answered)
    pick = choose(
        live_text=live,
        commit_text="",
        state=state,
        seen_ids=set(),
    )
    assert pick is not None
    assert pick.concept == "error-handling", (
        "Should pick try_except (new) over caching (not-due). "
        f"got concept={pick.concept!r}, source={pick.source!r}"
    )
    assert pick.source == "new"


def test_overdue_concept_wins_over_new():
    """An overdue review beats a new concept -- review is more urgent."""
    live = "code about @lru_cache and some try/except"
    overdue = {
        "ef": 2.5,
        "interval": 1,
        "reps": 1,
        "last": time.time() - 3 * 86400,  # 3 days ago, interval 1 -> overdue
        "correct": 1,
        "total": 1,
    }
    state = make_state_with_concepts(caching=overdue)
    pick = choose(
        live_text=live,
        commit_text="",
        state=state,
        seen_ids=set(),
    )
    assert pick is not None
    assert pick.source == "due", (
        f"overdue should win; got source={pick.source}, concept={pick.concept}"
    )
    assert pick.concept == "caching"


def test_interleaving_avoids_repeat_concept():
    """If last question was concept X and another concept Y is available,
    we should pick Y -- interleaving helps retention."""
    live = "code with @lru_cache and try/except"
    state = State()  # both concepts are "new"
    pick = choose(
        live_text=live,
        commit_text="",
        state=state,
        seen_ids=set(),
        last_concept="caching",
    )
    assert pick is not None
    assert pick.concept != "caching", (
        "interleaving failed; picked same concept twice in a row"
    )


def test_interleaving_falls_back_when_no_alternative():
    """If the only matching concept IS last_concept, we still pick it
    (better something than nothing)."""
    live = "code with @lru_cache only"  # only caching matches
    state = State()
    pick = choose(
        live_text=live,
        commit_text="",
        state=state,
        seen_ids=set(),
        last_concept="caching",
    )
    assert pick is not None
    assert pick.concept == "caching"


def test_seen_questions_are_skipped():
    """Fresh questions must be preferred; we skip any ID in seen."""
    from reskill.question import TEMPLATE_BANK

    caching_bank = TEMPLATE_BANK["lru_cache"]
    assert len(caching_bank) >= 2
    first_id = caching_bank[0].id

    live = "code about @lru_cache"
    state = State()
    pick = choose(
        live_text=live,
        commit_text="",
        state=state,
        seen_ids={first_id},
    )
    assert pick is not None
    assert pick.question.id != first_id


def test_fallback_returns_something_when_bank_exhausted():
    """When every question has been seen, fallback tier returns
    a previously-seen question rather than None."""
    from reskill.question import TEMPLATE_BANK

    all_ids = {q.id for bank in TEMPLATE_BANK.values() for q in bank}
    pick = choose(
        live_text="",
        commit_text="",
        state=State(),
        seen_ids=all_ids,
    )
    assert pick is not None, "must not return None when bank exists"
    assert pick.source == "fallback"


def test_concepts_ready_counts():
    state = State()
    live = "code with @lru_cache and try/except"
    due, new = concepts_ready(live, state, seen_ids=set())
    assert due == 0
    assert new >= 2  # at least caching and try_except are "new"


def test_concepts_ready_with_overdue():
    state = State()
    state.concepts["caching"] = {
        "ef": 2.5, "interval": 1, "reps": 1,
        "last": time.time() - 3 * 86400,
        "correct": 1, "total": 1,
    }
    live = "@lru_cache and try/except"
    due, new = concepts_ready(live, state, seen_ids=set())
    assert due == 1
    assert new >= 1


def test_format_mix_prefers_novel_format_over_repeat():
    """Given two fresh concepts with different formats, the one whose
    format hasn't appeared in recent_formats wins.

    This is a statistical assertion: over many calls we should see
    format diversity much stronger than random chance.
    """
    import random as _random
    _random.seed(1234)
    from reskill.question import TEMPLATE_BANK

    # Pool: live text mentions concepts that have both MC-gotcha and
    # non-MC formats in the bank. Look for a concept that actually has
    # mixed formats.
    mixed_live = (
        "async def fetch(): await x; try: ...; @lru_cache; "
        "def add(bag=[]): return bag"
    )
    state = State()

    # Ask 30 times with a biased "recent_formats" window full of 'output'.
    # If format-mix works, the picker should avoid 'output' when alternatives exist.
    recent = ["output", "output", "output", "output"]
    formats_chosen = []
    seen: set[str] = set()
    for _ in range(30):
        p = choose(
            live_text=mixed_live,
            commit_text="",
            state=state,
            seen_ids=seen,
            recent_formats=recent,
        )
        if p is None:
            break
        formats_chosen.append(p.question.format)
        seen.add(p.question.id)

    # 'output' may still appear when no alternative exists, but should
    # NOT dominate. At least one non-output format must show up.
    non_output = [f for f in formats_chosen if f != "output"]
    assert len(non_output) > 0, (
        f"no non-output formats chosen; got {formats_chosen}"
    )
