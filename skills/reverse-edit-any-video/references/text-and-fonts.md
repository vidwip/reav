# Text and fonts

## Identify the font

Grab a clean frame where the text is large (`strip.py` or `ffmpeg -ss T -frames:v 1`). Compare letter
shapes: `a` (one or two storey), `g`, `R` leg, `t` top, `G` spur, width, stroke contrast. Common
short-form fonts (all on Google Fonts unless noted):

| Look | Likely font |
|---|---|
| TikTok default caption, white box / black text, or plain white with shadow | **TikTok Sans** (Bold/SemiBold) |
| Instagram "Classic" / "Modern" text | system-ish: Inter, SF Pro (Apple only), **Figtree** / **Instrument Sans** are close |
| Bold condensed meme captions | **Anton**, **Bebas Neue**, **Oswald**, Impact-alike |
| Wide heavy captions (MrBeast / Hormozi style) | **Archivo** (width 125, weight 900), **Montserrat** ExtraBold/Black, **The Bold Font** (not Google) |
| Elegant serif "aesthetic" cards | **Libre Bodoni**, **Playfair Display**, **Cormorant**, **Crimson Text** SemiBold, **Source Serif 4** |
| Typewriter / documentary | **Courier Prime**, **Space Mono**, **IBM Plex Mono** |
| Handwritten | **Caveat**, **Kalam**, **Permanent Marker** |
| Rounded friendly | **Nunito**, **Quicksand**, **Poppins** |

Download a TTF into `fonts/` (Google Fonts serves TTF to old user agents):
```bash
curl -sA "Wget/1.12" "https://fonts.googleapis.com/css?family=Crimson+Text:600" | grep -o 'https://[^)]*\.ttf' | head -1 | xargs curl -sLo fonts/CrimsonText-600.ttf
# variable fonts / css2:
curl -sA "Wget/1.12" "https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,900" | grep -o 'https://[^)]*\.ttf' | head -1
```
Verify the match. Render a still with the font next to the reference frame at the same size, and check
letter widths within ~3%. Try the neighbours (Bold vs SemiBold, a different width) before accepting.

## Size and position

- Measure in the reference frame: cap height or line height in px, and the text block's centre (x, y)
  as fractions. For a 1080-wide reference, `size` ≈ line height × 0.8 (drawtext size ≈ em size). Iterate
  with `--still` until the rendered block covers the same pixels.
- Landscape reference → vertical output: keep size relative to frame **width**, put the block in the
  same *zone* (upper third, centre, lower third).
- **Safe zones** (9:16): Instagram and TikTok UI cover about the top 12% and bottom 20–25%, plus a
  right-side rail of about 15% at the bottom. Keep key text inside y 0.12–0.75 unless the reference
  deliberately puts it elsewhere.

## Style details that sell the match

- Box: padding (`box.pad`), opacity (`white@0.9`). Rounded corners need the Remotion text layer (`box.radius`).
- Stroke: `border.width` 2–6 px. Shadow: `shadow` {x: 2, y: 2, color: "black@0.5"} for TikTok-style white text.
- Line spacing, letter case, emoji (emoji need a colour-emoji font, so use the Remotion route), and
  per-word colour highlights (Remotion `karaoke`).
- Timing: the exact first and last frame (strip.py). Text that appears 2–3 frames after a cut feels
  different from text that's there on the cut.

## Animated text → Remotion text layer

Presets in `templates/remotion/src/Texts.tsx` (`anim` field): `fade`, `pop` (spring scale), `punch`
(overshoot), `slide_up`, `typewriter`, `words` (word-by-word reveal), `karaoke` (active word highlight,
`highlight` colour). Render transparent and overlay it in render.py:
```bash
cd remotion && npx remotion render TextLayer out/text.mov --codec=prores --prores-profile=4444 --pixel-format=yuva444p10le
```
Then add `{"src": "remotion/out/text.mov", "from": 0}` to `overlays` and delete those items from
`texts` so they don't draw twice. See remotion-route.md.

## Speech captions

Transcribe with whisper (setup.sh `--with-whisper`, or the video-analyzer skill's transcription), then
chunk the words the way the reference does (1 word, 2–3 words, or a line) into `texts` items with
frame times. Use `words`/`karaoke` animation for active-word styles.
