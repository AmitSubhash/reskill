"""Thinking spinner with ad display and auto-cleanup."""

from __future__ import annotations

import itertools
import sys
import time

from .palette import TEAL, ASH, paint
from .ads import (
    OneLinerAd, CardAd,
    render_oneliner, render_card,
    ONELINERS, CARDS,
)

SPINNER_CHARS = list("\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")

VERBS = [
    "Cogitating", "Ruminating", "Deliberating", "Pondering",
    "Cerebrating", "Noodling", "Percolating", "Machinating",
]


def _cursor_up(n: int) -> None:
    sys.stdout.write(f"\033[{n}A")
    sys.stdout.flush()


def _clear_n_lines(n: int) -> None:
    for _ in range(n):
        sys.stdout.write("\033[2K\n")
    _cursor_up(n)


def show_thinking(
    duration: float,
    ad: OneLinerAd | CardAd | None = None,
    ad_idx: int = 0,
) -> None:
    """Show spinner + ad for `duration` seconds, then erase everything."""
    # Pick ad if not provided
    if ad is None:
        if duration < 3.5:
            ad = ONELINERS[ad_idx % len(ONELINERS)]
        else:
            ad = CARDS[ad_idx % len(CARDS)]

    # Render ad lines
    if isinstance(ad, OneLinerAd):
        ad_lines = render_oneliner(ad)
    else:
        ad_lines = render_card(ad)

    # Print ad with blank line above and below
    print()
    for line in ad_lines:
        print(line)
    print()

    total_height = len(ad_lines) + 2  # blank lines

    # Animate spinner
    spinner = itertools.cycle(SPINNER_CHARS)
    steps = int(duration / 0.1)
    for i in range(steps):
        s = next(spinner)
        v = VERBS[(i // 10) % len(VERBS)]
        sys.stdout.write(f"\r  {paint(s, TEAL)} {paint(f'{v}...', ASH)}")
        sys.stdout.flush()
        time.sleep(0.1)

    # Clean up: clear spinner line, then erase ad
    sys.stdout.write("\r\033[2K")
    _cursor_up(total_height)
    _clear_n_lines(total_height)
