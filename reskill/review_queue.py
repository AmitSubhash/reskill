"""Session-local re-ask queue for wrong/skipped answers.

Evidence: within a session, re-testing a missed item 3-5 items later
reinforces the correction while the error is still salient. The
forgetting curve (Ebbinghaus, replicated in PMC5126970) shows
retention drops most in the first minutes after exposure; same-session
relearning cuts that loss. Anki's relearning steps implement the same
idea at a larger scale.

The queue is ephemeral -- one quiz-panel run only -- so restarts
don't drag old mistakes forward. The long-horizon scheduling is
still handled by SM-2 via state.record_answer.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .question import Question

_DEFAULT_PRIORITY = 3  # re-serve after this many other questions


@dataclass
class PendingReview:
    question: Question
    countdown: int  # re-serve when this hits 0


class ReviewQueue:
    """FIFO-ish queue with a per-entry countdown.

    Each tick (i.e. each time another question is served), every pending
    entry's countdown drops by 1. When it hits 0, the entry is eligible
    to re-serve on the next pick.
    """

    def __init__(self) -> None:
        self._pending: deque[PendingReview] = deque()

    def enqueue(
        self, question: Question, priority: int = _DEFAULT_PRIORITY
    ) -> None:
        """Push a question back for re-serve after `priority` other items."""
        self._pending.append(PendingReview(question=question, countdown=priority))

    def tick(self) -> None:
        """Call once when any other question has been served."""
        for item in self._pending:
            item.countdown = max(0, item.countdown - 1)

    def ready(self) -> Question | None:
        """Pop and return the oldest ready question, or None.

        Ready = countdown hit 0. The queue preserves FIFO for fairness.
        """
        for _ in range(len(self._pending)):
            item = self._pending[0]
            if item.countdown <= 0:
                self._pending.popleft()
                return item.question
            # Not ready; rotate to the back so the next one gets a look.
            self._pending.rotate(-1)
        return None

    def __len__(self) -> int:
        return len(self._pending)
