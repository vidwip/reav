# Gotchas (each one cost real retries)

## Reference downloads
- Instagram/TikTok files report odd frame rates (e.g. 56.45 fps VP9) and duplicate frames. The edit was
  made at 24/25/30/60. `cuts.py` snaps to the editing rate (30 when unsure). A cut can be ±1 frame
  ambiguous after the platform's resample.
- Some downloads carry an MJPEG cover image as video stream 0. The scripts skip attached pictures.
- yt-dlp needs cookies for private or age-gated posts (`--cookies-from-browser chrome`). Ask the user
  before touching their browser cookies. Otherwise have them download the file.
- `ffmpeg -ss N/30` on VP9 downloads can land one frame late. Use cuts.json frames, not hand-computed seeks.

## ffmpeg
- ffmpeg ≥ 7 removed `-vsync`. Use `-fps_mode cfr/passthrough`.
- Tag BT.709 explicitly (`setparams` + `-x264-params colorprim/transfer/colormatrix`) or players guess wrong colours.
- Homebrew's plain `ffmpeg` lacks drawtext/zscale. `ffmpeg-full` is keg-only. The scripts prefer
  `/opt/homebrew/opt/ffmpeg-full/bin` automatically. For other tools, `export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"`.
- `drawtext fontfile=`/`textfile=` break on paths with spaces or quotes. render.py copies fonts and text to a temp dir.
- drawtext expands `%` sequences. render.py sets `expansion=none`.
- **Animated zoom**: `scale=...:eval=frame` + `crop` silently keeps the first frame's size, so the crop
  pins to the top-left. render.py uses zoompan on a 2x pre-scaled frame instead.
- `blend` modes on rgb24 input run in YUV (black turns magenta). Put `format=gbrp` before `split`/`blend`.
- xfade needs equal timebases on both inputs. render.py adds `settb`.
- Don't run many `x264 -preset slower` encodes in parallel. About 4 at a time on a laptop.

## Footage
- iPhone HDR (HLG / Dolby Vision) looks washed out and grey without tonemapping. `hdr: true` in
  footage/index.json means the scripts tonemap. Grade after the tonemap.
- iPhone MOVs have extra data streams (`mebx`). Always map the video stream explicitly (scripts do).
- Rotation metadata: use display width/height (probe does). A "landscape" 1920x1080 file with
  rotation 90 is portrait.
- Slowing 24/30 fps footage stutters. Only 50/60 fps clips give clean 0.5x.

## Color
- Statistical colour transfer copies *content* colour (reference meadow → green clouds). Match tone
  and greys, damp saturation (color.py does), and always look at the result.
- Per-channel contrast curves add saturation. Recheck saturation after tone changes.
- Saturation-gated sky tweaks draw dark outlines on ridges (4:2:0 chroma at edges). Avoid, or use a soft spatial mask.

## Remotion
- One render at a time (parallel renders corrupt the Rspack cache: "Pack content hash mismatch").
- If headless Chrome hangs at launch (`Waiting for root component`, `CVDisplayLinkCreateWithCGDisplay
  failed`), kill stray `chrome-headless-shell` processes and fall back to render.py.
- An absolutely positioned text box centred with `left: 50%` + `translate(-50%)` shrink-wraps to half the
  frame. Use `width: max-content` (the template does).
- Remotion can't decode ProRes in `@remotion/media` `<Video>`. Export segments as H.264 (render.py does).

## Shell (zsh on macOS)
- Quote every path. Folders like "video editing" split otherwise.
- `$VAR:s...` inside filter strings is a zsh modifier. Write `${VAR}`.
- zsh doesn't word-split `$VAR`. Use `$=VAR` or arrays for space-separated lists.
- `echo ====` fails in zsh (`=` expansion). Quote it.
- macOS has no `timeout`. Use `perl -e 'alarm 120; exec @ARGV' cmd ...`.

## video-analyzer skill
- `extract-frames.sh` upstream bugs that setup.sh patches: the bash 3.2 empty-array `unbound variable`
  error, and ffmpeg without `-nostdin` inside its `while read` loop, which eats the next scene time
  (key frames 2+ get wrong timestamps such as `.966667`). End times must be integers (`13`, not `12.4`).
- Its key-frame step can error on VP9 downloads ("Non full-range YUV"). Grids are still fine. Use cuts.py for cuts.
