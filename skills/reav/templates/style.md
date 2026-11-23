# Style: <reference name / URL>

> The edit DNA of the reference. Everything here is measured or observed, with timecodes.
> The new edit is built from this file, so write it so another editor could rebuild the
> reference's *feel* without ever seeing it. Delete the hints in `<...>` as you fill it in.

## 0. Snapshot

| | |
|---|---|
| Format | <9:16 / 16:9 / 1:1>, <W>x<H>, <fps> fps, <duration>s, <shots> shots |
| Genre / purpose | <travel montage / talking-head tip / product promo / vlog / meme / ...> |
| The feel in one line | <"slow dreamy hook, then fast punchy montage that lands on the drop"> |
| Soundtrack | <song / voiceover / both>, ~<BPM> BPM, energy shape <build → drop at 7.9s → ride out> |

## 1. Story & structure

<Beats with timecodes. What each beat DOES for the viewer, not just what it shows.>

| Beat | Time | Frames | What it does (function) | How (shots / text / sound) |
|---|---|---|---|---|
| Hook | 0.00–<x>s | 0–<n> | <stop the scroll: question / promise / pattern break> | <single long shot + text card> |
| Setup | | | <context: where/who/what's at stake> | |
| Build | | | <escalate: faster cuts, bigger vistas, rising music> | |
| Payoff | | | <the reward the hook promised; usually on the drop> | |
| Outro / loop | | | <end card / loop back into frame 1 / CTA> | |

- Hook promise: <what the first 1–2 s make the viewer want>
- Emotional arc: <e.g. curiosity → awe → calm>
- Loop: <does the last frame flow back into the first? how?>

## 2. Pace

- Shot length: average <x>s, median <x>s, shortest <x>s, longest <x>s (cuts.py)
- Pace curve (cuts per 5s): <0-5s: 0, 5-10s: 2, 10-14s: 4>, accelerating / steady / decelerating
- Music sync (beats.py): <67>% of cuts on a beat, <x>% on accents; cuts land <~3 frames before> the hit;
  typical shot = <2> beats; <the drop at 7.9s gets a hard cut + flash>
- Rhythm rule in words: <"one long hook shot, then cut every 2 beats, last shot holds 1 beat">
- Speed: <real-time / slow-mo 0.5x on the hook / speed ramps into cuts>

## 3. Shot list

<From analysis/cuts.json + shots sheet. Shot size: ECU / CU / MCU / MS / WS / EWS / aerial / POV / insert.>

| # | Frames (start–end) | Dur | Shot size | Subject & role in story | Camera / subject motion | Speed | Transition in | Text on screen |
|---|---|---|---|---|---|---|---|---|
| 1 | 0–230 | 7.67s | | | | | — | |

## 4. Transitions

| Where (frame) | Type | Length (frames) | Details / how to build |
|---|---|---|---|
| <230> | <hard cut on the beat / white flash / dip to black / whip pan / zoom-through / match cut / J-cut> | <4> | <render.py: transition_in flash, 4 frames> |

## 5. Text

<One block per distinct text style. Measure from frames: size as % of frame height, position as
fraction of width/height, colours as hex.>

| Text | Frames | Font (match) | Size | Colour / box / stroke / shadow | Position (x, y) | Animation in / out | Case |
|---|---|---|---|---|---|---|---|
| "<POV: you finally made it>" | 0–230 | <TikTok Sans Bold> | <46px @1080w> | <black on white box, pad 14> | <0.5, 0.315> | <none / pop / typewriter / word-by-word> | <as typed> |

- Caption system (if speech): <word-by-word / 2–3 word chunks / full lines; active-word highlight colour>
- Safe zone: <text kept inside the middle 70%: clear of IG/TikTok UI at top ~12% and bottom ~20%>
- Keep / rewrite: <keep verbatim (generic hook) / rewrite for the new footage in the same voice and length>

## 6. Effects

| Effect | Where | Settings | Build with |
|---|---|---|---|
| <slow push-in> | <shot 1> | <1.00→1.08 over the shot, ease in-out> | <render.py zoom/zoom_to> |
| <camera shake on the drop> | | <8 frames, decaying> | <Remotion fx shake> |
| <film grain / vignette / letterbox / blur-fill for landscape clips / speed ramp> | | | |

## 7. Color correction

<From analysis/ref_color.json (color.py measure). Numbers + plain words.>

- Overall read: <normal contrast, lifted blacks (p2=25), soft highlight ceiling (p98=222), very saturated, ...>
- Tone: black point p2 <25>, midtones p50 <93>, highlight ceiling p98 <222>
- Saturation: <0.52 mean (vivid: greens and blues pushed)>
- White balance / split-tone (greys): shadows <neutral>, mids <neutral>, highlights <cool/teal>
- Per-shot differences: <shot 6 warmer (+27), shots 5/7 cooler skies>
- Texture: <grain / sharpening / softness / halation / none>
- Plan: <one global look.cube from all shots, strength 0.85; extra per-shot trims for the night clips>

## 8. Audio

- Track: <reference song, kept as-is / user's music / voiceover + bed>
- Key moments: <accents at 1.09, 3.37, 4.50 ... ; drop at 7.94s ; ends with a hit at 13.63s>
- SFX: <whoosh on whips, riser before the drop, none>
- Mix: <music only, -14 LUFS / VO with music ducked -18 dB>

## 9. Recreation rules

**Must keep** (this is what makes it feel the same):
- <cut frames + music sync>
- <hook structure: one long establishing shot with the text card>
- <the look: deep blues, rich greens, lifted blacks>

**Adapt to the new footage**:
- <subject matter, text wording if content-specific, which clip goes where>

**Avoid**:
- <cutting people/subjects in half; repeating a clip; mismatched motion directions across a cut>
