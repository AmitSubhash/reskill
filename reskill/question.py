"""Question data model and template-based generator.

Question DESIGN PRINCIPLES:
  1. Force a small decision, not a lookup. "Why does X behave this way?" beats
     "What is X?"
  2. Include code when possible. Concrete reasoning beats abstract recall.
  3. All options should look plausible. No obvious throw-aways.
  4. The explanation should teach something the developer didn't know, not
     just confirm the right letter.
  5. Ideal answer time: 20-45 seconds. If it's <10s, it's too easy; if >60s,
     it's a brain teaser, not micro-learning.

Question FORMATS:
  - output: show code, predict what prints
  - bug: show subtly broken code, find the line
  - tradeoff: two ways to solve a problem; one is meaningfully better
  - scenario: given a constraint, pick the right approach
  - why: Claude made a choice; explain the reason behind it
  - gotcha: show a common "looks right but isn't" pattern
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass


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
    format: str = "why"          # output | bug | tradeoff | scenario | why | gotcha
    code: str | None = None      # optional code snippet shown above the prompt
    source: str = "template"

    @property
    def correct_label(self) -> str:
        for o in self.options:
            if o.correct:
                return o.label
        return "?"

    @property
    def id(self) -> str:
        return hashlib.sha256(self.prompt.encode()).hexdigest()[:12]


def _q(**kwargs) -> Question:
    opts_raw = kwargs.pop("opts")
    opts = [
        Option(str(i + 1), text, i == kwargs.pop("correct_idx", 0))
        for i, text in enumerate(opts_raw)
    ] if False else None
    # build options from (text, correct) tuples
    opts = []
    for i, item in enumerate(opts_raw):
        if isinstance(item, tuple):
            text, correct = item
        else:
            text, correct = item, False
        opts.append(Option(str(i + 1), text, correct))
    return Question(options=opts, **kwargs)


# ───────── Template bank (thought-provoking, code-heavy) ──────

TEMPLATE_BANK: dict[str, list[Question]] = {
    "try_except": [
        _q(
            concept="error-handling",
            format="gotcha",
            prompt="This 'safe' code silently breaks something important. What?",
            code=(
                "try:\n"
                "    result = fetch_data()\n"
                "except:\n"
                "    result = None"
            ),
            opts=[
                ("The user's Ctrl+C now does nothing -- KeyboardInterrupt is caught", True),
                ("Silently returns None, which is actually fine for most cases", False),
                ("Only catches Exception, so bugs can still leak through", False),
                ("Nothing -- bare except is a perfectly safe pattern", False),
            ],
            explanation=(
                "Bare `except:` catches BaseException, which includes KeyboardInterrupt, "
                "SystemExit, and GeneratorExit. Users pressing Ctrl+C will get trapped. "
                "Use `except Exception:` if you really need a catch-all, but prefer "
                "specific exception types."
            ),
        ),
        _q(
            concept="error-handling",
            format="why",
            prompt="Why do experienced devs rarely re-raise the same exception type after logging?",
            code=(
                "try:\n"
                "    charge_card(amount)\n"
                "except PaymentError as e:\n"
                "    logger.error('Payment failed: %s', e)\n"
                "    raise PaymentError(str(e))  # <-- this line"
            ),
            opts=[
                ("It's slower -- creating a new exception has overhead", False),
                ("It destroys the original traceback and exception chain", True),
                ("Python forbids it in newer versions", False),
                ("It causes the logger to double-log the error", False),
            ],
            explanation=(
                "`raise PaymentError(str(e))` creates a NEW exception and loses the "
                "original traceback plus the `__cause__` chain. Just use bare `raise` "
                "to re-raise, or `raise NewError() from e` to wrap while keeping the "
                "context. This matters a lot when debugging production."
            ),
        ),
    ],
    "lru_cache": [
        _q(
            concept="caching",
            format="gotcha",
            prompt="This cache looks fine but will leak memory in a long-running process. Why?",
            code=(
                "@lru_cache\n"
                "def get_user(user: User) -> dict:\n"
                "    return db.query(...).filter_by(id=user.id).first()"
            ),
            opts=[
                ("@lru_cache without maxsize defaults to unlimited", True),
                ("User objects aren't hashable by default", False),
                ("db.query() returns a new object each time, breaking the cache", False),
                ("lru_cache should be applied to methods, not functions", False),
            ],
            explanation=(
                "Bare `@lru_cache` is equivalent to `@lru_cache(maxsize=128)` in older "
                "Python, but `@lru_cache` with no parens in modern Python means unlimited. "
                "Also: caching by User object is fragile -- if User has a custom __eq__ "
                "or is mutable, cache hits become inconsistent. Prefer caching by primitive "
                "keys like `user.id`."
            ),
        ),
        _q(
            concept="caching",
            format="tradeoff",
            prompt="Both memoize a pure function. When would you reach for the second one?",
            code=(
                "# A:\n"
                "@lru_cache(maxsize=128)\n"
                "def solve(n: int) -> int: ...\n\n"
                "# B:\n"
                "_cache: dict[int, int] = {}\n"
                "def solve(n: int) -> int:\n"
                "    if n not in _cache:\n"
                "        _cache[n] = ...\n"
                "    return _cache[n]"
            ),
            opts=[
                ("Never -- lru_cache is always better", False),
                ("When you need to inspect, clear, or mutate cache entries at runtime", True),
                ("When the function has side effects", False),
                ("When the function takes dict arguments", False),
            ],
            explanation=(
                "`lru_cache` is opaque -- you can call `.cache_info()` and `.cache_clear()`, "
                "but you can't peek at entries or evict a specific key. Manual dict caching "
                "is uglier but gives full control: inspect state, pre-warm from disk, "
                "selectively evict, share across modules. Use lru_cache by default; reach "
                "for manual dicts when you need control."
            ),
        ),
    ],
    "async_def": [
        _q(
            concept="async",
            format="output",
            prompt="What does this print?",
            code=(
                "async def work():\n"
                "    print('starting')\n"
                "    return 42\n\n"
                "result = work()\n"
                "print(result)"
            ),
            opts=[
                ("starting\\n42", False),
                ("42", False),
                ("<coroutine object work at 0x...>", True),
                ("RuntimeError: coroutine never awaited", False),
            ],
            explanation=(
                "Calling an async function does NOT run it -- it returns a coroutine "
                "object. 'starting' never prints because the body doesn't execute. "
                "You'd need `asyncio.run(work())` or `await work()` to actually run it. "
                "You WILL see a RuntimeWarning on exit though: 'coroutine was never "
                "awaited'."
            ),
        ),
        _q(
            concept="async",
            format="gotcha",
            prompt="This async function isn't faster than the sync version. Why?",
            code=(
                "async def fetch_all(urls):\n"
                "    results = []\n"
                "    for url in urls:\n"
                "        r = await client.get(url)\n"
                "        results.append(r)\n"
                "    return results"
            ),
            opts=[
                ("`async for` is needed instead of a plain for loop", False),
                ("`await` inside a for loop still runs sequentially -- use gather()", True),
                ("httpx client isn't async-compatible in this pattern", False),
                ("You need to await the results list at the end", False),
            ],
            explanation=(
                "`await` pauses until this one request completes, THEN the loop moves "
                "on. To run concurrently, collect coroutines first and `await "
                "asyncio.gather(*[client.get(u) for u in urls])`. This is the #1 async "
                "mistake -- you opt into async but accidentally keep the sequential "
                "behavior."
            ),
        ),
    ],
    "jwt": [
        _q(
            concept="jwt",
            format="scenario",
            prompt=(
                "Your JWT has a 30-minute expiry. A user's phone goes offline for an hour. "
                "They come back and fire 10 API calls. What's the best UX?"
            ),
            opts=[
                ("Return 401 on all 10 -- the client should re-login", False),
                ("Server-side extend the expiry if the token is 'nearly' valid", False),
                ("Use refresh tokens: short access token + long refresh token", True),
                ("Remove expiry entirely -- rely on revocation lists", False),
            ],
            explanation=(
                "Short access tokens limit damage from theft (good). But pure short "
                "tokens mean frequent re-logins (bad UX). Refresh tokens split the "
                "trade-off: the access token expires fast, but the client silently "
                "exchanges a long-lived refresh token for a new access token in the "
                "background. Revocation lists are fine but add database load on every "
                "request."
            ),
        ),
        _q(
            concept="jwt",
            format="gotcha",
            prompt="Why do security auditors flag this JWT code?",
            code=(
                "payload = jwt.decode(\n"
                "    token,\n"
                "    SECRET,\n"
                "    algorithms=['HS256', 'none']\n"
                ")"
            ),
            opts=[
                ("'none' bypasses signature verification -- anyone can forge tokens", True),
                ("Should use 'RS256' instead of 'HS256' in all cases", False),
                ("The SECRET is being passed positionally instead of by keyword", False),
                ("jwt.decode should be awaited", False),
            ],
            explanation=(
                "The 'none' algorithm means 'no signature verification'. Including it in "
                "`algorithms` lets an attacker send a token with `alg: none` and any "
                "payload they want -- and your code accepts it. This is the classic "
                "'alg confusion' attack. Never include 'none' in the allowed algorithms "
                "list. RS256 vs HS256 is orthogonal (asymmetric vs symmetric signing)."
            ),
        ),
    ],
    "http_status_created": [
        _q(
            concept="http-status",
            format="scenario",
            prompt=(
                "A client POSTs to /users. Creation succeeds but takes 30s because of "
                "downstream systems. What's the most correct response code?"
            ),
            opts=[
                ("201 Created, returned after everything finishes", False),
                ("202 Accepted, with a polling URL for status", True),
                ("200 OK, with a 'pending' field in the body", False),
                ("503 Service Unavailable until the creation completes", False),
            ],
            explanation=(
                "201 is for 'creation happened and here it is, now'. For slow or async "
                "creation, use `202 Accepted` with a Location or status URL the client "
                "can poll. 200 works but misses the signal that this is an async "
                "operation. 503 is wrong -- the service isn't unavailable, it's just "
                "being slow."
            ),
        ),
    ],
    "n_plus_one": [
        _q(
            concept="databases",
            format="bug",
            prompt="This endpoint is slow for users with many orders. Which line is the villain?",
            code=(
                "1  users = db.query(User).all()\n"
                "2  for user in users:\n"
                "3      user.order_total = sum(\n"
                "4          o.amount for o in user.orders\n"
                "5      )\n"
                "6  return users"
            ),
            opts=[
                ("Line 1 -- should use paginate()", False),
                ("Line 4 -- lazy-loads orders once per user (N+1)", True),
                ("Line 3 -- sum() is O(n) per user", False),
                ("Line 6 -- serializing the list is the bottleneck", False),
            ],
            explanation=(
                "`user.orders` on line 4 is a lazy relationship. For each user, the ORM "
                "fires a separate query -- 1 query for users + N queries for orders. "
                "Fix: `db.query(User).options(selectinload(User.orders)).all()` does "
                "it in 2 queries regardless of N."
            ),
        ),
    ],
    "list_comprehension": [
        _q(
            concept="comprehensions",
            format="output",
            prompt="What does this print?",
            code=(
                "data = [1, 2, 3, 4, 5]\n"
                "result = [x for x in data if x > 2 else 0]\n"
                "print(result)"
            ),
            opts=[
                ("[0, 0, 3, 4, 5]", False),
                ("[3, 4, 5]", False),
                ("SyntaxError", True),
                ("[1, 2, 3, 4, 5]", False),
            ],
            explanation=(
                "`if ... else` in a comprehension only works in the VALUE position, "
                "not the filter position. Legal: `[x if x>2 else 0 for x in data]`. "
                "Or filter: `[x for x in data if x>2]`. You can't combine `if...else` "
                "WITH a filter in the same comp; you'd nest them: "
                "`[x if x>2 else 0 for x in data if x is not None]`."
            ),
        ),
    ],
    "depends": [
        _q(
            concept="fastapi",
            format="why",
            prompt="Why use Depends() here instead of calling get_db() directly?",
            code=(
                "@app.get('/users/{id}')\n"
                "def get_user(id: int, db: Session = Depends(get_db)):\n"
                "    return db.query(User).get(id)"
            ),
            opts=[
                ("Performance -- Depends() caches the connection", False),
                ("Testability -- you can override get_db in tests with one line", True),
                ("FastAPI requires it for type hints to work", False),
                ("It automatically handles transactions", False),
            ],
            explanation=(
                "Dependency injection's main win is testing. In tests: "
                "`app.dependency_overrides[get_db] = lambda: fake_session`. Now every "
                "endpoint uses the fake DB without changing any application code. "
                "Calling get_db() directly ties your route to that specific function "
                "call site, making tests much harder to write."
            ),
        ),
    ],
    "generator_yield": [
        _q(
            concept="generators",
            format="tradeoff",
            prompt="Both process a 10GB log file. Which one do you reach for and why?",
            code=(
                "# A:\n"
                "def parse_log(path):\n"
                "    with open(path) as f:\n"
                "        lines = f.readlines()\n"
                "    return [parse(line) for line in lines]\n\n"
                "# B:\n"
                "def parse_log(path):\n"
                "    with open(path) as f:\n"
                "        for line in f:\n"
                "            yield parse(line)"
            ),
            opts=[
                ("A -- simpler, and the OS page cache handles memory", False),
                ("B -- streams one line at a time, constant memory", True),
                ("A if you need sorting later, B otherwise", False),
                ("Either one -- Python's GC handles it", False),
            ],
            explanation=(
                "A loads the entire 10GB file into memory as a list, then builds ANOTHER "
                "list of parsed results. B processes one line at a time, holding only "
                "the current line in memory. For large files, B uses ~O(1) memory vs "
                "A's O(N). This is the core value of generators: lazy evaluation."
            ),
        ),
    ],
    "context_manager_with": [
        _q(
            concept="resources",
            format="bug",
            prompt="What's wrong with this 'clean' code?",
            code=(
                "files = [open(p, 'r') for p in paths]\n"
                "try:\n"
                "    data = [f.read() for f in files]\n"
                "finally:\n"
                "    for f in files:\n"
                "        f.close()"
            ),
            opts=[
                ("Nothing -- the finally block handles cleanup", False),
                ("If open() raises on path 5/10, paths 1-4 never get closed", True),
                ("f.read() should be in a with block", False),
                ("It should use pathlib instead of open()", False),
            ],
            explanation=(
                "If `open()` raises partway through the comprehension, the files already "
                "opened will leak -- they're not in `files` yet, so the finally block "
                "misses them. `contextlib.ExitStack` handles this cleanly: "
                "`with ExitStack() as stack: files = [stack.enter_context(open(p)) for p in paths]`. "
                "Each file is registered as soon as it opens, so partial failure still cleans up."
            ),
        ),
    ],
    "pytest_fixture": [
        _q(
            concept="testing",
            format="why",
            prompt=(
                "You have a pytest fixture that opens a DB connection. Your test suite is "
                "slow because it opens a new connection for every test. How do you fix it?"
            ),
            code=(
                "@pytest.fixture\n"
                "def db():\n"
                "    conn = create_engine(TEST_URL).connect()\n"
                "    yield conn\n"
                "    conn.close()"
            ),
            opts=[
                ("Add @pytest.fixture(scope='session') -- one connection for all tests", True),
                ("Replace yield with return -- it's faster", False),
                ("Use a context manager instead of a fixture", False),
                ("Fixtures can't be cached; you have to use a global", False),
            ],
            explanation=(
                "The default scope is 'function' -- fixture runs once per test. Other "
                "scopes: 'class' (once per test class), 'module' (once per file), "
                "'session' (once per pytest run). Use session for expensive setup that's "
                "safe to share (DB connections, Docker containers). Be careful: shared "
                "state between tests is a common source of flaky tests."
            ),
        ),
    ],
}


# ───────── Pattern matchers ───────────────────────────────

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
    hits: list[str] = []
    for key, _, pat in PATTERNS:
        if pat.search(text):
            hits.append(key)
    return hits


def generate_question(text: str, seen_ids: set[str] | None = None) -> Question | None:
    """Pick a question that matches the context and hasn't been seen."""
    seen_ids = seen_ids or set()
    concepts = detect_concepts(text)
    random.shuffle(concepts)

    for concept in concepts:
        candidates = TEMPLATE_BANK.get(concept, [])
        fresh = [q for q in candidates if q.id not in seen_ids]
        if fresh:
            return random.choice(fresh)

    all_concepts = list(TEMPLATE_BANK.keys())
    random.shuffle(all_concepts)
    for concept in all_concepts:
        fresh = [q for q in TEMPLATE_BANK[concept] if q.id not in seen_ids]
        if fresh:
            return random.choice(fresh)

    return None
