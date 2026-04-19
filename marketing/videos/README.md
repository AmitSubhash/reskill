# reSkill launch videos

Rendered from the separate Remotion project at
`~/Projects/reskill-marketing/` (not vendored here — node_modules
would bloat the repo).

- `reskill-launch.mp4` — 1920x1080 landscape, 30s, ~2.2MB
- `reskill-tiktok.mp4` — 1080x1920 vertical for reels/shorts, 30s, ~2.3MB

## Re-render

```bash
cd ~/Projects/reskill-marketing
npm run dev                                    # interactive studio
# or just render:
npx remotion render src/index.ts MainComp out/reskill-launch.mp4
npx remotion render src/index.ts TikTokComp out/reskill-tiktok.mp4
```

## Swap in real frames

Captures live at `~/Projects/reskill-marketing/public/terminal/`.
Re-run `marketing/capture.sh` inside the Remotion project to refresh.

## Timeline (both comps, same 30s structure)

- 0-5s: hook ("Claude thinks. You wait.")
- 5-15s: terminal split + incoming-question animation
- 15-25s: answer, ✓ reveal, streak tick
- 25-30s: tagline + `pip install reskill` CTA
