"""
Non-quiz learning content formats for very short thinking times.
These are passive -- no interaction required. The developer just reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from .palette import (
    BOLD, DIM,
    INK, STONE, ASH, DARK_ASH, SAGE, TEAL, ROSE, VIOLET, GOLD, BLUE,
    paint,
)
from .panel import render_panel, TERM_W


# ── Data models ──────────────────────────────────────────────


@dataclass
class TilCard:
    """Today I Learned -- a surprising fact with context."""
    language: str
    fact: str
    example_code: str | None = None
    source: str = ""


@dataclass
class PatternCard:
    """Side-by-side: bad pattern vs good pattern."""
    title: str
    language: str
    bad_code: str
    good_code: str
    explanation: str


@dataclass
class DocCard:
    """Just-in-time documentation snippet."""
    library: str
    topic: str
    snippet: str
    url: str


@dataclass
class ReflectCard:
    """Shows the developer their OWN code and asks them to think about it."""
    file_path: str
    code_snippet: str
    prompt: str  # e.g., "What would you improve here?"


# ── Renderers ────────────────────────────────────────────────


def render_til(card: TilCard) -> list[str]:
    """Render a 'Today I Learned' card. Fits in 5-8 lines."""
    lines: list[str] = []
    lines.append("")
    lines.append(paint(f"  {card.fact}", INK))
    lines.append("")
    if card.example_code:
        for code_line in card.example_code.split("\n"):
            lines.append(paint(f"    {code_line}", TEAL))
        lines.append("")
    if card.source:
        lines.append(paint(f"  {card.source}", ASH, DIM))
        lines.append("")

    return render_panel(
        f"{card.language} \u2022 Did you know?",
        lines,
        border_color=DARK_ASH,
        title_color=GOLD,
    )


def render_pattern(card: PatternCard) -> list[str]:
    """Render a pattern comparison card."""
    lines: list[str] = []
    lines.append("")

    # Bad pattern
    lines.append(paint("  \u2717 Avoid:", ROSE))
    for code_line in card.bad_code.split("\n"):
        lines.append(paint(f"    {code_line}", STONE))
    lines.append("")

    # Good pattern
    lines.append(paint("  \u2713 Prefer:", SAGE))
    for code_line in card.good_code.split("\n"):
        lines.append(paint(f"    {code_line}", TEAL))
    lines.append("")

    # Why
    lines.append(paint(f"  {card.explanation}", ASH))
    lines.append("")

    return render_panel(
        f"{card.language} \u2022 {card.title}",
        lines,
        border_color=DARK_ASH,
        title_color=SAGE,
    )


def render_doc(card: DocCard) -> list[str]:
    """Render a documentation snippet card."""
    lines: list[str] = []
    lines.append("")
    lines.append(paint(f"  {card.topic}", INK, BOLD))
    lines.append("")
    for snippet_line in card.snippet.split("\n"):
        lines.append(paint(f"    {snippet_line}", TEAL))
    lines.append("")
    lines.append(paint(f"  {card.url}", BLUE, DIM))
    lines.append("")

    return render_panel(
        f"{card.library} docs",
        lines,
        border_color=DARK_ASH,
        title_color=TEAL,
    )


def render_reflect(card: ReflectCard) -> list[str]:
    """Render a reflection card about the developer's own code."""
    lines: list[str] = []
    lines.append("")
    lines.append(paint(f"  {card.file_path}", ASH, DIM))
    lines.append("")
    for code_line in card.code_snippet.split("\n"):
        lines.append(paint(f"    {code_line}", TEAL))
    lines.append("")
    lines.append(paint(f"  {card.prompt}", GOLD))
    lines.append("")

    return render_panel(
        "Your Code \u2022 Reflect",
        lines,
        border_color=VIOLET,
        title_color=VIOLET,
    )


# ── Sample content ───────────────────────────────────────────

SAMPLE_TILS: list[TilCard] = [
    TilCard(
        "Python",
        "dict.get(key, default) never raises KeyError.",
        'value = config.get("port", 8080)',
        "PEP 463",
    ),
    TilCard(
        "Python",
        "You can unpack with * to split head and tail.",
        "first, *rest = [1, 2, 3, 4, 5]\n# first = 1, rest = [2, 3, 4, 5]",
    ),
    TilCard(
        "Git",
        "git stash --include-untracked (-u) stashes new files too.",
        "git stash -u  # saves tracked + untracked\ngit stash     # only tracked files",
    ),
    TilCard(
        "Python",
        "functools.lru_cache memoizes function results.",
        "@lru_cache(maxsize=128)\ndef fib(n):\n    return n if n < 2 else fib(n-1) + fib(n-2)",
    ),
    TilCard(
        "HTTP",
        "PUT replaces the entire resource. PATCH updates partially.",
        "PUT  /users/1  {name, email, age}  # full replace\nPATCH /users/1  {email}            # partial",
    ),
]

SAMPLE_PATTERNS: list[PatternCard] = [
    PatternCard(
        "String building",
        "Python",
        '# Slow: O(n^2) string concatenation\nresult = ""\nfor word in words:\n    result += word + " "',
        '# Fast: O(n) join\nresult = " ".join(words)',
        "String concatenation creates a new object each iteration.",
    ),
    PatternCard(
        "Null checking",
        "Python",
        "if x != None:\n    do_something(x)",
        "if x is not None:\n    do_something(x)",
        "'is' checks identity, '==' checks equality. None is a singleton.",
    ),
    PatternCard(
        "Dict iteration",
        "Python",
        "for key in d.keys():\n    value = d[key]\n    process(key, value)",
        "for key, value in d.items():\n    process(key, value)",
        ".items() gives both key and value in one call.",
    ),
]

SAMPLE_DOCS: list[DocCard] = [
    DocCard(
        "FastAPI",
        "Background Tasks",
        '@app.post("/send-email")\nasync def send(bg: BackgroundTasks):\n    bg.add_task(send_email, to=email)\n    return {"status": "queued"}',
        "fastapi.tiangolo.com/tutorial/background-tasks/",
    ),
    DocCard(
        "pytest",
        "Parametrize decorator",
        '@pytest.mark.parametrize("input,expected", [\n    (1, 1), (2, 4), (3, 9),\n])\ndef test_square(input, expected):\n    assert input ** 2 == expected',
        "docs.pytest.org/en/stable/parametrize.html",
    ),
]

SAMPLE_REFLECTS: list[ReflectCard] = [
    ReflectCard(
        "src/auth.py:42",
        "def get_user(db, user_id):\n    user = db.query(User).filter(User.id == user_id).first()\n    if user is None:\n        raise HTTPException(404)\n    return user",
        "Could this be simplified with a reusable get_or_404 helper?",
    ),
]
