---
name: reav
description: Reverse Edit Any Video. Watches a sample video (Instagram reel, TikTok, YouTube Short, ad, vlog, trailer), writes down its edit DNA in style.md (pace, cuts on the beat, transitions, text, effects, color correction, story structure), then watches all of the user's footage, picks the best parts, plans a story in the same flow and renders the user's footage edited in the same pattern. Use when the user gives a reference video or link plus their own clips and says things like "edit my footage like this", "copy this edit", "recreate this reel with my clips", "same style / pacing / transitions as this", "reverse edit", "make it like this TikTok", or "match this video". Installs its own tools (ffmpeg, Remotion, the video-analyzer skill) on first run.
argument-hint: <reference URL or video> <footage folder> [notes]
---

# Reverse Edit Any Video

The job: **make the user's footage feel like the reference.** The viewer should feel the same hook,
rhythm, energy curve, transitions, text and look. They see the user's clips telling their own story,
in the reference's flow.

```
watch the sample ─► style.md ─► watch ALL footage ─► best parts ─► plan the sequence ─► apply style.md ─► review ─► deliver
   (measure)       (edit DNA)      (log + look)       (selects)      (story mapping)     (grade/text/fx/render)  (compare)
```

Scripts live in `${CLAUDE_SKILL_DIR}/scripts` (stdlib Python + ffmpeg). Run them with `python3`.
Every step writes a file into the job folder, so work can resume at any point.

## Defaults (unless the user says otherwise)

- Output **vertical 1080x1920**, even when the reference is landscape. Adapt the layout, don't letterbox.
- Timeline fps = the reference's editing rate (`cuts.py` picks it; 30 when the platform re-encoded it).
- Soundtrack = the reference's own audio, so cuts land on the same beats. If the user supplies music,
  re-time the pattern to that song's beats instead (see references/storytelling.md, "New music").
- Keep the reference's hook text and on-screen text (font, size, position, timing). Only rewrite
  wording that describes something the new footage doesn't show, in the same voice and length.
- Quality: H.264 High, CRF 14, preset slower, BT.709, AAC 320k. Write the final file to
  `final-videos/<job>_reverse_edit.mp4` in the project root as well as `<job>/out/`.

## Step 0: Setup (automatic, idempotent)

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/setup.sh"          # project scope (.claude/skills next to the cwd)
```
Installs or verifies ffmpeg (full build with drawtext/zscale/lut3d/xfade), python3, node, yt-dlp, the
**video-analyzer** skill (`.claude/skills/video-analyzer`), the **Remotion** agent skills, and Remotion
npm packages plus headless Chrome (cached). Re-running it is cheap. Read the summary. On FAIL, fix it
or tell the user what's missing before going on. Use `--with-whisper` if the reference is speech-led.

Then create the job:
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/new_job.py" --ref "<url or file>" --footage "<folder>" [--remotion]
cd reav-projects/<name>
```

## Step 1: Watch the sample

