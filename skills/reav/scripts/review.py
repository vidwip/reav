#!/usr/bin/env python3
"""Check a render against the reference: cut timing, look, loudness, plus side-by-side sheets.

Usage:
  review.py REFERENCE OUTPUT --cuts JOB/analysis/cuts.json [--out JOB/review] [--no-color]

Prints and writes OUT/review.md:
  - every reference cut vs the nearest cut found in the output (frame delta; soft transitions
    such as xfade/flash show up as 'soft' rather than a hard cut - that's fine if planned)
  - per-shot colour numbers, reference vs output (luma p50, saturation, palette warmth)
  - integrated loudness / true peak of the output, durations
  - OUT/side_by_side_NN.jpg: reference (left) | output (right) at the middle of every shot
Open the side-by-side sheets and actually look: framing, subject, energy, text position.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reav_common import (die, fmt_t, load_json, need, probe, read_rgb_frames, rgb_stats, run,  # noqa: E402
                         tonemap_chain)
from cuts import analyse, detect  # noqa: E402


def frame_at(video, t, dst, info):
    tm = tonemap_chain(info)
    vf = f"{tm}scale=360:640:force_original_aspect_ratio=decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{max(0.0, t):.4f}", "-i", video,
         "-map", f"0:{info['video_index']}", "-frames:v", "1", "-vf", vf, "-q:v", "3", "-update", "1", dst],
        check=False)


def loudness(path):
    p = run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-map", "0:a:0", "-af", "ebur128=peak=true",
             "-f", "null", "-"], check=False)
    err = (p.stderr or b"").decode(errors="replace")
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    return (float(i[-1]) if i else None), (float(pk[-1]) if pk else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference")
    ap.add_argument("output")
    ap.add_argument("--cuts", required=True, help="reference cuts.json")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--tolerance", type=int, default=1, help="frames of cut error that count as OK")
    a = ap.parse_args()
    need("ffmpeg")
    ref_cuts = load_json(a.cuts)
    fps = ref_cuts["fps"]
    out_dir = a.out or os.path.join(os.path.dirname(os.path.abspath(a.output)), "review")
    os.makedirs(out_dir, exist_ok=True)
    rinfo, oinfo = probe(a.reference), probe(a.output)
    report = [f"# Review: {os.path.basename(a.output)} vs {os.path.basename(a.reference)}", ""]

    # ---- cuts
    frames = analyse(a.output, oinfo)
    t0 = frames[0]["t"]
    idx, _soft = detect(frames, oinfo["fps"] or fps, ref_cuts.get("threshold", 0.3), 0.12)
    out_cut_f = [int(round((frames[i]["t"] - t0) * fps)) for i in idx]
    ref_cut_f = [s["start_f"] for s in ref_cuts["shots"][1:]]
    rows, ok, used = [], 0, set()
    for rf in ref_cut_f:
        near = [o for o in out_cut_f if abs(o - rf) <= 6 and o not in used]
        if near:
            o = min(near, key=lambda x: abs(x - rf))
            used.add(o)
            d = o - rf
            ok += abs(d) <= a.tolerance
            rows.append((rf, o, d, "OK" if abs(d) <= a.tolerance else "OFF"))
        else:
            # soft transition? look for elevated scene score around rf
            win = [f["scene"] for f in frames if abs((f["t"] - t0) * fps - rf) <= 5]
            rows.append((rf, None, None, "soft (transition, no hard cut)" if win and max(win) > 0.03 else "MISSING"))
    extra = [o for o in out_cut_f if o not in used]
    report += ["## Cuts", "", f"{ok}/{len(ref_cut_f)} reference cuts matched within ±{a.tolerance} frame(s).", "",
               "| ref frame | ref time | output frame | delta | status |", "|---|---|---|---|---|"]
    for rf, o, d, st in rows:
        report.append(f"| {rf} | {fmt_t(rf / fps)} | {o if o is not None else '-'} | "
                      f"{'%+d' % d if d is not None else '-'} | {st} |")
    if extra:
        report += ["", "Extra cuts in output (not in reference): " +
                   ", ".join(f"f{o} ({fmt_t(o / fps)})" for o in extra) +
                   " - fine if they are inside a planned effect (flash, whip), otherwise a jump in the footage."]

    # ---- durations / loudness
    ri, rp = loudness(a.reference) if rinfo.get("has_audio") else (None, None)
    oi, op = loudness(a.output) if oinfo.get("has_audio") else (None, None)
    report += ["", "## Length and loudness", "",
               f"- reference {rinfo['duration']:.3f}s, output {oinfo['duration']:.3f}s "
               f"(diff {oinfo['duration'] - rinfo['duration']:+.3f}s)",
               f"- reference loudness {ri} LUFS / peak {rp} dBFS; output {oi} LUFS / peak {op} dBFS",
               "- platform target about -14 LUFS integrated, true peak <= -1 dBFS"]

    # ---- per-shot colour + side by side
    shots = ref_cuts["shots"]
    if not a.no_color:
        report += ["", "## Look per shot (reference -> output)", "",
                   "| shot | p50 | sat | warmth | note |", "|---|---|---|---|---|"]
    pair_dir = os.path.join(out_dir, "pairs")
    os.makedirs(pair_dir, exist_ok=True)
    for old in os.listdir(pair_dir):
        os.unlink(os.path.join(pair_dir, old))
    for s in shots:
        mid = s["start"] + s["dur"] / 2
        ra, oa = os.path.join(pair_dir, "r.jpg"), os.path.join(pair_dir, "o.jpg")
        frame_at(a.reference, mid + rinfo.get("start", 0), ra, rinfo)
        frame_at(a.output, mid, oa, oinfo)
        label = os.path.join(pair_dir, "label.txt")
        with open(label, "w") as f:
            f.write(f"#{s['shot']} {s['start']:.2f}s  REF | OUT")
        dst = os.path.join(pair_dir, f"pair_{s['shot']:03d}.jpg")
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", ra, "-i", oa, "-filter_complex",
             "[0][1]hstack,pad=iw+8:ih+8:4:4:color=black,"
             f"drawtext=textfile='{label}':expansion=none:x=10:y=10:fontsize=22:fontcolor=white:"
             "box=1:boxcolor=black@0.6:boxborderw=4", "-q:v", "3", "-update", "1", dst], check=False)
        if not os.path.exists(dst):
            run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", ra, "-i", oa, "-filter_complex",
                 "[0][1]hstack", "-q:v", "3", "-update", "1", dst], check=False)
        if not a.no_color and s["frames"] > 4:
            pad = s["dur"] * 0.15
            rs = rgb_stats(read_rgb_frames(a.reference, s["start"] + pad, s["end"] - pad, samples=3,
                                           tonemap=tonemap_chain(rinfo)))
            os_ = rgb_stats(read_rgb_frames(a.output, s["start"] + pad, s["end"] - pad, samples=3))
            if rs and os_:
                note = []
                if abs(os_["luma_p50"] - rs["luma_p50"]) > 20:
                    note.append("exposure differs")
                if abs(os_["saturation"] - rs["saturation"]) > 0.12:
                    note.append("saturation differs")
                report.append(f"| {s['shot']} | {rs['luma_p50']} -> {os_['luma_p50']} | "
                              f"{rs['saturation']:.2f} -> {os_['saturation']:.2f} | "
                              f"{rs['warmth']:+.0f} -> {os_['warmth']:+.0f} | {', '.join(note)} |")
    for f in ("r.jpg", "o.jpg", "label.txt"):
        if os.path.exists(os.path.join(pair_dir, f)):
            os.unlink(os.path.join(pair_dir, f))
    for old in os.listdir(out_dir):
        if old.startswith("side_by_side_"):
            os.unlink(os.path.join(out_dir, old))
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-framerate", "1", "-start_number", "1",
         "-i", os.path.join(pair_dir, "pair_%03d.jpg"),
         "-vf", "scale=728:648:force_original_aspect_ratio=decrease,pad=728:648:(ow-iw)/2:(oh-ih)/2,"
                "tile=3x2:padding=6:color=black", "-q:v", "3",
         os.path.join(out_dir, "side_by_side_%02d.jpg")], check=False)
    sheets = sorted(f for f in os.listdir(out_dir) if f.startswith("side_by_side_"))
    report += ["", "## Side-by-side sheets", ""] + [f"- {os.path.join(out_dir, f)}" for f in sheets]
    report += ["", "Content is supposed to differ (new footage). Judge: same shot size & motion feel per slot, "
               "subject never cut by the frame, text in the same place, same energy at the same moment."]
    text = "\n".join(report) + "\n"
    with open(os.path.join(out_dir, "review.md"), "w") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
