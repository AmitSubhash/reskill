# reSkill

Turn AI thinking time into developer growth. Inline quizzes that pop
while Claude Code is thinking, a commit-driven deck for deliberate
practice, and a streak you care about.

## Install

```bash
cd ~/Projects/reskill
pip install -e .
```

## The two ways to use it

### 1. Live quizzes while Claude thinks (`reskill claude`)

Wrap Claude Code. A small panel pins to the bottom of your terminal
when Claude is mid-thought; your answers (1-4, `x` skip, `X` mute)
never leak through to Claude. Built on a DECSTBM scroll-region so
Claude's UI keeps streaming above the panel with no alt-screen
switch.

```bash
reskill claude                       # shortcut for `reskill run claude`
reskill run claude --continue        # or any args
reskill run claude /plan "fix bug"   # any claude subcommand
```

### 2. Quiz me on what I shipped this week (`reskill session`)

Reads the last N days of `git log` in the current repo, matches each
commit's diff against the concept patterns, and walks you through a
small deck that's stocked with *your* recent work.

```bash
reskill session                  # last 7 days, 5 questions
reskill session --since 14d
reskill session --since 24h --max 3
```

Each quiz shows a small "from <commit sha> <subject>" chip so you
recognize which commit the question came from.

## Learning loop (optional but recommended)

Install a Claude Code Stop hook that ingests your session transcripts
as they end. The hook extracts concepts your session actually touched
and tallies them per-project; `reskill session` then weights your
deck toward those concepts.

```bash
reskill install        # adds a Stop hook to ~/.claude/settings.json
reskill uninstall      # removes it
reskill hook-status    # check install state
```

The installer backs up your existing `settings.json` to
`settings.json.reskill-bak`.

## Streak + status

```bash
reskill status            # terse one-liner: "🔥 12  ·  3/5 today"
reskill status --plain    # ASCII, safe for $PS1 / tmux status-right
reskill streak            # 12-week github-style heatmap
reskill stats             # level, XP, best combo, per-concept mastery
```

Drop this in your `~/.zshrc`:

```bash
PROMPT="$(reskill status --plain) $PROMPT"
```

## Controls (live wrap)

| Key     | Action                       |
|---------|------------------------------|
| `1`-`4` | Answer the current quiz      |
| `x`     | Skip this quiz               |
| `X`     | Mute quizzes for the session |
| `esc`   | Alias for `x`                |

All other keys pass through to Claude unchanged. Permission prompts
("Yes / No, and tell Claude") auto-pause quizzes so your 1/2/3 goes
to Claude, not reSkill.

## How the live wrap works

- reSkill PTY-wraps the child command.
- When a spinner shows up and the input looks like a submitted prompt,
  a panel is pinned to the bottom via `\x1b[{top};{bottom}r` (DECSTBM
  scroll region). Claude's Ink UI keeps streaming above.
- On wrong/skipped answers, a teaching reveal slides in. On correct,
  a single flash and you keep coding.
- State lives in `~/.reskill/state.json`; per-project concept tallies
  in `~/.reskill/project_cache/<hash>/`.

## Status

Alpha. Template bank covers async, error handling, caching, JWT,
databases, HTTP status codes, generators, context managers,
comprehensions, FastAPI DI, and pytest. LLM-generated questions for
novel diffs are next.
