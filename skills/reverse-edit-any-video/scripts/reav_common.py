"""Shared helpers for the Reverse Edit Any Video scripts (stdlib only, Python 3.9+)."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys

# Homebrew's plain `ffmpeg` formula lacks drawtext/zscale; `ffmpeg-full` is keg-only. Prefer it when present.
for _d in (os.environ.get("REAV_FFMPEG_DIR", ""), "/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin"):
    if _d and os.path.isfile(os.path.join(_d, "ffmpeg")):
        if not os.environ.get("PATH", "").startswith(_d):
            os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
        break

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts", ".3gp"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".bmp"}
STANDARD_FPS = [23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 120]
HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def need(binary: str):
    if not shutil.which(binary):
        die(f"'{binary}' not found. Run scripts/setup.sh first.")


def run(cmd: list[str], capture: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None)
    if check and p.returncode != 0:
        err = (p.stderr or b"").decode(errors="replace")[-3000:]
        die(f"command failed ({p.returncode}): {' '.join(cmd[:8])} ...\n{err}")
    return p


def parse_rate(r: str | None) -> float:
    if not r or r in ("0/0", "N/A"):
        return 0.0
    if "/" in r:
        a, b = r.split("/", 1)
        try:
            return float(a) / float(b) if float(b) else 0.0
        except ValueError:
            return 0.0
    try:
        return float(r)
    except ValueError:
        return 0.0


def snap_fps(f: float) -> float:
    """Snap a measured frame rate to the nearest standard one (IG/TikTok VFR downloads report odd rates)."""
    if f <= 0:
        return 30.0
    best = min(STANDARD_FPS, key=lambda s: abs(s - f) / s)
    if abs(best - f) / best < 0.04:
        return {23.976: 24, 29.97: 30, 59.94: 60}.get(best, best)
    return round(f, 3)


def probe(path: str) -> dict:
    """Return a compact description of a media file: picks the real video stream (skips cover art)."""
    need("ffprobe")
    p = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    d = json.loads(p.stdout or b"{}")
    streams = d.get("streams", [])
    fmt = d.get("format", {})
    v = None
    for s in streams:
        if s.get("codec_type") != "video":
            continue
        if s.get("disposition", {}).get("attached_pic") == 1:
            continue
        if s.get("codec_name") in ("mjpeg", "png") and s.get("avg_frame_rate") in ("0/0", None) \
                and os.path.splitext(path)[1].lower() not in IMAGE_EXT:
            continue
        v = s
        break
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    info = {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "duration": float(fmt.get("duration") or 0) or None,
        "has_audio": a is not None,
        "audio_index": a.get("index") if a else None,
        "is_image": os.path.splitext(path)[1].lower() in IMAGE_EXT,
    }
    if v is None:
        info.update({"has_video": False})
        return info
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            try:
                rot = int(float(sd["rotation"]))
            except (TypeError, ValueError):
                pass
    if not rot:
        try:
            rot = int(v.get("tags", {}).get("rotate", 0))
        except (TypeError, ValueError):
            rot = 0
    dw, dh = (h, w) if abs(rot) % 180 == 90 else (w, h)
    avg = parse_rate(v.get("avg_frame_rate"))
    rfr = parse_rate(v.get("r_frame_rate"))
    fps = avg if 1 <= avg <= 240 else rfr
    nb = int(v.get("nb_frames") or 0)
    dur = float(v.get("duration") or 0) or info["duration"] or 0
    if nb and dur and (fps <= 0 or abs(nb / dur - fps) / max(fps, 1) > 0.15):
        fps = nb / dur  # VFR container: trust frame count over the header
    trc = v.get("color_transfer") or ""
    info.update({
        "has_video": True,
        "video_index": v.get("index", 0),
        "codec": v.get("codec_name"),
        "width": w, "height": h, "rotation": rot,
        "display_width": dw, "display_height": dh,
        "orientation": "portrait" if dh > dw else ("square" if dh == dw else "landscape"),
        "fps": round(fps, 4), "fps_snapped": snap_fps(fps),
        "pix_fmt": v.get("pix_fmt"),
        "color_transfer": trc, "color_primaries": v.get("color_primaries") or "",
        "hdr": trc in HDR_TRANSFERS,
        "bit_depth": 10 if "10" in (v.get("pix_fmt") or "") else 8,
    })
    if info["is_image"]:
        info["duration"] = None
    return info


def tonemap_chain(info: dict) -> str:
    """Filter chain that brings HDR (HLG/PQ, e.g. iPhone Dolby Vision) to SDR BT.709. Empty for SDR."""
    if not info.get("hdr"):
        return ""
    return ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
            "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,")


def has_filter(name: str) -> bool:
    p = run(["ffmpeg", "-hide_banner", "-filters"], check=False)
    return re.search(rf"\s{name}\s", (p.stdout or b"").decode()) is not None


def ff_escape(path: str) -> str:
    """Escape a path for use inside an ffmpeg filter argument (single-quoted)."""
    return path.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def safe_copy(path: str, tmpdir: str) -> str:
    """drawtext/lut3d choke on some paths (spaces, quotes): copy the file to a plain name in tmpdir."""
    os.makedirs(tmpdir, exist_ok=True)
    base = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(path))
    dst = os.path.join(tmpdir, base)
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(path):
        shutil.copy2(path, dst)
    return dst


def read_rgb_frames(path: str, start: float | None, end: float | None, width: int = 160,
                     samples: int = 6, tonemap: str = "", lut: str | None = None):
    """Yield (w, h, rgb_bytes) for `samples` frames spread across [start, end]."""
    info = probe(path)
    dur = info.get("duration") or 0
    s = start or 0.0
    e = end if end is not None else dur
    if info.get("is_image"):
        times = [0.0]
    else:
        e = max(s + 0.04, e)
        span = e - s
        times = [s + span * (i + 0.5) / samples for i in range(samples)]
    vf = f"{tonemap}scale={width}:-2:flags=area"
    if lut:
        vf += f",format=gbrpf32le,lut3d=file='{ff_escape(lut)}':interp=tetrahedral"
    vf += ",format=rgb24"
    for t in times:
        cmd = ["ffmpeg", "-v", "error", "-nostdin"]
        if not info.get("is_image"):
            cmd += ["-ss", f"{t:.4f}"]
        cmd += ["-i", path, "-map", f"0:{info.get('video_index', 0)}", "-frames:v", "1",
                "-vf", vf, "-f", "rawvideo", "-"]
        p = run(cmd, check=False)
        buf = p.stdout or b""
        if not buf:
            continue
        # height from buffer length
        h = len(buf) // (width * 3)
        if h <= 0:
            continue
        yield width, h, buf[: width * h * 3]


def rgb_stats(frames) -> dict:
    """Colour statistics for a set of RGB24 frames (all values 0-255 except sat 0-1)."""
    hist = [0] * 256
    n = 0
    sr = sg = sb = 0
    sat_sum = 0.0
    lo_acc = [0, 0, 0, 0]
    hi_acc = [0, 0, 0, 0]
    pix = []
    for _w, _h, buf in frames:
        mv = memoryview(buf)
        for i in range(0, len(mv) - 2, 3):
            r, g, b = mv[i], mv[i + 1], mv[i + 2]
            y = (2126 * r + 7152 * g + 722 * b) // 10000
            hist[y] += 1
            n += 1
            sr += r; sg += g; sb += b
            mx = r if r > g else g
            mx = mx if mx > b else b
            if mx:
                mn = r if r < g else g
                mn = mn if mn < b else b
                sat_sum += (mx - mn) / mx
            pix.append((y, r, g, b))
    if not n:
        return {}

    def pct(p):
        target = n * p
        c = 0
        for i, v in enumerate(hist):
            c += v
            if c >= target:
                return i
        return 255

    p2, p25, p50, p75, p98 = pct(0.02), pct(0.25), pct(0.5), pct(0.75), pct(0.98)
    # neutral zones: near-grey pixels (clouds, snow, concrete, shadows) carry the white balance /
    # split-tone of a grade; saturated pixels mostly carry *content* colour (grass, sky, skin).
    neu = {z: [0, 0, 0, 0] for z in ("shadow", "mid", "high")}
    for y, r, g, b in pix:
        if y <= p25:
            lo_acc[0] += r; lo_acc[1] += g; lo_acc[2] += b; lo_acc[3] += 1
        elif y >= p75:
            hi_acc[0] += r; hi_acc[1] += g; hi_acc[2] += b; hi_acc[3] += 1
        mx = max(r, g, b)
        if mx > 12 and (mx - min(r, g, b)) / mx < 0.22:
            z = "shadow" if y < 77 else "high" if y > 166 else "mid"
            acc = neu[z]
            acc[0] += r; acc[1] += g; acc[2] += b; acc[3] += 1

    def avg(acc):
        k = max(acc[3], 1)
        return [round(acc[0] / k, 1), round(acc[1] / k, 1), round(acc[2] / k, 1)]

    def offset(acc):
        """chroma offset (rgb - luma) of a neutral zone, or None when the zone is too rare to trust"""
        if acc[3] < n * 0.01:
            return None
        rr, gg, bb = acc[0] / acc[3], acc[1] / acc[3], acc[2] / acc[3]
        yy = 0.2126 * rr + 0.7152 * gg + 0.0722 * bb
        return [round(rr - yy, 2), round(gg - yy, 2), round(bb - yy, 2)]

    mean = [round(sr / n, 1), round(sg / n, 1), round(sb / n, 1)]
    return {
        "luma_p2": p2, "luma_p25": p25, "luma_p50": p50, "luma_p75": p75, "luma_p98": p98,
        "mean_rgb": mean,
        "shadow_rgb": avg(lo_acc), "highlight_rgb": avg(hi_acc),
        "neutral_offsets": {z: offset(acc) for z, acc in neu.items()},
        "saturation": round(sat_sum / n, 3),
        "warmth": round(mean[0] - mean[2], 1),             # + warm / - cool (content-dependent)
        "tint": round(mean[1] - (mean[0] + mean[2]) / 2, 1),  # + green / - magenta (content-dependent)
        "pixels": n,
    }


def describe_color(st: dict) -> str:
    """Plain-language read of rgb_stats(), for style.md."""
    if not st:
        return "n/a"
    parts = []
    contrast = st["luma_p98"] - st["luma_p2"]
    parts.append("high contrast" if contrast > 215 else "low contrast / matte" if contrast < 165 else "normal contrast")
    if st["luma_p2"] > 22:
        parts.append(f"lifted blacks (p2={st['luma_p2']})")
    elif st["luma_p2"] < 6:
        parts.append("crushed blacks")
    if st["luma_p98"] < 225:
        parts.append(f"soft highlight ceiling (p98={st['luma_p98']})")
    parts.append("bright" if st["luma_p50"] > 150 else "dark/moody" if st["luma_p50"] < 80 else "mid exposure")
    s = st["saturation"]
    parts.append("very saturated" if s > 0.5 else "saturated" if s > 0.35 else "muted" if s < 0.2 else "natural saturation")
    w = st["warmth"]
    parts.append("overall warm palette" if w > 12 else "overall cool palette" if w < -12 else "balanced palette")
    no = st.get("neutral_offsets") or {}

    def tone(o):
        if not o:
            return None
        warm = o[0] - o[2]
        green = o[1] - (o[0] + o[2]) / 2
        bits = []
        if warm > 4:
            bits.append("warm")
        elif warm < -4:
            bits.append("cool/teal" if green > 0 else "cool/blue")
        if green > 3:
            bits.append("green")
        elif green < -3:
            bits.append("magenta")
        return "/".join(bits) or "neutral"

    zt = {z: tone(no.get(z)) for z in ("shadow", "mid", "high")}
    zt = {z: v for z, v in zt.items() if v}
    if zt:
        parts.append("greys read: " + ", ".join(f"{z} {v}" for z, v in zt.items()))
    if zt.get("shadow", "").startswith("cool") and zt.get("high", "").startswith("warm"):
        parts.append("split-tone teal-orange")
    return ", ".join(parts)


def load_json(path: str):
    with open(path) as f:
        return json.load(f)


def save_json(path: str, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def fmt_t(t: float) -> str:
    m = int(t // 60)
    return f"{m}:{t - 60 * m:05.2f}"


def ceil_even(x: float) -> int:
    return int(math.ceil(x / 2.0)) * 2
