#!/usr/bin/env python3
"""Measure a look, then build a LUT that moves footage onto it (the "color correction" part of style.md).

  measure  VIDEO --cuts cuts.json [--out ref_color.json]     per-shot + overall look of the reference
  measure  VIDEO --range 2.0-4.5 [--range ...] [--lut X.cube] stats of clip ranges (optionally graded)
  match    --ref ref_color.json --src CLIP@A-B [--src ...] --out look.cube
           [--ref-shots 2,3] [--strength 0.85] [--sat-mult 1.0]
  check    --ref ref_color.json --src CLIP@A-B --lut look.cube [--ref-shots ...]

match fits a tone curve (black point / mids / highlight ceiling), a saturation scale and
shadow/mid/highlight colour balance on sampled pixels of the source, iterating until the measured
stats hit the target, then writes a 33^3 .cube for ffmpeg `lut3d` (apply in gbrpf32le, after any
HDR tonemap). Stats are on full-range RGB 0-255. Stdlib only.
"""
from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reav_common import (die, describe_color, load_json, need, probe, read_rgb_frames, rgb_stats,  # noqa: E402
                         save_json, tonemap_chain)


# ----------------------------------------------------------------------------- sampling

def parse_src(spec: str):
    """CLIP or CLIP@A-B (seconds)."""
    if "@" in spec and os.path.exists(spec.rsplit("@", 1)[0]):
        path, rng = spec.rsplit("@", 1)
        a, b = rng.split("-", 1)
        return path, float(a), float(b)
    if not os.path.exists(spec):
        die(f"not found: {spec}")
    return spec, None, None


def sample(path, start, end, n=6, lut=None, width=160):
    info = probe(path)
    return list(read_rgb_frames(path, start, end, width=width, samples=n,
                                tonemap=tonemap_chain(info), lut=lut))


def measure_cuts(video, cuts):
    shots, pooled = [], []
    for s in cuts["shots"]:
        pad = s["dur"] * 0.12 if s["frames"] > 6 else 0
        n = 1 if s["frames"] <= 4 else max(2, min(8, int(round(s["dur"] * 2))))
        fr = sample(video, s["start"] + pad, s["end"] - pad, n=n)
        st = rgb_stats(fr)
        pooled += fr
        shots.append({"shot": s["shot"], "start": s["start"], "end": s["end"], "stats": st,
                      "read": describe_color(st)})
    overall = rgb_stats(pooled)
    return {"source": os.path.abspath(video), "overall": overall, "overall_read": describe_color(overall),
            "shots": shots}


def target_from(ref: dict, shots: str | None) -> dict:
    if not shots:
        return ref["overall"]
    want = {int(x) for x in shots.split(",")}
    sel = [s["stats"] for s in ref["shots"] if s["shot"] in want and s["stats"]]
    if not sel:
        die(f"no shots {sorted(want)} in ref")
    keys = ["luma_p2", "luma_p25", "luma_p50", "luma_p75", "luma_p98", "saturation", "warmth", "tint"]
    out = {k: sum(s[k] for s in sel) / len(sel) for k in keys}
    for k in ["mean_rgb", "shadow_rgb", "highlight_rgb"]:
        out[k] = [sum(s[k][c] for s in sel) / len(sel) for c in range(3)]
    return out


# ----------------------------------------------------------------------------- the look model

