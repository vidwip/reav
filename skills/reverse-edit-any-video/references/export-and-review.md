# Export and review

## Delivery spec (render.py defaults)

| | |
|---|---|
| Frame | 1080x1920 (9:16), square pixels, progressive, constant frame rate = reference editing rate |
| Video | H.264 High, CRF 14, preset slower, tune film, yuv420p, BT.709 primaries/transfer/matrix tagged, `+faststart` |
| Pipeline | decode → (HDR tonemap) → reframe (lanczos) → float RGB LUT → 10-bit 4:4:4 compositing → one dithered conversion to 8-bit 4:2:0 |
| Audio | AAC-LC 320 kb/s, 48 kHz stereo |
| Loudness | about -14 LUFS integrated, true peak ≤ -1 dBFS (the reference's own track is usually already there) |

Platforms re-encode everything. Feeding them a clean high-bitrate master (~15–30 Mb/s for 1080x1920)
gives the best result after their transcode. For YouTube 4K uploads, set `width`/`height` to
2160x3840 only when the footage is 4K. Never upscale 1080p.

## Review loop

1. `render.py --preview` → watch it (video-analyzer, or strips at every cut) for story, flow and timing.
2. `render.py` final → `review.py ref out --cuts analysis/cuts.json`.
3. Read `review/review.md`:
   - **Cuts**: every reference cut OK (±1 frame) or soft where you planned a transition. An extra cut
     inside a slot means a jump in the source (bad in-point or a cut inside the source clip).
   - **Length**: equal to the reference (±1 frame).
   - **Look per shot**: exposure and saturation flags. Content differs, so judge by eye.
   - **Loudness**: about -14 LUFS, peak ≤ -1 dBFS.
4. Open every `review/side_by_side_*.jpg`. Per slot: same shot size? Same energy? Subject whole? Text in
   the same place and not covering faces? Same brightness feel?
5. Fix in edit-plan.json (in-points, focus, LUT, text), re-render, re-review. Stop when the side-by-side
   reads as "the same edit, different footage".

## Report to the user

- Output path(s): `final-videos/<job>_reverse_edit.mp4` (+ job folder)
- The story of the new edit in 2–3 sentences, and which shots fill hook and payoff
- Style rules carried over (pace, sync, transitions, text, look)
- Anything not matched exactly, and why (missing footage type, font licence, effect approximated)
