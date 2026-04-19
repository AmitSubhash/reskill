# reSkill launch kit

Content for posting when the video is ready. All copy is tuned for
each surface's audience and length limits. Swap `<LINK>` with the
repo URL at posting time.

---

## Twitter / X — launch thread

**Tweet 1 (hook):**

> Claude Code thinks for 10-30 seconds between tool calls.
>
> I was just sitting there.
>
> So I built reSkill: a quiz pane that appears during Claude's
> thinking time. Answer a question, Claude finishes the task, you've
> learned something.
>
> [VIDEO]
>
> <LINK>

**Tweet 2:**

> Questions aren't random.
>
> It reads your live Claude transcript + your recent git commits,
> matches concepts, and picks what you're actually working on.
>
> Just wrote async code? It'll quiz you on TaskGroup vs gather.
> Just touched lru_cache? You'll see a caching gotcha.

**Tweet 3:**

> The scheduler is evidence-based:
>
> · SM-2 spaced repetition
> · Interleaving only across confusable concepts (Rohrer & Taylor 2007)
> · 85% rule target error rate (Wilson 2019)
> · Format diversity (beats MC fluency illusion)
>
> Paper citations in the source.

**Tweet 4:**

> Hypercorrection: if you miss a question in under 5 seconds, the
> reveal tags it "◉ sticky one" — research shows high-confidence
> misses are where corrections stick hardest.
>
> Small touches, compounding effect.

**Tweet 5 (CTA):**

> tmux optional. Works in any macOS terminal via a second window.
> Mono theme for readability on any background.
>
> One install command, reversible.
>
> `pip install reskill && reskill install`
>
> <LINK>
>
> MIT licensed. Would love your feedback.

---

## Hacker News — Show HN

**Title:**

`Show HN: reSkill – quizzes during Claude Code's thinking time`

**Body:**

> While Claude Code runs tool calls and inference, there's usually a
> 10-30 second window where I'm just staring at the terminal. reSkill
> turns that into micro-practice.
>
> How it works:
>
> - Hooks into Claude Code's UserPromptSubmit / PreToolUse /
>   PostToolUse / Stop events
> - When Claude is thinking, a side pane (tmux split OR a second
>   Terminal window on macOS) shows one question
> - You answer 1-4, see the reveal, continue
>
> The scheduler isn't a vibe. It's built on:
>
> - SM-2 spaced repetition
> - Interleaving within confusable concept clusters (Rohrer & Taylor
>   2007 — blocking random topics doesn't help; interleaving
>   confusable ones does)
> - Target 15% error rate (Wilson et al. 2019 Nature Communications
>   on the "85% rule" for optimal learning)
> - Format diversity 50/30/20 to avoid MC fluency illusion
>   (Roediger & Karpicke 2006)
>
> Current bank: 54 questions across 50 Python + shell + SQL + React
> concepts. LLM-generated questions from your actual commits is the
> next milestone.
>
> Install is reversible; it composes with your existing statusLine
> command instead of replacing it. `reskill doctor` diagnoses every
> integration point in one command.
>
> Built it because I got tired of toggling to Anki. Having the
> questions arrive where I already am feels qualitatively different
> from having to remember to open a separate app.
>
> Feedback welcome. Especially curious what breaks on Linux/WSL
> (tested on macOS only so far).
>
> <LINK>

---

## Product Hunt

**Tagline:** Turn Claude Code's thinking time into dev practice.

**Description:**

reSkill shows you micro-quizzes while Claude Code is mid-thought.
Questions match what you're actually working on — read from your live
transcript + recent commits.

Scheduler is built on published learning science: SM-2 spaced
repetition, 85%-rule difficulty targeting (Wilson 2019), interleaving
within confusable clusters (Rohrer & Taylor 2007), format diversity
to beat the fluency illusion.

✓ Installs in one command, fully reversible
✓ tmux optional — works in any macOS terminal
✓ Composes with your existing statusLine, doesn't replace it
✓ 54 hand-written Python / shell / SQL / React questions to start
✓ Everforest + mono themes
✓ `reskill doctor` self-diagnoses any integration issue

MIT licensed.

**First comment (founder):**

I built this because I kept toggling to Anki between Claude runs.
Getting the questions where I already am is a completely different
experience.

The hook integration gets surprisingly tricky — Claude Code reads
hooks from settings.hooks.\* (nested), which the docs are subtle
about. Wrote `reskill doctor` specifically so the next person doesn't
debug that silently.

Happy to answer questions about the scheduler design — it's my
favorite part.

---

## LinkedIn

**Hook:**

> Spent the weekend converting the waiting-for-AI moments into
> learning moments.

**Body:**

Every Claude Code session has these 10-30s dead zones — the model
is thinking, I'm sitting there. That waiting adds up.

So I built reSkill: a terminal quiz pane that pops up exactly when
Claude is mid-thought, drawing questions from what you're actually
working on.

The scheduling is built on real spaced-repetition research (not
random shuffle): overdue > new > mastered, interleaved within
confusable concept clusters, 85% target error rate.

Small thing but it's changed how I feel about waiting for AI. Now
the wait is useful.

Installable in one command: `pip install reskill && reskill install`

MIT, feedback welcome: <LINK>

#developerlearning #pythondev #claudecode

---

## Reddit — r/MachineLearning / r/Python / r/ClaudeAI

**Title (r/ClaudeAI):**

`I built a tool that quizzes you on Python while Claude Code thinks (hooks + tmux split)`

**Body:**

[Same as HN body, slightly shorter.]

---

## README badges (for the repo)

```markdown
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)
![MIT](https://img.shields.io/badge/license-MIT-green)
![tests 45/45](https://img.shields.io/badge/tests-45%2F45-brightgreen)
```

---

## Screencast script (for video cuts)

**Scene 1 (0-5s):** Terminal with Claude Code running. User types
`reskill claude`. Text overlay: "Claude thinks. You wait."

**Scene 2 (5-10s):** Split tmux appears. Left: claude responding.
Right: reSkill pane with "waiting for claude to think".

**Scene 3 (10-18s):** User sends a prompt ("explain async/await
pitfalls"). Claude starts thinking. Right pane flashes GOLD,
question appears: "Why doesn't this async for loop run
concurrently?"

**Scene 4 (18-25s):** User clicks right pane, presses `2`. ✓ reveal.
Session badge updates to "Q1 · 1✓".

**Scene 5 (25-30s):** Back to Claude finishing its answer. Tagline:
"While Claude thinks, you learn."

**End card:** reSkill logo + GitHub link + "pip install reskill"

---

## Key messaging

Always lead with:
1. The concrete moment of friction (waiting during AI thinking)
2. That the questions are CONTEXTUAL (not random)
3. The scheduler is research-backed (not vibes)
4. Reversible install, no lock-in

Never lead with the streak/gamification — it's table stakes, not the
differentiator.
