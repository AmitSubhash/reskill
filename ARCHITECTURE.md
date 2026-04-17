# reSkill Architecture

## Core Concept

Context-aware micro-learning during Claude Code's working time.
Duolingo for developers, embedded in the AI coding agent workflow.

## Integration Surfaces

Claude Code exposes 4 surfaces for third-party content:

### 1. spinnerTipsOverride (passive learning, during thinking)

```json
// ~/.claude/settings.json
{
  "spinnerTipsOverride": {
    "excludeDefault": true,
    "tips": [
      "Python: list.copy() creates a shallow copy, not deep",
      "HTTP 201 means Created. Use it for POST endpoints.",
      "Git: rebase rewrites history. Never rebase shared branches."
    ]
  }
}
```

- Fires during ALL waiting (thinking + tool execution)
- Static text only, no interactivity
- Cycles randomly through the array
- Best for: micro-facts, "did you know?" tips

### 2. Hooks: PreToolUse / PostToolUse (interactive, during tool execution)

```json
// ~/.claude/settings.json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "reskill start"}]
    }],
    "PostToolUse": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "reskill stop"}]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "reskill stop"}]
    }]
  }
}
```

- Fires at tool execution boundaries (Bash, Read, Edit, etc.)
- Can fork an interactive process (quiz UI)
- Uses alternate screen buffer to preserve Claude's output
- Best for: interactive quizzes with keyboard input

### 3. statusLine (persistent, always visible)

```json
{
  "statusLine": {
    "type": "command",
    "command": "reskill statusline"
  }
}
```

- Persistent bottom bar, refreshes on each assistant message
- Receives JSON with model, context %, rate limits
- Best for: streak counter, XP display, daily progress

### 4. SessionStart hook (initialization)

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{"type": "command", "command": "reskill init"}]
    }]
  }
}
```

- Detect project tech stack
- Load relevant question bank
- Pre-generate LLM questions about the codebase
- Update spinnerTipsOverride with context-aware tips

## Content Pipeline

```
Project Files ──> detect.py ──> Quiz Topics ──> Question Bank ──> Quiz Selection
                                                                      |
pyproject.toml    "python,      Ebazhanov      Filter by topic,  ──> Display
package.json       fastapi,     dataset        SR scheduling
Cargo.toml         http"        (80+ topics)
```

### Tier 1: Static question bank (ship day 1)
- Parse Ebazhanov/linkedin-skill-assessments-quizzes (28.7k stars)
- 80+ tech topics, consistent MCQ markdown format
- Filter by detected project stack

### Tier 2: Dependency-aware questions
- Map specific libraries to curated question sets
- e.g., `sqlalchemy` in deps -> SQL + ORM questions

### Tier 3: LLM-generated codebase questions
- At SessionStart, generate 5-10 questions about the actual code
- "What does this function return when called with None?"
- Pre-generate to avoid latency during quiz display

## Gamification

### State: ~/.reskill/
```
~/.reskill/
  state.json          # streak, XP, level, daily progress
  progress.db         # SQLite: per-concept SM-2 intervals
  achievements.json   # unlocked badges
```

### Mechanics (priority order)
1. Streaks (7-day = 3.6x retention) with freeze tokens
2. XP + combo multiplier (max 5x)
3. Daily goal (5 correct answers)
4. SM-2 spaced repetition per concept
5. Kyu ranking (8 kyu beginner -> 1 dan master)
6. Session summary with contribution heatmap

## Question Formats

| Format | Time | When to show |
|--------|------|-------------|
| True/False | 10-15s | Short tool calls |
| Multiple Choice | 20-30s | Medium tool calls |
| "What's the output?" | 30-45s | Longer tool calls |
| "Spot the bug" | 45-60s | Bash commands, builds |

## Interruption Handling

When PostToolUse fires mid-quiz:
1. Show correct answer briefly (1s)
2. Queue unanswered question for next pause
3. Record as "skipped" (SR quality = 1)
