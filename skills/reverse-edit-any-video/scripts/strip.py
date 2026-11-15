#!/usr/bin/env python3
"""Frame-by-frame strip around moments of a video - to SEE a transition, text animation, speed ramp,
whip or flash that a 2 fps grid skips. Every frame is labelled with its timeline frame number.

Usage:
  strip.py VIDEO --at 7.67 [--at 8.97 ...] [--before 4] [--after 6] [--fps 30] [--width 240] [--out DIR]
  strip.py VIDEO --cuts analysis/cuts.json        (one strip per cut)

Writes DIR/strip_<time>.jpg (default DIR = <video dir>/strips).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reav_common import ff_escape, load_json, need, probe, run, snap_fps, tonemap_chain  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--at", type=float, action="append", default=[])
    ap.add_argument("--cuts")
    ap.add_argument("--before", type=int, default=4)
    ap.add_argument("--after", type=int, default=6)
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--width", type=int, default=240)
    ap.add_argument("--out")
    a = ap.parse_args()
    need("ffmpeg")
    info = probe(a.video)
    fps = a.fps or (load_json(a.cuts)["fps"] if a.cuts else snap_fps(info["fps"]))
    if fps not in (24, 25, 30, 48, 50, 60):
        fps = 30
    times = list(a.at)
    if a.cuts:
        times += [s["start"] for s in load_json(a.cuts)["shots"][1:]]
    if not times:
        sys.exit("give --at SECONDS or --cuts cuts.json")
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.video)), "strips")
    os.makedirs(out, exist_ok=True)
    n = a.before + a.after
    for t in times:
        f0 = max(0, int(round(t * fps)) - a.before)  # seek on the frame grid so labels match cuts.json
        start = f0 / fps
        dst = os.path.join(out, f"strip_{t:07.3f}s.jpg".replace(".", "_", 1))
        label = ("drawtext=text='f%{eif\\:n+" + str(f0) + "\\:d}':x=6:y=6:fontsize=20:fontcolor=white:"
                 "box=1:boxcolor=black@0.6:boxborderw=3")
        base = (f"fps={fps},{tonemap_chain(info)}scale={a.width}:-2")
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{start:.4f}", "-i", a.video,
               "-map", f"0:{info['video_index']}", "-frames:v", "1", "-q:v", "3", "-update", "1"]
        tile = f"tile={min(n, 10)}x{(n + 9) // 10}:padding=3:color=black"
        if run(cmd + ["-vf", f"{base},{label},{tile}", dst], check=False).returncode != 0:
            run(cmd + ["-vf", f"{base},{tile}", dst], check=False)
        print(dst)


if __name__ == "__main__":
    main()
