# reSkill -- Expanded Product Directions

Beyond quizzes. Twelve ways to make AI thinking time valuable.

## Tier 1: Ship First (proven formats, easy to build)

### 1. Interactive Quiz
The core format. "What does this code output?" with 4 choices.
Already built. Keyboard input, answer reveal, XP, combos.

### 2. TIL Card (Today I Learned)
Passive. One surprising fact with an example. No interaction needed.
Perfect for short thinks (<5s). Already built.

### 3. Pattern Comparison
"Avoid this / Prefer this" side-by-side. Teaches through contrast.
Already built. Context-aware to detected stack.

### 4. Just-in-Time Docs
Show relevant API docs for the library you're using RIGHT NOW.
Already built. Could be enhanced with real doc fetching.

## Tier 2: High Impact (worth building next)

### 5. Code Reflection
Show the developer their OWN code with a prompt:
"What would you improve here?"
Then when Claude finishes, they can compare their mental answer with Claude's actual change. Makes the developer a critical reviewer of AI output, not a passive accepter.

### 6. Spot the Bug (in real open source)
Show a real bug from a popular open source project.
"This was a real bug in Django 4.2. Can you spot it?"
After answering, link to the actual commit that fixed it.
Source: PVS-Studio's bug database, spotthebug.dev

### 7. Type Puzzle
Show a TypeScript/Python type annotation and ask what it means.
"What does this type accept?"
```typescript
type DeepPartial<T> = { [P in keyof T]?: DeepPartial<T[P]> }
```
Source: type-challenges/type-challenges (47k stars)

### 8. Mistake Journal
Track patterns in the developer's mistakes (from Claude's fixes):
- Claude often fixes their off-by-one errors -> quiz on boundaries
- Claude often adds null checks -> quiz on null handling
- Claude often converts loops to comprehensions -> quiz on pythonic patterns

This is the most powerful format because it's personalized to the developer's actual weaknesses.

## Tier 3: Ambitious (high effort, high differentiation)

### 9. Concept Map Builder
Progressively build a visual knowledge graph:
"You learned about generators. Did you know they connect to async/await? Both use yield under the hood."
Over time, the developer builds a mental model of how concepts connect.

### 10. Explain It Back
Instead of multiple choice, ask the developer to EXPLAIN a concept in their head.
"Think about what 'closure' means in Python. Then press Enter to see the explanation."
Research shows self-explanation is one of the most effective learning techniques.

### 11. Architecture Decision Records
"You're building a FastAPI app. Did you know about the Repository pattern?"
Show a 30-second overview of a relevant architectural pattern based on the current task.
Not a quiz -- a design insight.

### 12. Pair Programming Mode
While Claude is thinking about a task, show the developer a RELATED but different task to think about.
"While Claude optimizes the query, think about: what index would speed this up?"
When Claude responds, the developer has already been thinking about the problem space.

## Content Adaptation Strategy

### By thinking duration:
| Duration | Format |
|----------|--------|
| < 3s | Spinner tip (passive text) |
| 3-10s | TIL card (read only) |
| 10-30s | Pattern card or doc card |
| 30-60s | Interactive quiz |
| 60s+ | Spot the bug or code reflection |

### By session context:
- **Early in session**: More new content, introductory difficulty
- **Mid-session**: Mix of new and review (spaced repetition kicks in)
- **Late in session**: More review, easier questions (cognitive fatigue)
- **After an error**: Show content related to the error type

### By developer skill level:
- **New to stack**: Focus on basics, syntax, common patterns
- **Intermediate**: Design patterns, performance, edge cases
- **Advanced**: System design, tradeoffs, "why not" questions

## The Flywheel

```
Developer uses Claude Code
  -> reSkill shows relevant quiz during thinking time
  -> Developer answers correctly (or learns from explanation)
  -> Knowledge is spaced-repetition tracked
  -> Next quiz is harder/different (adaptation)
  -> Developer gets better at their stack
  -> Developer uses Claude Code more confidently
  -> More thinking time = more learning
```

The flywheel accelerates: the more you code with AI, the more you learn. The more you learn, the better you prompt the AI. The better you prompt, the better the output.

## What Makes This Different From Every Other Learning Tool

1. **Zero marginal time cost.** You're already waiting. This doesn't take time from your day.
2. **Context is built in.** You're working on FastAPI right now, so you learn FastAPI right now.
3. **Embedded in workflow.** No separate app, no browser tab, no "I should study but..."
4. **Spaced repetition without scheduling.** The AI's thinking IS the schedule.
5. **Compounds with AI usage.** More AI = more learning. Not competing with AI, amplifying it.
