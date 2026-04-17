# reSkill Implementation Plan

Based on 25+ research agents. Three independent investigations converged on the same architecture.

## The Architecture

```
  ┌─────────────────────────────────────────────────────────────┐
  │ tmux session (reskill)                                       │
  │                                                              │
  │  ┌────────────────────────────┐  ┌───────────────────────┐  │
  │  │ Left pane: claude          │  │ Right pane: quiz UI   │  │
  │  │                            │  │                       │  │
  │  │ User types prompt          │  │ ╭─────────────────╮   │  │
  │  │ Claude streams response    │  │ │ Think about:    │   │  │
  │  │ (unchanged experience)     │  │ │ Why lru_cache?  │   │  │
  │  │                            │  │ │                 │   │  │
  │  │                            │  │ │ 1) Speed        │   │  │
  │  │ ANTHROPIC_BASE_URL=        │  │ │ 2) Memoization  │   │  │
  │  │   http://127.0.0.1:8080    │  │ │ 3) Thread-safe  │   │  │
  │  │                            │  │ │ 4) All above    │   │  │
  │  │                            │  │ ╰─────────────────╯   │  │
  │  └────────────────────────────┘  └───────────────────────┘  │
  │                │                            ▲                │
  │                ▼                            │                │
  │  ┌─────────────────────────────────────────────────────┐    │
  │  │ reSkill proxy (127.0.0.1:8080)                      │    │
  │  │   - Forwards POST /v1/messages to Anthropic API     │    │
  │  │   - Tees SSE content_block_delta to Unix socket     │    │
  │  │   - Quiz engine reads socket, generates questions   │    │
  │  └─────────────────────────────────────────────────────┘    │
  └─────────────────────────────────────────────────────────────┘
```

## Why This Architecture Won

Three independent research agents converged:

| Agent | Verdict |
|-------|---------|
| Claude Code extensions analysis | "Proxy + tmux is cleanest, survives CC updates" |
| Terminal interception patterns | "HTTP proxy on ANTHROPIC_BASE_URL is production-grade" |
| Codex local inspection | "Binary reads ANTHROPIC_BASE_URL, no env vars set, free to intercept" |

## Existing Proof Points

These projects already implement parts of this architecture:

