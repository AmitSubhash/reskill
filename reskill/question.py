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
    ],    # ───── Python data model & gotchas ─────
    "mutable_default": [
        _q(
            concept="mutable-default",
            format="output",
            prompt="What does the second call print?",
            code=(
                "def add(item, bag=[]):\n"
                "    bag.append(item)\n"
                "    return bag\n\n"
                "print(add(1))\n"
                "print(add(2))"
            ),
            opts=[
                ("[1] then [2]", False),
                ("[1] then [1, 2]", True),
                ("[1] then [] then [2]", False),
                ("TypeError on the second call", False),
            ],
            explanation=(
                "Default arguments are evaluated ONCE at function definition. "
                "The list persists across calls. Idiom: use `bag=None` and "
                "`if bag is None: bag = []` inside the body."
            ),
        ),
    ],
    "late_binding_closure": [
        _q(
            concept="closures",
            format="output",
            prompt="What gets printed?",
            code=(
                "fns = [lambda: i for i in range(3)]\n"
                "print([f() for f in fns])"
            ),
            opts=[
                ("[0, 1, 2]", False),
                ("[2, 2, 2]", True),
                ("[3, 3, 3]", False),
                ("TypeError", False),
            ],
            explanation=(
                "Closures capture variables by reference, not value. By the time "
                "the lambdas run, `i` is 2. Fix with a default arg: "
                "`lambda i=i: i`, or `functools.partial`."
            ),
        ),
    ],
    "is_vs_eq": [
        _q(
            concept="identity",
            format="output",
            prompt="What does this print?",
            code=(
                "a = 257\n"
                "b = 257\n"
                "print(a is b, a == b)"
            ),
            opts=[
                ("True True", False),
                ("False True", True),
                ("True False", False),
                ("Implementation-defined for both", False),
            ],
            explanation=(
                "CPython caches small ints in [-5, 256], so `is` returns True "
                "there but is False above 256. Always use `==` for value compare; "
                "reserve `is` for None/True/False/sentinels."
            ),
        ),
    ],
    "copy_vs_deepcopy": [
        _q(
            concept="copy",
            format="bug",
            prompt="Mutating one row of grid_b corrupts grid_a. Which line is the bug?",
            code=(
                "1  import copy\n"
                "2  grid_a = [[0]*3 for _ in range(3)]\n"
                "3  grid_b = copy.copy(grid_a)\n"
                "4  grid_b[0][0] = 99\n"
                "5  print(grid_a[0][0])"
            ),
            opts=[
                ("Line 2 -- list multiplication shares references", False),
                ("Line 3 -- copy.copy is shallow; inner lists are shared", True),
                ("Line 4 -- you should slice with [0:1]", False),
                ("Line 5 -- print is evaluating lazily", False),
            ],
            explanation=(
                "`copy.copy` (shallow) duplicates the outer list but the inner "
                "lists are still the same objects. Use `copy.deepcopy(grid_a)` "
                "or `[row[:] for row in grid_a]`."
            ),
        ),
    ],
    "slots": [
        _q(
            concept="slots",
            format="why",
            prompt="Why might you add `__slots__` to a class with millions of instances?",
            code=(
                "class Point:\n"
                "    __slots__ = ('x', 'y')\n"
                "    def __init__(self, x, y):\n"
                "        self.x, self.y = x, y"
            ),
            opts=[
                ("Faster method dispatch via C-level lookups", False),
                ("Eliminates per-instance __dict__, cutting memory ~40-50%", True),
                ("Makes the class thread-safe", False),
                ("Required to use @dataclass", False),
            ],
            explanation=(
                "__slots__ replaces the per-instance dict with a fixed-size "
                "struct. Big memory win (and a small attribute-access speedup) "
                "but disallows new attributes and complicates multiple inheritance."
            ),
        ),
        _q(
            concept="slots",
            format="gotcha",
            prompt="Why does this code raise AttributeError?",
            code=(
                "class Node:\n"
                "    __slots__ = ('value',)\n"
                "\n"
                "n = Node()\n"
                "n.value = 1\n"
                "n.cached = 2   # <-- AttributeError"
            ),
            opts=[
                ("__slots__ must be a list, not a tuple", False),
                ("__slots__ forbids any attribute not listed, blocking dynamic additions", True),
                ("`cached` shadows a builtin slot name", False),
                ("Must use __setattr__ directly when __slots__ is set", False),
            ],
            explanation=(
                "A slotted class has no __dict__, so there is nowhere to store "
                "attributes that aren't named in __slots__. Add '__dict__' to the "
                "slots tuple to opt back into dynamic attributes (forfeiting most "
                "of the memory win), or list every attribute you need."
            ),
        ),
    ],
    "dataclass_frozen": [
        _q(
            concept="dataclass",
            format="idiom",
            prompt="You need a hashable, immutable record type. Most Pythonic?",
            opts=[
                ("class C:\n    def __init__(self, x): self.x = x", False),
                ("@dataclass(frozen=True, slots=True)\nclass C: x: int", True),
                ("collections.namedtuple('C', ['x'])", False),
                ("dict(x=1)  # just use a dict", False),
            ],
            explanation=(
                "`@dataclass(frozen=True, slots=True)` (3.10+) gives __hash__, "
                "__eq__, __repr__, immutability, and the memory benefit of "
                "__slots__ in one decorator. namedtuple still works but lacks "
                "field defaults and inheritance ergonomics."
            ),
        ),
    ],
    "walrus": [
        _q(
            concept="walrus",
            format="refactor",
            prompt="Best refactor of this read-loop?",
            code=(
                "chunk = f.read(4096)\n"
                "while chunk:\n"
                "    process(chunk)\n"
                "    chunk = f.read(4096)"
            ),
            opts=[
                ("for chunk in f: process(chunk)", False),
                ("while chunk := f.read(4096):\n    process(chunk)", True),
                ("while True:\n    process(f.read(4096))", False),
                ("process(f.read())  # one shot", False),
            ],
            explanation=(
                "The walrus `:=` (PEP 572) assigns AND tests in one expression, "
                "removing the duplicate read. `for chunk in f` would iterate "
                "lines, not 4096-byte blocks."
            ),
        ),
        _q(
            concept="walrus",
            format="idiom",
            prompt="Most idiomatic way to filter a list and reuse the computed value?",
            code=(
                "# goal: keep names whose lower-cased form starts with 'a'\n"
                "# and avoid calling .lower() twice per item"
            ),
            opts=[
                ("[n for n in names if n.lower().startswith('a')]", False),
                ("[low for n in names if (low := n.lower()).startswith('a')]", True),
                ("[n.lower() for n in names if n.startswith('a')]  # different result", False),
                ("list(filter(lambda n: n.lower().startswith('a'), names))", False),
            ],
            explanation=(
                "The walrus inside a comprehension lets you compute once and "
                "reuse in both the filter and the value. Writing it without "
                "`:=` either calls `.lower()` twice per element or changes the "
                "semantics (pre-filtering on the raw string)."
            ),
        ),
    ],
    "f_string_debug": [
        _q(
            concept="f-string",
            format="output",
            prompt="What prints?",
            code=(
                "x = [1, 2]\n"
                "print(f'{x=}')"
            ),
            opts=[
                ("[1, 2]", False),
                ("x=[1, 2]", True),
                ("x = [1, 2]", False),
                ("SyntaxError on older Pythons only", False),
            ],
            explanation=(
                "The `=` specifier (3.8+) prints both the expression text and "
                "its repr. Add `!r` or `:>10` after it for formatting. Best "
                "debug-print idiom in modern Python."
            ),
        ),
        _q(
            concept="f-string",
            format="output",
            prompt="What does this print?",
            code=(
                "name = 'ada'\n"
                "print(f'{name!r:>10}')"
            ),
            opts=[
                ("       ada", False),
                ("     'ada'", True),
                ("'       ada'", False),
                ("TypeError: conversion after format spec", False),
            ],
            explanation=(
                "The `!r` conversion runs first (yielding the 5-char string "
                "`'ada'`), then the format spec `>10` right-justifies that in "
                "a width-10 field. Order in f-strings is always value -> "
                "conversion (`!r`/`!s`/`!a`) -> format spec."
            ),
        ),
    ],
    "dict_order": [
        _q(
            concept="dict",
            format="why",
            prompt="Why can experienced devs now rely on dict iteration order?",
            opts=[
                ("PEP 468 made kwargs ordered, dicts are still arbitrary", False),
                ("CPython 3.6 made it an impl detail; 3.7 promoted it to language spec", True),
                ("Only OrderedDict guarantees it; dict does not", False),
                ("Sorted by hash, which is stable across runs", False),
            ],
            explanation=(
                "Insertion-order is GUARANTEED since Python 3.7. OrderedDict "
                "still has uses (move_to_end, equality is order-sensitive) but "
                "for plain ordering, dict is enough now."
            ),
        ),
        _q(
            concept="dict",
            format="output",
            prompt="What does this print?",
            code=(
                "from collections import OrderedDict\n"
                "a = {'x': 1, 'y': 2}\n"
                "b = {'y': 2, 'x': 1}\n"
                "print(a == b, OrderedDict(a) == OrderedDict(b))"
            ),
            opts=[
                ("True True", False),
                ("True False", True),
                ("False True", False),
                ("False False", False),
            ],
            explanation=(
                "Plain dict equality is order-INSENSITIVE even though iteration "
                "preserves insertion order. OrderedDict equality is "
                "order-SENSITIVE -- that's one of the few remaining reasons to "
                "reach for it. Same keys, different order, different answer."
            ),
        ),
    ],
    "pathlib_path": [
        _q(
            concept="pathlib",
            format="idiom",
            prompt="Most Pythonic way to read a UTF-8 JSON file?",
            opts=[
                ("open(os.path.join(d,'f.json')).read()", False),
                ("Path(d, 'f.json').read_text(encoding='utf-8')", True),
                ("with codecs.open(...) as f: f.read()", False),
                ("io.open(d+'/f.json','r').read()", False),
            ],
            explanation=(
                "`pathlib.Path` cross-platform-joins, opens with explicit "
                "encoding, and avoids file-descriptor leaks since `read_text` "
                "closes for you. Always pass `encoding=` -- the default is "
                "platform-dependent (locale.getencoding)."
            ),
        ),
        _q(
            concept="pathlib",
            format="gotcha",
            prompt="Why does `root.glob('*.py')` miss files inside subdirectories?",
            code=(
                "root = Path('src')\n"
                "files = list(root.glob('*.py'))  # only top-level hits"
            ),
            opts=[
                ("`.glob` only matches directories, use `.iterdir` for files", False),
                ("`*` doesn't cross directory boundaries; use `rglob` or `**/*.py`", True),
                ("Need to call `.resolve()` first for glob to recurse", False),
                ("Path.glob ignores hidden directories, including src/", False),
            ],
            explanation=(
                "In pathlib/fnmatch, a single `*` matches one path segment. To "
                "recurse, either use `root.rglob('*.py')` or the explicit "
                "double-star `root.glob('**/*.py')`. Same rule as shell globbing "
                "under globstar."
            ),
        ),
    ],
    "datetime_tz": [
        _q(
            concept="datetime",
            format="cause",
            prompt="`TypeError: can't compare offset-naive and offset-aware datetimes`. Why?",
            code=(
                "from datetime import datetime, timezone\n"
                "a = datetime.utcnow()\n"
                "b = datetime.now(timezone.utc)\n"
                "print(a < b)"
            ),
            opts=[
                ("Clock skew between OS calls", False),
                ("`utcnow()` returns a NAIVE datetime; `now(tz=...)` returns aware", True),
                ("`<` is undefined on datetime", False),
                ("UTC isn't a real timezone object", False),
            ],
            explanation=(
                "`datetime.utcnow()` is a footgun: returns naive UTC. Always "
                "use `datetime.now(timezone.utc)` (or `zoneinfo.ZoneInfo('UTC')`). "
                "Naive vs aware datetimes won't compare or subtract."
            ),
        ),
        _q(
            concept="datetime",
            format="gotcha",
            prompt="A scheduled event for 2:30 AM fires twice on the fall-back DST day. Most robust fix?",
            code=(
                "from zoneinfo import ZoneInfo\n"
                "dt = datetime(2025, 11, 2, 2, 30, tzinfo=ZoneInfo('America/New_York'))"
            ),
            opts=[
                ("Store local time; zoneinfo handles DST automatically", False),
                ("Store UTC internally and only convert to local for display", True),
                ("Pin `fold=0` and trust pytz instead of zoneinfo", False),
                ("Switch to `datetime.utcnow()` everywhere for safety", False),
            ],
            explanation=(
                "Local-time fields during the fall-back hour are ambiguous "
                "(2:30 AM happens twice). `fold=0/1` lets you disambiguate but "
                "is easy to forget. The durable fix is store-as-UTC, "
                "display-as-local. Naive utcnow is the opposite of what you want."
            ),
        ),
    ],
    "subprocess_shell": [
        _q(
            concept="subprocess",
            format="gotcha",
            prompt="Security review flags this. Why?",
            code=(
                "subprocess.run(\n"
                "    f'grep {pattern} {path}',\n"
                "    shell=True, check=True\n"
                ")"
            ),
            opts=[
                ("`check=True` raises on nonzero exit -- should be False", False),
                ("`shell=True` with f-string interpolation enables shell injection", True),
                ("`subprocess.run` is deprecated; use `os.system`", False),
                ("Missing `capture_output=True` makes it hang", False),
            ],
            explanation=(
                "If `pattern = 'foo; rm -rf ~'`, the shell happily runs both. "
                "Pass a list and skip the shell: "
                "`subprocess.run(['grep', pattern, path], check=True)`. Use "
                "`shell=True` only with hard-coded strings."
            ),
        ),
        _q(
            concept="subprocess",
            format="bug",
            prompt="`result.stdout.splitlines()` raises TypeError. Why?",
            code=(
                "result = subprocess.run(\n"
                "    ['git', 'log', '--oneline'],\n"
                "    capture_output=True, check=True,\n"
                ")\n"
                "for line in result.stdout.splitlines():\n"
                "    print(line.strip().upper())"
            ),
            opts=[
                ("`check=True` replaces stdout with None on success", False),
                ("stdout is `bytes` by default; need `text=True` (or decode)", True),
                ("`capture_output` and `check` are mutually exclusive", False),
                ("`splitlines()` doesn't exist on subprocess output objects", False),
            ],
            explanation=(
                "Without `text=True` (alias `universal_newlines=True`), "
                "stdout/stderr are `bytes`. `.upper()` on bytes works but then "
                "collides with later str ops; `.strip()` on bytes is fine but "
                "mixing with f-strings breaks. Prefer `text=True` or set "
                "`encoding='utf-8'`."
            ),
        ),
    ],
    "logging_lazy": [
        _q(
            concept="logging",
            format="bug",
            prompt="Why does the linter flag line 2?",
            code=(
                "1  user = lookup(uid)\n"
                "2  log.debug(f'fetched user {user!r}')\n"
                "3  return user"
            ),
            opts=[
                ("f-strings are slower than .format()", False),
                ("It formats the string even when DEBUG is disabled", True),
                ("`!r` is invalid in logging", False),
                ("log.debug shouldn't accept user data", False),
            ],
            explanation=(
                "`log.debug('fetched user %r', user)` defers formatting until "
                "the handler decides to emit. f-strings always evaluate, "
                "burning CPU on hot paths in production where DEBUG is off."
            ),
        ),
        _q(
            concept="logging",
            format="why",
            prompt="A library author writes `logging.getLogger(__name__)` but never adds handlers. Why?",
            opts=[
                ("Oversight -- handlers are required for logs to appear", False),
                ("Libraries should only emit; the APPLICATION configures handlers", True),
                ("Handlers must be attached to the root logger exclusively", False),
                ("Without handlers, nothing is emitted, silencing the library by default", False),
            ],
            explanation=(
                "The convention is: libraries create named loggers and emit. "
                "Applications decide where logs go (stdout, file, Sentry) and "
                "at what level. If the app configures nothing, Python's "
                "last-resort handler still emits warnings+ to stderr, so the "
                "library isn't silent by default."
            ),
        ),
    ],
    "typeddict": [
        _q(
            concept="typing-typeddict",
            format="idiom",
            prompt="REST endpoint returns a JSON dict with optional `email`. Best type?",
            opts=[
                ("dict[str, Any]", False),
                ("class User(TypedDict):\n    id: int\n    email: NotRequired[str]", True),
                ("@dataclass\nclass User: id: int; email: str | None", False),
                ("namedtuple('User', ['id','email'])", False),
            ],
            explanation=(
                "TypedDict (PEP 589) is the right tool for dict-shaped JSON "
                "payloads -- no runtime construction cost, mypy-checked. "
                "`NotRequired` (PEP 655) marks optional keys without unioning "
                "the value type."
            ),
        ),
        _q(
            concept="typing-typeddict",
            format="idiom",
            prompt="You want a type alias for a matrix row that's reusable and mypy-friendly. Best in 3.12+?",
            opts=[
                ("Row = list[float]  # assignment-based alias", False),
                ("type Row = list[float]  # PEP 695 type statement", True),
                ("Row: TypeAlias = list[float]  # still needed", False),
                ("Row = NewType('Row', list[float])  # strictest", False),
            ],
            explanation=(
                "PEP 695 (3.12) added the `type` soft keyword for lazy-"
                "evaluated, explicitly-aliased types -- resolves forward "
                "references and avoids `TypeAlias` noise. `NewType` creates a "
                "distinct nominal type, which is stricter than what an alias "
                "asks for."
            ),
        ),
    ],
    "protocol_vs_abc": [
        _q(
            concept="typing-protocol",
            format="why",
            prompt="Why prefer `Protocol` over an ABC for a `Repository` interface?",
            opts=[
                ("Protocols are faster at runtime", False),
                ("Structural typing -- existing classes match without inheriting", True),
                ("ABCs are deprecated in 3.12", False),
                ("Only Protocol supports generics", False),
            ],
            explanation=(
                "Protocol (PEP 544) gives static duck-typing: any class with "
                "the right methods is a Repository, no `class X(Repository)` "
                "needed. ABCs force inheritance, which couples you to the "
                "interface module."
            ),
        ),
        _q(
            concept="typing-protocol",
            format="gotcha",
            prompt="What does `isinstance(obj, HasLen)` do here?",
            code=(
                "from typing import Protocol, runtime_checkable\n"
                "\n"
                "@runtime_checkable\n"
                "class HasLen(Protocol):\n"
                "    def __len__(self) -> int: ...\n"
                "\n"
                "isinstance([1, 2], HasLen)"
            ),
            opts=[
                ("Raises TypeError -- Protocols aren't usable at runtime", False),
                ("Returns True; @runtime_checkable enables structural isinstance (members only, not signatures)", True),
                ("Returns False -- list doesn't inherit from Protocol", False),
                ("Always True for any object, since Protocol has no methods at runtime", False),
            ],
            explanation=(
                "`@runtime_checkable` lets `isinstance` verify that the object "
                "has the named attributes, but it does NOT check signatures or "
                "return types. It's a cheap structural probe, useful for duck-"
                "typed dispatch but not a substitute for a static type checker."
            ),
        ),
    ],
    "gil_decision": [
        _q(
            concept="concurrency",
            format="scenario",
            prompt="You need to speed up a CPU-bound numpy-light pure-Python loop. Best?",
            opts=[
                ("threading.Thread x 8", False),
                ("multiprocessing.Pool or ProcessPoolExecutor", True),
                ("asyncio.gather over the items", False),
                ("Add @lru_cache and call it a day", False),
            ],
            explanation=(
                "GIL serializes pure-Python bytecode, so threads don't help "
                "CPU-bound work. Processes get parallelism at the cost of IPC "
                "overhead. asyncio is for I/O-bound waits. (numpy-heavy code "
                "often releases the GIL and CAN benefit from threads.)"
            ),
        ),
        _q(
            concept="concurrency",
            format="scenario",
            prompt="You have 500 outbound HTTP requests to slow third-party APIs. Python 3.11. Best?",
            opts=[
                ("ProcessPoolExecutor with 500 workers", False),
                ("asyncio + aiohttp with a semaphore-bounded gather", True),
                ("Single-threaded requests.get in a for loop with lru_cache", False),
                ("threading.Thread per request, no pool", False),
            ],
            explanation=(
                "I/O-bound work is asyncio's sweet spot: one event loop "
                "juggles thousands of in-flight sockets with tiny overhead. "
                "Processes are heavy and wasteful here. A raw thread-per-"
                "request works but burns memory on stacks and context "
                "switches -- bound it with a pool or a semaphore."
            ),
        ),
    ],
    "asyncio_taskgroup": [
        _q(
            concept="async-taskgroup",
            format="refactor",
            prompt="Modern (3.11+) replacement for `asyncio.gather` with proper cancellation?",
            opts=[
                ("asyncio.wait_for(gather(...), 30)", False),
                ("async with asyncio.TaskGroup() as tg: tg.create_task(...)", True),
                ("asyncio.run_until_complete(...)", False),
                ("Just await each coroutine in a list", False),
            ],
            explanation=(
                "TaskGroup (3.11) gives structured concurrency: if one task "
                "raises, siblings are cancelled and an ExceptionGroup is "
                "raised. `gather` swallows the second-and-onward errors and "
                "leaks tasks on cancel."
            ),
        ),
        _q(
            concept="async-taskgroup",
            format="idiom",
            prompt="Three sibling tasks all fail. How do you catch only the TimeoutError subset from the TaskGroup?",
            opts=[
                ("except TimeoutError as e: ...   # still works on ExceptionGroup", False),
                ("except* TimeoutError as eg: ...  # PEP 654 except-star", True),
                ("for exc in tg.exceptions:\n    if isinstance(exc, TimeoutError): ...", False),
                ("Wrap the TaskGroup in asyncio.wait_for", False),
            ],
            explanation=(
                "TaskGroup raises ExceptionGroup. PEP 654's `except*` "
                "(3.11+) splits the group by type: matched exceptions go to "
                "the handler as a sub-group, the rest re-propagate. A plain "
                "`except TimeoutError` won't match an ExceptionGroup that "
                "CONTAINS one."
            ),
        ),
    ],
    "race_condition": [
        _q(
            concept="concurrency-race",
            format="cause",
            prompt="Counter occasionally undercounts under threads. Most likely cause?",
            code=(
                "count = 0\n"
                "def bump():\n"
                "    global count\n"
                "    count += 1"
            ),
            opts=[
                ("`global` is unsafe in threads", False),
                ("`count += 1` is read-modify-write, not atomic across threads", True),
                ("The GIL makes all integer ops atomic, so this can't happen", False),
                ("Python integers are immutable so writes are lost", False),
            ],
            explanation=(
                "Even with the GIL, bytecode boundaries can interleave between "
                "the LOAD and STORE. Use `threading.Lock`, `itertools.count`, "
                "or `queue.Queue`. (CPython's `list.append` IS atomic, but "
                "`+=` on an int is not.)"
            ),
        ),
        _q(
            concept="concurrency-race",
            format="bug",
            prompt="This 'check then act' cache occasionally double-fetches. Why?",
            code=(
                "def get(key):\n"
                "    if key not in cache:          # <-- check\n"
                "        cache[key] = fetch(key)   # <-- act\n"
                "    return cache[key]"
            ),
            opts=[
                ("`dict.__contains__` isn't thread-safe", False),
                ("TOCTOU: another thread can insert between the check and the act", True),
                ("`fetch` should be memoized with @lru_cache instead", False),
                ("Need `threading.local()` around the cache dict", False),
            ],
            explanation=(
                "Classic time-of-check / time-of-use race. Two threads see "
                "the key missing, both call fetch. Fix with a lock around "
                "the region, use `cache.setdefault(key, fetch(key))` "
                "(still calls fetch twice), or `dict.get` + lock, or a "
                "proper cache lib with single-flight semantics."
            ),
        ),
    ],
    "pytest_parametrize": [
        _q(
            concept="testing-parametrize",
            format="idiom",
            prompt="Most idiomatic way to test the same logic over 4 inputs?",
            opts=[
                ("Four separate test functions", False),
                ("@pytest.mark.parametrize('a,b,exp', [(1,2,3),...])", True),
                ("for a,b,exp in cases: assert f(a,b)==exp", False),
                ("subTest in a single test method", False),
            ],
            explanation=(
                "`parametrize` makes each case a separate reported test (own "
                "name, own pass/fail). A for-loop stops at the first failure "
                "and gives one combined report -- much harder to debug."
            ),
        ),
        _q(
            concept="testing-parametrize",
            format="why",
            prompt="Why add `ids=[...]` to a parametrize with dict payloads?",
            code=(
                "@pytest.mark.parametrize(\n"
                "    'payload,expected',\n"
                "    [({'role':'admin'}, 200), ({'role':'guest'}, 403)],\n"
                "    ids=['admin-allowed', 'guest-forbidden'],\n"
                ")"
            ),
            opts=[
                ("Required -- pytest won't run the test without ids", False),
                ("Readable test names in reports and `-k` filters; default repr is noisy or non-deterministic", True),
                ("Makes the fixture cache-key deterministic for xdist", False),
                ("ids control the order the cases run in", False),
            ],
            explanation=(
                "Without `ids`, pytest auto-generates them from the values, "
                "which is fine for primitives but ugly for dicts/objects "
                "(`payload0`, `payload1`). Custom ids give you grep-friendly "
                "names in test output and let you run a single case with "
                "`pytest -k guest-forbidden`."
            ),
        ),
    ],
    "mock_patch_target": [
        _q(
            concept="testing-mock",
            format="bug",
            prompt="Test still hits the real network. Why?",
            code=(
                "# myapp/service.py\n"
                "from requests import get\n"
                "def fetch(): return get(URL).json()\n\n"
                "# tests/test_service.py\n"
                "@patch('requests.get')\n"
                "def test_fetch(mock_get): ..."
            ),
            opts=[
                ("@patch can't replace functions, only classes", False),
                ("You patched where `get` is DEFINED, not where it's USED", True),
                ("Need autospec=True to patch builtins-like callables", False),
                ("`from x import y` makes y un-patchable", False),
            ],
            explanation=(
                "Patch the namespace that LOOKS UP the name: "
                "`@patch('myapp.service.get')`. The original module-level import "
                "in service.py created a local binding that the global "
                "`requests.get` patch can't reach."
            ),
        ),
        _q(
            concept="testing-mock",
            format="why",
            prompt="Why do senior devs default to `autospec=True` when patching?",
            code=(
                "@patch('myapp.db.Client', autospec=True)\n"
                "def test_save(mock_cls): ..."
            ),
            opts=[
                ("It runs the real constructor first for realism", False),
                ("It enforces the mocked object's signature so typo'd calls fail fast", True),
                ("It auto-restores the patch if the test raises", False),
                ("autospec enables async support in MagicMock", False),
            ],
            explanation=(
                "Plain `MagicMock` accepts any call, any attribute -- "
                "`mock.crete_user(...)` (typo) silently returns another mock "
                "and the test still passes. `autospec=True` copies the real "
                "signature, so wrong calls raise at test-time. Pair with "
                "`side_effect=Exception(...)` to simulate failures."
            ),
        ),
    ],
    "numpy_view_copy": [
        _q(
            concept="numpy",
            format="output",
            prompt="What does `a[0, 1]` print at the end?",
            code=(
                "import numpy as np\n"
                "a = np.arange(6).reshape(2, 3)\n"
                "b = a[:, 1:]\n"
                "b[0, 0] = 99\n"
                "print(a[0, 1])"
            ),
            opts=[
                ("1 (slice copies)", False),
                ("99 (basic slice returns a view)", True),
                ("0 (numpy is functional)", False),
                ("Raises -- can't assign into a slice", False),
            ],
            explanation=(
                "Basic slicing on ndarray returns a VIEW that shares memory. "
                "Use `a[:, 1:].copy()` to detach. Fancy indexing (boolean or "
                "integer arrays) DOES copy -- learn the boundary or you'll "
                "have ghost mutations."
            ),
        ),
        _q(
            concept="numpy",
            format="output",
            prompt="What does `a[0, 0]` print at the end?",
            code=(
                "import numpy as np\n"
                "a = np.arange(6).reshape(2, 3)\n"
                "idx = np.array([0, 1])\n"
                "b = a[idx]          # fancy indexing\n"
                "b[0, 0] = 99\n"
                "print(a[0, 0])"
            ),
            opts=[
                ("99 (any indexing returns a view)", False),
                ("0 (fancy integer indexing returns a COPY)", True),
                ("Raises -- can't mix slices and arrays", False),
                ("Implementation-defined between numpy versions", False),
            ],
            explanation=(
                "Integer-array and boolean-mask indexing ALWAYS copy. Only "
                "basic slicing (`a[:, 1:]`, `a[0]`) returns a view. "
                "`np.may_share_memory(a, b)` is the sanity check when you're "
                "unsure; also consider `np.ascontiguousarray` before passing "
                "to C extensions."
            ),
        ),
    ],
    "numpy_broadcasting": [
        _q(
            concept="numpy-broadcast",
            format="output",
            prompt="Shape of `out`?",
            code=(
                "a = np.ones((3, 1, 5))\n"
                "b = np.ones((4, 1))\n"
                "out = a + b"
            ),
            opts=[
                ("(3, 4, 5)", True),
                ("(4, 1, 5)", False),
                ("ValueError: shapes not aligned", False),
                ("(3, 5)", False),
            ],
            explanation=(
                "Broadcasting aligns trailing dims and stretches size-1 dims. "
                "(3,1,5) and (_,4,1) -> (3,4,5). Mental model: right-align the "
                "shapes, every dim must match or be 1."
            ),
        ),
        _q(
            concept="numpy-broadcast",
            format="bug",
            prompt="You want to subtract per-column means from a (1000, 4) matrix. Which fails?",
            code=(
                "X = np.random.rand(1000, 4)\n"
                "mu = X.mean(axis=0)   # shape (4,)\n"
                "# A: X - mu\n"
                "# B: X - mu[:, None]\n"
                "# C: X - mu.reshape(1, 4)"
            ),
            opts=[
                ("A fails -- (1000,4) and (4,) don't align", False),
                ("B fails -- (4,1) can't broadcast against (1000,4)", True),
                ("C fails -- reshape can't add axes", False),
                ("All three work identically", False),
            ],
            explanation=(
                "Right-align shapes: (1000,4) vs (4,) pads to (1,4) -> "
                "broadcasts fine (A and C work). (4,1) pads to (1,4,1) vs "
                "(1000,4) -- trailing dims 1 and 4 match, but middle 4 vs "
                "1000 does not. `mu[:, None]` is the right move for "
                "per-ROW means, not columns."
            ),
        ),
    ],
    "pandas_settingwithcopy": [
        _q(
            concept="pandas",
            format="bug",
            prompt="Pandas yells `SettingWithCopyWarning` here. Real fix?",
            code=(
                "subset = df[df.age > 18]\n"
                "subset['adult'] = True"
            ),
            opts=[
                ("Use `subset.adult = True`", False),
                ("Use `df.loc[df.age > 18, 'adult'] = True`", True),
                ("Wrap in `with pd.option_context(...)` to silence", False),
                ("Call `.reset_index()` on subset first", False),
            ],
            explanation=(
                "Chained indexing (`df[mask]['col'] = ...`) may write to a "
                "view OR a copy -- pandas can't tell. Always express the "
                "single assignment with `.loc[mask, col] = val`."
            ),
        ),
        _q(
            concept="pandas",
            format="gotcha",
            prompt="Why do experienced pandas users avoid `inplace=True`?",
            code=(
                "df.drop_duplicates(inplace=True)\n"
                "df.fillna(0, inplace=True)\n"
                "df.rename(columns={'a':'A'}, inplace=True)"
            ),
            opts=[
                ("It's faster but dangerous in multi-threaded code", False),
                ("It doesn't save memory (still copies internally), breaks method chaining, and is slated for removal", True),
                ("`inplace=True` is a typo -- the real kwarg is `in_place=True`", False),
                ("It only works on columns with a unique index", False),
            ],
            explanation=(
                "The pandas team has deprecated most `inplace` paths: they "
                "often allocate a new block internally anyway, they break "
                "fluent chains (`df.fillna(0).drop_duplicates()`), and they "
                "complicate Copy-on-Write (CoW) semantics in 2.x. Prefer "
                "`df = df.fillna(0)` or a pipeline."
            ),
        ),
    ],
    "torch_detach": [
        _q(
            concept="pytorch",
            format="why",
            prompt="Why `.detach().cpu().numpy()` and not just `.numpy()`?",
            code=(
                "loss = model(x).mean()\n"
                "history.append(loss.detach().cpu().numpy())"
            ),
            opts=[
                ("Cosmetic -- the three calls are equivalent to .numpy()", False),
                ("detach drops the autograd graph; cpu moves off CUDA; numpy needs CPU + no-grad", True),
                ("numpy() automatically detaches, but only for float32", False),
                ("Required for DataLoader workers", False),
            ],
            explanation=(
                "`.numpy()` errors if the tensor still requires grad OR is on "
                "CUDA. `.detach()` severs the autograd graph (otherwise you "
                "leak the whole compute graph through `history`). `.cpu()` "
                "transfers off-device. Skipping detach is the #1 silent OOM "
                "in training loops."
            ),
        ),
        _q(
            concept="pytorch",
            format="bug",
            prompt="Validation accuracy is erratic AND training is 3x slower than expected. Which single change helps both?",
            code=(
                "for x, y in val_loader:\n"
                "    out = model(x)\n"
                "    val_loss += loss_fn(out, y).item()"
            ),
            opts=[
                ("Wrap the loop in `with torch.no_grad(): model.eval()`", True),
                ("Call `model.train()` before the loop -- eval breaks BatchNorm", False),
                ("Replace `.item()` with `.numpy()` to save memory", False),
                ("Increase DataLoader `num_workers` to 16", False),
            ],
            explanation=(
                "`model.eval()` disables Dropout and switches BatchNorm to "
                "running stats -- that's the erratic accuracy fix. "
                "`torch.no_grad()` stops autograd from building the graph, "
                "which kills the memory/speed overhead during eval. Both are "
                "always-on in production inference loops."
            ),
        ),
    ],
    "matplotlib_close": [
        _q(
            concept="matplotlib",
            format="cause",
            prompt="Memory grows linearly while batch-saving 10k figures. Why?",
            code=(
                "for i, data in enumerate(items):\n"
                "    fig, ax = plt.subplots()\n"
                "    ax.plot(data)\n"
                "    fig.savefig(f'out/{i}.png')"
            ),
            opts=[
                ("savefig caches the rendered PNG in memory", False),
                ("pyplot keeps every Figure in its registry until you close it", True),
                ("matplotlib leaks the GIL", False),
                ("PNG encoder retains the last canvas", False),
            ],
            explanation=(
                "`plt.subplots()` registers the figure with the pyplot state "
                "machine. Add `plt.close(fig)` (or use the OO API: "
                "`Figure(); FigureCanvasAgg(...).print_png(...)`)."
            ),
        ),
        _q(
            concept="matplotlib",
            format="why",
            prompt="In a headless server / CI job, why switch to the Agg backend before importing pyplot?",
            code=(
                "import matplotlib\n"
                "matplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt"
            ),
            opts=[
                ("Agg renders faster than the interactive backends", False),
                ("Default backends try to open a GUI window, which fails without a display (Tkinter/Qt error)", True),
                ("Agg is required to save PNG -- other backends can't", False),
                ("It silences all matplotlib warnings", False),
            ],
            explanation=(
                "Interactive backends (TkAgg, QtAgg, MacOSX) need a display "
                "server; headless boxes throw `_tkinter.TclError` or Qt "
                "display-init errors. Agg is a pure pixel-buffer backend -- "
                "no GUI needed -- and outputs PNG/PDF/SVG fine. Set it BEFORE "
                "the first `import pyplot` or the backend is locked in."
            ),
        ),
    ],
    "constant_time_compare": [
        _q(
            concept="security",
            format="why",
            prompt="Why use `hmac.compare_digest(a, b)` instead of `a == b` for tokens?",
            opts=[
                ("It hashes both sides first", False),
                ("Constant-time comparison defeats timing-based side-channels", True),
                ("`==` is broken for bytes objects", False),
                ("It auto-base64-decodes", False),
            ],
            explanation=(
                "Plain `==` short-circuits at the first mismatched byte. Network "
                "attackers can use response-time differences to recover the "
                "secret one byte at a time. `compare_digest` always scans both "
                "fully."
            ),
        ),
    ],
    "cors_preflight": [
        _q(
            concept="cors",
            format="cause",
            prompt="Browser fires an OPTIONS request before POSTing JSON. Why?",
            opts=[
                ("Always for cross-origin requests", False),
                ("POST + Content-Type: application/json triggers preflight (non-simple)", True),
                ("Bug in the browser; should not happen", False),
                ("Service worker is intercepting", False),
            ],
            explanation=(
                "Simple requests (GET/HEAD/POST with form-data Content-Types) "
                "skip preflight. JSON bodies, custom headers, or methods "
                "outside GET/HEAD/POST trigger an OPTIONS preflight that the "
                "server must answer with the right Access-Control-* headers."
            ),
        ),
    ],
    "retry_jitter": [
        _q(
            concept="http-retry",
            format="tradeoff",
            prompt="Service overloaded; 1000 clients retry with `sleep(2**n)`. Result?",
            opts=[
                ("Smooth recovery -- exponential backoff is enough", False),
                ("Thundering herd at each power of 2 boundary; add jitter", True),
                ("Clients give up; backoff is too aggressive", False),
                ("OS combines retries via TCP coalescing", False),
            ],
            explanation=(
                "Synchronized exponential backoff just moves the spike. Add "
                "random jitter: `sleep(random.uniform(0, 2**n))` (full jitter) "
                "or `sleep(2**n / 2 + random.uniform(0, 2**n / 2))` "
                "(equal jitter). AWS Architecture Blog has the canonical writeup."
            ),
        ),
    ],
    "sql_null_semantics": [
        _q(
            concept="sql",
            format="output",
            prompt="A column has values [1, 2, NULL]. What does `SELECT * WHERE col NOT IN (2, NULL)` return?",
            opts=[
                ("[1]", False),
                ("[1, NULL]", False),
                ("Empty set", True),
                ("[1, 2]", False),
            ],
            explanation=(
                "`x NOT IN (2, NULL)` becomes `x<>2 AND x<>NULL`. Anything "
                "compared to NULL is UNKNOWN, so the AND is never TRUE. Use "
                "`NOT EXISTS` or strip NULLs from the IN list."
            ),
        ),
    ],
    "window_function": [
        _q(
            concept="sql-window",
            format="refactor",
            prompt="Get each user's most recent order without losing other columns. Best?",
            opts=[
                ("GROUP BY user_id and MAX(created_at) -- columns will collapse", False),
                ("ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) = 1", True),
                ("DISTINCT ON every column -- portable across DBs", False),
                ("SELECT MAX(*) FROM orders", False),
            ],
            explanation=(
                "Window functions retain row context. `ROW_NUMBER() OVER (...)` "
                "ranks per-partition without collapsing; filter on rn=1. "
                "Postgres has `DISTINCT ON` as a shortcut, but it's non-standard."
            ),
        ),
    ],
    "rebase_vs_merge": [
        _q(
            concept="git",
            format="scenario",
            prompt="You want to update your feature branch with main without ugly merge bubbles. Best?",
            opts=[
                ("git merge main", False),
                ("git rebase main, then force-push WITH-LEASE", True),
                ("git pull --rebase=preserve", False),
                ("git reset --hard origin/main", False),
            ],
            explanation=(
                "Rebase replays your commits on top of main for a linear "
                "history. Use `--force-with-lease` (not `--force`) so you "
                "abort if someone else pushed to your branch in the meantime. "
                "Never rebase shared/long-lived branches like main."
            ),
        ),
    ],
    "set_pipefail": [
        _q(
            concept="bash",
            format="bug",
            prompt="`curl bad-url | tee out.log` exits 0 even though curl failed. Fix?",
            opts=[
                ("Add `set -e` at the top", False),
                ("Add `set -euo pipefail` -- without pipefail, pipeline status is the LAST cmd", True),
                ("Replace tee with `>` redirect", False),
                ("Use `&&` between curl and tee", False),
            ],
            explanation=(
                "Default bash returns the exit status of the rightmost "
                "command in a pipeline. `set -o pipefail` makes the pipeline "
                "fail if ANY stage fails. Combined with `set -eu` it's the "
                "safe default for scripts."
            ),
        ),
    ],
    "find_xargs": [
        _q(
            concept="bash-xargs",
            format="bug",
            prompt="`find . -name '*.py' | xargs grep TODO` mishandles a file named `my file.py`. Fix?",
            opts=[
                ("Quote the glob: `'*.py'` (already done; should still work)", False),
                ("`find . -name '*.py' -print0 | xargs -0 grep TODO`", True),
                ("Use `find -exec grep TODO {} +` -- xargs is deprecated", False),
                ("Wrap in a subshell", False),
            ],
            explanation=(
                "xargs splits on whitespace by default, so `my file.py` "
                "becomes two args. `-print0` separates with NUL bytes; `-0` "
                "tells xargs to use them. `-exec ... +` is also fine and "
                "avoids xargs entirely."
            ),
        ),
    ],
    "useeffect_deps": [
        _q(
            concept="react",
            format="bug",
            prompt="Counter logs stale values forever. Fix?",
            code=(
                "function C() {\n"
                "  const [n, setN] = useState(0);\n"
                "  useEffect(() => {\n"
                "    const id = setInterval(() => console.log(n), 1000);\n"
                "    return () => clearInterval(id);\n"
                "  }, []);\n"
                "  return <button onClick={() => setN(n+1)}>{n}</button>;\n"
                "}"
            ),
            opts=[
                ("Use `useLayoutEffect` instead", False),
                ("Add `n` to the deps array, or use a ref / functional setState", True),
                ("Move setInterval outside the effect", False),
                ("React effects can't read state -- use Redux", False),
            ],
            explanation=(
                "Empty deps freezes the closure on the first render's `n` "
                "(stale closure). Either depend on `n` (re-creates the "
                "interval) or use `setN(prev => prev+1)` plus a `useRef` to "
                "read the latest value without re-subscribing."
            ),
        ),
    ],
    "react_keys": [
        _q(
            concept="react-keys",
            format="why",
            prompt="Why is `key={index}` an anti-pattern when the list can reorder?",
            opts=[
                ("React requires string keys", False),
                ("Keys identify instances; index keys cause state to follow position, not data", True),
                ("Performance -- index lookups are O(n)", False),
                ("It's fine; only matters in React 16", False),
            ],
            explanation=(
                "If you delete the first item, every subsequent item gets a "
                "new key, so React unmounts and remounts them all. Form "
                "state, focus, animations get reset. Use a stable id from "
                "your data."
            ),
        ),
    ],
    "ts_unknown_vs_any": [
        _q(
            concept="typescript",
            format="idiom",
            prompt="JSON.parse returns `any`. Best replacement type?",
            opts=[
                ("Cast to `any`; it's just JSON", False),
                ("Type as `unknown` and narrow with a type guard", True),
                ("`object` -- safer than any", False),
                ("`Record<string, string>` -- close enough", False),
            ],
            explanation=(
                "`any` disables type-checking everywhere it touches. "
                "`unknown` forces you to narrow before use, keeping safety. "
                "Pair with a runtime validator (zod, valibot) for end-to-end "
                "guarantees."
            ),
        ),
    ],
    "eq_eq_eq": [
        _q(
            concept="javascript",
            format="output",
            prompt="What does `[] == false` evaluate to in JS?",
            opts=[
                ("false (different types)", False),
                ("true (both coerce to '' / 0)", True),
                ("TypeError", False),
                ("undefined", False),
            ],
            explanation=(
                "`==` triggers ToPrimitive then ToNumber: `[]` -> `''` -> 0, "
                "`false` -> 0. Equal! This is why ESLint's `eqeqeq` rule "
                "exists. Always use `===` unless you specifically want "
                "null-undefined coalescing (`x == null`)."
            ),
        ),
    ],
    "complexity_in_list": [
        _q(
            concept="complexity",
            format="complexity",
            prompt="`x in seen` where `seen` is a list of N items. Big-O?",
            opts=[
                ("O(1) -- Python optimizes membership", False),
                ("O(log N) -- bisect is implicit", False),
                ("O(N) -- linear scan", True),
                ("O(N log N)", False),
            ],
            explanation=(
                "`in` on a list is linear. Convert to a set for O(1) average. "
                "This is the most common 'works in dev, dies in prod' "
                "performance bug -- a tight loop with `if x in big_list`."
            ),
        ),
    ],
    "cloze_counter": [
        _q(
            concept="collections",
            format="cloze",
            prompt="Fill the blank to count word occurrences in one line:",
            code=(
                "from collections import _____\n"
                "counts = _____(words)"
            ),
            opts=[
                ("defaultdict / defaultdict(int)", False),
                ("Counter / Counter", True),
                ("OrderedDict / OrderedDict", False),
                ("ChainMap / ChainMap", False),
            ],
            explanation=(
                "`Counter(iterable)` does it in one call and gives you "
                "`.most_common(k)` for free. defaultdict(int) works but is "
                "more code; OrderedDict and ChainMap solve different problems."
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
     re.compile(r"\bwith\s+\w+\s+as\b|\b__enter__\b|\b__exit__\b", re.I)),    ("mutable_default", "mutable default args",
     re.compile(r"def\s+\w+\([^)]*=\s*\[\]|=\s*\{\}|=\s*set\(\)", re.I)),
    ("late_binding_closure", "closure late binding",
     re.compile(r"lambda\s+[^:]*:\s*\w+|\bfor\b.{0,40}\blambda\b", re.I)),
    ("is_vs_eq", "identity vs equality",
     re.compile(r"\bis\s+(None|True|False|not\s+None)\b|\bid\(", re.I)),
    ("copy_vs_deepcopy", "shallow vs deep copy",
     re.compile(r"\bcopy\.(copy|deepcopy)\b|\bimport\s+copy\b", re.I)),
    ("slots", "__slots__",
     re.compile(r"__slots__\s*=", re.I)),
    ("dataclass_frozen", "dataclasses",
     re.compile(r"@dataclass(\s*\(|\b)|from\s+dataclasses\s+import", re.I)),
    ("walrus", "walrus operator",
     re.compile(r":=")),
    ("f_string_debug", "f-string debug",
     re.compile(r"f['\"][^'\"]*\{\w+=\}", re.I)),
    ("dict_order", "dict ordering",
     re.compile(r"\bOrderedDict\b|insertion[-\s]?order", re.I)),
    ("pathlib_path", "pathlib",
     re.compile(r"\bfrom\s+pathlib\b|\bPath\(|os\.path\.(join|exists|dirname)", re.I)),
    ("datetime_tz", "timezone-aware datetime",
     re.compile(r"datetime\.(utcnow|now)\b|\btzinfo\b|\bzoneinfo\b|\btimezone\.utc\b", re.I)),
    ("subprocess_shell", "subprocess shell injection",
     re.compile(r"subprocess\.(run|call|Popen|check_output)|shell\s*=\s*True", re.I)),
    ("logging_lazy", "logging vs print",
     re.compile(r"\blogger?\.(debug|info|warning|error)\(\s*f['\"]", re.I)),
    ("typeddict", "TypedDict",
     re.compile(r"\bTypedDict\b|\bNotRequired\b|\bRequired\[", re.I)),
    ("protocol_vs_abc", "Protocol typing",
     re.compile(r"\bProtocol\)|\bruntime_checkable\b|\bfrom\s+typing\s+import.*Protocol", re.I)),
    ("gil_decision", "GIL / threading vs multiprocessing",
     re.compile(r"\bGIL\b|threading\.(Thread|Lock)|multiprocessing\.|ProcessPoolExecutor", re.I)),
    ("asyncio_taskgroup", "asyncio TaskGroup",
     re.compile(r"\bTaskGroup\b|asyncio\.gather|asyncio\.wait\b", re.I)),
    ("race_condition", "race conditions",
     re.compile(r"\brace\s+condition\b|\bthread[-\s]?safe\b|\bLock\(\)", re.I)),
    ("pytest_parametrize", "pytest parametrize",
     re.compile(r"@pytest\.mark\.parametrize|@parametrize\b", re.I)),
    ("mock_patch_target", "mock patching",
     re.compile(r"@patch\(|mock\.patch\(|MagicMock\(|unittest\.mock", re.I)),
    ("numpy_view_copy", "numpy view vs copy",
     re.compile(r"\bnp\.(asarray|ascontiguousarray|may_share_memory)\b|\.copy\(\).{0,20}numpy", re.I)),
    ("numpy_broadcasting", "numpy broadcasting",
     re.compile(r"\bbroadcast(ing)?\b|np\.newaxis|reshape\([^)]*1\b", re.I)),
    ("pandas_settingwithcopy", "pandas SettingWithCopy",
     re.compile(r"SettingWithCopy|\.loc\[|\.iloc\[|chained\s+assignment", re.I)),
    ("torch_detach", "torch detach/cpu",
     re.compile(r"\.detach\(\)|\.cpu\(\)|\.requires_grad|torch\.no_grad", re.I)),
    ("matplotlib_close", "matplotlib figure leak",
     re.compile(r"plt\.(subplots|figure|savefig|close)|matplotlib\.pyplot", re.I)),
    ("constant_time_compare", "timing-safe compare",
     re.compile(r"hmac\.compare_digest|secrets\.compare_digest|constant[-\s]?time", re.I)),
    ("cors_preflight", "CORS preflight",
     re.compile(r"\bCORS\b|Access-Control-|preflight|OPTIONS\s+request", re.I)),
    ("retry_jitter", "retry with jitter",
     re.compile(r"\bretry\b|exponential\s+backoff|tenacity|backoff\.expo", re.I)),
    ("sql_null_semantics", "SQL NULL semantics",
     re.compile(r"\bNOT\s+IN\s*\(|IS\s+NULL\b|COALESCE\(", re.I)),
    ("window_function", "SQL window functions",
     re.compile(r"\bOVER\s*\(|ROW_NUMBER\(\)|PARTITION\s+BY|RANK\(\)", re.I)),
    ("rebase_vs_merge", "git rebase",
     re.compile(r"git\s+rebase|--force-with-lease|interactive\s+rebase", re.I)),
    ("set_pipefail", "bash pipefail",
     re.compile(r"set\s+-[eo]+\s+pipefail|pipefail|set\s+-euo", re.I)),
    ("find_xargs", "find/xargs quoting",
     re.compile(r"\bfind\s+\.[^|]*\|\s*xargs\b|-print0|xargs\s+-0", re.I)),
    ("useeffect_deps", "React useEffect deps",
     re.compile(r"useEffect\s*\(|stale\s+closure|dependency\s+array", re.I)),
    ("react_keys", "React list keys",
     re.compile(r"key=\{[^}]*index", re.I)),
    ("ts_unknown_vs_any", "TypeScript unknown",
     re.compile(r":\s*(unknown|any)\b|as\s+unknown\s+as\b", re.I)),
    ("eq_eq_eq", "JS strict equality",
     re.compile(r"==[^=]|!=[^=]|eqeqeq", re.I)),
    ("complexity_in_list", "membership complexity",
     re.compile(r"\bin\s+\w+_?list\b|\.index\(", re.I)),
    ("cloze_counter", "Counter",
     re.compile(r"\bCounter\(|collections\.Counter", re.I)),

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
