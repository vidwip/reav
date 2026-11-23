# Storytelling: plan the sequence so the new edit *flows* like the reference

The reference is a solved problem: someone already found an order, rhythm and energy curve that holds
attention. Your job is to tell **the user's** story through that same shape. Match by **function**
(what a shot does for the viewer), not by literal content. A reference shot of flowers doing "calm
establishing beauty" is matched by the user's calmest, most beautiful wide shot, mountains or not.

## 1. Read the reference's story first

For every shot in cuts.json, write its function in style.md:

| Function | What it does | Typical form |
|---|---|---|
| **Hook** | Stops the scroll in <1.5 s. Opens a question or makes a promise. | Striking image, motion toward camera, a face, text that creates curiosity, a pattern break |
| **Setup / context** | Where, who, what's at stake | Wide/establishing, subject introduced |
| **Build / escalation** | Raises intensity: faster, bigger, closer, more surprising | Shorter shots, more motion, rising music |
| **Turn / reveal** | The "but…" or "and then…": new information that reframes | Reveal shot, contrast, punchline text |
| **Payoff** | Delivers what the hook promised, usually on the drop / biggest accent | Hero shot, widest vista, emotional face |
| **Breath** | A held moment after intensity so the payoff lands | Slower shot, held frame, silence |
| **Outro / loop / CTA** | Ends so people rewatch or act | Hold, black, last frame that flows back into frame 1 |

Also note the **energy curve** (sketch it 1–5 per shot), the **emotional arc** (curiosity → awe → calm,
problem → struggle → win, setup → twist), and whether the ending **loops**.

## 2. Principles that make short-form flow

1. **Hook in the first frame, not the first second.** Frame 1 must already be interesting. Put the most
   arresting select in the hook slot, cut to the reference hook's length and covered by its text.
2. **Every cut earns its place.** Each new shot adds information or emotion. If two consecutive shots say
   the same thing, the second one is a stall. Replace it with something that moves the story.
3. **Escalate, then pay off.** Follow the reference's energy curve. Don't spend the best shot early
   unless the reference opens with its best shot (some do: "end result first, then how").
4. **Cause and effect beats "and then".** Order shots so each one follows from the last (walk → arrive
   → see the view → react). "But/therefore" sequencing feels like a story. A random tour feels like a slideshow.
5. **Cut on action and match motion.** Cut while something moves. Keep screen direction consistent
   across a cut (left-moving into left-moving). Carry the eye: if the subject is top-left at the end of
   shot A, start shot B with interest near top-left. Opposite directions read as a jolt, so use that only
   where the reference jolts.
6. **Shot-size grammar.** Mirror the reference's pattern (e.g. wide → medium → close builds intimacy;
   close → wide is a reveal). Avoid two near-identical framings back to back (jump cut) unless the style
   is deliberately jumpy.
7. **Put the payoff on the music.** The biggest select goes on the drop or strongest accent (beats.json
   `energy_changes` / `accents`). Cuts land where the reference's cuts land, the same few frames before
   the hit (`median_event_offset_s`).
8. **Let it breathe where the reference breathes.** A held shot after a burst of fast cuts makes the
   burst feel faster. Keep the reference's long shots long.
9. **Faces and people carry emotion.** If the user has a shot of a person reacting, place it right
   after the thing they react to (Kuleshov effect), in a slot whose function is emotional.
10. **End deliberately.** Match the reference's ending. For loops, pick a last shot whose motion or
    composition flows into frame 1.
11. **Text is part of the story.** Keep hook text on the hook shot. If text names something
    ("this view…"), the shot under it must show that thing.

## 3. Matching slots to selects

For each slot, score candidate selects (from footage/selects.md) on:

| Criterion | Weight | Question |
|---|---|---|
| Function fit | 3 | Can this shot do this slot's job (hook / build / payoff…)? |
| Energy / motion fit | 2 | Same motion amount and direction feel? Calm slot gets a calm shot. |
| Shot size fit | 1 | Same size class as the reference shot (or the size the grammar needs)? |
| Quality | 2 | Sharp, steady (unless handheld is the style), well exposed, subject whole in 9:16? |
| Length available | gate | Enough clean footage for the slot's frames ÷ speed (+ handles for xfades)? |
| Continuity | 1 | Flows from the previous slot (direction, eye trace, color, no repeat)? |

Fill the **hook and payoff first** (your heroes), then the slots around accents, then the rest. Then
read the sequence top to bottom as a viewer and fix stalls, repeats and direction clashes.

Pick the in-point inside the select so the **action peak sits where the reference's peak sits** in that
slot. If the reference shot's interesting moment is at the end (a reveal), put the select's peak at the
end too.

## 4. When footage and reference don't fit

- **Fewer good clips than slots**: use a different moment, size or speed of a strong clip (a slow
  0.5x, a punch-in crop) instead of a weak clip. Never put the same frames on screen twice.
- **More good clips than slots**: don't add slots. The reference's count *is* the pace. Keep the best.
- **Slot needs motion, clip is static**: add the reference's kind of move in post (`zoom_to`/`pan_to`
  push-in, or a speed change) only if it looks natural. Otherwise choose another clip.
- **Landscape clips in a vertical edit**: crop with `focus` so the subject stays whole, or `fit: blur`
  when the composition can't survive the crop.
- **Speech / talking-head references**: the story is the words. Transcribe (whisper), keep the user's
  sentences intact, cut on sentence boundaries and breaths, and place b-roll where the reference places
  b-roll. Use `clip_audio` and keep the reference's caption style.

## 5. New music (user supplied a different track)

1. `beats.py new_song.wav --out analysis/new_beats.json`
2. Express each reference shot in beats (style.md: "shot = 2 beats", "cut on the drop").
3. Re-time: slot frames = beats × new beat period × fps, snapped to the new beat/accent grid, keeping the
   reference's lead (cut N frames before the hit). Put the payoff on the new song's drop.
4. Total length follows the song section you use (start at a phrase boundary).

## 6. Write it down (sequence.md)

```
## Story
3 sentences: hook promise → what builds → payoff/ending.

## Slots
| slot | frames | ref function | select (clip @ in–out) | why | in-point | focus/zoom | speed | transition | text |
```
Then sanity-check: hook strong? escalation real? payoff on the drop? any repeats? any direction clash?
Any subject cut in half at 9:16?