| Project | Stars | What it proves |
|---------|-------|----------------|
| [proxyclawd](https://github.com/dyshay/proxyclawd) | - | MITM proxy for Claude Code with real-time TUI |
| [seifghazi/claude-code-proxy](https://github.com/seifghazi/claude-code-proxy) | 443 | Transparent SSE capture, SQLite logging, dashboard |
| [1rgs/claude-code-proxy](https://github.com/1rgs/claude-code-proxy) | 3,444 | Full Anthropic→OpenAI translator |
| [sokojh/claude-code-tmux-hud](https://github.com/sokojh/claude-code-tmux-hud) | - | tmux side-pane + state file architecture |
| [claude-arcade](https://github.com/anshuman-dev/claude-arcade) | - | `/dev/tty` + fork + alt screen fallback |
| [LiteLLM Anthropic passthrough](https://docs.litellm.ai/docs/pass_through/anthropic_completion) | - | Production-grade passthrough with callbacks |

None of them do learning. That's our wedge.

## The Build

### Phase 0: Clean slate (1 hour)
The old reSkill code (quiz-during-hook approach) is superseded. Keep:
- `palette.py`, `panel.py` (rendering primitives, still useful)
- `detect.py` (project stack detection, still useful)
- `quiz.py`, `cards.py` (data models, still useful)

Move or remove:
- `spinner.py`, `cli.py` (old hook-based approach)
- `patterns.py`, `showcase.py`, `quiz_demo.py`, `demo.py` (old demos)

### Phase 1: The Proxy (1 day)
```python
# reskill/proxy.py
# aiohttp async HTTP proxy, ~80 lines
# 1. Accept POST /v1/messages
# 2. Forward to https://api.anthropic.com with original headers
# 3. Stream SSE response back UNCHANGED
# 4. Parse content_block_delta events in parallel
# 5. Push text deltas to asyncio.Queue (or Unix socket)
```

**Test:** set `ANTHROPIC_BASE_URL=http://127.0.0.1:8080`, run `claude "hello"`, verify:
- Response works identically
- Proxy logs show all streaming deltas

### Phase 2: Question Generation (1 day)
Two layers:

**Layer 2a: Template matching (no LLM, <1ms)**
```python
# reskill/generator/templates.py
# Python ast module to detect patterns in streaming text
# Map patterns to pre-authored question templates
# Examples:
#   detect "try/except" → 5 possible error-handling questions
#   detect "@lru_cache" → 3 caching questions
#   detect "async def" → 4 concurrency questions
```

**Layer 2b: LLM-generated (Gemini 2.0 Flash Lite, ~500ms, $0.000045/question)**
```python
# reskill/generator/llm.py
# For novel contexts, call Gemini with structured JSON output
# Budget: pre-generate at session start, cache per-project
```

### Phase 3: tmux Launcher (half day)
```bash
# reskill/bin/reskill-launch.sh
# Creates tmux session named "reskill"
# Left pane: runs claude with ANTHROPIC_BASE_URL set
# Right pane: runs reskill-ui (the quiz renderer)
# Both share a Unix socket for deltas
```

### Phase 4: Quiz UI (1 day)
Reuse existing `panel.py` rendering. Read from Unix socket.
Press 1/2/3/4 to answer. Answer persists to SQLite.

### Phase 5: The `/learn` Slash Command (half day)
When user types `/learn` in their actual Claude Code session:
- Read last answered question from state
- Show expanded explanation, related concepts, links to docs

### Phase 6: Spaced Repetition (half day)
- SQLite schema for SM-2 per concept
- Ease factor, interval, repetitions
- Weight next question selection toward concepts user got wrong

### Phase 7: Growth Metrics (half day)
`reskill stats` command shows:
- Streak (days active)
- Questions answered
- Concepts mastered
- Weak areas (where Claude keeps fixing the same mistake)

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Proxy | Python + aiohttp | Async SSE streaming, minimal code |
| Quiz rendering | Python + raw ANSI (existing `panel.py`) | Already built |
| Question gen (fast) | Python ast module | Zero deps, <1ms |
| Question gen (smart) | Gemini 2.0 Flash Lite | $0.000045/question, ~500ms |
| IPC | Unix domain socket | Simpler than TCP, local-only |
| State | SQLite | SM-2 per concept, indexed queries |
| Gamification state | JSON | Simple, streak/XP reads on every session |
| Session orchestration | bash + tmux | Battle-tested, universal |

## Open Questions

1. **User's API key**: The proxy needs the user's Anthropic key to forward. Solutions:
   - Read from env (`ANTHROPIC_API_KEY`)
   - User keeps their existing auth (proxy just passes through)
   - Could we avoid forwarding by reading the key Claude Code already has?

2. **Max subscription users**: Claude Code Max uses OAuth bearer tokens, not API keys. The `cc-max-proxy` project solved this by re-invoking the `claude` CLI under the hood. We may need the same.

3. **Non-tmux users**: Fall back to alt screen buffer (like claude-arcade does)?
   Or require tmux? (Simpler product, smaller audience.)

4. **Privacy**: The proxy sees ALL of the user's prompts and Claude's responses. This needs clear disclosure. Local-only processing mitigates the concern.

5. **Cost**: If we use Gemini for LLM-generated questions, we pay (tiny) cost. Options:
   - User brings their own Gemini key
   - We ship template-only and add LLM later
   - Use Claude Haiku via same proxy (user pays through their existing Anthropic quota)

## Ship Order

1. **Day 1-2**: Proxy + basic tee to console (prove streaming interception works)
2. **Day 3**: Template question generator (ast + Python library)
3. **Day 4-5**: tmux launcher + side-pane quiz UI
4. **Day 6**: Keyboard input (1/2/3/4) + answer capture + state persistence
5. **Day 7**: Gemini integration for LLM-generated questions
6. **Day 8**: `/learn` command + spaced repetition
7. **Day 9**: Growth metrics (`reskill stats`)
8. **Day 10**: Package, docs, README

Total: **~2 weeks to a shippable MVP**.

## Success Criteria

- Proxy adds <5ms latency to Claude responses
- Template matcher generates a relevant question from 200 tokens in <10ms
- 80% of questions are perceived as "relevant" (subjective, self-test)
- Developer can press 1/2/3/4 during streaming without breaking Claude's flow
- Post-MVP: beta users report learning something they didn't know
