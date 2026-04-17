# reSkill -- Initial Research

## The Problem

Vibe coding is the new default. Developers prompt AI, accept the output, ship it, and move on -- without understanding what they shipped. The AI makes them feel productive, but they're not learning. Over time, they become dependent on the AI for tasks they used to handle themselves.

reSkill fixes this by turning Claude Code's response streaming time into micro-learning moments. While Claude streams its answer, a parallel process generates a quick question from the content. The developer presses 1/2/3/4 to answer. If they get it right, they understood what Claude did. If they don't, they know what to `/learn` about.

## The Core Mechanism

```
User prompt → Claude starts streaming response
                  |
                  ├── Tokens render normally (developer reads)
                  |
                  └── First ~200 tokens → parallel question generator
                        |
                        ├── Template match (fast, no LLM)
                        │   "detect try/except → error handling question"
                        |
                        └── OR cheap LLM call (Haiku, <1s)
                              "generate 1 MCQ about this concept"
                        |
                        v
                  Question appears in small panel
                  Developer presses 1/2/3/4 while stream continues
                  Answer stored → spaced repetition tracking
```

### Key technical insight

Claude Code already accepts keyboard input during streaming (Ctrl+C to interrupt, permission prompts). The infrastructure for concurrent input + output exists. reSkill adds a question panel that coexists with the streaming response.

### The UX

```
  Claude is responding...

  ╭─────────────────────────────────────────────╮
  │ Do you know why we catch specific           │
  │ exceptions instead of bare except?          │
  │                                             │
  │  1) Performance   2) Debugging clarity      │
  │  3) Both          4) Neither                │
  ╰─────────────────────────────────────────────╯

  I'll add error handling to the JWT validation in
  src/auth.py. The issue is that expired tokens aren't
  being caught, which causes a 500 instead of a 401.

  Here's the fix:

    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
  ...
```

The question appears ABOVE or ALONGSIDE the streaming response. No screen takeover. The developer can answer or ignore -- the response keeps streaming regardless.

## Why This Works

### For vibe coders
"You don't have to stop vibe coding. Just glance at the question. If you know the answer, you understood what Claude did. If you don't, now you know what to learn."

### Psychologically
- **Priming effect**: The question prepares the developer's brain to understand the response better
- **Testing effect**: Being tested on material improves retention 50% more than re-reading
- **Situated cognition**: Learning about error handling WHILE looking at error handling code is the ideal learning context
- **Zero additional time cost**: The streaming was happening anyway

### vs. Every alternative we considered
| Alternative | Problem reSkill solves |
|------------|----------------------|
| Post-session recap | Too late -- developer already moved on |
| Interactive quizzes during tool execution | Wrong timing window, screen takeover |
| Passive tips in spinner | No interaction, no testing effect |
| Separate learning app | Context switch, won't be used |
| Mentor mode (Claude explains more) | Adds response length, slows workflow |

## Question Sources (layered)

### Layer 1: Template-based (no LLM, instant)
Detect code patterns in streaming tokens and match to pre-authored questions:

```python
PATTERN_QUESTIONS = {
    "try/except": [
        "Why catch specific exceptions instead of bare except?",
        "What's the parent class of all Python exceptions?",
    ],
    "async def": [
        "What does async/await actually do under the hood?",
        "When should you use async vs threading?",
    ],
    "jwt": [
        "Why do JWT tokens have an expiry time?",
        "What are the three parts of a JWT?",
    ],
    "@app.get": [
        "What HTTP method is GET used for?",
        "What's the difference between GET and POST?",
    ],
}
```

### Layer 2: Project-context questions
Read project files at session start. Know the stack. Weight questions toward the frameworks and libraries in use.

### Layer 3: LLM-generated (Haiku, <1s)
For novel code patterns that don't match templates, generate a question with a fast/cheap model:

```
System: Generate exactly 1 multiple-choice question (4 options) about the
programming concept in the following code context. Format as JSON.
Make it test understanding, not memorization. One option must be correct.

User: [first 200 tokens of Claude's response]

→ {"question": "...", "options": [...], "correct": 1, "explanation": "..."}
```

### Layer 4: Personalized (from learning state)
Track what the developer knows and doesn't. Re-surface concepts they got wrong. Use SM-2 or simpler ELO for difficulty calibration.

## Learning State Storage

```
~/.reskill/
  state.json          # streak, XP, level, session stats
  progress.db         # SQLite: per-concept mastery, SM-2 intervals
  project_cache/      # per-project question caches
    <project_hash>/
      detected_stack.json
      asked_questions.json
      concept_history.json
```

## The `/learn` Command

After Claude finishes responding, the developer can type `/learn` to go deeper:

```
> /learn

  You answered: "2) Debugging clarity" -- Correct!

  Why specific exceptions matter:

  Bare `except:` catches EVERYTHING, including:
  - SystemExit (breaks Ctrl+C)
  - KeyboardInterrupt (breaks Ctrl+C)
  - GeneratorExit (breaks generators)

  In this code, we catch jwt.ExpiredSignatureError separately
  from jwt.InvalidTokenError because they need different
  HTTP status codes and error messages.

  Related concepts you might want to explore:
  - Exception hierarchy in Python (BaseException vs Exception)
  - Custom exception classes
  - Context managers for error handling

  Would you like to explore any of these? (type the topic or press Enter to continue)
```

## Target User

The vibe coder who:
- Uses Claude Code / Cursor / Copilot daily
- Accepts most AI suggestions without deeply understanding them
- Knows they SHOULD understand their code but doesn't have time to study
- Feels anxiety about becoming dependent on AI
- Wants to grow as a developer without adding study time to their day

## What This Is NOT

- Not a quiz app that interrupts your work
- Not a learning platform you have to visit separately
- Not a replacement for real study/courses
- Not competitive (no leaderboards, no judgment)
- Not mandatory (skip any question, always optional)

## What This IS

- A learning layer that lives inside your existing AI coding workflow
- Micro-questions generated from what the AI is actively doing
- Zero additional time investment (uses streaming time that was already "wasted")
- Context-aware (questions match your project, your stack, your skill gaps)
- Progressive (tracks what you know, adapts difficulty, builds over time)

## Research Still Needed

- [ ] Exact Claude Code streaming architecture (how to intercept/proxy the token stream)
- [ ] Keyboard input handling during streaming (Ink's concurrent input model)
- [ ] Latency benchmarks for question generation (Haiku vs template matching)
- [ ] Vibe coding prevalence data and skill atrophy research
- [ ] How Claude Code's permission prompt (y/n) coexists with streaming
- [ ] Whether MCP or hooks can be used instead of a proxy
- [ ] Privacy implications of reading the token stream

## Next Steps

1. Prototype the parallel question generator (template-based first)
2. Build the streaming interceptor / proxy
3. Test the 1/2/3/4 keypress UX during streaming
4. Implement project-context detection (already built in detect.py)
5. Add learning state persistence (SQLite + JSON)
6. Build the `/learn` deep-dive command
7. Package and distribute
