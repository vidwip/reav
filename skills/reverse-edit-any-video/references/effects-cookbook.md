# Effects cookbook: how to rebuild what you see

Use **render.py** (ffmpeg, one pass, best quality) for everything in the first table. Use the
**Remotion route** (remotion-route.md) for the second, or render just those moments as an overlay.

## render.py (edit-plan.json fields)

| Reference shows | Build |
|---|---|
| Hard cut on the beat | segment `frames` from cuts.json (nothing else) |
| White or colour flash at a cut | `transition_in: {"type": "flash", "frames": 2-6, "color": "white"}` |
| Dip to black | `transition_in: {"type": "dip", "frames": 6-12}` |
| Fade from black at the start, fade out at the end | `transition_in: {"type": "fade_in"}` on S01 / `fade_out` on the last segment |
| Crossfade / dissolve | `transition_in: {"type": "xfade", "effect": "fade", "frames": 8}` |
| Slide, wipe, smooth slide, circle reveal, pixelize, blur transition | xfade `effect`: slideleft, wipeleft, smoothleft, circleopen, pixelize, hblur, zoomin… |
| Slow push-in or pull-out | `zoom: 1.0, zoom_to: 1.08` (+ `ease: "inout"`) |
| Punch-in crop (static) | `zoom: 1.2`, `focus` on the subject |
| Pan across a wide shot | `zoom: 1.15` (or a landscape source), `focus: [0.2, 0.5]`, `pan_to: [0.8, 0.5]` |
| Slow motion | `speed: 0.5` (60 fps sources) |
| Speed ramp (fast → slow → fast) | split the slot into 3–5 segments with stepped `speed`, `in: "continue"` for each step after the first |
| Freeze frame | `freeze: true` (holds the exact frame at `in` for the whole slot) |
| Mirror for screen direction | `hflip: true` |
| Landscape clip inside a vertical edit | `fit: "blur"` (blurred fill) or `fit: "contain"` with `background` |
| Black end card / text card | `{"color": "black", "frames": N}` + a text item |
| Film grain / sharpen / soften | `filters: "noise=alls=6:allf=t"`, `"unsharp=5:5:0.4"`, `"gblur=sigma=2"` |
| B&W shot | `filters: "hue=s=0"` |
| Static sticker, logo, PNG text | `overlays: [{"src": "x.png", "from": a, "to": b, "x": .., "y": ..}]` |

## Remotion (`fx` on a segment, frames relative to the segment start)

| Reference shows | `fx` entry |
|---|---|
| Camera shake on a hit | `{"type": "shake", "from": 0, "frames": 8, "amount": 1}` |
| Whip-pan in (motion blur + slide) | `{"type": "whip", "from": 0, "frames": 6, "dir": "x"}` (`-x`, `y`, `-y`) or `transition_in` xfade `effect: "whip"` |
| Zoom punch on the beat | `{"type": "punch", "from": 0, "frames": 10, "amount": 1}` |
| Flash on a beat inside a shot | `{"type": "flash", "from": 12, "frames": 3, "color": "white"}` |
| Invert / B&W flicker | `{"type": "invert", "from": 5, "frames": 2}`, `{"type": "bw", ...}` |
| Blur-in | `{"type": "blur", "from": 0, "frames": 8}` |
| Vignette | `{"type": "vignette"}` |
| Animated captions | `texts[].anim`: pop, punch, slide_up, typewriter, words, karaoke |

Things neither covers directly (masks, cut-outs, split screens with moving windows, clones, rotoscoped
pops, 3D) need custom Remotion components. Start from `templates/remotion/src/Reel.tsx` and the
remotion-* skills. Person masks on macOS: Apple Vision (`VNGenerateForegroundInstanceMaskRequest`) via
a small Swift tool writing per-frame PNG masks. Composite in ffmpeg (`alphamerge`/`overlay`) or Remotion.

## Sound effects

If the reference has whooshes, hits or risers on transitions, add them to the music bed (mix a WAV with
ffmpeg `amix`, then use it as `audio.track`), placed on the transition frames. The `real-sfx` and
`real-sound` skills can source real recordings if they're installed.
