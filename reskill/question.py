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
            format="bug",
            prompt="A handler randomly drops one of the two DB writes. Why?",
            code=(
                "async def save_both(user, order):\n"
                "    asyncio.create_task(db.save(user))\n"
                "    asyncio.create_task(db.save(order))\n"
                "    return 'ok'"
            ),
            opts=[
                ("create_task holds only a weak ref, so the task can be GC'd before it completes", True),
                ("db.save must be awaited directly; create_task requires a sync callable argument", False),
                ("The two tasks race on the same connection and one of them gets cancelled early", False),
                ("create_task needs an explicit event loop argument when called outside asyncio.run", False),
            ],
            explanation=(
                "asyncio holds only a WEAK reference to tasks created via "
                "create_task. If no strong reference is kept, the task can be "
                "garbage-collected mid-flight -- you see 'Task was destroyed "
                "but it is pending!'. The function also returns before the "
                "tasks run because create_task is non-blocking. Either hold "
                "refs in a set (and discard on done_callback), or use "
                "TaskGroup for structured lifetimes. Python 3.11+ docs "
                "explicitly warn about this."
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
                "Your POST /users is idempotent-keyed and must return the SAME "
                "resource body on retry. What's the status?"
            ),
            opts=[
                ("201 Created with Idempotency-Key and the original response body echoed back", True),
                ("200 OK because the resource already exists and the second call was a no-op", False),
                ("409 Conflict to tell the client the resource is already there and stop retrying", False),
                ("204 No Content because the client retried and doesn't need the body echoed back", False),
            ],
            explanation=(
                "This is why Stripe/GitHub/AWS all adopt `Idempotency-Key`. "
                "The server stores (key -> prior response) and on a repeat "
                "POST with the same key returns the exact same 201 Created "
                "body. 200 OK hides that this was a creation attempt; 409 is "
                "wrong because the first call DID succeed and the client has "
                "no way to know that; 204 throws away the body the client "
                "specifically needs to re-read. RFC 9110 and the IETF draft "
                "on HTTP idempotency cover the pattern."
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
            prompt="A teammate refactors a loop into this comprehension. What prints?",
            code=(
                "rows = [{'id': 1}, {'id': 2}, {'id': 3}]\n"
                "seen = set()\n"
                "unique = [r for r in rows if r['id'] not in seen and not seen.add(r['id'])]\n"
                "print([r['id'] for r in unique])"
            ),
            opts=[
                ("[1, 2, 3] -- works, but relies on set.add returning None", True),
                ("[] -- set.add returns None which is falsy, filtering everything out", False),
                ("SyntaxError: cannot call mutating method inside a comprehension", False),
                ("[1, 1, 2, 2, 3, 3] -- each id appears twice from the short-circuit", False),
            ],
            explanation=(
                "`set.add` returns None, and `not None` is True, so the filter "
                "passes every first-seen id. Clever, but this is exactly the kind "
                "of code that gets flagged in review: side effects inside a "
                "comprehension make the intent opaque. Prefer `dict.fromkeys(ids)` "
                "or a plain for-loop when you need de-duplication with order."
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
            format="bug",
            prompt=(
                "Every log line in prod has the SAME timestamp -- the moment "
                "the module was imported. What's the bug?"
            ),
            code=(
                "def log(msg, ts=datetime.now()):\n"
                "    print(f'[{ts}] {msg}')"
            ),
            opts=[
                ("ts is bound once at def-time, so every call reuses that single value", True),
                ("datetime.now() is lazy; it needs .timestamp() called to actually evaluate", False),
                ("You must write datetime.now().timestamp() to get a fresh value each call", False),
                ("It works unless you pass timezone=; naive datetime shares a module cache", False),
            ],
            explanation=(
                "The mutable-default rule is really the 'default evaluated at "
                "def-time' rule. Any call expression in a default binds once: "
                "`datetime.now()`, `uuid.uuid4()`, `socket.gethostname()` all "
                "freeze at import. Idiom: `ts: datetime | None = None` and "
                "`ts = ts or datetime.now()` inside the body."
            ),
        ),
    ],
    "late_binding_closure": [
        _q(
            concept="closures",
            format="bug",
            prompt=(
                "Click handlers in a dashboard all open the LAST user's profile. "
                "The registration loop looks clean. Which fix is correct AND readable?"
            ),
            code=(
                "handlers = []\n"
                "for user in users:\n"
                "    handlers.append(lambda: open_profile(user))"
            ),
            opts=[
                ("Use `functools.partial(open_profile, user)` -- binds the value at construction time", True),
                ("Wrap in a frozen dataclass so user can't be mutated later", False),
                ("Replace the for-loop with `map(lambda u: lambda: open_profile(u), users)` -- map forces early binding", False),
                ("Add `nonlocal user` inside the lambda to force a fresh binding per iteration", False),
            ],
            explanation=(
                "Every lambda closes over the SAME `user` name, which by the end "
                "of the loop points to the last element. `partial` evaluates its "
                "args immediately, capturing the value. `lambda u=user: ...` also "
                "works via the default-arg trick, but `partial` is more explicit "
                "about intent. `map` doesn't change closure semantics -- the "
                "inner lambda still captures its enclosing `u` by reference. "
                "`nonlocal` is the opposite of what you want."
            ),
        ),
    ],
    "is_vs_eq": [
        _q(
            concept="identity",
            format="bug",
            prompt="Running this raises SyntaxWarning: 'is' with a literal. Why, and what's actually wrong?",
            code=(
                "def describe(x):\n"
                "    if x is 1:\n"
                "        return 'one'\n"
                "    return 'other'"
            ),
            opts=[
                ("is compares identity; CPython caches small ints but it's an impl detail, not a guarantee", True),
                ("== would fail here too because int literals aren't equal to boxed ints in CPython 3.x", False),
                ("This only works on PyPy; CPython never interned 1 and the comparison is always False", False),
                ("It's a SyntaxError, not a Warning -- `is` with literals was removed from the grammar", False),
            ],
            explanation=(
                "CPython caches small ints (typically -5..256) and interns some "
                "strings, so `x is 1` HAPPENS to work -- but that's a CPython "
                "implementation detail, not a language guarantee. Python 3.8+ "
                "emits a SyntaxWarning for `is` with literals, and linters "
                "(ruff F632) flag it. Rule: `is` is for None/True/False/"
                "sentinels only; use `==` for value comparison."
            ),
        ),
    ],
    "copy_vs_deepcopy": [
        _q(
            concept="copy",
            format="bug",
            prompt=(
                "You `deepcopy` a config object before mutating it for a test. The "
                "test still corrupts prod state. What's the most likely cause?"
            ),
            code=(
                "cfg = prod_config          # dataclass with a `db: Connection` field\n"
                "test_cfg = copy.deepcopy(cfg)\n"
                "test_cfg.db.execute('DELETE FROM users')"
            ),
            opts=[
                ("Connection objects define __deepcopy__ returning self (or __reduce__ falls back to sharing) -- deepcopy doesn't clone live resources", True),
                ("deepcopy is shallow when called on dataclasses; you need `dataclasses.replace`", False),
                ("`Connection` inherits from object, which doesn't support deepcopy at all -- should have raised", False),
                ("deepcopy preserves class identity via copyreg, so subclasses aren't cloned", False),
            ],
            explanation=(
                "Objects can opt OUT of deepcopy by defining `__deepcopy__`, "
                "`__copy__`, or `__reduce__`. Live resources (DB connections, "
                "file handles, sockets, thread locks) typically return self "
                "because copying a socket makes no sense. deepcopy's contract is "
                "'respect what each class says'. If you need isolation, inject "
                "a test-config by construction, don't deepcopy your way to it."
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
            format="bug",
            prompt=(
                "You mark a dataclass `frozen=True` to use it as a dict key. It hashes "
                "fine on creation but raises `TypeError: unhashable type` later. Why?"
            ),
            code=(
                "@dataclass(frozen=True)\n"
                "class CacheKey:\n"
                "    user_id: int\n"
                "    scopes: list[str] = field(default_factory=list)"
            ),
            opts=[
                ("`frozen=True` prevents rebinding the attribute, but the `list` field is still mutable and hashing fails when Python hashes the contents", True),
                ("`default_factory` disables the auto-generated __hash__; must add `eq=False`", False),
                ("`frozen=True` requires `slots=True` to actually freeze attributes", False),
                ("Dataclasses drop __hash__ when any field has a default, regardless of frozen", False),
            ],
            explanation=(
                "`frozen=True` gives you `__hash__`, but the hash is computed "
                "from `tuple(fields)`. Python hashes by calling hash() on each "
                "element -- and `hash([])` raises. Fix: make containers "
                "immutable too (`tuple[str, ...]` with a `tuple()` factory, or "
                "`frozenset`). Frozen dataclasses are 'shallowly immutable': "
                "the references are frozen, not the pointees."
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
            format="refactor",
            prompt=(
                "This file-parsing loop calls line.strip().lower() twice per TODO line. "
                "Cleanest refactor that evaluates it once?"
            ),
            code=(
                "for line in f:\n"
                "    if line.strip().lower().startswith('todo'):\n"
                "        process(line.strip().lower())"
            ),
            opts=[
                ("Use :=, e.g. `if (s := line.strip().lower()).startswith('todo'): process(s)`", True),
                ("Wrap line.strip().lower() in functools.lru_cache so repeat calls are free", False),
                ("Rewrite as a generator: `(line.strip().lower() for line in f)` then filter", False),
                ("Use itertools.groupby keyed on line.strip().lower() to dedupe the calls", False),
            ],
            explanation=(
                "The walrus `:=` (PEP 572) assigns AND tests in one "
                "expression, so you compute `line.strip().lower()` once, "
                "bind it to `s`, and reuse `s` in the body. lru_cache keys "
                "on the argument -- every iteration has a new `line`, so "
                "nothing caches. A generator forces you to re-filter and "
                "loses the ability to skip work. groupby solves a different "
                "problem (runs of equal adjacent keys)."
            ),
        ),
    ],
    "f_string_debug": [
        _q(
            concept="f-string",
            format="output",
            prompt="A 3.11 codebase upgrades to 3.12 and this line starts working that used to SyntaxError. Why?",
            code=(
                "names = ['ada', 'lin']\n"
                "print(f'users: {\", \".join(n.upper() for n in names)}')"
            ),
            opts=[
                ("PEP 701 (3.12) lifts the 'no same-quote inside f-string' rule; reused quotes and multi-line expressions now parse", True),
                ("3.12 made generator expressions implicitly list-cast inside f-strings", False),
                ("3.12 added automatic `.upper()` on str fields inside f-strings", False),
                ("It always worked -- the SyntaxError was a linter false positive", False),
            ],
            explanation=(
                "Pre-3.12, f-strings were parsed by a hand-rolled mini-tokenizer "
                "that couldn't handle quotes reused inside the expression, "
                "backslashes, or comments. PEP 701 made f-strings full "
                "expressions in the grammar -- so `f\"{', '.join(...)}\"` and "
                "multi-line expressions now work. Mostly invisible, but upgrades "
                "can quietly change which code parses."
            ),
        ),
        _q(
            concept="f-string",
            format="output",
            prompt=(
                "This line raised SyntaxError on Python 3.11 but prints fine on 3.12. "
                "What changed?"
            ),
            code=(
                "d = {'k': 'v'}\n"
                "print(f\"{d['k']}\")"
            ),
            opts=[
                ("3.12 allows the same quote inside f-string expressions; 3.11 raised SyntaxError", True),
                ("3.12 added automatic escaping of nested quotes inside f-string expressions", False),
                ("3.11 could not subscript dicts inside f-strings; 3.12 added dict subscripting", False),
                ("3.12 changed the tokenizer so bytes literals are permitted inside f-strings", False),
            ],
            explanation=(
                "Pre-3.12, f-strings were parsed by a hand-rolled mini-"
                "tokenizer that forbade reusing the outer quote inside the "
                "expression -- so `f\"{d['k']}\"` needed `f'{d[\"k\"]}'` or "
                "escapes. PEP 701 made f-strings full expressions in the "
                "grammar, so the same quote inside is fine. Nested quotes, "
                "multi-line expressions, comments, and backslashes all now "
                "work. Upgrades can quietly change which code parses."
            ),
        ),
    ],
    "dict_order": [
        _q(
            concept="dict",
            format="scenario",
            prompt=(
                "You implement a request-rate-limited LRU cache manually with a dict "
                "since Python 3.7 guarantees insertion order. Which is the best way "
                "to move an existing key to the MRU position on hit?"
            ),
            opts=[
                ("`d[k] = d[k]` -- re-assigning an existing key keeps its original position (no-op)", False),
                ("`d[k] = d.pop(k)` -- removes then re-inserts, putting it at the end", True),
                ("`OrderedDict(d).move_to_end(k)` -- only OrderedDict supports reorder", False),
                ("`sorted(d.items(), key=lambda kv: kv[0] == k)` -- O(n log n) but portable", False),
            ],
            explanation=(
                "Subtle: re-assigning an EXISTING key preserves its original "
                "insertion slot -- that's a documented language guarantee, not a "
                "bug. `pop` + re-insert is the idiom for 'touch'. This is exactly "
                "why `OrderedDict.move_to_end` still exists: it's O(1) and "
                "doesn't rebucket. For hot paths, use it; for cold paths, the "
                "pop-reinsert trick is fine. Knowing this distinction separates "
                "'uses dict order' from 'understands dict order'."
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
            format="bug",
            prompt="A CLI breaks on Windows. `Path.home() / '/etc/config'` returns `/etc/config`. Why?",
            code=(
                "CONFIG_DIR = Path.home() / '/etc/config'\n"
                "print(CONFIG_DIR)  # expected ~/etc/config"
            ),
            opts=[
                ("pathlib joins lose the left side whenever the right starts with `/` -- it's treated as ABSOLUTE and resets the path", True),
                ("`Path.home()` returns bytes on Windows; string concat with `/` fails silently", False),
                ("The `/` operator on Path only works with single components, not paths with separators", False),
                ("Windows uses `\\` so the left side is dropped when joined with `/`-style paths", False),
            ],
            explanation=(
                "`Path('/foo') / '/bar'` returns `Path('/bar')` -- the same "
                "semantics as `os.path.join`. The right operand being absolute "
                "resets the accumulation. Fix: strip the leading slash (`'etc/"
                "config'`) or use `Path.home().joinpath('etc', 'config')`. This "
                "is THE most common pathlib bug and it silently works on your "
                "dev box if HOME happens to be `/` -- a.k.a. CI containers."
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
            format="refactor",
            prompt=(
                "The 2nd case fails and the report just says 'test_solve failed' "
                "with no hint which input. First diagnostic improvement?"
            ),
            code=(
                "def test_solve():\n"
                "    cases = [(1, 1), (2, 3), (3, 6), (4, 10)]\n"
                "    for n, expected in cases:\n"
                "        assert solve(n) == expected"
            ),
            opts=[
                ("@pytest.mark.parametrize so each case is a separate test with its own id and failure", True),
                ("Split into four def test_solve_* functions, one per case, each with its own assert", False),
                ("Replace the loop body with `assert all(solve(n) == e for n, e in cases)` for clarity", False),
                ("Wrap each assert in try/except and print which (n, expected) raised before re-raising", False),
            ],
            explanation=(
                "`parametrize` makes each case a separate reported test with "
                "its own name (`test_solve[2-3]`), its own pass/fail, and "
                "first-class `-k` filtering. Splitting into four def "
                "functions works but is verbose and drifts out of sync. "
                "`assert all(...)` is strictly worse -- it hides which case "
                "failed behind a single False. try/except noise obscures "
                "pytest's built-in assertion rewriting."
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
                ("inplace returns None, so method chaining silently breaks", True),
                ("inplace is faster and avoids an intermediate allocation", False),
                ("inplace is deprecated and likely removed in pandas 3.0", False),
                ("inplace doesn't work on views, only on fully owned frames", False),
            ],
            explanation=(
                "The headline issue: `inplace=True` mutates and returns None, "
                "so `df.fillna(0, inplace=True).drop_duplicates()` blows up "
                "with 'NoneType has no attribute ...'. It ALSO doesn't save "
                "memory (pandas often allocates a new block internally) and "
                "the pandas team is actively discussing removing most inplace "
                "paths in 3.0 because they complicate Copy-on-Write (CoW) "
                "semantics. The chaining foot-gun is the one that bites "
                "day-to-day. Prefer `df = df.fillna(0)` or a pipeline."
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
            format="bug",
            prompt="Auditor says this token check is still vulnerable to a timing attack. You're already using `compare_digest`. What's the leak?",
            code=(
                "def verify(tok: str) -> bool:\n"
                "    if tok not in TOKEN_INDEX:\n"
                "        return False\n"
                "    expected = TOKEN_INDEX[tok]\n"
                "    return hmac.compare_digest(sign(tok), expected)"
            ),
            opts=[
                ("dict membership leaks hit-vs-miss via timing, letting attackers enumerate valid tokens", True),
                ("sign(tok) must be called BEFORE the membership check to keep the path constant-time", False),
                ("HMAC key is hardcoded; rotating it per-request fixes the leak in compare_digest", False),
                ("Dict membership IS constant-time in Python; the real leak is inside compare_digest", False),
            ],
            explanation=(
                "Dict lookup is amortized O(1) but NOT constant-wallclock -- "
                "hash collisions, resizing, and branch timing all vary between "
                "hit and miss. The early `return False` on miss exits faster "
                "than the full sign + compare_digest path on hit, leaking "
                "'this token exists' vs 'this token doesn't' via response "
                "time. Fix: always run the full signing + compare_digest "
                "path, returning False at the end regardless of lookup "
                "result. compare_digest IS safe for unequal lengths."
            ),
        ),
        _q(
            concept="security",
            format="bug",
            prompt=(
                "Staging and prod share the same HMAC signing key loaded from "
                "`os.environ['HMAC_SECRET']`. A staging exploit now forges prod "
                "tokens. What's the actual fix?"
            ),
            code=(
                "SECRET = os.environ['HMAC_SECRET']\n"
                "def sign(tok: str) -> bytes:\n"
                "    return hmac.new(SECRET.encode(), tok.encode(), 'sha256').digest()"
            ),
            opts=[
                ("Use a distinct secret per environment so a staging leak can't verify in prod", True),
                ("Hash the secret with sha256 before hmac.new so envs derive different keys", False),
                ("Prepend the env name to the token so the signature is environment-scoped", False),
                ("Rotate the shared secret hourly; staging exposure ages out before exploit", False),
            ],
            explanation=(
                "HMAC's security rests on key secrecy. Reusing a key across "
                "trust boundaries (staging <-> prod, dev <-> prod) means any "
                "leak in the weaker environment forges tokens in the stronger "
                "one. Hashing the key or prepending env names keeps the same "
                "underlying secret, so compromise still transfers. Rotation "
                "helps but doesn't solve the structural issue. Provision "
                "per-environment secrets from your secret manager and never "
                "copy prod secrets into staging."
            ),
        ),
    ],
    "cors_preflight": [
        _q(
            concept="cors",
            format="bug",
            prompt=(
                "Your SPA can fetch /api from localhost but gets 'CORS error' in prod. "
                "The server sets `Access-Control-Allow-Origin: *` AND "
                "`Access-Control-Allow-Credentials: true`. Where's the bug?"
            ),
            opts=[
                ("`Allow-Origin: *` is incompatible with `Allow-Credentials: true` -- browsers reject the combo", True),
                ("Prod is HTTPS and preflight requires `Access-Control-Allow-Protocol: https`", False),
                ("Credentials are stripped from OPTIONS requests; must use a custom header to bypass", False),
                ("`Allow-Origin: *` only works for GET -- POST needs an explicit origin", False),
            ],
            explanation=(
                "The CORS spec is explicit: when `Allow-Credentials: true`, the "
                "`Allow-Origin` MUST be a specific origin, not `*`. The reason "
                "is cookie/credential theft -- a wildcard + credentials would "
                "let any site ride user sessions. Fix: echo the request's Origin "
                "header back (from an allowlist). Works locally because browsers "
                "often skip CORS for localhost in dev flags."
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
            format="bug",
            prompt=(
                "A dashboard shows the wrong count. `SELECT COUNT(*) FROM users "
                "WHERE deleted_at != '2025-01-01'` returns a number, but you "
                "verified rows with that exact deleted_at exist. What's wrong?"
            ),
            opts=[
                ("Rows with `deleted_at IS NULL` are silently excluded -- `NULL != '2025-01-01'` is UNKNOWN, not TRUE", True),
                ("Postgres string-compares dates; must cast with `::date`", False),
                ("`COUNT(*)` ignores rows where any column is NULL", False),
                ("SQL requires `<>` instead of `!=` in the WHERE clause", False),
            ],
            explanation=(
                "Three-valued logic: `NULL != x` is UNKNOWN, and WHERE only "
                "keeps rows that evaluate to TRUE. So every 'active' user (with "
                "NULL deleted_at) gets silently dropped from your negative "
                "filter. Fix: `WHERE deleted_at IS DISTINCT FROM '2025-01-01'` "
                "(Postgres/ANSI) or `WHERE deleted_at != '...' OR deleted_at IS "
                "NULL`. This is the #1 cause of 'count is off by a lot' bugs."
            ),
        ),
    ],
    "window_function": [
        _q(
            concept="sql-window",
            format="tradeoff",
            prompt=(
                "Two devs want the latest order per user on a table with ties in "
                "created_at. They write ROW_NUMBER() vs RANK() OVER (PARTITION BY "
                "user_id ORDER BY created_at DESC). Which picks the right one -- and why?"
            ),
            opts=[
                ("Always ROW_NUMBER() -- RANK() returns ties and you'll get duplicate rows per user", True),
                ("Always RANK() -- ROW_NUMBER() is non-deterministic on ties, so results flap between runs", False),
                ("DENSE_RANK() is the only one that breaks ties correctly", False),
                ("They're identical except for performance; use whichever the planner prefers", False),
            ],
            explanation=(
                "If two orders share the exact created_at, `RANK()` returns 1 "
                "for both -- filtering on rank=1 gives you TWO rows for that "
                "user, silently inflating totals. `ROW_NUMBER()` is guaranteed "
                "to assign distinct numbers, at the cost of picking arbitrarily "
                "among ties. Add a tie-breaker to the ORDER BY (e.g. "
                "`created_at DESC, id DESC`) to make it deterministic. Use "
                "RANK/DENSE_RANK only when you WANT tied winners."
            ),
        ),
    ],
    "rebase_vs_merge": [
        _q(
            concept="git",
            format="scenario",
            prompt=(
                "You rebased 10 commits onto main, pushed with `--force-with-lease`, "
                "and the push succeeded. A teammate yells that their local branch "
                "is broken. What went wrong that force-with-lease didn't catch?"
            ),
            opts=[
                ("`--force-with-lease` only checks YOUR local ref, not whether anyone else pulled -- pulls don't update your ref", True),
                ("`--force-with-lease` was silently downgraded to `--force` because the remote was ahead", False),
                ("The teammate had a stale fetch; force-with-lease works only on rebased MERGE commits", False),
                ("Rebasing a feature branch is always safe to push; teammate should `git pull --rebase`", False),
            ],
            explanation=(
                "`--force-with-lease` protects YOU from overwriting commits YOU "
                "haven't seen -- not from disrupting collaborators. If a "
                "teammate already pulled the old tip, your rewrite strands "
                "their work: their branch diverges and `git pull` tries to "
                "merge two histories. The rule is: feature branches shared "
                "with collaborators become 'public' too. Use `--force-if-"
                "includes` (Git 2.30+) for an even stricter safety net, or "
                "better, coordinate before rewriting shared history."
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
            prompt=(
                "You want to grep thousands of files for TODO, NUL-safely AND "
                "stream in batches (not one file per invocation). Which pipeline?"
            ),
            opts=[
                ("find . -name '*.py' -print0 | xargs -0 grep TODO   # NUL-safe, batched", True),
                ("find . -name '*.py' | xargs grep TODO   # simplest pipeline, whitespace safe", False),
                ("find . -name '*.py' -exec grep TODO {} \\;   # per-file exec, no xargs needed", False),
                ("find . -name '*.py' -print | xargs -I{} grep TODO {}   # -I handles spaces", False),
            ],
            explanation=(
                "`-print0` separates paths with NUL (which cannot appear in "
                "a filename) and `xargs -0` consumes NUL-delimited input, so "
                "spaces/newlines in names are safe. xargs also batches "
                "arguments into as few grep invocations as ARG_MAX allows, "
                "so you stream thousands of files efficiently. `-exec ... "
                "\\;` is NUL-safe but spawns one grep per file -- not "
                "batched. `-I{}` forces one invocation per item too, and "
                "plain `xargs` without `-0` still splits on whitespace."
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
            format="bug",
            prompt=(
                "A checkbox list for 5 todos looks right, but when the user deletes "
                "todo #2, the checked state jumps to the wrong row. The code uses "
                "`key={todo.id}`. What's the actual villain?"
            ),
            code=(
                "{todos.map(todo => (\n"
                "  <TodoRow key={todo.id}>\n"
                "    <input type='checkbox' />\n"
                "  </TodoRow>\n"
                "))}"
            ),
            opts=[
                ("The <input> is uncontrolled -- checkbox state lives in the DOM node and gets reused when React reconciles by key", True),
                ("`todo.id` must be a string; numeric ids cause React to fall back to index", False),
                ("The key should be on the <input>, not the <TodoRow> wrapper", False),
                ("Deletion triggers a full re-mount, which always resets inputs", False),
            ],
            explanation=(
                "Stable keys correctly identify each TodoRow instance across "
                "renders, but the native checkbox is UNCONTROLLED -- its "
                "'checked' bit lives in the DOM element. When row #2 is deleted, "
                "React keeps the existing DOM nodes for rows 1,3,4,5 (correct "
                "by key) but the checkbox DOM still has whatever last state it "
                "had. Fix: make inputs controlled (`checked={todo.done} onChange="
                "...`). The deeper lesson: keys solve identity, not state "
                "ownership."
            ),
        ),
    ],
    "ts_unknown_vs_any": [
        _q(
            concept="typescript",
            format="bug",
            prompt=(
                "A PR adds a `User` type and parses JSON with `JSON.parse(s) as User`. "
                "TypeScript is happy. The runtime crashes with "
                "`Cannot read property 'email' of undefined`. Best fix?"
            ),
            opts=[
                ("Replace `as User` with a runtime validator (zod/valibot/ajv); casts skip checking, validators enforce the shape at runtime", True),
                ("Change `as User` to `<User>JSON.parse(s)` -- angle-bracket casts do runtime checks", False),
                ("Narrow `JSON.parse(s)` with `typeof result === 'object'` -- that's enough to confirm User", False),
                ("Wrap the parse in a try/catch -- malformed JSON is the only way this fails", False),
            ],
            explanation=(
                "`as X` is a TYPE assertion, not a runtime check. It's a "
                "developer promise that gets erased at compile time. If the "
                "API returns `{user: {...}}` instead of the User directly, "
                "TypeScript still greenlights it. Zod et al. give you a schema "
                "AND a type that are guaranteed to agree. The `unknown` type "
                "alone is better than `any` because it forces SOME narrowing, "
                "but even narrowed code only checks what you remember to check."
            ),
        ),
    ],
    "eq_eq_eq": [
        _q(
            concept="javascript",
            format="bug",
            prompt=(
                "A `user.role === 'admin'` guard works in tests, fails in prod with "
                "JSON-parsed data. Devtools shows `user.role` is `'admin'`. Why does "
                "strict equality still fail?"
            ),
            code=(
                "// API payload has trailing whitespace or a Unicode lookalike\n"
                "console.log(user.role);            // 'admin'\n"
                "console.log(user.role === 'admin'); // false"
            ),
            opts=[
                ("The string likely has a zero-width space / non-breaking space / Cyrillic 'а' -- devtools shows them identical but codepoints differ", True),
                ("`===` falls back to `==` for single-character strings; upgrade Node", False),
                ("JSON.parse returns String objects, not primitives, so `===` fails on identity", False),
                ("`'admin'` is interned but API strings aren't; use `.valueOf()` first", False),
            ],
            explanation=(
                "`===` is fine; the trap is visual. Hidden codepoints (ZWSP "
                "U+200B, NBSP U+00A0, Cyrillic 'а' U+0430) render identically. "
                "Debug with `[...user.role].map(c => c.codePointAt(0))`. "
                "Production defenses: normalize with `.trim().normalize('NFKC')` "
                "before comparing, or validate enum fields with zod. "
                "JSON.parse ALWAYS returns primitive strings, not String "
                "objects."
            ),
        ),
    ],
    "complexity_in_list": [
        _q(
            concept="complexity",
            format="bug",
            prompt=(
                "A dedup job converts `seen = []` to `seen = set()` and now runs "
                "20x faster -- except for one input class where it's SLOWER than "
                "the list version. What's the input?"
            ),
            code=(
                "# items is a list of dicts / lists / numpy arrays\n"
                "seen = set()\n"
                "for item in items:\n"
                "    if item not in seen:\n"
                "        seen.add(item)\n"
                "        process(item)"
            ),
            opts=[
                ("Items are unhashable (dicts/lists/ndarray) -- raises TypeError; list version 'worked' because `in` on list uses == not hash", True),
                ("Small inputs (<100) -- set's hash overhead beats list's linear scan", False),
                ("Items with expensive __hash__ methods -- list __eq__ is always faster", False),
                ("Items with a lot of duplicates -- sets have O(n) worst-case for collisions", False),
            ],
            explanation=(
                "Sets require hashable keys. `dict`, `list`, `ndarray`, and any "
                "mutable-by-default class (dataclass without frozen=True) raise "
                "`TypeError: unhashable type`. The list version silently used "
                "`==` and worked, at O(n^2). Fix: build a set of a hashable "
                "projection (`tuple(item)`, `frozenset(d.items())`, `item.id`). "
                "Small-input optimization is real (~20 elements) but rare in "
                "practice. This is the classic 'replace list-in with set-in' "
                "pitfall."
            ),
        ),
    ],
    "cloze_counter": [
        _q(
            concept="collections",
            format="gotcha",
            prompt=(
                "A teammate uses `Counter.most_common()` for a leaderboard. QA "
                "reports the top-10 sometimes includes users with score 0. The "
                "Counter is built with `Counter(scores_by_user)`. What happened?"
            ),
            code=(
                "scores = Counter(scores_by_user)    # dict: user -> int\n"
                "scores['dropped_user'] -= 5          # subtract a penalty\n"
                "top = scores.most_common(10)"
            ),
            opts=[
                ("Counter.most_common() includes ZERO and NEGATIVE counts; only `+counter` (or filtering) drops non-positive entries", True),
                ("Counter is insertion-ordered; most_common falls back to insertion order on ties and includes stale zeros", False),
                ("`Counter -= penalty` doesn't exist; the line silently no-ops, leaving raw scores", False),
                ("most_common(10) returns 10 items even if fewer have positive counts, padding with zeros", False),
            ],
            explanation=(
                "Counter willingly stores zero and negative counts -- that's "
                "what lets `-` and `subtract` behave like a multiset difference. "
                "`most_common` sorts by value, so negatives appear near the "
                "bottom and zeros can tie in. Canonical cleanup: `+scores` "
                "(unary plus drops zero/negative entries). Full idiom: "
                "`(+scores).most_common(10)`. Not in any tutorial, but it's "
                "the reason Counter is a multiset, not a frequency dict."
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
