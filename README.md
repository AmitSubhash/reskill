# reSkill

Turn AI thinking time into developer growth. Interactive quizzes that
run in a **tmux pane alongside Claude Code**, a live badge in Claude
Code's statusline, and a commit-driven post-session deck for deliberate
practice.

## Why not just overlay on top of Claude Code?

Tried it. Doesn't work. Claude Code uses Ink (React), which repaints
via relative cursor moves and periodic full-screen clears -- it always
thinks it owns the entire terminal. Our earlier PTY-wrap + DECSTBM
scroll-region approach looked fine in synthetic tests and collapsed in
real use (borders scattered, quizzes firing on response bullets,
panel overwritten by Ink repaints).

The architecture that actually works:

  * **tmux split-pane** for the interactive quiz -- Claude gets one
    pane, reSkill gets the other. Two independent PTYs, zero
    escape-sequence collision.
  * **Claude Code statusLine** for ambient display -- Ink itself
    reserves the row, debounces, and hides during permission prompts.
    Not interactive, but always visible.
  * **`reskill session`** for post-run deliberate practice on the
    commits you just shipped.

## Install

```bash
cd ~/Projects/reskill
pip install -e .
brew install tmux           # required for `reskill claude`
reskill install             # adds hooks + statusLine to ~/.claude/settings.json
```

## The three ways to use it

### 1. `reskill claude` -- tmux split-pane launcher

```bash
reskill claude                      # claude in main pane, quiz in side pane
reskill claude --continue
reskill claude /plan "..."
```

Claude runs in the left pane exactly as normal. A `reskill quiz-panel`
runs in the right pane and watches a file signal (`~/.reskill/state/
thinking`) written by the Claude Code hooks we installed. When Claude
is mid-thought, a question appears. You answer with 1/2/3/4, `x`
skips, `q` exits the pane.

### 2. `reskill session` -- git-log deliberate practice

```bash
reskill session                  # last 7 days, 5 questions
reskill session --since 14d
reskill session --since 24h --max 3
```

Parses `git log` in the current repo, matches each commit's diff
against the concept patterns, and walks you through a deck stocked
with your own recent work. Each quiz shows a "from <sha> <subject>"
chip so you know which commit triggered the question.

### 3. statusLine badge (always on)

Once `reskill install` has run, Claude Code calls
`reskill statusline` every 2 seconds. You'll see:

- idle: `reskill · day 3 · 2/5 today · 470 xp`
- during a turn: `reskill  quiz pane is live / 🔥 3  ·  2/5 today  ·  quiz this turn`

## Status + streak

```bash
reskill status            # terse one-liner: "🔥 12  ·  3/5 today"
reskill status --plain    # ASCII, safe for $PS1 / tmux status-right
reskill streak            # 12-week github-style heatmap
reskill stats             # level, XP, best combo, per-concept mastery
```

Drop this in your `~/.zshrc`:

```bash
PROMPT='$(reskill status --plain) %# '
```

## Controls in the quiz pane

| Key     | Action                       |
|---------|------------------------------|
| `1`-`4` | Answer the current quiz      |
| `x`     | Skip this quiz               |
| `esc`   | Alias for `x`                |
| `q`     | Quit the quiz pane           |

Your answer cannot leak to Claude -- the panes are isolated PTYs.

## How the hooks wire up

`reskill install` edits `~/.claude/settings.json` (with a backup) to add:

- `UserPromptSubmit` + `PreToolUse` -- touch `~/.reskill/state/thinking`
- `PostToolUse` + `Stop` -- remove that file
- `Stop` -- also call `reskill log-session` to ingest the transcript
  into the per-project concept cache at `~/.reskill/project_cache/`
- `statusLine` -- point at `reskill statusline` with a 2s refresh

`reskill uninstall` removes only those entries; your existing hooks
are untouched.

## What's in the box (data)

- `~/.reskill/state.json` -- streak, XP, per-concept mastery (SM-2)
- `~/.reskill/project_cache/<hash>/concepts.json` -- per-project
  concept tally from ingested session transcripts; used by
  `reskill session` and `reskill quiz-panel` to prioritize concepts
  you've actually touched
- `~/.reskill/state/thinking` -- flag file, presence means "Claude is
  mid-thought right now"

## Status

Alpha. Template bank covers async, error handling, caching, JWT,
databases, HTTP status codes, generators, context managers,
comprehensions, FastAPI DI, and pytest. LLM-generated questions for
novel diffs are next.
