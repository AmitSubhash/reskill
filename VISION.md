# reSkill

**Turn AI thinking time into developer growth.**

## The Insight

Every time Claude Code thinks, the developer waits. 5 seconds. 30 seconds. Sometimes two minutes. Multiply by dozens of times per session, every day. That's hours of dead time per week.

What if that time made you better?

## What reSkill Does

reSkill detects your project's tech stack and serves context-aware micro-learning content during Claude Code's working time. A Python FastAPI developer sees Python and HTTP quizzes. A React developer sees JavaScript and React patterns. It adapts to what you're building.

## Five Content Formats

### 1. Interactive Quiz (during tool execution, 30-60s)
```
  ╭──────────────────────────────────────────────────╮
  │ Python Quiz                           3/5 today  │
  ├──────────────────────────────────────────────────┤
  │                                                   │
  │  x = [1, 2, 3]                                    │
  │  y = x                                            │
  │  y.append(4)                                      │
  │  print(len(x))                                    │
  │                                                   │
  │  What does this code output?                      │
  │                                                   │
  │    a) 3    b) 4    c) TypeError    d) None        │
  │                                                   │
  │  Press a/b/c/d     15s remaining        +10 XP   │
  ╰──────────────────────────────────────────────────╯
```

### 2. TIL Card (during thinking, 5-15s)
A surprising fact you didn't know. No interaction needed. Just read.

### 3. Pattern Comparison (during reads/edits, 10-20s)
Bad pattern vs good pattern, side by side. Learn through contrast.

### 4. Just-in-Time Docs (during thinking, 10-20s)
The exact API documentation you need for what you're building.

### 5. Code Reflection (during longer waits, 20-40s)
Your own code, with a prompt: "What would you improve here?"

## How It Works

reSkill uses Claude Code's hook system:

1. **SessionStart**: Detects your tech stack from project files. Loads relevant questions. Writes context-aware tips to the spinner.

2. **PreToolUse**: When Claude calls a tool (Bash, Read, Edit), reSkill shows learning content on the alternate screen buffer. The developer answers or reads.

3. **PostToolUse**: Content disappears. Claude's output renders normally. Zero disruption.

4. **spinnerTipsOverride**: During pure thinking time (no hook available), passive learning tips appear next to the spinner.

## Gamification

Learning sticks when it feels rewarding, not like homework.

- **Streaks**: Consecutive days of engagement. "Day 12 streak!" with freeze tokens so one missed day doesn't reset everything.
- **XP + Combos**: Points per correct answer with combo multipliers (up to 5x for consecutive correct answers).
- **Spaced Repetition**: Questions you got wrong come back. SM-2 algorithm adapted for session-based intervals.
- **Kyu Ranking**: 8 kyu (Novice) to 1 dan (Grandmaster). Exponential scoring curve.
- **Session Summary**: "You answered 7/10 correctly. +180 XP. Python mastery: 73% -> 76%."
- **Contribution Heatmap**: GitHub-style green squares showing daily quiz engagement.

## Content Sources

**Day 1 (static, ship immediately):**
- Ebazhanov/linkedin-skill-assessments-quizzes (28.7k stars, 80+ tech topics)
- QuizAPI.io (REST API, 60 req/min free tier)

**Week 1 (dependency-aware):**
- Map specific libraries to curated question sets
- e.g., `sqlalchemy` in deps -> SQL + ORM questions

**Month 1 (LLM-generated):**
- Generate questions about the developer's actual codebase
- "What does this function return when called with None?"
- Pre-generate at session start to avoid latency

## Design Principles

1. **Never interrupt.** Content appears only during waiting time and vanishes when Claude responds.
2. **Always relevant.** Questions match the project's tech stack, not random trivia.
3. **Progressive disclosure.** Question -> Answer -> Explanation (only if you want it).
4. **Desirable difficulty.** Hard enough to make you think, easy enough to not frustrate.
5. **No homework feeling.** The frame is "sharpening your blade while the smith works," not "pop quiz."

## Why Not Games?

claude-arcade puts Pong and Bird Hunt during thinking time. It has 2 HN upvotes and ~0 GitHub stars. Games are a novelty. After the first week, nobody plays Pong in their terminal.

Learning compounds. Every quiz question makes you a slightly better developer. Over weeks and months, that adds up. The developer who uses reSkill for a year has answered thousands of questions, reinforced hundreds of concepts, and built deep fluency in their stack -- all without spending a single minute they wouldn't have spent waiting anyway.

## The Market

- No "learn while AI thinks" product exists today
- AI coding agents are used by millions of developers daily
- Average developer waits 30-120 minutes per day for AI responses
- Duolingo proved that micro-learning in idle moments works at massive scale

## Try It

```bash
pip install reskill
reskill setup    # Installs Claude Code hooks
# Start coding. reSkill activates automatically.
```
