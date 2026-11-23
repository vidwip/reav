#!/usr/bin/env python3
"""Music map of a soundtrack: tempo, beat grid, downbeat guess, accents, energy changes, silences.
With --cuts it also says how the reference's cuts sit on the music (on beat / on accent / free).

Pure Python + ffmpeg (no numpy/librosa). Onsets from low-band (kick) + high-band (snare/hat) +
full-band spectral-energy flux; tempo by autocorrelation with a 120 BPM prior; beats by
dynamic programming (Ellis 2007).

Usage:
  beats.py AUDIO_OR_VIDEO [--out beats.json] [--cuts cuts.json] [--fps 30] [--bpm-hint 128]
"""
from __future__ import annotations

import argparse
import array
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reav_common import die, fmt_t, load_json, need, probe, run, save_json  # noqa: E402

SR = 11025
HOP = 256
FR = SR / HOP  # envelope frames per second (~43.07)


def decode(path: str):
    info = probe(path)
    if not info.get("has_audio"):
        die("no audio stream in " + path)
    m = "aformat=sample_fmts=s16:sample_rates=11025:channel_layouts=mono"
    fc = (f"[0:a:0]aresample=11025,aformat=channel_layouts=mono,asplit=3[a][b][c];"
          f"[a]{m}[f];[b]lowpass=f=160,lowpass=f=160,{m}[l];[c]highpass=f=1800,{m}[h];"
          f"[f][l][h]amerge=inputs=3[o]")
    p = run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-filter_complex", fc,
             "-map", "[o]", "-f", "s16le", "-acodec", "pcm_s16le", "-"])
    x = array.array("h")
    x.frombytes(p.stdout[: len(p.stdout) // 6 * 6])
    if sys.byteorder == "big":
        x.byteswap()
    return x[0::3], x[1::3], x[2::3]


def rms_frames(sig) -> list[float]:
    out = []
    n = len(sig)
    for s in range(0, n - HOP + 1, HOP):
        acc = 0
        for v in sig[s:s + HOP]:
            acc += v * v
        out.append(math.sqrt(acc / HOP) / 32768.0)
    return out


def flux(env: list[float], gamma: float = 100.0) -> list[float]:
    c = [math.log1p(gamma * e) for e in env]
    out = [0.0, 0.0]
    for i in range(2, len(c)):
        out.append(max(0.0, c[i] - max(c[i - 1], c[i - 2] * 0.5 + c[i - 1] * 0.5)))
    return out


def normalise(x: list[float]) -> list[float]:
    sd = statistics.pstdev(x) or 1.0
    return [v / sd for v in x]


def local_detrend(x: list[float], w: int = 8) -> list[float]:
    out = []
    n = len(x)
    pref = [0.0]
    for v in x:
        pref.append(pref[-1] + v)
    for i in range(n):
        lo, hi = max(0, i - w), min(n, i + w + 1)
        out.append(max(0.0, x[i] - (pref[hi] - pref[lo]) / (hi - lo)))
    return out


def tempo(onset: list[float], bpm_hint: float | None):
    lo_lag = int(FR * 60 / 210)
    hi_lag = int(FR * 60 / 55) + 1
    n = len(onset)
    mean = statistics.fmean(onset)
    o = [v - mean for v in onset]
    ac = {}
    for lag in range(lo_lag, min(hi_lag, n - 1)):
        s = 0.0
        for i in range(lag, n):
            s += o[i] * o[i - lag]
        ac[lag] = s / (n - lag)
    center = bpm_hint or 120.0
    best_lag, best = None, -1e18
    for lag, v in ac.items():
        bpm = 60 * FR / lag
        w = math.exp(-0.5 * (math.log2(bpm / center) / (0.5 if bpm_hint else 1.0)) ** 2)
        if v * w > best:
            best, best_lag = v * w, lag
    if best_lag is None:
        return 120.0, FR * 0.5
    # parabolic refinement
    l0 = best_lag
    if l0 - 1 in ac and l0 + 1 in ac:
        a, b, c = ac[l0 - 1], ac[l0], ac[l0 + 1]
        den = a - 2 * b + c
        if den:
            l0 = best_lag + 0.5 * (a - c) / den
    return 60 * FR / l0, l0


def track(onset: list[float], period: float, tightness: float = 100.0) -> list[int]:
    n = len(onset)
    score = [0.0] * n
    back = [-1] * n
    lo, hi = int(round(period / 2)), int(round(period * 2))
    for t in range(n):
        best, arg = 0.0, -1
        for p in range(max(0, t - hi), t - lo + 1):
            d = t - p
            v = score[p] - tightness * (math.log(d / period)) ** 2
            if arg < 0 or v > best:
                best, arg = v, p
        score[t] = onset[t] + (best if arg >= 0 and best > 0 else 0.0)
        back[t] = arg if arg >= 0 and best > 0 else -1
    # start from best score in the last period
    tail = range(max(0, n - int(period) - 1), n)
    t = max(tail, key=lambda i: score[i])
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    beats.reverse()
    return beats


def peaks(x: list[float], thresh: float, min_gap: int) -> list[int]:
    out = []
    for i in range(1, len(x) - 1):
        if x[i] >= thresh and x[i] >= x[i - 1] and x[i] > x[i + 1]:
            if out and i - out[-1] < min_gap:
                if x[i] > x[out[-1]]:
                    out[-1] = i
                continue
            out.append(i)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media")
    ap.add_argument("--out", default=None)
    ap.add_argument("--cuts", default=None, help="cuts.json from cuts.py: classify each cut against the music")
    ap.add_argument("--fps", type=float, default=None, help="timeline fps for *_f fields (default: cuts.json fps or 30)")
    ap.add_argument("--bpm-hint", type=float, default=None, help="if you know the song's tempo roughly")
    ap.add_argument("--tolerance", type=float, default=0.1, help="seconds: how close counts as on a beat (0.1 = 3 frames @30)")
    a = ap.parse_args()
    need("ffmpeg")

    cuts = load_json(a.cuts) if a.cuts else None
    fps = a.fps or (cuts["fps"] if cuts else 30)
    print(f"Decoding audio from {os.path.basename(a.media)}...", file=sys.stderr)
    full, low, high = decode(a.media)
    dur = len(full) / SR
    e_full, e_low, e_high = rms_frames(full), rms_frames(low), rms_frames(high)
    f_full, f_low, f_high = normalise(flux(e_full)), normalise(flux(e_low)), normalise(flux(e_high))
    onset = local_detrend([0.5 * f + 1.0 * l + 0.8 * h for f, l, h in zip(f_full, f_low, f_high)])
    onset = normalise(onset) if any(onset) else onset

    bpm, period = tempo(onset, a.bpm_hint)
    beat_idx = track(onset, period)
    beats = [round(i / FR, 3) for i in beat_idx]

    # downbeat guess: phase (mod 4) with the most low-band (kick) energy
    phase_score = [0.0] * 4
    for k, i in enumerate(beat_idx):
        phase_score[k % 4] += sum(f_low[max(0, i - 1): i + 2])
    ph = max(range(4), key=lambda p: phase_score[p])
    downbeats = [beats[k] for k in range(ph, len(beats), 4)]

    # accents = strongest onsets (what big cuts / flashes / text pops usually hit)
    pk = peaks(onset, 1.5, int(FR * 0.12))
    accents = sorted(pk, key=lambda i: -onset[i])[: max(8, int(dur / 1.5))]
    accents = sorted(accents)

    # loudness curve in 0.25 s windows (dB rel. to loudest window)
    win = int(FR * 0.25)
    curve = []
    for s in range(0, len(e_full), win):
        seg = e_full[s:s + win]
        r = math.sqrt(sum(v * v for v in seg) / max(len(seg), 1))
        curve.append(20 * math.log10(r + 1e-9))
    top = max(curve) if curve else 0
    curve = [round(v - top, 1) for v in curve]
    changes = []
    for i in range(4, len(curve) - 4):
        before = statistics.fmean(curve[i - 4:i])
        after = statistics.fmean(curve[i:i + 4])
        if after - before >= 6 and (not changes or i * 0.25 - changes[-1]["t"] > 1.0):
            changes.append({"t": round(i * 0.25, 2), "type": "rise / drop hits", "delta_db": round(after - before, 1)})
        elif before - after >= 6 and (not changes or i * 0.25 - changes[-1]["t"] > 1.0):
            changes.append({"t": round(i * 0.25, 2), "type": "break / drop-out", "delta_db": round(after - before, 1)})
    silences = []
    i = 0
    while i < len(curve):
        if curve[i] < -40:
            j = i
            while j < len(curve) and curve[j] < -40:
                j += 1
            if (j - i) * 0.25 >= 0.5:
                silences.append({"from": round(i * 0.25, 2), "to": round(min(j * 0.25, dur), 2)})
            i = j
        else:
            i += 1

    data = {
        "source": os.path.abspath(a.media), "duration": round(dur, 3), "fps": fps,
        "bpm": round(bpm, 2), "beat_period": round(60 / bpm, 4),
        "beats": beats, "beats_f": [int(round(t * fps)) for t in beats],
        "downbeats_guess": downbeats,
        "accents": [{"t": round(i / FR, 3), "f": int(round(i / FR * fps)), "strength": round(onset[i], 2)} for i in accents],
        "energy_changes": changes, "silences": silences,
        "loudness_curve_db_0_25s": curve,
    }

    if cuts:
        rows = []
        on_b = on_a = 0
        acc_t = [x["t"] for x in data["accents"]]
        all_on = [round(i / FR, 3) for i in peaks(onset, 0.8, int(FR * 0.08))]
        offsets = []
        for s in cuts["shots"][1:]:
            t = s["start"]
            # signed: + = the musical event comes AFTER the cut (editor cut early)
            db = min((b - t for b in beats), key=abs, default=99)
            da = min((x - t for x in acc_t + all_on), key=abs, default=99)
            kind = "beat" if abs(db) <= a.tolerance else "accent" if abs(da) <= a.tolerance else "free"
            on_b += kind == "beat"
            on_a += kind == "accent"
            delta = db if kind == "beat" else da if kind == "accent" else None
            if delta is not None:
                offsets.append(delta)
            beat_pos = None
            if kind == "beat":
                k = min(range(len(beats)), key=lambda q: abs(beats[q] - t))
                beat_pos = (k - ph) % 4 + 1
            rows.append({"shot": s["shot"], "t": t, "f": s["start_f"], "kind": kind,
                         "event_offset_s": round(delta, 3) if delta is not None else None,
                         "bar_pos_guess": beat_pos})
        n = max(len(rows), 1)
        durs = [s["dur"] / (60 / bpm) for s in cuts["shots"] if s["frames"] > 4]
        acc_gaps = [b - a_ for a_, b in zip(acc_t, acc_t[1:])]
        data["cut_sync"] = {
            "on_beat_pct": round(100 * on_b / n), "on_accent_pct": round(100 * on_a / n),
            "free_pct": round(100 * (n - on_b - on_a) / n),
            "median_beats_per_shot": round(statistics.median(durs), 2) if durs else None,
            "median_event_offset_s": round(statistics.median(offsets), 3) if offsets else None,
            "median_accent_gap_s": round(statistics.median(acc_gaps), 3) if acc_gaps else None,
            "cuts": rows,
        }

    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.media)), "beats.json")
    save_json(out, data)

    print(f"\n{dur:.2f}s  ~{bpm:.1f} BPM (beat every {60 / bpm:.3f}s = {fps * 60 / bpm:.1f} frames @ {fps}fps)  "
          f"{len(beats)} beats, first beat {beats[0] if beats else '-'}s")
    print("accents: " + "  ".join(f"{x['t']:.2f}" for x in data["accents"]))
    if changes:
        print("energy changes: " + "  ".join(f"{c['t']:.2f}s {c['type']} ({c['delta_db']:+.0f}dB)" for c in changes))
    if silences:
        print("silences: " + "  ".join(f"{s['from']:.2f}-{s['to']:.2f}s" for s in silences))
    if cuts:
        cs = data["cut_sync"]
        print(f"cuts: {cs['on_beat_pct']}% on beat, {cs['on_accent_pct']}% on an accent, {cs['free_pct']}% free; "
              f"median shot = {cs['median_beats_per_shot']} beats; median accent gap {cs['median_accent_gap_s']}s")
        if cs["median_event_offset_s"] is not None:
            off = cs["median_event_offset_s"]
            print(f"synced cuts land {abs(off) * 1000:.0f} ms ({abs(off) * fps:.1f} frames) "
                  f"{'BEFORE' if off > 0 else 'after'} the musical hit (median)")
        print(f"(BPM can be off by x2, /2 or x2/3 - alternatives {bpm / 2:.0f} / {bpm * 2:.0f} / {bpm * 2 / 3:.0f}; "
              "trust the accent times most)")
        for r in cs["cuts"]:
            off = r["event_offset_s"]
            print(f"  cut {r['shot']:>3} @ {fmt_t(r['t'])} (f{r['f']}): {r['kind']:<6} "
                  f"{'(hit %+.0f ms from cut)' % (off * 1000) if off is not None else ''}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
