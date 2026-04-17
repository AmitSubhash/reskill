"""Question data model and template-based generator."""

from __future__ import annotations

import ast
import hashlib
import random
import re
from dataclasses import dataclass, field


@dataclass
class Option:
    label: str  # "1", "2", "3", "4"
    text: str
    correct: bool


@dataclass
class Question:
    prompt: str
    options: list[Option]
    explanation: str
    concept: str
    source: str = "template"  # template | llm | manual

    @property
    def correct_label(self) -> str:
        for o in self.options:
            if o.correct:
                return o.label
        return "?"

    @property
    def id(self) -> str:
        h = hashlib.sha256(self.prompt.encode()).hexdigest()
        return h[:12]


# ───────── Template bank ─────────────────────────────────────
# Patterns detected in streaming content map to questions here.
# Patterns are ordered: first match wins.

TEMPLATE_BANK: dict[str, list[Question]] = {
    "try_except": [
        Question(
            concept="error-handling",
            prompt="Why catch specific exceptions instead of bare except?",
            options=[
                Option("1", "Performance is better", False),
                Option("2", "Clearer error handling and easier debugging", True),
                Option("3", "Python requires it", False),
                Option("4", "It's just convention", False),
            ],
            explanation=(
                "Bare except catches everything including KeyboardInterrupt and "
                "SystemExit, hiding bugs and breaking Ctrl+C."
            ),
        ),
        Question(
            concept="error-handling",
            prompt="What's the parent class of most user-facing Python exceptions?",
            options=[
                Option("1", "BaseException", False),
                Option("2", "Exception", True),
                Option("3", "RuntimeError", False),
                Option("4", "StandardError", False),
            ],
            explanation=(
                "Exception is the base for ordinary errors. BaseException also "
                "includes SystemExit and KeyboardInterrupt which you usually "
                "don't want to catch."
            ),
        ),
    ],
    "lru_cache": [
        Question(
            concept="caching",
            prompt="What does @lru_cache(maxsize=128) do?",
            options=[
                Option("1", "Logs function calls for debugging", False),
                Option("2", "Caches results, evicts least recently used", True),
                Option("3", "Makes the function thread-safe", False),
                Option("4", "Retries on failure", False),
            ],
            explanation=(
                "LRU = Least Recently Used. When the cache fills past maxsize, "
                "the oldest entry is discarded. Great for pure functions with "
                "repeated inputs."
            ),
        ),
    ],
    "async_def": [
        Question(
            concept="async",
            prompt="What does calling an async function return?",
            options=[
                Option("1", "The function's return value directly", False),
                Option("2", "A coroutine that must be awaited", True),
                Option("3", "A Future object", False),
                Option("4", "None until the task completes", False),
            ],
            explanation=(
                "async def creates a coroutine. You get the actual value by "
                "awaiting it or passing it to asyncio.run() / gather()."
            ),
        ),
    ],
    "jwt": [
        Question(
            concept="jwt",
            prompt="Why do JWT tokens have an expiry time?",
            options=[
                Option("1", "Performance (smaller tokens over time)", False),
                Option("2", "Security: limits damage if a token is stolen", True),
                Option("3", "Storage: saves database space", False),
                Option("4", "GDPR compliance", False),
            ],
            explanation=(
                "JWTs are stateless -- once issued, the server can't revoke them. "
                "Expiry limits the window an attacker could use a stolen token."
            ),
        ),
    ],
    "http_status_created": [
        Question(
            concept="http-status",
            prompt="Which HTTP status code should a successful POST that creates a resource return?",
            options=[
                Option("1", "200 OK", False),
                Option("2", "201 Created", True),
                Option("3", "204 No Content", False),
                Option("4", "202 Accepted", False),
            ],
            explanation=(
                "201 Created is the precise code for a POST that created something. "
                "Include a Location header pointing to the new resource."
            ),
        ),
    ],
    "list_comprehension": [
        Question(
            concept="comprehensions",
            prompt="What's the main advantage of a list comprehension over a for loop with append?",
            options=[
                Option("1", "It's always much faster", False),
                Option("2", "More concise, and slightly faster for simple cases", True),
                Option("3", "Uses less memory in all cases", False),
                Option("4", "Supports async operations", False),
            ],
            explanation=(
                "List comprehensions are idiomatic Python. They're roughly 30-50% "
                "faster than equivalent append loops for simple cases, and often "
                "clearer."
            ),
        ),
    ],
    "depends": [
        Question(
            concept="fastapi",
            prompt="What does FastAPI's Depends() provide?",
            options=[
                Option("1", "Automatic dependency installation", False),
                Option("2", "Dependency injection for sharing logic and auth", True),
                Option("3", "Async retry logic", False),
                Option("4", "Route caching", False),
            ],
            explanation=(
                "Depends() injects values (DB sessions, current user, config) into "
                "routes. It makes dependencies testable, reusable, and declarative."
            ),
        ),
    ],
    "n_plus_one": [
        Question(
            concept="databases",
            prompt="What's the fix for an N+1 query pattern?",
            options=[
                Option("1", "Add indexes to all foreign keys", False),
                Option("2", "Use eager loading or a JOIN to fetch related data", True),
                Option("3", "Move to a NoSQL database", False),
                Option("4", "Cache each individual query", False),
            ],
            explanation=(
                "N+1 happens when fetching N parents then doing 1 query per child. "
                "Fix by joining (SQL JOIN) or eager loading (joinedload, "
                "selectinload) to fetch everything in 1-2 queries."
            ),
        ),
    ],
    "generator_yield": [
        Question(
            concept="generators",
            prompt="Why use `yield` instead of building and returning a list?",
            options=[
                Option("1", "yield is always faster", False),
                Option("2", "Lazy evaluation: values produced on demand, lower memory", True),
                Option("3", "Generators support more methods than lists", False),
                Option("4", "It's required for async code", False),
            ],
            explanation=(
                "Generators produce values one at a time. For large or infinite "
                "sequences, you don't need to hold everything in memory at once."
            ),
        ),
    ],
    "context_manager_with": [
        Question(
            concept="resources",
            prompt="What does the `with` statement guarantee?",
            options=[
                Option("1", "Thread-safe access", False),
                Option("2", "Cleanup runs even if an exception is raised", True),
                Option("3", "The block executes atomically", False),
                Option("4", "File contents are auto-parsed", False),
            ],
            explanation=(
                "The context manager's __exit__ runs on normal completion AND on "
                "exceptions. That's why it's safer than manual open/close."
            ),
        ),
    ],
    "pytest_fixture": [
        Question(
            concept="testing",
            prompt="What does @pytest.fixture do?",
            options=[
                Option("1", "Marks a function as a test case", False),
                Option("2", "Provides reusable setup/teardown for tests", True),
                Option("3", "Skips the test until a condition is met", False),
                Option("4", "Runs the test in parallel", False),
            ],
            explanation=(
                "Fixtures create test dependencies (db sessions, test data, mocks) "
                "that pytest injects into test functions by parameter name."
            ),
        ),
    ],
}


