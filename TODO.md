# reSkill -- End-to-End Build Plan (C + D)

Living todo list. Grows as work reveals new sub-tasks. Items marked:
- [ ] open
- [>] in progress
- [x] done
- [~] abandoned (with reason)

---

## Phase D1: Region overlay prototype (the technical wedge)

- [x] Standalone prototype /tmp/region_proto.py -- ANSI sequences correct,
      scroll region + panel + save/restore pattern works
- [x] Integrated into reskill.region.Region class
- [x] Tested against REAL Claude Code via tmux: quiz box renders CLEANLY
      in the bottom region, Claude's UI + response stream above.
      THE SCROLL REGION APPROACH WORKS. 🎉
- [x] Options 4 getting clipped when terminal is short (40 rows) --
      fixed with compact mode + code truncation (inline_box.py)
- [ ] Handle SIGWINCH (terminal resize) -- region needs recalculation
- [ ] Handle edge: region too small for panel content (terminal < 30 lines)
- [ ] Verify in iTerm2, Terminal.app (not just tmux), WezTerm
- [x] SHIP IT. Falling back to C on top of this.

## Phase D2: Integrate region overlay into wrap.py

- [ ] Replace current "hold bytes + render inline" in run_quiz with
      region overlay rendering
- [ ] Claude's output keeps streaming to the main area (DON'T hold bytes)
- [ ] Quiz panel renders in bottom region, updates countdown in place
- [ ] On permission prompt detection: clear region immediately, let
      Claude's prompt render above as normal
- [ ] Commit + write end-to-end test

## Phase C1: Session command and commit-based questions

The "quiz me on this week's commits" killer feature from research.

- [x] `reskill session` command entry point (cli.py: cmd_session)
- [x] `reskill session --since 7d` flag (also --from-commits alias)
- [x] Git log parser: extract commits from N days with their diffs
      (reskill/git_diffs.py)
- [x] Commit-to-question generator: template-based matching against
      detect_concepts over commit subject + added lines
- [x] Integrate with existing SM-2 state machinery (record_answer/skip)
- [ ] LLM-based question gen for novel diffs (Haiku, pre-generated, cached)
- [ ] Question cache at `~/.reskill/project_cache/<project_hash>/`
- [ ] Show the diff snippet that triggered the question (just commit
      chip for now; deeper drill-in later)

## Phase C2: Stop hook integration

- [x] `reskill install` command:
  - [x] Writes Stop hook to `~/.claude/settings.json`
  - [x] Hook calls `reskill log-session` (transcript via stdin JSON)
  - [x] Idempotent (detects marker string, skips re-install)
  - [x] `reskill uninstall` removes the hook
  - [x] `reskill hook-status` reports install state
- [x] `reskill log-session` command:
  - [x] Reads Claude Code session transcript JSONL
  - [x] Extracts concepts/patterns/tools used via detect_concepts
  - [x] Enqueues concept tally into ~/.reskill/project_cache/<hash>/
  - [x] Writes a non-blocking single-line notice to stderr
- [ ] Verify against a real Claude Code session transcript format
      (tested against synthetic JSONL; real path probably works but
      untested end-to-end)
- [ ] Use cached concept tallies to PRIORITIZE question selection in
      `reskill session` (currently session only uses git commits)

## Phase C3: Shell prompt widget + streak UI

- [ ] `reskill status` -- terse line for $PS1 / tmux status-right
      ("🔥 12 · 3/5 today")
- [ ] Daily goal logic: counts toward goal on session completion
- [ ] Streak freeze mechanic (one miss per week forgiven)
- [ ] `reskill streak` for a visual weekly heatmap

## Phase C4: Context detection polish (already 80% done)

- [ ] Expand detect.py to use lockfiles (package-lock, poetry.lock)
- [ ] Detect recently-edited files (last 20 by mtime)
- [ ] Framework signals: grep for key imports beyond just package deps
- [ ] Cache detection result per-project (fast on re-runs)

## Phase E: Cleanup and polish

- [ ] Deprecate `reskill run <cmd>` wrap (it's a dead path)
- [ ] Simplify `reskill claude` to show a helpful message:
      "This requires region overlay support. Try `reskill session` instead."
      OR remove entirely if D1 succeeds
- [ ] Update README with new architecture
- [ ] Package for pip install
- [ ] First-run setup wizard: detect shell, offer hook install, offer
      prompt widget install

## Discovered issues (will be filled in as we go)

(Nothing yet. Items land here as work uncovers them.)
