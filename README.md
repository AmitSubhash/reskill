# reSkill

[![tests](https://github.com/AmitSubhash/reskill/actions/workflows/tests.yml/badge.svg)](https://github.com/AmitSubhash/reskill/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

> A terminal companion for Claude Code. While Claude thinks for 23
> seconds, reSkill hands you a quiz about the exact code it's working
> on.

Zero network. No Claude slowdown. Local state, single flag file. MIT,
alpha. Landing: <https://amitsubhash.github.io/reskill/>.

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

## Install

```bash
# 1. install the package
pip install git+https://github.com/AmitSubhash/reskill.git

# 2. see it work, no settings touched
reskill demo

# 3. wire it into Claude Code (reversible; backs up your settings.json)
reskill install
reskill doctor
```

Prefer editable? `git clone https://github.com/AmitSubhash/reskill.git && cd reskill && pip install -e .`

## Use

Live during Claude sessions (the main one):

```bash
reskill claude   # opens claude + a quiz pane alongside
```

If you have tmux: splits the current window. If not: pops a second
Terminal.app or iTerm2 window. Click the quiz pane (or `Ctrl+B →`) to
focus it, press `1` to `4` to answer.

Anytime, anywhere:

```bash
reskill next                    # one context-matched quiz, right now
reskill next --concept torch    # target a specific topic
reskill session                 # commit-driven deck (last 7 days)
reskill review                  # drill your recently-missed questions
reskill topics                  # learning map: every concept + mastery
reskill doctor                  # diagnose anything that feels off
reskill status                  # one-liner: 0 mastered, 3/5 today, 5 streak
reskill stats                   # level, XP, per-concept mastery
reskill streak                  # 12-week heatmap of your answered days
```

## How it works

- **Hooks** fire on `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
  `Stop` to toggle a flag file at `~/.reskill/state/thinking`.
- **Quiz pane** watches the flag (or falls back to transcript-mtime
  polling if hooks aren't installed) and serves a question whenever
  Claude is mid-thought.
- **Scheduler** picks questions matched to what Claude is writing.
  Tiers: live transcript > recent git commits > cumulative cache.
  Within a tier: SM-2 overdue > new > not-due. Across concepts:
  interleaved within confusable clusters (Rohrer &amp; Taylor 2007).
  Within a concept: format diversity (Roediger &amp; Karpicke 2006).
  Targets a 15% error rate per Wilson 2019.
- **Pacing gate** rate-limits with sensible defaults, tunable via
  `RESKILL_*` env vars.
- **In-session re-queue** pushes wrong answers back 3 items later
  (Butler &amp; Roediger 2008).
- **Hypercorrection cue**: wrong answers given in under 5 seconds
  get a sticky flag. Research says these stick hardest.

## Controls

| Key       | Action                               |
|-----------|--------------------------------------|
| `1` to `4`| Answer                               |
| `x`, esc  | Skip this question                   |
| `b`       | Later, requeue after 5 items         |
| `B`       | Bury, gone for today                 |
| `q`       | Quit the pane (idle card only)       |

## Themes

```bash
export RESKILL_THEME=everforest  # default on truecolor terminals
export RESKILL_THEME=mono        # BOLD/DIM only
export NO_COLOR=1                # standard, also forces mono
```

Auto-falls-back to mono when `COLORTERM` is not `truecolor` or
`24bit` (Apple Terminal.app, many ssh contexts).

## Tuning

```bash
export RESKILL_MIN_GAP=10                # seconds between quizzes
export RESKILL_MAX_PER_HOUR=20
export RESKILL_MAX_PER_DAY=60
export RESKILL_THINKING_DEBOUNCE=3       # skip first N seconds
export RESKILL_SAME_CONCEPT_COOLDOWN=90
```

## What's inside

- 74 hand-written questions across 50 concepts
- Python (async, typing, numpy / pandas / torch, stdlib gotchas,
  packaging, testing) plus shell, git, SQL, React and TypeScript
  essentials
- 8 question formats: output, bug, tradeoff, scenario, why, gotcha,
  refactor, cloze
- LLM-generated questions from your live transcript or real commit
  diffs via `reskill gen --live`

## Uninstall

```bash
reskill uninstall   # removes hooks + statusline, keeps a backup
```

Your existing `settings.json` hooks and statusLine are preserved. We
only touch entries we own.

## Status

Alpha. Data model stable, scheduler is evidence-based. The template
bank is hand-written; LLM-generated questions from novel diffs are
the next major milestone.

## License

MIT. See [LICENSE](./LICENSE).

## Credits

Built by Amit Subhash ([@AmitSubhash](https://github.com/AmitSubhash)).
Scheduler grounded in the spaced-repetition literature: Bjork &amp;
Bjork 2011 (desirable difficulties), Rohrer &amp; Taylor 2007
(interleaving), Butler &amp; Roediger 2008 (delayed feedback), Wilson
et al. 2019 (85% rule), Butterfield &amp; Metcalfe 2001
(hypercorrection). Mistakes are mine.
