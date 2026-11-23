# Color correction: match the reference's look

## Measure the reference

`color.py measure ref/reference.mp4 --cuts analysis/cuts.json --out analysis/ref_color.json` gives
per shot and overall:

- **Tone**: luma percentiles p2 (black point), p25, p50 (exposure), p75, p98 (highlight ceiling), 0–255.
  p2 > 22 = lifted, matte blacks. p98 < 225 = soft, film-like highlights. p98 − p2 = contrast.
- **Saturation**: mean HSV saturation (content-dependent: a meadow is more saturated than snow).
- **Greys**: chroma offset of near-neutral pixels in shadows, mids and highlights. This is the grade's
  white balance and split-tone (teal shadows, warm highlights…), independent of content.
- **Palette warmth/tint**: mean colour. Describes *content* (lots of sky = cool). Don't grade toward it.

## Build the look

```bash
python3 "$S/color.py" match --ref analysis/ref_color.json \
  --src "CLIP_A@2-6" --src "CLIP_B@0-4" ... --out grading/look.cube --strength 0.85
```
Feed several representative selects (different scenes) so the LUT is a *look*, not a fix for one clip.
It fits:
1. **Tone curve**: source percentiles → reference percentiles (monotone, so no banding or inversions).
2. **Saturation**: uniform chroma scale with gamut protection, moved part of the way (`--sat-damp 0.6`)
   because saturation follows content. Push with `--sat-mult 1.1` if the reference is clearly more vivid.
3. **Grey balance**: shadows, mids and highlights offsets so the source's greys get the reference's tint
   (`--balance 0..1`).

`--strength` blends the LUT with identity. 0.8–0.9 usually reads as "same look" without overcooking.

Per-shot looks: when one reference shot is clearly graded differently (warm sunset slot, night slot),
build a second LUT with `--ref-shots N` from the select that fills that slot, and set it as that
segment's `lut`.

## Verify (numbers, then eyes)

```bash
python3 "$S/color.py" check --ref analysis/ref_color.json --src "CLIP_A@2-6" --lut grading/look.cube
```
Tone should be CLOSE (p2 ±8, p50 ±10, p98 ±12) and greys CLOSE. Saturation may "differ" when the
content differs. Judge it by eye. Then render stills and compare next to the reference shot:
```bash
python3 "$S/render.py" edit-plan.json --still 150 --out review/f150.jpg
```
Look for: skin tones (never green or grey), skies (blue, not cyan or purple unless the reference does
that), whites (clouds and snow neutral unless the reference tints them), crushed shadow detail, banding.

## Problems and fixes

| Symptom | Cause | Fix |
|---|---|---|
| Neutral clouds turn green or olive | reference full of green content, statistical colour transfer | color.py already matches greys only. Lower `--balance`, check the source isn't already tinted |
| Electric cyan skies | too much saturation on blue | `--sat-mult 0.9` or per-segment `filters: "hue=s=0.9"` |
| Dark teal outline on ridges | saturation-gated grading on 4:2:0 edges | grade with the LUT only (no gated filters), or soften with a mask |
| Washed out, grey iPhone clip | HDR (HLG / Dolby Vision) shown without tonemap | render.py tonemaps when `hdr` is true. Make sure the clip's metadata says HLG/PQ (log_footage shows HDR) |
| Banding in skies | 8-bit grading | render.py grades in float RGB and dithers once. Don't pre-grade to 8-bit intermediates |
| One clip much brighter than the rest | different exposure | per-segment `lut` from `color.py match --src that_clip`, or `filters: "eq=brightness=-0.03"` |

## Texture

Grain: `filters: "noise=alls=5:allf=t"` (luma-ish film grain; 3–8). Sharpening: `"unsharp=5:5:0.4:5:5:0"`.
Softness or halation: Remotion `blur` fx, or a blurred highlight overlay. Vignette: Remotion `vignette` fx.
