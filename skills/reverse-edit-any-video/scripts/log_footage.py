#!/usr/bin/env python3
"""Log every clip in a footage folder so Claude can "watch" it and pick the best parts.

Per clip: orientation, resolution, fps, duration, HDR flag, audio, a per-second activity curve
(motion + brightness + internal cuts) and timestamped contact sheets (6 columns, burned-in clip
time). Photos are logged too (usable as stills).

Usage:
  log_footage.py FOOTAGE_DIR --out JOB/footage [--every 1.0] [--workers 4]

Writes OUT/index.json, OUT/index.md and OUT/sheets/<clip>_NN.jpg.
Then: read the sheets (all of them), write OUT/selects.md (see references/footage-and-selects.md).
"""
from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reav_common import (IMAGE_EXT, VIDEO_EXT, ff_escape, fmt_t, need, probe, run, save_json,  # noqa: E402
                         tonemap_chain)

FRAME_RE = re.compile(r"pts_time:\s*(-?[\d.]+)")
KV_RE = re.compile(r"lavfi\.(scene_score|signalstats\.YAVG|signalstats\.YDIF)=(-?[\d.]+)")


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(name)[0])


def activity(path: str, info: dict) -> list[dict]:
    """Per-second motion (YDIF), brightness and internal cut count, decoded at 10 fps / 160 px."""
    tmp = tempfile.NamedTemporaryFile(prefix="reav_log_", suffix=".txt", delete=False)
    tmp.close()
    vf = (f"fps=10,{tonemap_chain(info)}scale=160:-2:flags=area,select='gte(scene\\,0)',signalstats,"
          f"metadata=mode=print:file='{ff_escape(tmp.name)}'")
    run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", f"0:{info['video_index']}",
         "-vf", vf, "-an", "-f", "null", "-"], check=False)
    rows, cur = [], None
    with open(tmp.name) as f:
        for line in f:
            m = FRAME_RE.search(line)
            if m:
                cur = {"t": float(m.group(1)), "scene": 0.0, "y": 0.0, "ydif": 0.0}
                rows.append(cur)
                continue
            k = KV_RE.search(line)
            if k and cur is not None:
                key = {"scene_score": "scene", "signalstats.YAVG": "y", "signalstats.YDIF": "ydif"}[k.group(1)]
                cur[key] = float(k.group(2))
    os.unlink(tmp.name)
    if not rows:
        return []
    t0 = rows[0]["t"]
    secs: dict[int, list] = {}
    for r in rows:
        secs.setdefault(int(r["t"] - t0), []).append(r)
    out = []
    for s in sorted(secs):
        rr = secs[s]
        out.append({
            "t": s,
            "motion": round(statistics.fmean(x["ydif"] for x in rr), 2),
            "luma": round(statistics.fmean(x["y"] for x in rr)),
            "cuts": sum(1 for x in rr if x["scene"] > 0.35),
        })
    return out


def sheets(path: str, info: dict, out_dir: str, every: float, cols: int = 6, rows: int = 5) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    base = slug(info["name"])
    for old in os.listdir(out_dir):
        if old.startswith(base + "_") and old.endswith(".jpg"):
            os.unlink(os.path.join(out_dir, old))
    portrait = info["display_height"] >= info["display_width"]
    cell = "216:384" if portrait else "384:216"
    tm = tonemap_chain(info)
    if info["is_image"]:
        dst = os.path.join(out_dir, f"{base}_01.jpg")
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", path, "-frames:v", "1", "-vf",
             f"scale={cell}:force_original_aspect_ratio=decrease", "-q:v", "3", dst], check=False)
        return [dst] if os.path.exists(dst) else []
    pattern = os.path.join(out_dir, f"{base}_%02d.jpg")
    common = (f"fps=1/{every},{tm}scale={cell}:force_original_aspect_ratio=decrease,"
              f"pad={cell}:(ow-iw)/2:(oh-ih)/2")
    stamp = (",drawtext=text='%{pts\\:hms}':x=6:y=6:fontsize=18:fontcolor=white:"
             "box=1:boxcolor=black@0.6:boxborderw=3")
    tile = f",tile={cols}x{rows}:padding=3:color=black"
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", path, "-map", f"0:{info['video_index']}",
           "-q:v", "3"]
    if run(cmd + ["-vf", common + stamp + tile, pattern], check=False).returncode != 0:
        run(cmd + ["-vf", common + tile, pattern], check=False)  # no fontconfig -> no timestamps
    return sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir)
                  if f.startswith(base + "_") and f.endswith(".jpg"))


