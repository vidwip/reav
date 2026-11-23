#!/usr/bin/env python3
"""Start a Reverse Edit job: folders, reference download/copy, soundtrack, style.md skeleton.

Usage:
  new_job.py --ref URL_OR_FILE --footage DIR [--name NAME] [--root DIR] [--remotion]

Creates ROOT/reav-projects/NAME/ (ROOT defaults to the current directory):
  ref/reference.mp4  ref/audio.wav   analysis/  footage/  grading/  fonts/  build/  out/  review/
  style.md (skeleton to fill in)     job.json
  remotion/ (with --remotion: template + node_modules cloned from the setup.sh cache)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reav_common import die, need, probe, run  # noqa: E402

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def name_from(ref: str) -> str:
    m = re.search(r"/(?:reel|reels|p|shorts|video)/([A-Za-z0-9_-]{5,})", ref)
    if m:
        return m.group(1)
    if os.path.exists(ref):
        return re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(os.path.basename(ref))[0])[:40]
    return "job_" + datetime.datetime.now().strftime("%Y%m%d_%H%M")


def fetch(ref: str, dst_dir: str) -> str:
    os.makedirs(dst_dir, exist_ok=True)
    if os.path.exists(ref):
        ext = os.path.splitext(ref)[1].lower() or ".mp4"
        dst = os.path.join(dst_dir, "reference" + ext)
        if os.path.abspath(ref) != os.path.abspath(dst):
            shutil.copy2(ref, dst)
        return dst
    if not shutil.which("yt-dlp"):
        die("yt-dlp not installed (run setup.sh) - or download the reference yourself and pass the file")
    out_t = os.path.join(dst_dir, "reference.%(ext)s")
    cmd = ["yt-dlp", "--no-playlist", "-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", out_t, ref]
    print("downloading reference:", ref, file=sys.stderr)
    p = subprocess.run(cmd)
    if p.returncode != 0:
        die("yt-dlp failed. Private/age-gated posts need cookies: add --cookies-from-browser chrome "
            "(ask the user first), or have the user download the video and pass the file.")
    for f in os.listdir(dst_dir):
        if f.startswith("reference."):
            return os.path.join(dst_dir, f)
    die("download finished but no reference file found")
    return ""


def clone_tree(src: str, dst: str):
    if sys.platform == "darwin":
        r = subprocess.run(["cp", "-Rc", src, dst])  # APFS clone: instant, no extra disk
    else:
        r = subprocess.run(["cp", "-R", "--reflink=auto", src, dst])
    if r.returncode != 0:
        shutil.copytree(src, dst, symlinks=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", required=True, help="reference URL (Instagram/TikTok/YouTube...) or video file")
    ap.add_argument("--footage", required=True, help="folder with the user's clips")
    ap.add_argument("--name")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--remotion", action="store_true", help="also set up the Remotion effects project")
    a = ap.parse_args()
    need("ffmpeg")
    if not os.path.isdir(a.footage):
        die(f"footage folder not found: {a.footage}")

    name = a.name or name_from(a.ref)
    job = os.path.join(os.path.abspath(a.root), "reav-projects", name)
    for d in ("ref", "analysis", "footage", "grading", "fonts", "build", "out", "review"):
        os.makedirs(os.path.join(job, d), exist_ok=True)

    ref = fetch(a.ref, os.path.join(job, "ref"))
    info = probe(ref)
    wav = os.path.join(job, "ref", "audio.wav")
    if info.get("has_audio"):
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", ref, "-map", "0:a:0", "-ac", "2", "-ar", "48000",
             "-c:a", "pcm_s16le", wav])

    style = os.path.join(job, "style.md")
    if not os.path.exists(style):
        shutil.copy2(os.path.join(SKILL, "templates", "style.md"), style)

    if a.remotion:
        rdir = os.path.join(job, "remotion")
        if not os.path.exists(rdir):
            shutil.copytree(os.path.join(SKILL, "templates", "remotion"), rdir)
        cache = os.path.join(os.environ.get("REAV_CACHE", os.path.expanduser("~/.cache/reav")), "remotion",
                             "node_modules")
        nm = os.path.join(rdir, "node_modules")
        if not os.path.exists(nm):
            if os.path.isdir(cache):
                clone_tree(cache, nm)
            else:
                print("no Remotion cache - running npm install (setup.sh caches this for next time)", file=sys.stderr)
                subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"], cwd=rdir)

    meta = {
        "name": name, "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "reference_source": a.ref, "reference": ref, "footage": os.path.abspath(a.footage),
        "reference_info": {k: info.get(k) for k in ("duration", "display_width", "display_height", "fps",
                                                   "fps_snapped", "orientation", "has_audio", "hdr")},
    }
    with open(os.path.join(job, "job.json"), "w") as f:
        json.dump(meta, f, indent=2)

    S = os.path.join(SKILL, "scripts")
    q = lambda p: f'"{p}"' if " " in p else p  # noqa: E731
    print(f"""
Job ready: {job}
reference: {os.path.basename(ref)}  {info.get('display_width')}x{info.get('display_height')}  {info.get('fps')} fps  {info.get('duration') or 0:.2f}s  audio={'yes' if info.get('has_audio') else 'no'}

Next (from the job dir):
  python3 {q(S + '/cuts.py')} ref/{os.path.basename(ref)} --out analysis
  python3 {q(S + '/beats.py')} ref/audio.wav --cuts analysis/cuts.json --out analysis/beats.json
  python3 {q(S + '/color.py')} measure ref/{os.path.basename(ref)} --cuts analysis/cuts.json --out analysis/ref_color.json
  python3 {q(S + '/log_footage.py')} {q(os.path.abspath(a.footage))} --out footage
""")


if __name__ == "__main__":
    main()
