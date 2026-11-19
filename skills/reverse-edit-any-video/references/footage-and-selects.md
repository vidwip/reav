# Watching the footage and picking the best parts

## Log everything

```bash
python3 "$S/log_footage.py" "<footage folder>" --out footage
```
`footage/index.md` gives per clip: duration, resolution, orientation, fps, **HDR**, audio, median motion
(<1.5 locked-off, 1.5–4 gentle, 4–9 moving, >9 fast or shaky) and the second with the most motion.
`footage/index.json` has a per-second activity curve (motion, luma, internal cuts).

Read **every** contact sheet in `footage/sheets/` (timestamps burned in). With many clips, give
batches to parallel subagents. Each subagent gets the sheet paths, index.md, this file and the
reference's slot list (functions + shot sizes), and returns selects in the format below.

## What makes a select

Keep a moment only if it is:
- **Readable**: sharp where it matters, exposed so the subject reads, no focus hunting.
- **Stable enough**: shake is fine only when handheld energy is the reference's style.
- **Complete**: the action has a beginning, peak and end inside the usable range, or a clean slice of it.
- **Croppable to 9:16**: the subject stays whole in the vertical frame (check where the subject is in
  landscape clips and note the `focus` x you'd use).
- **Interesting**: something happens or something is beautiful. "Camera pointed at nothing while walking" isn't a select.

Then rate **energy 1–5** (1 = still, contemplative; 5 = fast action, big reveal) and mark **heroes**:
the 2–4 shots you would open or end with.

## selects.md format

```markdown
| id | clip | in–out (s) | len | size | subject / action | motion (cam / subject, direction) | energy | quality | roles | focus (x,y) |
|----|------|-----------|-----|------|------------------|-----------------------------------|--------|---------|-------|-------------|
| A1 ★ | IMG_2440.MOV | 0.0–3.0 | 3.0 | WS | mountain summit at sunrise, two people on the rock | static → slow pan R | 3 | sharp, HDR | hook, payoff | 0.5,0.4 |
| A2 | IMG_2492.MOV | 3.0–48.0 | 45 | MS | hiker walks away up the snow slope | locked-off / subject walks away, up | 2 | locked-off, clean plate | setup, breath | 0.5,0.45 |
```
`★` = hero. **roles** = functions from references/storytelling.md. Add a short "not usable" list
(clip, range, reason) so nobody re-checks those later.

## Checks before committing a select

- `strip.py CLIP --at T --before 6 --after 6` around the planned in/out: no blur frame, no subject
  entering or leaving at the wrong moment.
- Enough length: slot frames ÷ fps × speed, plus handles for xfades (half the xfade length each side).
- HDR clips: the scripts tonemap automatically (`hdr: true` in index.json). Grade after the tonemap.
- 60 fps clips allow clean 0.5x slow motion. 24/30 fps slowed down will stutter, so avoid it or use it as a style choice.
- Rotation metadata is handled (display size is used). Mixed portrait and landscape is fine.