def log_one(path: str, out: str, every: float | None) -> dict:
    info = probe(path)
    if not info.get("has_video"):
        return {"name": os.path.basename(path), "path": os.path.abspath(path), "error": "no video stream"}
    dur = info.get("duration") or 0
    step = every or (0.5 if dur <= 8 else 1.0 if dur <= 40 else 2.0 if dur <= 120 else 5.0)
    act = [] if info["is_image"] else activity(path, info)
    sh = sheets(path, info, os.path.join(out, "sheets"), step)
    motions = [a["motion"] for a in act] or [0]
    rec = {
        "name": info["name"], "path": info["path"], "type": "image" if info["is_image"] else "video",
        "duration": round(dur, 3) if dur else None,
        "width": info["display_width"], "height": info["display_height"], "orientation": info["orientation"],
        "fps": info.get("fps"), "hdr": info.get("hdr"), "color_transfer": info.get("color_transfer"),
        "has_audio": info.get("has_audio"),
        "sheet_every_s": step, "sheets": [os.path.relpath(s, out) for s in sh],
        "motion_median": round(statistics.median(motions), 2),
        "motion_peak_s": max(act, key=lambda a: a["motion"])["t"] if act else None,
        "internal_cuts": sum(a["cuts"] for a in act),
        "activity": act,
    }
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("footage")
    ap.add_argument("--out", required=True)
    ap.add_argument("--every", type=float, default=None, help="seconds between sheet frames (default: by length)")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    need("ffmpeg")
    files = []
    for root, _dirs, names in os.walk(a.footage):
        if os.path.abspath(root).startswith(os.path.abspath(a.out)):
            continue
        for n in sorted(names):
            ext = os.path.splitext(n)[1].lower()
            if n.startswith("."):
                continue
            if ext in VIDEO_EXT or ext in IMAGE_EXT:
                files.append(os.path.join(root, n))
    if not files:
        print("no video/image files found in " + a.footage, file=sys.stderr)
        sys.exit(1)
    os.makedirs(a.out, exist_ok=True)
    print(f"Logging {len(files)} files with {a.workers} workers...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        recs = list(ex.map(lambda p: log_one(p, a.out, a.every), files))
    total = sum(r.get("duration") or 0 for r in recs)
    save_json(os.path.join(a.out, "index.json"), {"footage_dir": os.path.abspath(a.footage),
                                                  "total_duration": round(total, 2), "clips": recs})
    lines = [f"# Footage log: {os.path.abspath(a.footage)}", "",
             f"{len(recs)} files, {total / 60:.1f} min total. Motion = mean frame difference "
             "(<1.5 static/locked-off, 1.5-4 gentle, 4-9 moving, >9 fast/shaky).", "",
             "| clip | type | dur | WxH | orient | fps | HDR | audio | motion (median / peak at) | sheets |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        if r.get("error"):
            lines.append(f"| {r['name']} | ERROR: {r['error']} |||||||||")
            continue
        lines.append(f"| {r['name']} | {r['type']} | {fmt_t(r['duration']) if r['duration'] else '-'} | "
                     f"{r['width']}x{r['height']} | {r['orientation']} | {r['fps'] or '-'} | "
                     f"{'YES' if r['hdr'] else '-'} | {'yes' if r['has_audio'] else '-'} | "
                     f"{r['motion_median']} / {r['motion_peak_s'] if r['motion_peak_s'] is not None else '-'}s | "
                     f"{', '.join(r['sheets'])} |")
    lines += ["", "Next: open every sheet, then write selects.md (best moments with in/out, shot type, "
              "motion, energy, story role, quality notes)."]
    with open(os.path.join(a.out, "index.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    hdr = [r["name"] for r in recs if r.get("hdr")]
    if hdr:
        print(f"\nHDR clips (render.py tonemaps them automatically): {', '.join(hdr)}")


if __name__ == "__main__":
    main()
