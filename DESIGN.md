# reSkill Design Principles

## The Five Rules

### 1. Complete-in-place
Every micro-lesson delivers full value where it appears. No "click here to learn more." The terminal output IS the classroom. A developer should gain knowledge by reading what's already on screen.

### 2. One concept, one moment
Never bundle. One fact, one question, one insight per appearance. Duolingo's most important lesson: a 2-minute lesson beats a 10-minute one. For reSkill, a 15-second insight beats a 60-second tutorial.

### 3. Progressive depth, not progressive gates
Show the minimum by default (1-2 lines). Let the user dig deeper voluntarily. Never force traversal of all layers. The question is the floor, not the ceiling.

### 4. Surprise over instruction
Lead with what violates expectations. "You'd think X, but Y" is more memorable than "Here's how X works." The SUCCESs framework: Simple, Unexpected, Concrete, Credentialed, Emotional, Story.

### 5. Safe by default
No grades, no failure tracking. Frame everything as discovery. Wrong answers are "interesting," not "incorrect." Make skipping trivially easy (one keypress or just ignore it). Target 80% success rate.

## Language Guide

### Never say
quiz, test, exam, score, grade, wrong, fail, incorrect, lesson, homework

### Prefer
"quick question", "think about this", "did you know", "interesting", "actually",
"most people don't know", "turns out", "here's the trick"

### Encouragement
Factual ("5-day streak") not evaluative ("Great job!!"). The content IS the reward, not praise attached to it.

### Tone
Knowledgeable peer, not teacher. "Here's something neat" not "Today's lesson is..." Think helpful senior engineer at lunch, not professor at podium.

## The Aha Template

For passive content (TIL cards, spinner tips):
```
Did you know?  [Surprising claim that violates an assumption]
               [Concrete code example: 1-2 lines]
               [Why this matters in practice]
```

## The Discovery Template

For interactive content (replaces "quiz"):
```
Think about this:  [Question framed as genuine curiosity]

  [Press a/b/c/d]

  Interesting -- [Answer + brief why]
  [Optional: "Most developers guess X" -- normalizes not knowing]
```

## Content Adaptation

### By thinking duration
| Duration | Format |
|----------|--------|
| < 3s | Spinner tip (1 line, passive) |
| 3-10s | TIL card (3-5 lines, read only) |
| 10-30s | Pattern card or doc snippet |
| 30-60s | Discovery question (interactive) |
| 60s+ | Spot the bug or code reflection |

### By developer context
| Context | Content strategy |
|---------|-----------------|
| Early in session | More new content, introductory difficulty |
| Mid-session | Mix of new and review (spaced repetition) |
| Late in session | More review, easier (cognitive fatigue) |
| After an error | Content related to the error type |
| First time using a library | "Did you know?" about that library |

### The 80% Rule
If a developer gets fewer than 80% right, the questions are too hard.
If they get more than 95% right, the questions are too easy.
Adapt difficulty per concept using SM-2 ease factor.

## What Makes This Different

The ideas that make reSkill transformative (not just useful) are the ones that connect to the developer's own code:

1. **Mistake Journal**: Track what Claude fixes in your code. Quiz you on YOUR weaknesses.
2. **Code Reflection**: Show YOUR code with a prompt to think critically.
3. **Refactoring Preview**: Predict what Claude will change before it does.
4. **Git Detective**: Show YOUR recent diffs and ask what was being fixed.

Generic quizzes are good. Questions about YOUR code, YOUR mistakes, YOUR git history -- those are what turns reSkill from a learning tool into a growth engine.
