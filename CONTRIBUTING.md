# Contributing

Short guide so you know where things live.

## Layout

```
reskill/
  cli.py              main CLI dispatcher
  quiz_panel.py       interactive quiz UI (live-mode)
  session.py          commit-driven deck (reskill session)
  next_cmd.py         one-shot question (reskill next)
  review_cmd.py       wrong-list drill (reskill review)
  doctor.py           diagnostic (reskill doctor)

  scheduler.py        SM-2 + 85% rule + interleaving + format mix
  pacing.py           rate-limit gate (3s debounce, 10s gap, N/hr, N/day)
  review_queue.py     in-session wrong-answer re-queue

  question.py         Question dataclass + TEMPLATE_BANK (50 concepts)
  activity.py         is_claude_active() — hook flag + transcript poll
  state.py            persistent state (streak, XP, SM-2, wrong-list)
  log_session.py      ingests Claude transcript on Stop hook

  hookinstall.py      install/uninstall hooks + statusLine
  tmux_launcher.py    the reskill claude split-pane launcher
  statusline.py       the `reskill statusline` command
  status_ui.py        render_status / render_heatmap
  inline_box.py       the ╭── think about this ── ╮ box renderer
  palette.py          color/theme definitions

  demo.py             offline demo (no Claude needed)
  wrap.py             legacy PTY wrap (kept for non-Ink programs only)
  region.py           DECSTBM helper used by wrap.py

tests/                pytest suite (45 tests)
  integration/        shell-driven smoke tests

marketing/
  LAUNCH.md           copy for every launch surface
  videos/             rendered MP4s + hero GIF (source: reskill-marketing/)

.github/workflows/    CI config
```

## Adding a question

Open `reskill/question.py`. Find `TEMPLATE_BANK` (near line 78). Each
concept is a key mapping to a list of `_q(...)` calls. Match an existing
shape:

```python
"mutable_default": [
    _q(
        concept="mutable-default",
        format="output",
        prompt="...",
        code="...",
        opts=[
            ("wrong option 1", False),
            ("correct option", True),
            ...
        ],
        explanation="...",
    ),
],
```

Then add a regex to `PATTERNS` (bottom of the file) so
`detect_concepts(text)` can route to it.

## Running tests

```bash
pip install -e . && pytest -q
```

## Adding a scheduler rule

Everything scheduler-related lives in `reskill/scheduler.py`. The
public entry point is `choose(live_text, commit_text, state,
seen_ids, last_concept, recent_formats) -> Pick | None`. Any new
bias goes into `_bucketize()` or `_pick_from_concepts()`. Add a test
in `tests/test_scheduler.py` that proves the new bias wins over
older biases.

## Debugging

```bash
reskill doctor       # 12-check integration audit
```

If hooks aren't firing, check:
1. `reskill install` has run
2. `~/.claude/settings.json` has entries under `hooks.*` (nested),
   not at the root. `reskill doctor` catches this.
3. `/tmp/reskill-hook.log` gets touched when you end a Claude
   session (Stop hook redirect).

## Evidence for scheduler choices

Every scheduling decision has a docstring citation. If you're
proposing a change, bring evidence at the same level. Key papers:

- Rohrer & Taylor 2007 — interleaving > blocking (for confusable items)
- Bjork & Bjork 2011 — desirable difficulties
- Wilson et al. 2019 *Nature Communications* — 85% rule
- Karpicke & Roediger 2008 *Science* — retrieval > restudy
- Butler & Roediger 2008 — delayed feedback > immediate for MC
- Butterfield & Metcalfe 2001 — hypercorrection effect
- Iqbal & Bailey 2008 — interrupt at coarse breakpoints
- Brunmair & Richter 2021 — interleaving's mechanism is contrast

See `docs/RESEARCH.md` (if it exists) or grep `scheduler.py` for the
inline citations.
