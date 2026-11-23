#!/usr/bin/env python3
"""Frame-exact shot list of a reference video (the "pace" half of style.md).

One decode pass gives, per frame: scene-change score, luma, saturation and motion (YDIF).
From that we get hard cuts, flash frames, fades, soft-transition suspects (dissolves / whips),
per-shot brightness + motion, pacing stats and a contact sheet of every shot.

Usage:
  cuts.py VIDEO [--out DIR] [--fps 30] [--threshold 0.3] [--min-gap 0.12] [--no-thumbs]

Writes DIR/cuts.json, DIR/shots/shot_NNN.jpg, DIR/shots_sheet_NN.jpg and prints a table.
Always eyeball the sheet: scene detection misses soft transitions and can double-fire on flashes.
"""
from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reav_common import die, ff_escape, fmt_t, need, probe, run, save_json, tonemap_chain  # noqa: E402

FRAME_RE = re.compile(r"frame:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:\s*(-?[\d.]+)")
KV_RE = re.compile(r"lavfi\.([\w.]+)=(-?[\d.]+|nan|inf)")


def analyse(path: str, info: dict) -> list[dict]:
    """Per-frame metrics via select(scene) + signalstats + metadata=print."""
    tmp = tempfile.NamedTemporaryFile(prefix="reav_meta_", suffix=".txt", delete=False)
    tmp.close()
    vf = (f"{tonemap_chain(info)}scale=240:-2:flags=area,select='gte(scene\\,0)',signalstats,"
          f"metadata=mode=print:file='{ff_escape(tmp.name)}'")
    run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", f"0:{info['video_index']}",
         "-vf", vf, "-an", "-f", "null", "-"])
    frames: list[dict] = []
    cur = None
    with open(tmp.name) as f:
        for line in f:
            m = FRAME_RE.search(line)
            if m:
                cur = {"n": int(m.group(1)), "t": float(m.group(3))}
                frames.append(cur)
                continue
            if cur is None:
                continue
            k = KV_RE.search(line)
            if k:
                key, val = k.group(1), k.group(2)
                try:
                    v = float(val)
                except ValueError:
                    continue
                if key == "scene_score":
                    cur["scene"] = v
                elif key == "signalstats.YAVG":
                    cur["y"] = v
                elif key == "signalstats.SATAVG":
                    cur["sat"] = v
                elif key == "signalstats.YDIF":
                    cur["ydif"] = v
    os.unlink(tmp.name)
    for fr in frames:
        fr.setdefault("scene", 0.0)
        fr.setdefault("y", 0.0)
        fr.setdefault("sat", 0.0)
        fr.setdefault("ydif", 0.0)
    return frames


