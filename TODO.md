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
- [ ] Options 4 getting clipped when terminal is short (40 rows) --
      need more compact render or smarter fallback
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

- [ ] `reskill session` command entry point
- [ ] `reskill session --from-commits 7d` flag
- [ ] Git log parser: extract commits from N days with their diffs
- [ ] Commit-to-question generator:
  - [ ] Template-based for common patterns (new file, error handling,
        typing changes, refactors)
  - [ ] LLM-based for novel diffs (Haiku, pre-generated, cached)
- [ ] Question cache at `~/.reskill/project_cache/<project_hash>/`
- [ ] Integrate with existing SM-2 state machinery

## Phase C2: Stop hook integration

- [ ] `reskill install` command:
  - [ ] Writes Stop hook to `~/.claude/settings.json`
  - [ ] Hook calls `reskill log-session <transcript_path>`
  - [ ] Idempotent (don't duplicate if already installed)
  - [ ] `reskill uninstall` removes the hook
- [ ] `reskill log-session` command:
  - [ ] Reads Claude Code session transcript JSONL
  - [ ] Extracts concepts/patterns/tools used
  - [ ] Enqueues question candidates for the project
  - [ ] Writes a non-blocking single-line notice to user
- [ ] Verify session transcript format / path resolution

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
