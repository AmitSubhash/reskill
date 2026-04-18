# reSkill

Turn AI thinking time into developer growth. A quiz box appears inline
while Claude Code is thinking. You answer with 1-4 (or skip with esc).
Claude's response is held until you answer. When Claude finishes, it
shows you the response. You learned something. You keep coding.

## Install

```bash
cd ~/Projects/reskill
pip install -e .
```

## Use

```bash
# Try the demo first (no API needed)
reskill demo

# Check your stats
reskill stats

# The real thing: wrap Claude Code
reskill claude                       # shortcut for `reskill run claude`
reskill run claude --continue        # or any args
reskill run claude /plan "fix bug"   # any claude subcommand
```

## What you'll see

1. You type a prompt in Claude and hit Enter.
2. Claude starts thinking. A small spinner appears.
3. ~0.3 seconds in, a quiz box pops inline -- full width.
4. You press 1/2/3/4 or esc. The answer reveal appears with the correct
   option and a short teaching explanation.
5. If Claude is still thinking, another question may appear.
6. When Claude finishes thinking, any queued output is released.
7. Claude's response streams as usual. You can keep coding.

Your XP, streak, and per-concept mastery persist in `~/.reskill/`.

## Safety: permission prompts

When Claude asks you to approve an action ("1. Yes / 2. Yes, always /
3. No"), reSkill detects it and suppresses quizzes. Your 1/2/3 answer
always goes to Claude, not to reSkill.

## Keyboard

| Key   | Action                  |
|-------|-------------------------|
| `1`-`4` | Answer current quiz   |
| `esc` | Skip the current quiz   |

All other keys pass through to Claude unchanged.

## Status

Alpha. The template bank has ~20 thought-provoking questions across
async, error handling, caching, JWT, databases, testing. More coming.
