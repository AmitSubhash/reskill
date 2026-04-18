"""Session-local wrong-answer re-queue behaviour."""

from __future__ import annotations

from reskill.question import Question, Option
from reskill.review_queue import ReviewQueue


def _q(prompt: str) -> Question:
    return Question(
        prompt=prompt,
        options=[Option("1", "a", True), Option("2", "b", False)],
        explanation="x",
        concept="test",
    )


def test_enqueued_question_not_ready_until_countdown_hits_zero():
    rq = ReviewQueue()
    q = _q("one")
    rq.enqueue(q, priority=3)
    assert rq.ready() is None
    rq.tick()
    assert rq.ready() is None
    rq.tick()
    assert rq.ready() is None
    rq.tick()
    # After 3 ticks, it's ready.
    assert rq.ready() is q


def test_ready_returns_fifo():
    rq = ReviewQueue()
    a, b = _q("a"), _q("b")
    rq.enqueue(a, priority=1)
    rq.enqueue(b, priority=1)
    rq.tick()
    assert rq.ready() is a
    assert rq.ready() is b
    assert rq.ready() is None


def test_tick_drains_monotonically_not_below_zero():
    rq = ReviewQueue()
    rq.enqueue(_q("x"), priority=1)
    rq.tick()
    rq.tick()
    rq.tick()
    assert rq.ready() is not None
    assert rq.ready() is None


def test_ready_skips_not_yet_ready_and_returns_ready_behind():
    rq = ReviewQueue()
    slow = _q("slow")
    quick = _q("quick")
    rq.enqueue(slow, priority=5)
    rq.enqueue(quick, priority=1)
    rq.tick()
    # slow has countdown 4, quick has 0 -> quick pops first.
    assert rq.ready() is quick
    # slow still waiting.
    assert rq.ready() is None
    for _ in range(4):
        rq.tick()
    assert rq.ready() is slow


def test_len_reflects_pending_count():
    rq = ReviewQueue()
    assert len(rq) == 0
    rq.enqueue(_q("a"))
    rq.enqueue(_q("b"))
    assert len(rq) == 2
    rq.tick()
    rq.tick()
    rq.tick()
    rq.ready()
    assert len(rq) == 1
