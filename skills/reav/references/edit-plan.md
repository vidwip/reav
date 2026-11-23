# edit-plan.json (input to render.py)

One file describes the whole edit. Paths are relative to the plan file (absolute paths work too).
Segments play back to back. Each segment's `frames` is exactly the reference slot length from
cuts.json, so cuts land on the reference's frames.

```json
{
  "fps": 30, "width": 1080, "height": 1920,
  "output": "out/myjob_final.mp4",
  "quality": {"crf": 14, "preset": "slower", "tune": "film"},
  "audio": {
    "track": "ref/audio.wav", "track_start": 0.0, "track_gain_db": 0, "fade_out_s": 0.25,
    "clip_audio": false, "clip_gain_db": -6, "loudnorm": false, "lufs": -14
  },
  "grade": {"lut": "grading/look.cube"},
  "fonts": {"caption": "fonts/TikTokSans-Bold.ttf"},
  "segments": [
    {"id": "S01", "src": "/path/IMG_2492.MOV", "in": 3.0, "frames": 120,
     "focus": [0.5, 0.45], "zoom": 1.0, "zoom_to": 1.08, "ease": "inout", "note": "hook"},
    {"id": "S01b", "src": "/path/IMG_2492.MOV", "in": "continue", "frames": 110, "speed": 0.5, "zoom": 1.08, "focus": [0.5, 0.45]},
    {"id": "S02", "src": "/path/IMG_2394.MOV", "in": 2.0, "frames": 39, "transition_in": {"type": "flash", "frames": 4}},
    {"id": "S03", "src": "/path/IMG_2440.MOV", "in": 1.0, "frames": 35, "zoom": 1.15, "focus": [0.3, 0.5], "pan_to": [0.7, 0.5]},
    {"id": "S04", "src": "/path/IMG_2499.MOV", "in": 3.0, "frames": 34, "transition_in": {"type": "xfade", "effect": "smoothleft", "frames": 8}},
    {"id": "S05", "src": "/path/landscape.mp4", "in": 1.0, "frames": 32, "fit": "blur"},
    {"id": "END", "color": "black", "frames": 17}
  ],
  "texts": [
    {"text": "POV: you finally made it", "from": 0, "to": 230, "font": "caption", "size": 46,
     "color": "black", "x": "center", "y": 0.315, "box": {"color": "white", "pad": 14}}
  ],
  "overlays": [
    {"src": "remotion/out/text.mov", "from": 0, "to": 430},
    {"src": "build/sticker.png", "from": 40, "to": 90, "x": 120, "y": 300}
  ]
}
```

## Segment fields

| Field | Default | Meaning |
|---|---|---|
| `id` | S01… | name for logs and Remotion export |
| `src` | — | clip or image. Omit and set `color` for a solid colour slot |
| `color` | — | solid colour segment (`black`, `white`, `#RRGGBB`) |
| `in` | 0 | source seconds at the slot's first frame. `"continue"` = right after the previous segment of the same `src` (use it for speed ramps split into steps) |
| `frames` | **required** | slot length in timeline frames |
| `speed` | 1.0 | playback rate (0.5 = slow-mo; 60 fps sources slow cleanly) |
| `freeze` | false | hold the single frame at `in` for the whole slot |
| `fit` | cover | `cover` (crop to fill), `contain` (letterbox, `background` colour), `blur` (blurred cover behind contained clip) |
| `focus` | [0.5, 0.5] | where the crop window sits: x, y in 0..1 of the spare area (0 = left/top, 1 = right/bottom) |
| `zoom` | 1.0 | extra scale on top of cover (1.1 = punch-in 10%) |
| `zoom_to` | = zoom | animated zoom target at the slot's last frame (push-in / pull-out, via zoompan) |
| `pan_to` | = focus | animated crop position target (pan / tilt). Needs `zoom` > 1 or a source wider/taller than the canvas |
| `ease` | linear | `linear`, `inout`, `in`, `out` for zoom and pan |
| `hflip` | false | mirror (fixes screen direction for continuity; avoid if text or signs are visible) |
| `lut` | plan `grade.lut` | per-segment `.cube`, or `"none"` |
| `filters` | — | raw ffmpeg filters appended after the grade (e.g. `"unsharp=5:5:0.4"`, `"noise=alls=6:allf=t"`) |
| `transition_in` | cut | `{"type": "flash", "frames": 4, "color": "white"}` (outgoing ramps to colour over frames/2, incoming fades from it), `{"type": "dip", "frames": 8, "color": "black"}`, `{"type": "fade_in", "frames": 6}`, `{"type": "xfade", "effect": "fade", "frames": 8}` (centred on the cut, so frame counts stay exact) |
| `fade_out` | — | `{"frames": 10, "color": "black"}` at the end of this segment |
| `mute`, `audio_gain_db` | — | per-segment clip audio control (when `audio.clip_audio` is true) |
| `fx` | — | Remotion-only effects (ignored by render.py): see effects-cookbook.md |

xfade effects: fade, fadeblack, fadewhite, dissolve, wipeleft/right/up/down, slideleft/right/up/down,
smoothleft/right/up/down, circleopen, circleclose, circlecrop, rectcrop, radial, zoomin, hblur, pixelize,
squeezeh, squeezev, distance, diagtl, diagtr, hlslice, hrslice, vuslice, vdslice, coverleft/right,
revealleft/right.

## Text fields (drawtext; for animation use the Remotion text layer)

`text` (use `\n` for line breaks, or `wrap`: max characters per line), `from`/`to` (timeline frames,
end exclusive), `font` (key in `fonts` or a path), `size` (px), `color` (`white`, `#FFE600`,
`black@0.8`), `x` (`"center"`, 0..1 = centre of the block, or px), `y` (0..1 = centre of the block, or
px), `align` (`center`/`left`/`right`), `line_spacing`, `box` `{color, pad}`, `border` `{width, color}`,
`shadow` `{x, y, color}`, `fade_in`/`fade_out` (frames). Text with `%`, `:` or quotes is safe (read
from a file with expansion off).

## Overlays

PNG/JPG/WebP stills, or videos with alpha (ProRes 4444 `.mov`, VP9 `.webm`) such as a Remotion
`TextLayer` render. `from`/`to` in timeline frames, `x`/`y` px, optional `scale` (`"540:-1"`).
Videos start at `from`.

## Audio

- `track`: the music bed (default: the reference's audio, so the sync is exact). `track_start` offsets into it.
- `clip_audio: true`: the clips' own sound per segment (speed-matched with atempo), mixed with the track
  at `clip_gain_db`. Use it for speech or natural sound.
- `loudnorm: true`: normalise to `lufs` (-14 default). Leave it off when the track is the reference's
  audio (already mastered for the platform).

## Render modes

`--preview` (half-res, fast), `--frames A-B`, `--still N --out f.jpg`, `--dry-run` (prints the
filtergraph, also saved to `build/filtergraph.txt`), `--export-segments remotion/public`.
