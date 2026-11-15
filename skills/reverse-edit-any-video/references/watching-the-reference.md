# Watching the reference

Goal: by the end you can describe every frame-relevant decision of the edit in style.md. Measure with
scripts, confirm with your eyes.

## Tools, in order

| Tool | Gives you | Watch out for |
|---|---|---|
| `cuts.py` | Frame-exact shot list, shot lengths, pace curve, per-shot luma, saturation and motion, flash/fade flags, soft-transition suspects, `shots_sheet_*.jpg` | Misses dissolves and whips (listed as suspects). Can split one shot at a flash. Fix cuts.json by hand. |
| `beats.py` | BPM, beat grid, accents (the hits), energy changes (drops), how cuts sit on the music, lead or lag in frames | BPM may be ×2, ÷2 or ×2/3. Trust accent times over BPM. |
| `color.py measure` | Per-shot and overall tone, saturation, grey balance and a plain-language read | Content colours aren't grade colours. Read the greys. |
| `strip.py` | Frame-by-frame strips around cuts or any time | Use it for every transition and every text appearance |
| video-analyzer skill | Scene-by-scene description, transcript (whisper), key frames | Use a high rate for short videos ("at 4fps"). It describes, it doesn't measure. |

On macOS, video-analyzer's `extract-frames.sh` needs integer start/end times (`10 0 0 4x4 0 13`, not
`16.4`). setup.sh already patched its empty-array bug.

## What to extract, by style.md section

**Story & structure**: function of each shot (references/storytelling.md), hook length, where the
payoff lands, ending type (hold / black / loop / CTA).

**Pace**: from cuts.json `summary` (avg, median, min, max, pace curve) and beats.json `cut_sync`.
Say it as a rule: "hook 7.7 s, then one cut every ~3 beats, cuts 3 frames before the hit".

**Shot list**: for each shot, size (ECU / CU / MCU / MS / WS / EWS / aerial / POV / insert), subject,
camera move (static, pan L/R, tilt, push-in, pull-out, handheld, gimbal walk, drone orbit), subject
motion and direction, speed (real-time / slow-mo / ramp; slow-mo looks smooth with motion blur at 50–60 fps).

**Transitions**: for every cut, read its strip:
- *hard cut*: frame N old, frame N+1 new
- *flash*: 1–4 near-white frames (luma > 200 in per_frame), often with fade-out of the outgoing shot
- *dip*: frames go to black and come back
- *dissolve / xfade*: both images visible for several frames
- *whip pan*: heavy directional blur on both sides of the cut
- *zoom-through / punch*: scale jumps or rushes with blur
- *match cut*: shape or motion continues across the cut
- *J/L cut*: sound changes before or after the picture
Note the frame counts. render.py and the Remotion template take frames.

**Text**: for each text element, take the first and last frame it's visible (strip), font (see
text-and-fonts.md), size (cap height or line height in px at 1080 width), colour (hex from a frame),
box, stroke or shadow, position as fractions of width and height (centre of the block), alignment, and the
animation in and out with its frame count. Note casing and emoji. For captions: chunking (1 word / 2–3
words / full line) and the active-word highlight.

**Effects**: push-ins and pull-outs (scale at start and end), shake (frames, amplitude), speed ramps,
grain, vignette, blur fills, overlays and stickers, split screens, masks, freeze frames, colour flashes.

**Color**: copy the `overall_read` line and the tone numbers. Look at shots that differ from the
overall look (night shots, a warmer sunset shot). Check texture: grain, sharpening, halation, softness.

**Audio**: track (music only / voice / both), where the drop is, SFX on transitions (whooshes, hits,
risers), whether the music ducks under speech, and loudness (review.py prints LUFS).

## Measuring from a frame

```bash
ffmpeg -ss 2.5 -i ref/reference.mp4 -frames:v 1 analysis/f_2_5.png
```
Open it. For a 1080-wide reference, pixel positions map 1:1 to the 1080x1920 output. For other sizes,
scale by 1080 / width. For a landscape reference going to vertical, keep text size relative to frame
*width* and re-place text in the vertical frame's equivalent zone.

## Platform re-encodes

Instagram and TikTok downloads are often VP9 or H.264 at strange rates (56.45 fps) with duplicated
frames. The original edit was almost always 24, 25, 30 or 60. cuts.py snaps to the editing rate, and
a cut can be ±1 frame ambiguous after re-encoding. That's fine.
