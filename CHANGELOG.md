# Changelog

All notable changes to reSkill. Follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with minor
liberties for pre-1.0 pace.

## [Unreleased]

### Added
- `reskill topics` — learning-map view of all 50 concepts grouped by
  confusable cluster, with per-concept mastery markers.
- `reskill next --concept X` — drill a specific concept directly
  instead of waiting for the scheduler to pick it.
- 20 second-entry questions across concepts that previously had only
  one variant. Bank now 74 questions across 50 concepts; 24 concepts
  have 2+ variants so the scheduler has real within-concept choice.
- 7 new smoke tests covering doctor/topics/next/review_queue/activity
  cache. Total: 52 tests.
- GitHub social preview image (1280x640), hero GIF inline in README,
  landscape + vertical MP4 demos.
- CONTRIBUTING.md and marketing/LAUNCH_CHECKLIST.md.

### Fixed
- `have_reskill_hooks()` now looks under `settings.hooks.*` first so
  the quiz pane correctly detects hook-driven timing after the codex
  schema fix.
- Bumped `TRANSCRIPT_FRESH_SECONDS` 3s → 15s and the quiz-pane grace
  period 6s → 30s so long xhigh-effort Claude inferences don't
  falsely register as idle.
- Quiz pane now shows a "claude is still thinking... next question in
  ~Ns" cooldown card instead of the generic idle card when blocked by
  the pacing gate during an active turn.

### Performance
- 30,000× faster transcript-polling hot path via TTL cache and
  active-directory filtering. Was ~32ms/call; now ~0.001ms cached,
  ~0.05ms uncached.

### Changed
- Pacing defaults relaxed: 10s min gap (was 30), 20/hr (was 10),
  60/day (was 40), 90s per-concept cooldown (was 120). All still
  env-var tunable.

## [0.2.0] - 2026-04-18

First properly-shippable build. The tmux/macOS live pane works
end-to-end, hooks wire up correctly, and there's enough of a launch
kit that this can be shared publicly.

### Added
- `reskill doctor` — 12-check integration audit that catches silent
  failures (hook schema, fire history, pacing caps, cache state).
- `reskill next` — one context-matched question any time.
- `reskill review` — drill the recent-wrong list.
- macOS fallback: `reskill claude` on a system without tmux opens a
  second Terminal.app / iTerm2 window for the quiz pane.
- Rich end-of-session summary (`reskill session`) with per-concept
  hit/miss markers and revisit-later items.
- Evidence-based scheduler: SM-2 + 85% rule (Wilson 2019) + format
  diversity + interleaving within confusable clusters.
- In-session wrong-answer re-queue (`reskill/review_queue.py`).
- Pacing gate with env-var tuning: `RESKILL_MIN_GAP`,
  `RESKILL_MAX_PER_HOUR`, `RESKILL_MAX_PER_DAY`,
  `RESKILL_SAME_CONCEPT_COOLDOWN`, `RESKILL_THINKING_DEBOUNCE`.
- Hypercorrection cue — wrong answers given in <5s get a "◉ sticky
  one" banner (Butterfield & Metcalfe 2001).
- Semantic pane-border colors via tmux: ash idle, gold arming,
  teal focused, sage correct, rose wrong.
- Statusline compose wrapper — preserves your existing statusLine
  command and adds reSkill's line below (instead of overwriting).
- `RESKILL_THEME=mono` + `NO_COLOR=1` for high-contrast / colorblind /
  light-terminal users.
- 50 concept patterns, 54 hand-written questions covering Python
  (async, typing, numpy/pandas/torch, stdlib gotchas, packaging,
  testing), shell, git, SQL, React/TS.
- Launch kit: videos (landscape + vertical MP4 + hero GIF + social
  preview PNG), `marketing/LAUNCH.md` copy for every surface,
  `marketing/LAUNCH_CHECKLIST.md` day-of-launch playbook.
- CI via GitHub Actions on Python 3.10 / 3.11 / 3.12.

### Fixed
- Hooks weren't firing because entries were written at the
  settings.json root; Claude Code reads them from
  `settings.hooks.*` (nested). Codex caught this after a real
  session showed zero `/tmp/reskill-hook.log` activity.
- `●` (U+25CF — Claude's bullet) was in the spinner-glyph set,
  causing quizzes to fire on every list item in a streamed
  response.
- `tty.setraw` in the session loop disabled output-post-processing
  so reveal newlines staircased. Switched to `tty.setcbreak`.
- After a quiz completed, `prompt_submitted_at` stayed set, letting
  another quiz fire on the same Claude turn. Now cleared.
- `have_reskill_hooks()` looked at the legacy root location and
  returned False after the hook-nesting fix, making the pane fall
  back to transcript polling even though hooks were installed.

### Changed
- Mono is no longer the default theme; Everforest is, with brighter
  `ASH` / `STONE` than v0.1 so the dim-body-text reads on any
  background. `RESKILL_THEME=mono` still available for opt-in.
- Pacing defaults loosened: 10s min gap (was 30), 20/hr (was 10),
  60/day (was 40), 90s per-concept cooldown (was 120).
- Grace period 6s → 30s; transcript freshness 3s → 15s. Long
  xhigh-effort inferences stop falsely registering as idle.

### Removed
- `reskill/simulator.py`, `reskill/panel.py`, `reskill/detect.py` —
  dead code with no callers. Net -470 lines.

## [0.1.0] - 2026-04-17

Initial. PTY-wrap + DECSTBM overlay attempt for live quizzes
during Claude sessions. Works for non-Ink programs via
`reskill wrap`; abandoned for Claude Code itself in favor of
the tmux split-pane approach (see v0.2.0).
