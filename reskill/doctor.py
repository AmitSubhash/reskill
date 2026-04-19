"""`reskill doctor` -- diagnose why reskill isn't behaving.

Checks every touchpoint the live-pane and session flows depend on,
reports PASS/WARN/FAIL with a short explanation, and suggests a fix
for each failure. Intended to catch silent issues like "hooks are
registered but Claude Code isn't reading them" — exactly the trap
that bit us in the schema-nesting bug.

Ordering matters: checks flow roughly along the data path
  prereqs -> hooks -> signals -> pacing -> bank -> scheduler -> cache

Each check:
  - returns one of "pass" / "warn" / "fail"
  - prints an icon + one-line summary
  - for warn/fail, prints a remediation hint below
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import state as state_mod
from .palette import ASH, BOLD, DIM, GOLD, ROSE, SAGE, paint


@dataclass
class CheckResult:
    name: str
    status: str  # 'pass' | 'warn' | 'fail'
    detail: str
    fix: str | None = None


STATE_DIR = Path.home() / ".reskill" / "state"
THINKING_FILE = STATE_DIR / "thinking"
HOOK_LOG = Path("/tmp/reskill-hook.log")
SETTINGS = Path.home() / ".claude" / "settings.json"
TRANSCRIPTS = Path.home() / ".claude" / "projects"


def _is_first_run() -> bool:
    """True when the user has never answered a quiz.

    Several checks report "missing file" conditions that are perfectly
    normal on a fresh install -- hook log, transcript dir, concept
    cache. Surfacing them as warnings makes `reskill doctor` look
    broken 30 seconds after `pip install`, which is exactly when new
    users are deciding whether to keep the tool.
    """
    try:
        s = state_mod.load()
    except Exception:
        return True
    return s.xp_total == 0 and s.streak == 0 and not s.seen_questions


def _check_claude_installed() -> CheckResult:
    if shutil.which("claude"):
        return CheckResult(
            "claude binary",
            "pass",
            f"found at {shutil.which('claude')}",
        )
    return CheckResult(
        "claude binary",
        "fail",
        "not on PATH",
        "install Claude Code -- https://docs.claude.com/en/docs/claude-code/overview",
    )


def _check_reskill_installed() -> CheckResult:
    path = shutil.which("reskill")
    if path:
        return CheckResult("reskill binary", "pass", f"found at {path}")
    return CheckResult(
        "reskill binary",
        "fail",
        "not on PATH",
        "pip install git+https://github.com/AmitSubhash/reskill.git",
    )


def _check_settings_file() -> CheckResult:
    if not SETTINGS.exists():
        return CheckResult(
            "~/.claude/settings.json",
            "fail",
            "file does not exist",
            "run `reskill install`",
        )
    try:
        json.loads(SETTINGS.read_text())
        return CheckResult("~/.claude/settings.json", "pass", "valid JSON")
    except json.JSONDecodeError as exc:
        return CheckResult(
            "~/.claude/settings.json",
            "fail",
            f"invalid JSON: {exc}",
            "fix the JSON manually; last backup at settings.json.reskill-bak",
        )


def _check_hook_schema() -> CheckResult:
    """Verify reskill hooks are under settings.hooks.* (nested), not at
    the settings root. The nesting-was-flat bug silently dropped every
    hook fire for a whole dev session; this is the most important check.
    """
    if not SETTINGS.exists():
        return CheckResult("hook schema", "fail", "no settings.json")
    try:
        data = json.loads(SETTINGS.read_text())
    except json.JSONDecodeError:
        return CheckResult("hook schema", "fail", "settings.json isn't JSON")

    nested_found = 0
    root_found = 0
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        nested = data.get("hooks", {}).get(event, []) if isinstance(data.get("hooks"), dict) else []
        for entry in nested if isinstance(nested, list) else []:
            for h in entry.get("hooks", []):
                if "reskill" in h.get("command", "") or "thinking" in h.get("command", ""):
                    nested_found += 1
        legacy = data.get(event, [])
        for entry in legacy if isinstance(legacy, list) else []:
            for h in entry.get("hooks", []):
                if "reskill" in h.get("command", "") or "thinking" in h.get("command", ""):
                    root_found += 1

    if nested_found and not root_found:
        return CheckResult(
            "hook schema",
            "pass",
            f"{nested_found} reskill hooks under settings.hooks.*",
        )
    if root_found and not nested_found:
        return CheckResult(
            "hook schema",
            "fail",
            f"{root_found} hooks at settings root (Claude Code ignores these)",
            "run `reskill uninstall && reskill install`",
        )
    if nested_found and root_found:
        return CheckResult(
            "hook schema",
            "warn",
            f"{nested_found} nested + {root_found} legacy -- mixed state",
            "run `reskill uninstall && reskill install` to normalize",
        )
    return CheckResult(
        "hook schema",
        "fail",
        "no reskill hooks found in settings",
        "run `reskill install`",
    )


def _check_hook_actually_fired() -> CheckResult:
    """Did the hooks EVER fire? /tmp/reskill-hook.log existing is the
    signal -- our Stop hook redirects stderr there, so it gets touched
    on every Stop event even if the underlying command errors.
    """
    if not HOOK_LOG.exists():
        if _is_first_run():
            return CheckResult(
                "hook fire history",
                "pass",
                "not yet -- run `reskill claude` to start a session",
            )
        return CheckResult(
            "hook fire history",
            "warn",
            "/tmp/reskill-hook.log does not exist",
            "end a Claude session; the Stop hook should create this file",
        )
    try:
        age = time.time() - HOOK_LOG.stat().st_mtime
    except OSError:
        age = 999999
    if age < 3600:
        return CheckResult(
            "hook fire history",
            "pass",
            f"last hook fire {int(age)}s ago",
        )
    return CheckResult(
        "hook fire history",
        "warn",
        f"last fire was {int(age)}s ago -- no recent Claude sessions?",
    )


def _check_thinking_signal() -> CheckResult:
    """Current state of the thinking flag. Transient, may legitimately
    be absent. We just report; don't flag unless something looks stuck.
    """
    if not THINKING_FILE.exists():
        return CheckResult(
            "thinking signal",
            "pass",
            "flag clear (Claude is idle or no session active)",
        )
    age = time.time() - THINKING_FILE.stat().st_mtime
    if age > 600:
        return CheckResult(
            "thinking signal",
            "warn",
            f"flag set but stale ({int(age)}s old)",
            "remove it: rm ~/.reskill/state/thinking",
        )
    return CheckResult(
        "thinking signal",
        "pass",
        f"flag set {int(age)}s ago (Claude is active right now)",
    )


def _check_pacing_state() -> CheckResult:
    """Are we hitting a rate-limit cap invisibly?"""
    from . import pacing

    ps = pacing.load()
    now = time.time()
    hourly = sum(1 for t in ps.quiz_timestamps if t > now - 3600)
    daily = sum(1 for t in ps.quiz_timestamps if t > now - 86400)
    from .pacing import MAX_QUIZZES_PER_DAY, MAX_QUIZZES_PER_HOUR

    if hourly >= MAX_QUIZZES_PER_HOUR:
        return CheckResult(
            "pacing",
            "warn",
            f"hourly cap hit ({hourly}/{MAX_QUIZZES_PER_HOUR})",
            "wait, OR clear ~/.reskill/state/pacing.json to reset",
        )
    if daily >= MAX_QUIZZES_PER_DAY:
        return CheckResult(
            "pacing",
            "warn",
            f"daily cap hit ({daily}/{MAX_QUIZZES_PER_DAY})",
            "raise with RESKILL_MAX_PER_DAY=N env var",
        )
    return CheckResult(
        "pacing",
        "pass",
        f"{hourly}/h {daily}/d -- plenty of headroom",
    )


def _check_template_bank() -> CheckResult:
    from .question import TEMPLATE_BANK

    concepts = len(TEMPLATE_BANK)
    total = sum(len(v) for v in TEMPLATE_BANK.values())
    if total < 10:
        return CheckResult(
            "template bank",
            "fail",
            f"only {total} questions, bank may be broken",
        )
    return CheckResult(
        "template bank",
        "pass",
        f"{total} questions across {concepts} concepts",
    )


def _check_state_sanity() -> CheckResult:
    s = state_mod.load()
    return CheckResult(
        "state.json",
        "pass",
        f"streak={s.streak} xp={s.xp_total} today={s.correct_today}/{s.daily_goal} "
        f"wrong_list={len(s.recent_wrongs)}",
    )


def _check_transcripts() -> CheckResult:
    if not TRANSCRIPTS.exists():
        if _is_first_run():
            return CheckResult(
                "Claude transcripts",
                "pass",
                "not yet -- ~/.claude/projects will populate on first session",
            )
        return CheckResult(
            "Claude transcripts",
            "warn",
            "~/.claude/projects not found",
            "run `claude` at least once so transcripts exist",
        )
    jsonls = list(TRANSCRIPTS.rglob("*.jsonl"))
    if not jsonls:
        if _is_first_run():
            return CheckResult(
                "Claude transcripts",
                "pass",
                "not yet -- start a Claude session to populate",
            )
        return CheckResult(
            "Claude transcripts",
            "warn",
            "no .jsonl files yet",
        )
    newest = max(jsonls, key=lambda p: p.stat().st_mtime)
    age = time.time() - newest.stat().st_mtime
    return CheckResult(
        "Claude transcripts",
        "pass",
        f"{len(jsonls)} files, newest {int(age)}s ago",
    )


def _check_tmux() -> CheckResult:
    if shutil.which("tmux"):
        try:
            out = subprocess.run(
                ["tmux", "-V"], capture_output=True, text=True, timeout=2,
            )
            return CheckResult("tmux", "pass", out.stdout.strip())
        except subprocess.SubprocessError:
            return CheckResult("tmux", "warn", "found but doesn't respond")
    return CheckResult(
        "tmux",
        "warn",
        "not installed",
        "`brew install tmux` for the split-pane experience; "
        "without it reskill claude opens a 2nd Terminal window (macOS) "
        "or prints an install hint",
    )


def _check_concept_cache() -> CheckResult:
    cache_root = Path.home() / ".reskill" / "project_cache"
    if not cache_root.exists():
        if _is_first_run():
            return CheckResult(
                "concept cache",
                "pass",
                "not yet -- per-project cache builds on first Claude session",
            )
        return CheckResult(
            "concept cache",
            "warn",
            "no per-project cache yet",
            "end a Claude session -- the Stop hook populates this",
        )
    caches = list(cache_root.glob("*/concepts.json"))
    if not caches:
        if _is_first_run():
            return CheckResult(
                "concept cache",
                "pass",
                "not yet -- cache dir exists but not populated",
            )
        return CheckResult(
            "concept cache",
            "warn",
            "cache dir exists but empty",
        )
    total_sessions = 0
    for c in caches:
        try:
            total_sessions += json.loads(c.read_text()).get("sessions", 0)
        except (OSError, json.JSONDecodeError):
            pass
    return CheckResult(
        "concept cache",
        "pass",
        f"{len(caches)} project(s), {total_sessions} session(s) ingested",
    )


CHECKS = [
    _check_claude_installed,
    _check_reskill_installed,
    _check_settings_file,
    _check_hook_schema,
    _check_hook_actually_fired,
    _check_thinking_signal,
    _check_pacing_state,
    _check_template_bank,
    _check_state_sanity,
    _check_transcripts,
    _check_tmux,
    _check_concept_cache,
]


def _autofix(results: list[CheckResult]) -> list[str]:
    """Try to silently resolve any warn/fail we know how to fix.

    Returns a list of human-readable actions taken.
    """
    actions: list[str] = []
    import json
    import os as _os

    for r in results:
        if r.status == "pass":
            continue
        name = r.name
        if name == "pacing":
            # Reset the pacing state file to clear rate-limit accumulation.
            pac = Path.home() / ".reskill" / "state" / "pacing.json"
            pac.parent.mkdir(parents=True, exist_ok=True)
            pac.write_text(json.dumps({
                "thinking_started_at": 0,
                "last_quiz_finished_at": 0,
                "last_concept_at": {},
                "quiz_timestamps": [],
            }))
            actions.append("cleared ~/.reskill/state/pacing.json (hourly/daily cap reset)")
        elif name == "thinking signal" and r.status == "warn":
            # Stale thinking flag -- remove it.
            try:
                THINKING_FILE.unlink()
                actions.append("removed stale ~/.reskill/state/thinking flag")
            except (OSError, FileNotFoundError):
                pass
        elif name == "hook schema" and "legacy" in r.detail:
            # Nesting fix: run reinstall.
            from . import hookinstall as hi
            hi.uninstall()
            hi.install()
            actions.append("ran `reskill uninstall && reskill install` to fix hook nesting")
    _ = _os  # keep the import side-effect-free silencer
    return actions


def run(fix: bool = False) -> int:
    print()
    print(paint("  reSkill doctor", SAGE, BOLD))
    print(paint("  checking every integration point...", ASH, DIM))
    print()

    results = [check() for check in CHECKS]

    pass_n = sum(1 for r in results if r.status == "pass")
    warn_n = sum(1 for r in results if r.status == "warn")
    fail_n = sum(1 for r in results if r.status == "fail")

    for r in results:
        if r.status == "pass":
            glyph = paint("\u2713", SAGE, BOLD)
        elif r.status == "warn":
            glyph = paint("!", GOLD, BOLD)
        else:
            glyph = paint("\u2717", ROSE, BOLD)
        print(f"  {glyph}  {paint(r.name.ljust(24), BOLD)} {r.detail}")
        if r.fix and r.status != "pass":
            print(f"       {paint('-> ' + r.fix, ASH, DIM)}")

    print()
    summary = (
        paint(f"{pass_n} pass", SAGE, BOLD)
        + paint(f"   {warn_n} warn", GOLD, BOLD if warn_n else DIM)
        + paint(f"   {fail_n} fail", ROSE, BOLD if fail_n else DIM)
    )
    print(f"  {summary}")
    print()

    if fix and (warn_n or fail_n):
        print(paint("  running --fix...", ASH, DIM))
        actions = _autofix(results)
        if not actions:
            print(paint("  nothing auto-fixable", ASH, DIM))
        else:
            for a in actions:
                print(paint(f"  * {a}", SAGE))
            print()
            print(paint("  re-checking...", ASH, DIM))
            return run(fix=False)
        print()

    return 0 if fail_n == 0 else 1
