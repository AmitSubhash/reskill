"""Tests for the research-backed question validator."""

from __future__ import annotations

from reskill.question import Option, Question
from reskill.validate import is_acceptable, validate_question


def make_q(
    prompt: str,
    options: list[tuple[str, bool]],
    explanation: str,
    concept: str = "test",
    fmt: str = "gotcha",
    code: str | None = None,
) -> Question:
    opts = [Option(str(i + 1), t, c) for i, (t, c) in enumerate(options)]
    return Question(
        prompt=prompt,
        options=opts,
        explanation=explanation,
        concept=concept,
        format=fmt,
        code=code,
    )


def test_clean_question_has_no_flaws():
    src = "def fetch_all(urls): return await asyncio.gather(*[fetch(u) for u in urls])"
    q = make_q(
        prompt="In fetch_all above, what happens if one fetch raises?",
        options=[
            ("gather cancels siblings and propagates the error immediately", True),
            ("siblings keep running detached; exception returns after", False),
            ("gather retries the failed fetch up to three times", False),
            ("only the first three fetches complete, rest are dropped", False),
        ],
        explanation="asyncio.gather without return_exceptions raises the first error immediately but detaches siblings. Use a TaskGroup (3.11+) for structured cancellation, or wrap with asyncio.wait.",
    )
    assert is_acceptable(validate_question(q, src))


def test_catches_negative_stem():
    q = make_q(
        prompt="Which of the following is NOT a way to release the GIL?",
        options=[("a", True), ("b", False), ("c", False), ("d", False)],
        explanation="x",
    )
    flaws = validate_question(q, "import threading")
    assert any(f.code == "R5_negative_stem" for f in flaws)
    assert not is_acceptable(flaws)


def test_catches_all_of_the_above():
    q = make_q(
        prompt="What does threading provide in python?",
        options=[
            ("parallelism", False),
            ("concurrency", False),
            ("none of the above", False),
            ("all of the above", True),
        ],
        explanation="x",
    )
    flaws = validate_question(q, "threading")
    assert any(f.code == "R5_meta_option" for f in flaws)
    assert not is_acceptable(flaws)


def test_catches_ungrounded_stem():
    src = "def foo(): return 1"
    q = make_q(
        prompt="What does Python's garbage collector do for circular references?",
        options=[
            ("runs mark-and-sweep eventually", True),
            ("ignores them by design", False),
            ("raises a RuntimeError", False),
            ("triggers a segfault", False),
        ],
        explanation="x",
    )
    flaws = validate_question(q, src)
    assert any(f.code == "R8_ungrounded_stem" for f in flaws)


def test_catches_longest_is_correct():
    src = "def handle(): pass"
    q = make_q(
        prompt="In the handle function above, what is the return type?",
        options=[
            ("int", False),
            ("None, because the function has no explicit return statement so Python returns None implicitly", True),
            ("str", False),
            ("bool", False),
        ],
        explanation="Missing returns produce None, which is a falsy value in boolean contexts.",
    )
    flaws = validate_question(q, src)
    assert any(f.code == "R3_longest_is_correct" for f in flaws)
    assert not is_acceptable(flaws)


def test_catches_multi_key():
    q = make_q(
        prompt="What does Counter in collections do in the code above?",
        options=[
            ("counts hashable items", True),
            ("also counts items (duplicate correct)", True),
            ("c", False),
            ("d", False),
        ],
        explanation="x",
    )
    flaws = validate_question(q, "from collections import Counter")
    assert any(f.code == "R4_multi_key" for f in flaws)
    assert not is_acceptable(flaws)


def test_three_options_allowed():
    """Rodriguez 2005: 3 options are optimal. Validator must accept 3."""
    q = make_q(
        prompt="In fetch_all above, what happens on a ConnectionError?",
        options=[
            ("propagates, siblings detach", True),
            ("silent, gather returns partial results", False),
            ("gather retries automatically", False),
        ],
        explanation="asyncio.gather raises immediately but siblings keep running. Use TaskGroup for structured cancellation.",
    )
    flaws = validate_question(q, "async def fetch_all(urls): ...")
    # Only check this doesn't flag "wrong option count" -- other rules may fire.
    assert not any(
        f.code in ("R4_multi_key",) for f in flaws
    ), f"3-option question rejected: {flaws}"


def test_catches_duplicate_options():
    q = make_q(
        prompt="What does urlopen do in the snippet?",
        options=[
            ("opens a url", False),
            ("opens a url", True),
            ("c", False),
            ("d", False),
        ],
        explanation="x",
    )
    flaws = validate_question(q, "urlopen")
    assert any(f.code == "duplicate_option" for f in flaws)
    assert not is_acceptable(flaws)
