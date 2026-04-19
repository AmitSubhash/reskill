# Editorial banner, reSkill

Rendered from the Remotion project at `~/Projects/reskill-marketing/`,
composition `EditorialBanner` (1600 x 500) and `EditorialBannerSocial`
(1200 x 630). See `src/editorial/STORYBOARD.md` in the marketing repo
for scene-by-scene direction.

## Files

| File                   | Dimensions  | Size  | Use                          |
|------------------------|-------------|-------|------------------------------|
| `banner.gif`           | 1200 x 375  | 2.3 MB| README hero (auto-loops)     |
| `banner.mp4`           | 1600 x 500  | 1.0 MB| high-fidelity fallback       |
| `banner-social.mp4`    | 1200 x 630  | 1.0 MB| paid social reuse            |
| `social-preview.png`   | 1200 x 630  |  87 KB| OG `og:image` on the landing |

## Re-render

```bash
cd ~/Projects/reskill-marketing
npx remotion render EditorialBanner out/editorial-banner.mp4
npx remotion render EditorialBannerSocial out/editorial-banner-social.mp4
npx remotion still EditorialBannerSocial out/editorial-banner-social.png --frame=305

# mp4 -> looping gif (palette-optimized, ~2.3 MB at 18 fps, 1200px wide)
ffmpeg -y -i out/editorial-banner.mp4 \
  -vf "fps=18,scale=1200:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  -loop 0 out/editorial-banner.gif
```

Then copy the four artifacts back into `reskill/marketing/banner/`.
