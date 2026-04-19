# Launch checklist

Post-demo, pre-announcement. Work top-to-bottom the day you go live.

## Before posting anywhere

- [ ] Pull latest: `git pull && pip install -e . && reskill doctor`
      — every check should be PASS (one WARN is fine if it's pacing
      from your own testing)
- [ ] Verify the videos still render: `cd ~/Projects/reskill-marketing
      && npm run build` — both `out/reskill-launch.mp4` and
      `out/reskill-tiktok.mp4` should regenerate
- [ ] Do a fresh `reskill claude` run against a real prompt
      ("explain the GIL in one paragraph") — confirm quiz pane
      actually fires a question within 5 seconds
- [ ] Confirm `reskill uninstall` leaves your existing hooks intact
      (inspect `~/.claude/settings.json` diff before/after)

## GitHub polish (2 min each)

- [ ] Add repo description on github.com: "Quizzes during Claude
      Code's thinking time"
- [ ] Add topics: `claude-code`, `python`, `developer-tools`,
      `micro-learning`, `spaced-repetition`, `tmux`, `terminal`
- [ ] Pin the README hero GIF as the social preview image
      (Settings → Social preview — use the first frame or generate
      a 1280x640 crop from `reskill-hero.gif`)
- [ ] Enable Discussions for community feedback (repo Settings →
      Features → Discussions)

## Post in this order (spaced)

Start with HN because it decides if the others even matter:

### 1. Hacker News (best: Tuesday 9am ET, or Sunday afternoon)

- Title: `Show HN: reSkill – quizzes during Claude Code's thinking time`
- Body: see `marketing/LAUNCH.md` HN section
- Upload the MP4 to a host first (Vimeo, YouTube, or just the
  GitHub raw link to `marketing/videos/reskill-launch.mp4`)
- Don't ask anyone to upvote. Reply to every question for the
  first 2 hours.

### 2. Twitter thread (immediately after HN post goes live)

- Copy the 5-tweet thread from `marketing/LAUNCH.md`
- Tweet 1 has the video attached
- Quote-post your own HN submission from tweet 5

### 3. Reddit (r/ClaudeAI then r/Python, 4+ hours apart)

- Use the body copy from `marketing/LAUNCH.md`
- Different title per subreddit (don't cross-post verbatim)

### 4. LinkedIn (next morning)

- Post from your personal profile
- Tag relevant folks in comments (not in the post body — looks spammy)

### 5. Product Hunt (schedule for the following Tuesday)

- Schedule 12:01am PT
- The founder-comment is already drafted in LAUNCH.md

## Things to track

- GitHub stars in the first 24h (indicator of HN traction)
- `pip install` count from your repo traffic (Insights → Traffic)
- Hook log `/tmp/reskill-hook.log` if people email you with broken
  installs
- Open issues — respond within 4 hours for the first 72h; community
  perception is shaped in that window

## Things to NOT do

- Don't promise features that aren't built (LLM-gen questions are
  LATER, don't claim now)
- Don't reply defensively to criticism; say "good point, tracking"
  and open an issue
- Don't post the video to reels/shorts until at least the first
  wave of organic traffic has settled (days 1-3 belong to the
  long-form surfaces)

## If it blows up

- Tag a v0.1.0 release on GitHub so people can pin
- Consider publishing to PyPI so `pip install reskill` works
  without the git URL (nice-to-have; not blocking launch)
- Open a GitHub Project board and move every bug report / feature
  request into it publicly
