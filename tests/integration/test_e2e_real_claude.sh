#!/bin/bash
# Full end-to-end: spawn tmux, start claude in pane 0 + quiz-panel in pane 1,
# flip thinking flag, send prompt, verify no scrambling.
set -e
SESSION="reskill-e2e-$$"
mkdir -p ~/.reskill/state
rm -f ~/.reskill/state/thinking ~/.reskill/state/last_active

tmux new-session -d -s "$SESSION" -x 200 -y 50 -c /Users/amit/Projects/reskill
sleep 0.3
tmux send-keys -t "$SESSION:0.0" "claude" C-m
sleep 0.5
tmux split-window -h -l 54 -t "$SESSION:0.0" "reskill quiz-panel"
sleep 4

# User types prompt (this triggers UserPromptSubmit, which sets thinking)
touch ~/.reskill/state/thinking
tmux select-pane -t "$SESSION:0.0"
tmux send-keys -t "$SESSION:0.0" "explain what a sigterm does in one short sentence"
tmux send-keys -t "$SESSION:0.0" C-m

# Claude is thinking; quiz pane should show a question
sleep 4
tmux capture-pane -t "$SESSION:0.0" -e -p > /tmp/e2e_claude.log
tmux capture-pane -t "$SESSION:0.1" -e -p > /tmp/e2e_quiz.log

# Wait for Claude response to complete
sleep 5
rm -f ~/.reskill/state/thinking  # simulate Stop hook

sleep 1
tmux capture-pane -t "$SESSION:0.0" -e -p > /tmp/e2e_claude_done.log
tmux capture-pane -t "$SESSION:0.1" -e -p > /tmp/e2e_quiz_done.log

tmux kill-session -t "$SESSION" 2>/dev/null || true

python3 << 'PYEOF'
import re
def strip_ansi(s): return re.sub(r'\x1b\[[0-9;]*[mKH]|\x1b\]8;[^\x07]*\x07', '', s)

print("=== CLAUDE PANE MID-THINK ===")
c = strip_ansi(open('/tmp/e2e_claude.log').read())
for i, l in enumerate(c.split('\n')[-18:]):
    print(f"  {l[:100]}")

print("\n=== QUIZ PANE MID-THINK ===")
q = strip_ansi(open('/tmp/e2e_quiz.log').read())
for i, l in enumerate(q.split('\n')):
    print(f"  {l[:60]}")

print("\n=== QUIZ PANE AFTER CLAUDE DONE (should go idle or keep quiz) ===")
q2 = strip_ansi(open('/tmp/e2e_quiz_done.log').read())
for l in q2.split('\n')[:15]:
    print(f"  {l[:60]}")

# Assertion: no quiz borders in claude pane
print("\n=== ASSERTIONS ===")
if "think about this" in c:
    print("  FAIL: quiz box leaked into Claude pane")
else:
    print("  PASS: no quiz leak into Claude pane")

if "think about this" in q or "reskill" in q:
    print("  PASS: quiz pane rendered quiz or reskill UI")
else:
    print("  FAIL: quiz pane empty")

# Check Claude pane doesn't have scrambled borders
bad_borders = c.count('┃') + c.count('│')
if bad_borders > 10:
    print(f"  FAIL: Claude pane has {bad_borders} border chars (scrambled)")
else:
    print(f"  PASS: Claude pane has {bad_borders} border chars (clean)")
PYEOF
