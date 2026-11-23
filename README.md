# REAV: Reverse Edit Any Video

## Overview

REAV is a Claude Code skill that **copies the edit of any video onto your own footage**.

Show it an Instagram reel, TikTok or YouTube video you like. Claude breaks down how it's edited
(pace, cuts on the beat, transitions, text, effects, color and story structure) and writes that
recipe down as `style.md`. Then it watches every clip in your folder, picks the best moments, plans
a story that flows like the sample and renders a finished video: frame-exact cuts, matched color,
same text style. No timeline, no editing app.

## How it works

- **Add the link** to an Instagram reel, TikTok or YouTube video (or use a video file).
- **Give it folder access**: point it at the folder with your clips.
- **Ask `/reav` to clone the edit**. The finished video lands in `final-videos/`.

```
/reav https://www.instagram.com/reel/XXXXXXXX/ ./footage
```

## Use cases

- **Creators**: turn a pile of raw clips into a reel cut like the one that's trending right now.
- **Brands and marketers**: rebuild an ad that works with your own product shots and rewritten text.
- **Agencies and freelance editors**: turn a client's "make it like this" reference into a
  measured spec and a first cut in one go, then polish from there.
- **Travel and vlog**: edit trip footage in the style of your favorite travel reel, cut to your own song.
- **Series and batch content**: run the same sample against each new batch of clips so every
  post keeps the same pace and look.
- **Learning to edit**: get a plain-words breakdown of how any video is cut (shot lengths, beat sync,
  transitions, color, text) without rendering anything.

## Install

