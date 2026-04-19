# reSkill

[![tests](https://github.com/AmitSubhash/reskill/actions/workflows/tests.yml/badge.svg)](https://github.com/AmitSubhash/reskill/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

> Quizzes that appear while Claude Code is thinking. Turn waiting time
> into learning time.

![reSkill demo](./marketing/videos/reskill-hero.gif)

> Full videos: [landscape](./marketing/videos/reskill-launch.mp4)
> · [vertical](./marketing/videos/reskill-tiktok.mp4)

```
Claude is thinking...                   reSkill   Q1
                                        ╭── think about this ──╮
  · Reading 3 files                     │ Most Pythonic way to │
  · Analyzing scheduler.py              │ read a UTF-8 JSON?   │
                                        │                      │
  Actioning... 16s                      │  1) open(...)        │
                                        │  2) Path(...).read_  │
                                        │     text(utf-8)  ✓   │
                                        │  3) codecs.open()    │
                                        │  4) io.open()        │
                                        ╰──────────────────────╯
```

While Claude thinks, you answer. When Claude finishes, you've learned
something you didn't want to Google. Over time the scheduler tracks
what you miss and drills it again. Streaks are loss-averse-free — miss
a day, come back, pick up where you left off.

## Install

```bash
pip install -e ~/Projects/reskill
reskill install     # adds Claude Code hooks + statusline (reversible)
reskill doctor      # confirms everything is wired up
```

## Use

**Live during Claude sessions** (the main one):

```bash
reskill claude   # opens claude + a quiz pane alongside
```

If you have tmux: splits the current window. If not: pops a second
Terminal.app / iTerm2 window. Click the quiz pane (or `Ctrl+B →`) to
focus it, press `1`-`4` to answer.

**Anytime, anywhere:**

```bash
reskill next                          # one context-matched quiz, right now
reskill next --concept torch          # target a specific topic
reskill session                       # commit-driven deck (last 7 days)
reskill review                        # drill your recently-missed questions
reskill topics                        # learning map: every concept + mastery
reskill doctor                        # diagnose anything that feels off
reskill status                        # one-liner: 0 mastered · 3/5 today · 🔥 5
reskill stats                         # level, XP, per-concept mastery
reskill streak                        # 12-week github-style heatmap
```

## How it works

- **Hooks** fire on `UserPromptSubmit` / `PreToolUse` / `PostToolUse`
  to toggle a flag file at `~/.reskill/state/thinking`.
- **Quiz pane** watches the flag (or falls back to transcript-mtime
  polling if hooks aren't installed) and serves a question whenever
  Claude is mid-thought.
- **Scheduler** picks questions matched to what Claude is writing.
  Tiers: live transcript > recent git commits > cumulative cache.
  Within a tier: SM-2 overdue > new > not-due. Across concepts:
  interleaved within confusable clusters (Rohrer & Taylor 2007).
  Within a concept: format diversity (Roediger & Karpicke 2006).
  Targets 15% error rate per Wilson 2019.
- **Pacing gate** rate-limits: 10s min gap, 20/hr, 60/day. All
  `RESKILL_*` env-var tunable.
- **In-session re-queue** pushes wrong answers back 3 items later
  (Butler & Roediger 2008).
- **Hypercorrection cue** — wrong answers given in <5s get a "◉
  sticky one" banner; research says these stick hardest.

## Controls in every quiz

| Key      | Action                                    |
|----------|-------------------------------------------|
| `1`-`4`  | Answer                                    |
| `x`/esc  | Skip this question                        |
| `b`      | Later — requeue after 5 items             |
| `B`      | Bury — gone for today                     |
| `q`      | Quit the pane                             |

## Themes

```bash
export RESKILL_THEME=everforest  # default
export RESKILL_THEME=mono        # BOLD/DIM only, works on any background
export NO_COLOR=1                # standard -- also forces mono
```

## Tuning

```bash
export RESKILL_MIN_GAP=10                # seconds between quizzes
export RESKILL_MAX_PER_HOUR=20
export RESKILL_MAX_PER_DAY=60
export RESKILL_THINKING_DEBOUNCE=3       # skip first N seconds
export RESKILL_SAME_CONCEPT_COOLDOWN=90
```

## What's inside

- 54 hand-written questions across 50 concepts
- Python (async, typing, numpy/pandas/torch, stdlib gotchas,
  packaging, testing) + shell, git, SQL, React/TS essentials
- 8 question formats: output, bug, tradeoff, scenario, why, gotcha,
  refactor, cloze

## Uninstall

```bash
reskill uninstall   # removes hooks + statusline, keeps a backup
```

Your existing `settings.json` hooks and statusLine are preserved — we
only touch entries we own.

## Status

Alpha. Data model stable, scheduler is evidence-based. The template
bank is hand-written; LLM-generated questions from novel diffs are
the next major milestone.

## License

MIT. See LICENSE.

## Credits

Built by Amit Subhash ([@AmitSubhash](https://github.com/AmitSubhash)).
Scheduler grounded in the spaced-repetition literature: Bjork & Bjork
2011 (desirable difficulties), Rohrer & Taylor 2007 (interleaving),
Butler & Roediger 2008 (delayed feedback), Wilson et al. 2019 (85%
rule), Butterfield & Metcalfe 2001 (hypercorrection). Mistakes are
mine.