Measure first, then watch. Run all four (they're fast):
```bash
S="${CLAUDE_SKILL_DIR}/scripts"
python3 "$S/cuts.py" ref/reference.mp4 --out analysis                    # frame-exact shots, pace, contact sheet
python3 "$S/beats.py" ref/audio.wav --cuts analysis/cuts.json --out analysis/beats.json   # tempo, accents, cut sync
python3 "$S/color.py" measure ref/reference.mp4 --cuts analysis/cuts.json --out analysis/ref_color.json
python3 "$S/strip.py" ref/reference.mp4 --cuts analysis/cuts.json --out analysis/strips   # every cut, frame by frame
```
Then **actually watch**:
1. Read `analysis/shots_sheet_*.jpg`: one frame per shot, with frame ranges.
2. Run the **video-analyzer** skill on the reference at a high rate for short videos ("at 4fps",
   transcription on if anyone speaks) for the timeline of what happens and what is said.
3. Read every `analysis/strips/strip_*.jpg`. This is where you see how each transition is built (flash
   frames, whip blur, zoom-through, dip), when text appears and how it animates, speed ramps, and
   whether `cuts.py` missed or double-counted a cut. Run more strips (`--at T`) for text pop-ins, effects
   and `soft_transition_suspects`.
4. Fix `analysis/cuts.json` by hand if a cut is wrong. Everything downstream trusts it.

Details and what to look for: references/watching-the-reference.md

## Step 2: Write style.md

Fill `style.md` (skeleton already in the job folder) from the measurements plus what you saw:
**story & structure, pace, shot list, transitions, text, effects, color correction, audio, recreation rules.**
Use numbers and timecodes, not adjectives. Two things matter most:
- **Function of each shot** (hook / setup / build / payoff / loop), not just its content. That's what
  you'll match the new footage to.
- **Recreation rules**: the 3–6 things that make this edit *this* edit (e.g. "cuts 3 frames before each
  snare", "one 7.7 s hook shot with a white-box caption", "deep blue skies, lifted blacks").

Identify fonts and measure text size and position from frames: references/text-and-fonts.md.
Show the user a 5-line summary of style.md before building if they're around. It's the cheapest
place to catch a misread.

## Step 3: Watch all footage

```bash
python3 "$S/log_footage.py" "<footage folder>" --out footage      # metadata, HDR flag, motion curve, contact sheets
```
Open **every** sheet in `footage/sheets/`, not a sample. For more than about 12 clips, split the sheets
across parallel subagents (Agent tool). Give each the sheet paths, `footage/index.md` and the selects
format from references/footage-and-selects.md, and have each return selects, not prose. Strip-check
(`strip.py CLIP --at T`) any moment you plan to use for blur, focus hunting, or a subject leaving frame.

## Step 4: Get the best parts → footage/selects.md

For every usable moment: clip, in/out (s), shot size, subject, motion and direction, energy 1–5,
quality flags, and which story roles it could play. Mark heroes (the 2–4 shots that would make
someone stop scrolling). Be ruthless: shaky, soft, badly exposed, or "nothing happens" moments don't
make the list. Format and criteria: references/footage-and-selects.md

## Step 5: Plan the sequence → sequence.md

This is the storytelling step. Map **every reference slot** (shot) to a select by *function*, then
check the whole as a story. Read references/storytelling.md first. In short:
- **Hook** (first 1–2 s): the strongest, most curiosity-making image, matched to the reference's hook
  shape (same length, same text treatment). Never open on a weak establishing shot unless the reference does.
- **Escalate**: each shot adds new information or more intensity. Follow the reference's energy curve
  (calm slots get calm shots, fast slots get motion).
- **Payoff on the drop / biggest accent**: your best hero shot.
- **Continuity across cuts**: match motion direction, carry the eye's position, cut on action,
  alternate shot sizes as the reference does, no jump cuts unless that's the style.
- **End**: the reference's ending type (hold, black, loop back into frame 1).
- One clip per slot, no repeats unless the reference repeats. Fill a slot that has no good match with a
  different moment of a strong clip, not a weak clip.

Write `sequence.md` as a table (slot | frames | function in reference | chosen select | why it fits |
in-point | framing/focus | speed | notes) plus a 3-sentence story summary of the new edit. Re-read it as
a viewer: does the hook promise something, does it build, does it pay off?

## Step 6: Apply style.md → edit-plan.json → render

1. **Color**: build the look from the reference measurements, verify by numbers *and* by eye.
   ```bash
   python3 "$S/color.py" match --ref analysis/ref_color.json --src CLIP@IN-OUT [--src ...] --out grading/look.cube --strength 0.85
   python3 "$S/color.py" check --ref analysis/ref_color.json --src CLIP@IN-OUT --lut grading/look.cube
   ```
   Per-shot LUTs with `--ref-shots N` when one shot's look clearly differs. references/color-correction.md
2. **Text**: download or match the font into `fonts/`, set size, position, box, stroke and timing from
   style.md. references/text-and-fonts.md
3. **Write `edit-plan.json`**: segments with **exact frame counts from cuts.json** (`frames` per slot),
   in-points from sequence.md, reframing (`focus`, `zoom`, `zoom_to`, `pan_to`, `fit`), `speed`,
   `transition_in`, `lut`, texts, audio. Schema: references/edit-plan.md
4. **Effects** that ffmpeg can't do (shake, whip, punch-zoom, animated or word-by-word captions,
   rounded boxes): use the Remotion route (`--export-segments`) or render a transparent Remotion
   text layer and add it as an overlay. references/effects-cookbook.md, references/remotion-route.md
5. Render:
   ```bash
   python3 "$S/render.py" edit-plan.json --preview          # fast half-res check
   python3 "$S/render.py" edit-plan.json --still 120 --out review/f120.jpg   # one frame
   python3 "$S/render.py" edit-plan.json                    # final
   ```

## Step 7: Review against the reference, then deliver

```bash
python3 "$S/review.py" ref/reference.mp4 out/<final>.mp4 --cuts analysis/cuts.json --out review
```
Look at every `review/side_by_side_*.jpg` and the cut table. Fix and re-render until:
- all reference cuts match within ±1 frame (planned flashes and xfades read as "soft");
- each slot has the same shot size, motion feel and energy as the reference slot;
- no subject is cut off, no text sits under the platform UI, nothing flickers at a cut;
- the look matches (color.py check on the graded clips, and by eye on the side-by-side);
- loudness about -14 LUFS, true peak ≤ -1 dBFS; duration equals the reference.

Watch the final with the video-analyzer skill (or strips around every cut) once more. Then copy it to
`final-videos/`. Report to the user: output path, a one-paragraph story summary, the style rules
applied, anything you couldn't match and why. references/export-and-review.md

## Gotchas (read before Step 1)

references/gotchas.md has the full list. The ones that bite most:
- Platform downloads report odd frame rates (56.45 fps). Edit at 30 and trust `cuts.json`.
- iPhone HDR (HLG / Dolby Vision) clips look washed out unless tonemapped. The scripts detect `hdr` and handle it.
- Animated zoom must use `zoom`/`zoom_to` in the plan (zoompan). ffmpeg `scale eval=frame` + `crop` silently pins top-left.
- Never run several `npx remotion` renders in parallel (bundle cache corruption). One render, many frames.
- zsh: quote every path (folders with spaces), use `${VAR}` in filter strings.
- Statistical color match copies *content* colors (green meadow → green clouds). `color.py` matches
  greys and tone only, and damps saturation. Always eyeball the graded frame.