**One line** (inside the project folder you'll work in):
```bash
curl -fsSL https://raw.githubusercontent.com/vidwip/reav/main/install.sh | bash
```

**From a clone**:
```bash
git clone https://github.com/vidwip/reav.git
cd /path/to/your/project
bash /path/to/reav/install.sh            # add --global to install for every project
```

**With the skills CLI**: `npx skills add vidwip/reav`. The skill installs its own dependencies the
first time it runs.

### What gets installed automatically

`install.sh` copies the skill to `.claude/skills/reav` and runs
`scripts/setup.sh`, which installs or verifies:

| Tool | Why | How |
|---|---|---|
| **ffmpeg** (full build: drawtext, zscale, lut3d, xfade) | analysis, grading, rendering | macOS: `brew install ffmpeg-full` · Linux: distro `ffmpeg` |
| **video-analyzer** skill → `.claude/skills/video-analyzer` | lets Claude watch the sample (frames, scenes, transcript) | cloned from [bsisduck/video-analyzer-skill](https://github.com/bsisduck/video-analyzer-skill), plus two bug fixes (macOS bash 3.2, ffmpeg stdin) |
| **Remotion** skills → `.claude/skills/remotion-*` | effects and animated captions | `npx skills add remotion-dev/skills` |
| **Remotion** packages + headless Chrome | renders effects and text layers | cached once in `~/.cache/reav/remotion`, cloned into each job |
| python3 ≥ 3.9, node ≥ 20, yt-dlp | scripts, Remotion, downloading the sample | Homebrew / package manager / pip |
| whisper (optional, `--with-whisper`) | speech-led samples (talking heads, captions) | pip / pipx |

Re-running `setup.sh` is safe. It only fills in what's missing (about 1 s when everything is there).
Check without installing: `bash .claude/skills/reav/scripts/setup.sh --check`.

## Use it

Start Claude Code in your project and ask in plain words:

```
Reverse edit https://www.instagram.com/reel/XXXXXXXX/ using my clips in ./footage
```
```
/reav ./samples/ad.mp4 ./trip-clips  make it 9:16, use my own song ./music/track.mp3
```

The final video lands in `final-videos/` and the whole job in `reav-projects/<name>/`.

### Example prompts

- "Edit my footage in `./ABC` exactly like this reel: <link>. Keep the hook text."
- "Copy the pacing and transitions of this TikTok, but use my music `song.mp3`."
- "Same style as `ref.mp4`, but for my product clips in `./shots`. Rewrite the text for my product."
- "Recreate this YouTube Short's edit with my vlog clips, vertical, highest quality."
- "Just analyse this reel and write the style.md, don't render yet."

## Under the hood

```
sample video ─► watch & measure ─► style.md ─► watch ALL footage ─► best parts ─► plan the sequence ─► apply style.md ─► review ─► final.mp4
```

| Step | What Claude does | Output |
|---|---|---|
| 0. Setup | installs or verifies tools, creates the job, downloads the sample (yt-dlp) | `reav-projects/<job>/` |
| 1. Watch the sample | frame-exact cut detection, beat/accent map and how cuts sit on the music, per-shot color measurement, frame strips around every cut, full watch with video-analyzer | `analysis/cuts.json`, `beats.json`, `ref_color.json`, contact sheets, strips |
| 2. **style.md** | writes the edit DNA: story beats, pace, shot list, transitions, text, effects, color correction, audio, recreation rules | `style.md` |
| 3. Watch all footage | logs every clip (orientation, HDR, motion curve) and reads every contact sheet | `footage/index.md`, `footage/sheets/` |
| 4. Best parts | rates moments (quality, energy, story role) and marks hero shots | `footage/selects.md` |
| 5. Plan the sequence | maps every sample slot to a select **by story function** (hook, build, payoff…), checks flow | `sequence.md` |
| 6. Apply style.md | fits a LUT to the sample's look, matches fonts and text, builds the edit plan, renders | `grading/*.cube`, `edit-plan.json`, `out/*.mp4` |
| 7. Review | compares cuts frame by frame, look per shot, loudness, side-by-side sheets, then fixes and re-renders | `review/review.md`, `final-videos/*.mp4` |

### What style.md captures

- **Story & structure**: hook, setup, build, payoff, loop, with timecodes and what each beat does for the viewer
- **Pace**: shot lengths, pace curve, % of cuts on the beat, how many frames before the hit cuts land
- **Shot list**: size, subject, camera and subject motion, speed, transition, on-screen text per shot
- **Transitions**: hard cut, flash, dip, xfade, whip, zoom, match cut, with frame counts
- **Text**: font match, size, colour, box/stroke/shadow, position, timing, animation, safe zones
- **Effects**: push-ins, pans, shakes, speed ramps, grain, blur fills…
- **Color correction**: black point, exposure, highlight ceiling, saturation, grey balance / split-tone, per-shot changes
- **Audio** and **recreation rules** (must keep / adapt / avoid)

### Storytelling

The skill matches your shots to the sample by **function, not content**. The sample's "stop-the-scroll
hook" gets your most arresting shot, its "payoff on the drop" gets your hero shot, calm slots get calm
shots. It then checks the cut as a story: hook promise, real escalation, payoff on the music, motion
continuity across cuts, no repeats, nobody cut in half at 9:16. See
[`references/storytelling.md`](skills/reav/references/storytelling.md).

## Quality

- Cuts land on the sample's exact frames (one-pass ffmpeg render, exact frame counts per slot)
- Float-RGB LUT grading on 10-bit 4:4:4, one dithered conversion at the end, HDR iPhone footage tonemapped
- H.264 High, CRF 14, BT.709-tagged, AAC 320k, `+faststart`; vertical 1080x1920 by default

## Job folder

```
reav-projects/<job>/
  ref/reference.mp4, audio.wav       the sample + its soundtrack
  analysis/                          cuts.json, beats.json, ref_color.json, shots_sheet_*.jpg, strips/
  style.md                           the edit DNA
  footage/                           index.md, sheets/, selects.md
  sequence.md                        the story plan
  grading/look.cube                  fitted look
  fonts/                             matched fonts
  edit-plan.json                     what render.py renders
  remotion/                          (optional) effects / animated-text project
  out/, review/                      renders, review sheets
```

## Scripts

All in `skills/reav/scripts/`, Python stdlib + ffmpeg, usable on their own:

| Script | Does |
|---|---|
| `setup.sh` | install or verify all dependencies (idempotent) |
| `new_job.py` | job folders, download the sample, extract audio, seed style.md, optional Remotion project |
| `cuts.py` | frame-exact shot list, pace stats, flash/fade/soft-transition flags, contact sheet |
| `beats.py` | tempo, beats, accents, drops, and how the sample's cuts sit on them |
| `color.py` | measure a look · fit a `.cube` LUT to it · check the result |
| `strip.py` | frame-by-frame strips around cuts or any moment |
| `log_footage.py` | log a footage folder: metadata, HDR, motion curve, contact sheets |
| `render.py` | `edit-plan.json` → finished video (also `--preview`, `--still`, `--export-segments` for Remotion) |
| `review.py` | output vs sample: cut timing, look per shot, loudness, side-by-side sheets |

## Requirements

macOS or Linux (Windows via WSL), Claude Code, about 1 GB free for the Remotion cache. Network access
on first run. Instagram, TikTok and YouTube links download through yt-dlp. Private posts need you
to download the file yourself.

## Troubleshooting

- **`setup.sh` says FAIL for ffmpeg**: macOS `brew install ffmpeg-full`. Linux: install your distro's
  `ffmpeg` (it needs the drawtext, zscale and lut3d filters).
- **Sample won't download**: download it yourself and pass the file path.
- **Remotion render hangs**: kill `chrome-headless-shell` processes and retry once. The skill falls
  back to pure ffmpeg rendering, which covers cuts, transitions, text, grading and zooms.
- More in [`references/gotchas.md`](skills/reav/references/gotchas.md).

## Credits & licences

- [video-analyzer-skill](https://github.com/bsisduck/video-analyzer-skill) by bsisduck (GPL-3.0). Downloaded at install time, not bundled here.
- [Remotion](https://www.remotion.dev) and [remotion-dev/skills](https://github.com/remotion-dev/skills). Remotion is free for individuals and small teams. Companies may need a license: see [remotion.dev/license](https://www.remotion.dev/license).
- [FFmpeg](https://ffmpeg.org), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [Whisper](https://github.com/openai/whisper).

Only recreate edits and use footage and music you have the rights to.
