"""A simulator that pretends to be Claude so you can see the full UX
without needing Claude Code or an API key.

Run: python -m reskill.simulator
"""

from __future__ import annotations

import itertools
import os
import random
import sys
import time

from .palette import (
    BOLD, DIM, INK, STONE, ASH, DARK_ASH, SAGE, TEAL, GOLD, VIOLET,
    paint,
)


SPINNER = list("\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")


HR = "\u2500" * 60


def banner() -> None:
    print()
    print(f"  {paint('Claude', TEAL, BOLD)}  {paint('Sonnet 4.6', DARK_ASH)}")
    print(paint(f"  {HR}", DARK_ASH, DIM))
    print()


def you(text: str) -> None:
    time.sleep(0.5)
    print(f"  {paint('>', SAGE, BOLD)} {paint(text, INK, BOLD)}")
    print()


def spin(duration: float) -> None:
    spinner = itertools.cycle(SPINNER)
    verbs = ["Thinking", "Cogitating", "Pondering", "Ruminating"]
    t0 = time.time()
    while time.time() - t0 < duration:
        s = next(spinner)
        v = verbs[int((time.time() - t0)) % len(verbs)]
        sys.stdout.write(f"\r  {paint(s, TEAL)} {paint(v + '...', ASH)}")
        sys.stdout.flush()
        time.sleep(0.08)
    sys.stdout.write("\r" + " " * 40 + "\r")


def stream(text: str, wpm: int = 400) -> None:
    """Stream text at roughly the given words-per-minute rate."""
    delay = 60.0 / (wpm * 5)  # crude: 5 chars per word
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay * random.uniform(0.3, 1.7))
    sys.stdout.write("\n")


def tool_call(name: str, arg: str) -> None:
    print()
    print(f"  {paint('*', GOLD)} {paint(name, GOLD, BOLD)} {paint(arg, ASH)}")
    time.sleep(0.6)


def done_mark(text: str) -> None:
    print(f"  {paint(chr(0x2713), SAGE, BOLD)} {paint(text, ASH)}")


# ───────── Scripted scenarios ─────────────────────────────

SCENARIOS = [
    {
        "user": "add error handling to the JWT validation in src/auth.py",
        "thinking": 3.0,
        "tools": [
            ("Read", "src/auth.py"),
        ],
        "stream_text": (
            "\n  I'll add error handling to the JWT validation. "
            "Looking at the current code, expired tokens aren't being caught "
            "properly -- they return a 500 instead of 401.\n\n"
            "  I'll wrap the decode call in a try/except block and catch both "
            "`ExpiredSignatureError` and `InvalidTokenError` specifically, "
            "since bare `except` would also catch KeyboardInterrupt which we "
            "never want.\n\n"
            "  Here's the fix:\n"
        ),
        "code": (
            "\n"
            "  try:\n"
            "      payload = jwt.decode(token, SECRET, algorithms=['HS256'])\n"
            "  except jwt.ExpiredSignatureError:\n"
            "      raise HTTPException(401, detail='Token expired')\n"
            "  except jwt.InvalidTokenError:\n"
            "      raise HTTPException(401, detail='Invalid token')\n"
        ),
        "after": [
            ("Edit", "src/auth.py"),
            "Applied edit to src/auth.py",
            None,
        ],
    },
    {
        "user": "use lru_cache to memoize the expensive lookup in helpers.py",
        "thinking": 2.5,
        "tools": [
            ("Read", "src/helpers.py"),
        ],
        "stream_text": (
            "\n  I'll add @lru_cache to the lookup function. This will cache "
            "results so repeated calls with the same arguments return instantly.\n\n"
            "  Using maxsize=128 will keep memory bounded -- once we hit 128 "
            "distinct inputs, the least recently used entry gets evicted.\n"
        ),
        "code": (
            "\n"
            "  from functools import lru_cache\n"
            "\n"
            "  @lru_cache(maxsize=128)\n"
            "  def get_user_by_email(email: str) -> User | None:\n"
            "      return db.query(User).filter_by(email=email).first()\n"
        ),
        "after": [
            ("Edit", "src/helpers.py"),
            "Applied edit to src/helpers.py",
            None,
        ],
    },
    {
        "user": "what status code should I return for POST /users?",
        "thinking": 1.5,
        "tools": [],
        "stream_text": (
            "\n  For a successful POST that creates a new resource, return "
            "`201 Created`. The response body should contain the created resource, "
            "and you should include a `Location` header pointing to the new "
            "resource's URL.\n\n"
            "  200 OK would work but is less precise -- 201 specifically signals "
            "that creation happened. 204 No Content is for successful operations "
            "that don't return a body, like DELETE.\n"
        ),
        "code": None,
        "after": [],
    },
]


def run_scenario(scenario: dict) -> None:
    you(scenario["user"])
    spin(scenario["thinking"])

    for tool in scenario["tools"]:
        tool_call(tool[0], tool[1])
        time.sleep(0.3)

    stream(scenario["stream_text"])

    if scenario["code"]:
        time.sleep(0.5)
        print(paint("  \u250c" + "\u2500" * 58 + "\u2510", STONE, DIM))
        for line in scenario["code"].strip("\n").split("\n"):
            padded = line + " " * max(0, 58 - len(line))
            print(paint("  \u2502", STONE, DIM) + paint(padded, TEAL) + paint("\u2502", STONE, DIM))
        print(paint("  \u2514" + "\u2500" * 58 + "\u2518", STONE, DIM))

    for item in scenario["after"]:
        if item is None:
            time.sleep(1.0)
            continue
        if isinstance(item, tuple):
            tool_call(item[0], item[1])
        else:
            done_mark(item)
        time.sleep(0.3)

    print()


def main() -> None:
    os.system("clear")
    banner()
    time.sleep(0.6)

    for scenario in SCENARIOS:
        run_scenario(scenario)
        time.sleep(1.2)

    print()
    print(paint(f"  {HR}", DARK_ASH, DIM))
    print()
    print(paint("  session ended", ASH))
    print()


if __name__ == "__main__":
    main()