def detect(frames: list[dict], fps_src: float, thr: float, min_gap_s: float):
    """Hard cut = scene score over threshold, OR a frame-difference spike far above its
    neighbourhood (catches cuts between two similar-looking shots that score just under thr)."""
    n = len(frames)
    gap = max(1, int(round(min_gap_s * fps_src)))
    win = max(4, int(round(0.5 * fps_src)))
    s = [f["scene"] for f in frames]
    yd = [f["ydif"] for f in frames]
    strength = [0.0] * n
    for i in range(1, n):
        if s[i] >= thr:
            strength[i] = s[i]
            continue
        if s[i] >= thr * 0.35:
            neigh = yd[max(1, i - win):i] + yd[i + 1:min(n, i + win + 1)]
            local = statistics.median(neigh) if neigh else 0.0
            if yd[i] >= 6 * local + 4:
                strength[i] = max(s[i], thr)  # adaptive hit
    cuts = []
    for i in range(1, n):
        if strength[i] <= 0:
            continue
        lo, hi = max(1, i - gap), min(n, i + gap + 1)
        if strength[i] >= max(strength[lo:hi]) and (not cuts or i - cuts[-1] >= gap):
            cuts.append(i)
    # soft transitions: >=4 consecutive frames of moderate change with no hard cut nearby
    suspects = []
    i = 1
    while i < n:
        if thr * 0.2 <= s[i] < thr:
            j = i
            while j < n and thr * 0.2 <= s[j] < thr:
                j += 1
            if j - i >= 4 and not any(i - gap <= c <= j + gap for c in cuts):
                suspects.append((i, j))
            i = j
        else:
            i += 1
    return cuts, suspects


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", default=None, help="output dir (default: <video dir>/analysis)")
    ap.add_argument("--fps", type=float, default=None, help="timeline fps (default: source fps snapped)")
    ap.add_argument("--threshold", type=float, default=0.3,
                    help="scene score for a hard cut (0.2 for soft/dark footage, 0.4 for shaky action)")
    ap.add_argument("--min-gap", type=float, default=0.12, help="min seconds between two cuts")
    ap.add_argument("--no-thumbs", action="store_true")
    a = ap.parse_args()

    need("ffmpeg")
    if not os.path.isfile(a.video):
        die(f"not found: {a.video}")
    info = probe(a.video)
    if not info.get("has_video"):
        die("no video stream")
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.video)), "analysis")
    os.makedirs(out, exist_ok=True)
    fps = a.fps or info["fps_snapped"]
    if not a.fps and fps not in (24, 25, 30, 48, 50, 60, 120):
        print(f"note: source is {info['fps']} fps (platform re-encode, not an editing rate) -> "
              "timeline 30 fps. Pass --fps to override.", file=sys.stderr)
        fps = 30

    print(f"Analysing {info['name']} ({info['display_width']}x{info['display_height']}, "
          f"{info['fps']} fps -> timeline {fps} fps, {info['duration']:.2f}s)...", file=sys.stderr)
    frames = analyse(a.video, info)
    if not frames:
        die("no frames decoded")
    t0 = frames[0]["t"]
    dur = info["duration"] or (frames[-1]["t"] - t0 + 1 / fps)
    cut_idx, suspects = detect(frames, info["fps"] or fps, a.threshold, a.min_gap)

    bounds = [0] + cut_idx + [len(frames)]
    shots = []
    for k in range(len(bounds) - 1):
        i0, i1 = bounds[k], bounds[k + 1]
        st = frames[i0]["t"] - t0
        en = (frames[i1]["t"] - t0) if i1 < len(frames) else dur
        f0, f1 = int(round(st * fps)), int(round(en * fps))
        seg = frames[i0:i1]
        ys = [f["y"] for f in seg]
        y_mean = statistics.fmean(ys)
        # 8-bit TV-range luma -> rough 0-255 full-range for readability
        notes = []
        if f1 - f0 <= 4 and y_mean > 190:
            notes.append("white flash")
        elif f1 - f0 <= 4 and y_mean < 25:
            notes.append("black flash")
        if len(ys) >= 6:
            head, tail = statistics.fmean(ys[:3]), statistics.fmean(ys[-3:])
            if tail < 22 and statistics.fmean(ys[len(ys) // 2 - 1: len(ys) // 2 + 2]) > tail + 25:
                notes.append("fades to black")
            if head < 22 and statistics.fmean(ys[len(ys) // 2 - 1: len(ys) // 2 + 2]) > head + 25:
                notes.append("fades in from black")
        motion = statistics.fmean([f["ydif"] for f in seg[1:]] or [0])
        shots.append({
            "shot": k + 1,
            "start": round(st, 4), "end": round(en, 4), "dur": round(en - st, 4),
            "start_f": f0, "end_f": f1, "frames": f1 - f0,
            "cut_score": round(frames[i0]["scene"], 3) if k else None,
            "luma": round(y_mean, 1),
            "sat": round(statistics.fmean([f["sat"] for f in seg]), 1),
            "motion": round(motion, 2),
            "motion_label": "static" if motion < 1.5 else "gentle" if motion < 4 else "moving" if motion < 9 else "fast",
            "notes": notes,
        })

    durs = [s["dur"] for s in shots if "flash" not in " ".join(s["notes"])] or [s["dur"] for s in shots]
    pace = []
    w = 5.0
    t = 0.0
    while t < dur - 1e-6:
        c = sum(1 for s in shots[1:] if t <= s["start"] < t + w)
        pace.append({"from": round(t, 2), "to": round(min(t + w, dur), 2), "cuts": c})
        t += w
    summary = {
        "shots": len(shots), "cuts": len(shots) - 1,
        "avg_shot_len": round(statistics.fmean(durs), 3),
        "median_shot_len": round(statistics.median(durs), 3),
        "min_shot_len": round(min(durs), 3), "max_shot_len": round(max(durs), 3),
        "first_cut_at": shots[1]["start"] if len(shots) > 1 else None,
        "cuts_per_second": round((len(shots) - 1) / dur, 3) if dur else None,
        "pace_curve_5s": pace,
    }
    data = {
        "source": os.path.abspath(a.video),
        "width": info["display_width"], "height": info["display_height"],
        "source_fps": info["fps"], "fps": fps, "duration": round(dur, 4),
        "total_frames": int(round(dur * fps)), "threshold": a.threshold,
        "summary": summary, "shots": shots,
        "soft_transition_suspects": [
            {"from": round(frames[i]["t"] - t0, 3), "to": round(frames[min(j, len(frames) - 1)]["t"] - t0, 3)}
            for i, j in suspects],
        "per_frame": [[round(f["t"] - t0, 4), round(f["scene"], 3), round(f["y"], 1), round(f["ydif"], 2)]
                      for f in frames],
    }
    save_json(os.path.join(out, "cuts.json"), data)

    if not a.no_thumbs:
        sd = os.path.join(out, "shots")
        os.makedirs(sd, exist_ok=True)
        for old in os.listdir(sd):
            if old.startswith("shot_") and old.endswith(".jpg"):
                os.unlink(os.path.join(sd, old))
        tm = tonemap_chain(info)
        for s in shots:
            mid = s["start"] + s["dur"] / 2 + t0
            dst = os.path.join(sd, f"shot_{s['shot']:03d}.jpg")
            label = os.path.join(sd, ".label.txt")
            with open(label, "w") as lf:
                lf.write(f"#{s['shot']}  {s['start']:.2f}-{s['end']:.2f}s  {s['frames']}f")
            base = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{mid:.4f}", "-i", a.video,
                    "-map", f"0:{info['video_index']}", "-frames:v", "1", "-q:v", "3", "-update", "1"]
            scale = "scale=360:640:force_original_aspect_ratio=decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2"
            dt = (f",drawtext=textfile='{ff_escape(label)}':expansion=none:x=8:y=8:fontsize=20:"
                  "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=4")
            if run(base + ["-vf", tm + scale + dt, dst], check=False).returncode != 0:
                run(base + ["-vf", tm + scale, dst], check=False)
        if os.path.exists(os.path.join(sd, ".label.txt")):
            os.unlink(os.path.join(sd, ".label.txt"))
        for old in os.listdir(out):
            if old.startswith("shots_sheet_"):
                os.unlink(os.path.join(out, old))
        cols = 6
        rows = min(4, (len(shots) + cols - 1) // cols)
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-framerate", "1", "-start_number", "1",
             "-i", os.path.join(sd, "shot_%03d.jpg"), "-vf", f"tile={cols}x{rows}:padding=4:color=black",
             "-q:v", "3", os.path.join(out, "shots_sheet_%02d.jpg")], check=False)

    # report
    print(f"\n{len(shots)} shots / {len(shots) - 1} cuts in {dur:.2f}s @ {fps} fps  "
          f"(avg {summary['avg_shot_len']:.2f}s, median {summary['median_shot_len']:.2f}s, "
          f"min {summary['min_shot_len']:.2f}s, max {summary['max_shot_len']:.2f}s)")
    print(f"{'#':>3} {'start':>8} {'end':>8} {'frames':>6} {'dur':>6} {'luma':>5} {'sat':>5} {'motion':>8}  notes")
    for s in shots:
        print(f"{s['shot']:>3} {fmt_t(s['start']):>8} {fmt_t(s['end']):>8} {s['frames']:>6} {s['dur']:>6.2f} "
              f"{s['luma']:>5.0f} {s['sat']:>5.0f} {s['motion_label']:>8}  {', '.join(s['notes'])}")
    print("pace (cuts per 5s): " + "  ".join(f"{p['from']:.0f}-{p['to']:.0f}s:{p['cuts']}" for p in pace))
    if data["soft_transition_suspects"]:
        print("soft-transition suspects (check frames): " +
              ", ".join(f"{x['from']:.2f}-{x['to']:.2f}s" for x in data["soft_transition_suspects"]))
    print(f"\nwrote {os.path.join(out, 'cuts.json')}" + ("" if a.no_thumbs else f" + shots/ + shots_sheet_*.jpg"))


if __name__ == "__main__":
    main()
