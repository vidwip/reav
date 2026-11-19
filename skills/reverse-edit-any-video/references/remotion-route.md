# Remotion route (effects and animated text)

ffmpeg (render.py) does the heavy, quality-critical work: decode, HDR tonemap, LUT grade in float,
reframe, exact frame trims. Remotion does what needs a browser: shakes, whips, punches, animated text,
rounded boxes, emoji, custom React effects. Remotion can't apply `.cube` LUTs and is slow on raw 4K,
so **never feed it raw footage**. Feed it render.py's graded segments.

Setup is automatic. `setup.sh` caches the npm packages and headless Chrome in `~/.cache/reav/remotion`,
and `new_job.py --remotion` copies `templates/remotion` into `<job>/remotion` with `node_modules`
cloned from that cache.

## A) Text-only layer (most common)

Footage stays 100% render.py. Only the animated text comes from Remotion:
```bash
python3 "$S/render.py" edit-plan.json --export-segments remotion/public     # writes plan.json + fonts (and segments)
cd remotion
npx remotion still TextLayer out/t.png --frame=12                          # check one frame
npx remotion render TextLayer out/text.mov --codec=prores --prores-profile=4444 --pixel-format=yuva444p10le
```
In edit-plan.json: move the animated items out of `texts`, add
`"overlays": [{"src": "remotion/out/text.mov", "from": 0}]`, then render.py as usual.

## B) Full Reel with effects

```bash
python3 "$S/render.py" edit-plan.json --export-segments remotion/public    # graded, reframed segments with xfade handles
cd remotion
npx remotion studio                                    # optional: scrub it
npx remotion render Reel out/reel.mp4 --crf=12 --muted
cd .. && ffmpeg -i remotion/out/reel.mp4 -i ref/audio.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k \
   -ar 48000 -shortest -movflags +faststart out/final.mp4
```
Segment `fx` arrays and `transition_in` (flash, dip, fade_in, xfade with effect fade, slideleft, slideright,
slideup, slidedown, zoomin, whip) are drawn by `src/Reel.tsx`. Texts are drawn by `src/Texts.tsx`. Extend
those components for custom effects. The remotion-* skills (installed by setup.sh) cover the Remotion API.

Edits to edit-plan.json need a fresh `--export-segments` (it rewrites `public/plan.json`). If only
texts or fx changed, edit `remotion/public/plan.json` directly to skip the re-export.

## Rules

- One render at a time. Parallel `npx remotion still/render` corrupts the bundle cache ("Pack content
  hash mismatch"). For many frames, use one `npx remotion render Reel out/frames --sequence --frames=0-60 --scale=0.4`.
- Fonts come from `plan.fonts` → `public/fonts/`, loaded as FontFace named by their key. Use that key as `font` in texts.
- If Chrome hangs at launch ("Waiting for root component", `CVDisplayLinkCreateWithCGDisplay`): kill stray
  `chrome-headless-shell` processes, retry once, then fall back to render.py (+ PNG overlays made with ffmpeg).
- Keep `fps`, `width` and `height` from the plan. Remotion reads them from `public/plan.json`.
