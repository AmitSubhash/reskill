# reSkill -- End-to-End Build Plan

Living todo list. Items marked:
- [ ] open
- [>] in progress
- [x] done
- [~] abandoned (with reason)

---

## Architecture (settled after real-world testing 2026-04-18)

The PTY-wrap + DECSTBM scroll-region approach cannot work with Claude
Code. Ink repaints via `CUU + EL` (relative cursor up + erase-in-line)
anchored to the current cursor row, and periodically issues
`\x1b[2J\x1b[3J\x1b[H` (full clear + scrollback wipe, Ink issue #935).
DECSTBM only constrains newline-driven scrolling -- neither of those
sequences are bounded. No public Ink API exists to reserve rows
(issues #263, #182, #442, #78).

Research confirmed the two surfaces that DO work:

  1. tmux split-pane launcher -- two independent PTYs, zero collision,
     fully interactive quiz. This is the primary `reskill claude` path.
  2. Claude Code statusLine -- Ink itself reserves the row, debounced,
     auto-hides for permission prompts. Non-interactive but persistent.

## Phase D (overlay) -- ABANDONED, replaced by tmux split

- [~] PTY-wrap + DECSTBM overlay -- proven catastrophic in real use
      (quiz borders scatter across screen, Claude's Ink clobbers panel,
      quiz fires on response bullets). See commit/research notes.
- [x] `reskill claude` -- tmux split-pane launcher
      (reskill/tmux_launcher.py)
- [x] `reskill quiz-panel` -- interactive quiz UI in the side pane
      (reskill/quiz_panel.py)
- [x] `reskill statusline` -- passive display for Claude's bottom row
      (reskill/statusline.py)
- [x] Thinking-flag IPC between Claude (via hooks) and the quiz pane
      (~/.reskill/state/thinking)
- [ ] Handle tmux pane resize gracefully (quiz pane should reflow)
- [ ] If user has no tmux, fall back to `reskill session` after each
      Claude Stop hook instead of trying to overlay

## Phase C1: Session command and commit-based questions

- [x] `reskill session` command entry point (cli.py: cmd_session)
- [x] `reskill session --since 7d` flag (also --from-commits alias)
- [x] Git log parser: extract commits from N days with their diffs
- [x] Commit-to-question generator: template-based matching
- [x] Integrate with existing SM-2 state machinery
- [x] cbreak mode (not raw) so reveal newlines render correctly
- [x] "any key to continue" hint after reveal to fix "stuck after skip"
- [ ] LLM-based question gen for novel diffs (Haiku, pre-generated)
- [ ] Question cache at `~/.reskill/project_cache/<project_hash>/`
- [ ] Show the diff snippet that triggered the question

## Phase C2: Hooks

- [x] `reskill install`: writes UserPromptSubmit + PreToolUse +
      PostToolUse + Stop hooks AND the statusLine config
- [x] `reskill uninstall`: removes only reskill's entries
- [x] `reskill hook-status`: reports install state
- [x] `reskill log-session`: ingests Claude Code JSONL, tallies
      concepts into per-project cache
- [ ] Verify against a REAL Claude Code session transcript format

## Phase C3: Shell prompt widget + streak UI

- [x] `reskill status` -- terse line for $PS1 / tmux status-right
- [x] --plain ASCII variant
- [x] Daily goal logic (state.daily_goal)
- [x] Streak freeze mechanic
- [x] `reskill streak` -- 12-week heatmap

## Phase C4: Polish (ongoing)

- [ ] Allow `reskill goal N` to adjust daily goal
- [ ] Expand detect.py / question patterns
- [ ] Cache detection per-project
- [ ] Uninstall leaves empty `[]` arrays; prune them

## Phase E: Cleanup

- [x] Update README with new architecture (tmux + statusline)
- [~] Deprecate `reskill run` / `reskill wrap` in messaging
- [ ] Delete reskill/region.py (dead code now)
- [ ] Delete reskill/wrap.py (dead code, replaced by tmux_launcher)
- [ ] Package for pip install (TestPyPI first)

## Known bugs fixed in this pass

- [x] Quiz fires on Claude's response bullets (`●`) -- removed from
      spinner glyphs. Requires Braille + verb for positive detection.
- [x] "Stuck after skip" -- session.py was using `tty.setraw` which
      disables output processing; switched to `tty.setcbreak`.
- [x] "Quiz keeps popping up after Claude answer" -- set
      `prompt_submitted_at = 0` after each quiz, so one quiz per turn.
- [x] Rendering scrambled in live wrap -- fundamental Ink collision,
      fixed by abandoning the overlay approach entirely.

## Tests

- [x] tests/test_wrap_detection.py -- 12 regression tests covering
      spinner false positives (bullets in response), true positives
      (Braille + verb), turn-end detection, and permission detection.
      These should have existed from day 1.