def lum(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def monotone_table(xs, ys, n=1024):
    """Fritsch-Carlson monotone cubic through (xs, ys), tabulated on [0,1]."""
    pts = sorted(zip(xs, ys))
    dedup = []
    for x, y in pts:
        if dedup and x - dedup[-1][0] < 1e-3:
            continue
        dedup.append((x, y))
    xs = [p[0] for p in dedup]
    ys = [p[1] for p in dedup]
    for i in range(1, len(ys)):  # enforce monotone
        ys[i] = max(ys[i], ys[i - 1] + 1e-4)
    k = len(xs)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(k - 1)]
    m = [d[0]] + [(d[i - 1] + d[i]) / 2 if d[i - 1] * d[i] > 0 else 0 for i in range(1, k - 1)] + [d[-1]]
    for i in range(k - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9:
            t = 3 / s ** 0.5
            m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    tab = []
    j = 0
    for q in range(n):
        x = q / (n - 1)
        while j < k - 2 and x > xs[j + 1]:
            j += 1
        h = xs[j + 1] - xs[j]
        t = min(1.0, max(0.0, (x - xs[j]) / h))
        h00, h10 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t
        h01, h11 = -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        tab.append(min(1.0, max(0.0, h00 * ys[j] + h10 * h * m[j] + h01 * ys[j + 1] + h11 * h * m[j + 1])))
    return tab


class Look:
    KEYS = ("luma_p2", "luma_p25", "luma_p50", "luma_p75", "luma_p98")

    def __init__(self, src: dict, tgt: dict):
        self.xs = [0.0] + [src[k] / 255 for k in self.KEYS] + [1.0]
        self.ys = [0.0] + [tgt[k] / 255 for k in self.KEYS] + [1.0]
        # endpoints follow the target black point / highlight ceiling
        self.ys[0] = max(0.0, min(self.ys[1], self.ys[1] - self.xs[1] * 0.8))
        self.ys[-1] = min(1.0, max(self.ys[-2], self.ys[-2] + (1 - self.xs[-2]) * 0.8))
        self.k = max(0.4, min(1.8, (tgt["saturation"] / src["saturation"]) if src["saturation"] else 1.0))
        self.bal = {"s": [0.0, 0.0, 0.0], "m": [0.0, 0.0, 0.0], "h": [0.0, 0.0, 0.0]}
        self.rebuild()

    def rebuild(self):
        self.tab = monotone_table(self.xs, self.ys)

    def curve(self, y):
        i = y * 1023
        i0 = int(i)
        if i0 >= 1023:
            return self.tab[1023]
        f = i - i0
        return self.tab[i0] * (1 - f) + self.tab[i0 + 1] * f

    def apply(self, r, g, b):
        y = lum(r, g, b)
        y2 = self.curve(min(1.0, max(0.0, y)))
        w = smooth(0.02, 0.15, y)
        if y > 1e-5:
            ratio = y2 / y
            r1, g1, b1 = r * ratio, g * ratio, b * ratio
        else:
            r1 = g1 = b1 = y2
        d = y2 - y
        r = w * r1 + (1 - w) * (r + d)
        g = w * g1 + (1 - w) * (g + d)
        b = w * b1 + (1 - w) * (b + d)
        yy = lum(r, g, b)
        k = self.k
        if k > 1:  # gamut protection: never push a channel past 0/1 (no clipping / hue shifts)
            for c in (r, g, b):
                if c > yy + 1e-6:
                    k = min(k, max(1.0, (1 - yy) / (c - yy)))
                elif c < yy - 1e-6:
                    k = min(k, max(1.0, yy / (yy - c)))
        r, g, b = yy + (r - yy) * k, yy + (g - yy) * k, yy + (b - yy) * k
        ws, wh, wm = zone_weights(yy)
        bs, bm, bh = self.bal["s"], self.bal["m"], self.bal["h"]
        r += ws * bs[0] + wm * bm[0] + wh * bh[0]
        g += ws * bs[1] + wm * bm[1] + wh * bh[1]
        b += ws * bs[2] + wm * bm[2] + wh * bh[2]
        return min(1.0, max(0.0, r)), min(1.0, max(0.0, g)), min(1.0, max(0.0, b))


def zone_weights(y):
    """shadow / mid / highlight weights; bands match the neutral zones in rgb_stats (77, 166 of 255)."""
    ws = 1 - smooth(0.22, 0.38, y)
    wh = smooth(0.58, 0.72, y)
    return ws, wh, max(0.0, 1 - ws - wh)


def stats_after(look: Look, pix: list) -> dict:
    buf = bytearray()
    for r, g, b in pix:
        R, G, B = look.apply(r, g, b)
        buf += bytes((int(R * 255 + 0.5), int(G * 255 + 0.5), int(B * 255 + 0.5)))
    return rgb_stats([(0, 0, bytes(buf))])


def neutral_offsets_after(look: Look, neutral_pix: list) -> dict:
    """Where do the source's grey pixels land after the grade? -> chroma offset per luma zone (0-255)."""
    acc = {"shadow": [0.0, 0.0, 0.0, 0], "mid": [0.0, 0.0, 0.0, 0], "high": [0.0, 0.0, 0.0, 0]}
    for r, g, b in neutral_pix:
        R, G, B = look.apply(r, g, b)
        y = lum(R, G, B)
        z = "shadow" if y < 77 / 255 else "high" if y > 166 / 255 else "mid"
        a = acc[z]
        a[0] += R - y; a[1] += G - y; a[2] += B - y; a[3] += 1
    total = max(len(neutral_pix), 1)
    return {z: ([a[0] / a[3] * 255, a[1] / a[3] * 255, a[2] / a[3] * 255] if a[3] >= max(20, total * 0.02) else None)
            for z, a in acc.items()}


def fit(src_frames, src_stats, tgt, sat_mult=1.0, sat_damp=0.6, balance=1.0, iters=6, verbose=True):
    pix = []
    for _w, _h, buf in src_frames:
        for i in range(0, len(buf) - 2, 3):
            pix.append((buf[i] / 255, buf[i + 1] / 255, buf[i + 2] / 255))
    random.seed(7)
    if len(pix) > 40000:
        pix = random.sample(pix, 40000)
    neutral = [p for p in pix if max(p) > 0.05 and (max(p) - min(p)) / max(p) < 0.22]
    look = Look(src_stats, tgt)
    # saturation is content-dependent (a flower meadow vs a cloudy peak), so move only part-way
    ratio = (tgt["saturation"] / src_stats["saturation"]) if src_stats["saturation"] else 1.0
    want_sat = src_stats["saturation"] * max(0.6, min(1.6, ratio ** sat_damp)) * sat_mult
    look.k = max(0.4, min(2.5, want_sat / max(src_stats["saturation"], 1e-3)))
    tgt_neu = tgt.get("neutral_offsets") or {}
    zmap = {"shadow": "s", "mid": "m", "high": "h"}
    for it in range(iters):
        cur = stats_after(look, pix)
        for j, key in enumerate(Look.KEYS, start=1):  # tone: chase the percentile error
            look.ys[j] = min(1.0, max(0.0, look.ys[j] + 0.8 * (tgt[key] - cur[key]) / 255))
        look.rebuild()
        if cur["saturation"] > 0:
            look.k = max(0.3, min(2.5, look.k * (want_sat / cur["saturation"]) ** 0.9))
        have = neutral_offsets_after(look, neutral)
        for z, key in zmap.items():  # white balance / split-tone from greys only
            if tgt_neu.get(z) is None or have.get(z) is None:
                continue
            for c in range(3):
                step = 0.8 * (balance * tgt_neu[z][c] - have[z][c]) / 255
                look.bal[key][c] = max(-0.06, min(0.06, look.bal[key][c] + step))
        if verbose:
            print(f"  iter {it + 1}: p2/p50/p98 {cur['luma_p2']}/{cur['luma_p50']}/{cur['luma_p98']} "
                  f"sat {cur['saturation']:.3f} (aim {want_sat:.3f})", file=sys.stderr)
    after = stats_after(look, pix)
    after["neutral_offsets"] = {z: ([round(v, 1) for v in o] if o else None)
                                for z, o in neutral_offsets_after(look, neutral).items()}
    return look, after, want_sat


def write_cube(look: Look, path: str, size: int = 33, strength: float = 1.0, title: str = "reav look"):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(f'TITLE "{title}"\nLUT_3D_SIZE {size}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        n = size - 1
        for bi in range(size):
            for gi in range(size):
                for ri in range(size):  # red fastest
                    r, g, b = ri / n, gi / n, bi / n
                    R, G, B = look.apply(r, g, b)
                    R, G, B = r + strength * (R - r), g + strength * (G - g), b + strength * (B - b)
                    f.write(f"{R:.6f} {G:.6f} {B:.6f}\n")


# ----------------------------------------------------------------------------- CLI

def row(name, st):
    no = st.get("neutral_offsets") or {}

    def z(k):
        o = no.get(k)
        return "  -  " if not o else f"{o[0] - o[2]:+.0f}w{o[1] - (o[0] + o[2]) / 2:+.0f}g"
    return (f"{name:<28} p2 {st['luma_p2']:>3}  p50 {st['luma_p50']:>3}  p98 {st['luma_p98']:>3}  "
            f"sat {st['saturation']:.3f}  palette warmth {st['warmth']:+6.1f}  "
            f"greys(w=warm,g=green) sh {z('shadow')} mid {z('mid')} hi {z('high')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("video")
    m.add_argument("--cuts")
    m.add_argument("--range", action="append", default=[], help="A-B seconds")
    m.add_argument("--lut")
    m.add_argument("--out")
    mt = sub.add_parser("match")
    mt.add_argument("--ref", required=True)
    mt.add_argument("--ref-shots")
    mt.add_argument("--src", action="append", required=True, help="CLIP or CLIP@A-B, repeatable")
    mt.add_argument("--out", required=True)
    mt.add_argument("--strength", type=float, default=0.85, help="0-1, how far toward the reference look")
    mt.add_argument("--sat-mult", type=float, default=1.0, help="extra saturation on top of the match")
    mt.add_argument("--sat-damp", type=float, default=0.6,
                    help="0 = keep source saturation, 1 = copy reference saturation fully (content-dependent!)")
    mt.add_argument("--balance", type=float, default=1.0, help="0-1, how much of the reference's grey tint to copy")
    mt.add_argument("--size", type=int, default=33)
    ck = sub.add_parser("check")
    ck.add_argument("--ref", required=True)
    ck.add_argument("--ref-shots")
    ck.add_argument("--src", action="append", required=True)
    ck.add_argument("--lut", required=True)
    a = ap.parse_args()
    need("ffmpeg")

    if a.cmd == "measure":
        if a.cuts:
            data = measure_cuts(a.video, load_json(a.cuts))
            for s in data["shots"]:
                if s["stats"]:
                    print(row(f"shot {s['shot']} {s['start']:.2f}-{s['end']:.2f}s", s["stats"]))
            print(row("OVERALL", data["overall"]))
            print("read:", data["overall_read"])
        else:
            rngs = a.range or [None]
            data = {"source": os.path.abspath(a.video), "lut": a.lut, "ranges": []}
            for rg in rngs:
                st_, en_ = (None, None) if rg is None else map(float, rg.split("-", 1))
                st = rgb_stats(sample(a.video, st_, en_, lut=a.lut))
                data["ranges"].append({"range": rg, "stats": st, "read": describe_color(st)})
                print(row(rg or "whole clip", st))
                print("  read:", describe_color(st))
        if a.out:
            save_json(a.out, data)
            print("wrote", a.out)
        return

    ref = load_json(a.ref)
    tgt = target_from(ref, a.ref_shots)
    frames = []
    for spec in a.src:
        p, s0, s1 = parse_src(spec)
        frames += sample(p, s0, s1, n=6, lut=getattr(a, "lut", None) if a.cmd == "check" else None)
    src_stats = rgb_stats(frames)
    if a.cmd == "check":
        print(row("TARGET (reference)", tgt))
        print(row("graded source", src_stats))
        d50, d98, d2 = src_stats["luma_p50"] - tgt["luma_p50"], src_stats["luma_p98"] - tgt["luma_p98"], \
            src_stats["luma_p2"] - tgt["luma_p2"]
        ds = src_stats["saturation"] - tgt["saturation"]
        grey = []
        for z in ("shadow", "mid", "high"):
            o, t = (src_stats.get("neutral_offsets") or {}).get(z), (tgt.get("neutral_offsets") or {}).get(z)
            if o and t:
                grey.append(max(abs(o[c] - t[c]) for c in range(3)))
        dg = max(grey) if grey else 0.0
        tone_ok = abs(d50) <= 10 and abs(d98) <= 12 and abs(d2) <= 8
        print(f"delta  p2 {d2:+}  p50 {d50:+}  p98 {d98:+}  sat {ds:+.3f}  grey-tint max {dg:.1f}")
        print("tone: " + ("CLOSE" if tone_ok else "OFF - re-run match on these clips") +
              " | greys: " + ("CLOSE" if dg <= 8 else "OFF - check white balance") +
              " | saturation: " + ("CLOSE" if abs(ds) <= 0.05 else
                                   "differs (normal when content differs; judge by eye, tune --sat-mult)"))
        print("Now LOOK at a graded frame next to the reference shot - numbers can't see skin tones or casts.")
        return

    print(row("TARGET (reference)", tgt))
    print(row("source before", src_stats))
    look, after, want_sat = fit(frames, src_stats, tgt, sat_mult=a.sat_mult, sat_damp=a.sat_damp,
                                balance=a.balance)
    print(row("source after (strength 1)", after))
    print(f"saturation aimed at {want_sat:.3f} (damped toward the reference; content differs between clips)")
    write_cube(look, a.out, size=a.size, strength=a.strength,
               title=f"reav match {os.path.basename(a.ref)} {a.ref_shots or 'overall'}")
    print(f"wrote {a.out} (strength {a.strength}). Verify: color.py check --ref {a.ref} "
          f"--src {a.src[0]} --lut {a.out}")


if __name__ == "__main__":
    main()