# ───────── Pattern matchers (regex + ast) ──────────────────

# Patterns ordered from most-specific to most-generic. First match wins.
PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("jwt", "JWT tokens",
     re.compile(r"\bjwt\b|\btoken\b.*\b(expir|sign|verify)", re.I)),
    ("lru_cache", "caching",
     re.compile(r"\blru_cache\b|@lru_cache|functools\.cache|\bmemoiz|@cache\b", re.I)),
    ("http_status_created", "HTTP 201",
     re.compile(r"\b201\b|\bCreated\b|(POST).{0,40}\b(resource|creat)", re.I)),
    ("n_plus_one", "N+1 queries",
     re.compile(r"\bN\+1\b|n\s*plus\s*one|joinedload|selectinload|eager.{0,10}load", re.I)),
    ("depends", "dependency injection",
     re.compile(r"\bDepends\s*\(|Depends\[", re.I)),
    ("pytest_fixture", "pytest fixtures",
     re.compile(r"@pytest\.fixture|@fixture\b", re.I)),
    ("async_def", "async/await",
     re.compile(r"\basync\s+def\b|\bawait\b|asyncio\.", re.I)),
    ("generator_yield", "generators",
     re.compile(r"\byield\b(?!\s*from)", re.I)),
    ("list_comprehension", "list comprehensions",
     re.compile(r"\[[^\[\]]+\bfor\b[^\[\]]+\]", re.I)),
    ("try_except", "error handling",
     re.compile(r"\btry\s*:|\bexcept\b|\braise\b", re.I)),
    ("context_manager_with", "context managers",
     re.compile(r"\bwith\s+\w+\s+as\b|\b__enter__\b|\b__exit__\b", re.I)),
]


def detect_concepts(text: str) -> list[str]:
    """Return a list of concept keys that appear in the text."""
    hits: list[str] = []
    for key, _, pat in PATTERNS:
        if pat.search(text):
            hits.append(key)
    return hits


def generate_question(text: str, seen_ids: set[str] | None = None) -> Question | None:
    """Generate a question from streaming text via template matching.

    Returns None if no pattern matches or all matching questions have been asked.
    """
    seen_ids = seen_ids or set()
    concepts = detect_concepts(text)
    random.shuffle(concepts)

    for concept in concepts:
        candidates = TEMPLATE_BANK.get(concept, [])
        fresh = [q for q in candidates if q.id not in seen_ids]
        if fresh:
            return random.choice(fresh)

    # Fallback: any concept with fresh questions
    all_concepts = list(TEMPLATE_BANK.keys())
    random.shuffle(all_concepts)
    for concept in all_concepts:
        candidates = TEMPLATE_BANK[concept]
        fresh = [q for q in candidates if q.id not in seen_ids]
        if fresh:
            return random.choice(fresh)

    return None
