#!/bin/bash
# Integration test: `reskill claude` launches a tmux split, both panes
# render cleanly, and the thinking-flag IPC drives the quiz pane.
#
# This test intentionally doesn't install hooks into ~/.claude/settings.json.
# It toggles the flag file directly, which is what the hooks would do.
set -e

FAIL=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

SESSION="reskill-integ-$$"
mkdir -p ~/.reskill/state

# Start tmux manually -- simulate what tmux_launcher does in the
# inside-tmux path.
tmux new-session -d -s "$SESSION" -x 180 -y 45
tmux send-keys -t "$SESSION:0.0" "claude" C-m
sleep 0.5
tmux split-window -h -l 52 -t "$SESSION:0.0" "reskill quiz-panel"
sleep 3

# With no thinking flag, quiz pane should show "waiting for claude".
rm -f ~/.reskill/state/thinking
sleep 1.5
IDLE=$(tmux capture-pane -t "$SESSION:0.1" -p)
if echo "$IDLE" | grep -q "waiting for claude"; then
  pass "quiz pane shows idle card when no thinking flag"
else
  fail "idle card not visible; got:"; echo "$IDLE" | head -10
fi

# Now signal thinking; quiz pane should render a question.
touch ~/.reskill/state/thinking
sleep 2
Q=$(tmux capture-pane -t "$SESSION:0.1" -p)
if echo "$Q" | grep -q "think about this"; then
  pass "quiz pane renders question when thinking flag set"
else
  fail "no quiz visible; got:"; echo "$Q" | head -15
fi

# The main pane (Claude) should still look normal -- no border artifacts.
MAIN=$(tmux capture-pane -t "$SESSION:0.0" -p)
if echo "$MAIN" | grep -q "Claude Code"; then
  pass "claude pane still shows normal UI"
else
  fail "claude pane corrupted; got:"; echo "$MAIN" | head -10
fi

# No scrambled `│` borders bleeding into claude pane.
if echo "$MAIN" | grep -E "think about this" >/dev/null; then
  fail "quiz box leaked into claude pane"
else
  pass "quiz pane is isolated from claude pane"
fi

# Clean up
rm -f ~/.reskill/state/thinking
tmux kill-session -t "$SESSION" 2>/dev/null || true

if [ "$FAIL" -eq 0 ]; then
  echo
  echo "ALL GREEN"
  exit 0
else
  echo
  echo "$FAIL assertion(s) failed"
  exit 1
fi
