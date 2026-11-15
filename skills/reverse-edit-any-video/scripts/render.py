#!/usr/bin/env python3
"""Render an edit-plan.json to a finished video in ONE ffmpeg pass (frame-exact, 10-bit inside).

Every segment is cut straight from the original file, reframed to the canvas, tone-mapped if HDR,
graded with its LUT, joined on exact frame counts (hard cut / flash / dip / xfade), then text,
overlays (PNG or alpha video, e.g. Remotion-rendered titles) and audio are added and the result is
dithered once to 8-bit 4:2:0 H.264 for Instagram / TikTok / Shorts.

Usage:
  render.py edit-plan.json                       final quality (plan's output path)
  render.py edit-plan.json --preview             half-res, fast, for checking cuts and timing
  render.py edit-plan.json --frames 0-150        only that part of the timeline
  render.py edit-plan.json --still 42 --out f.jpg one frame (for side-by-side checks)
  render.py edit-plan.json --dry-run             print the filtergraph only
  render.py edit-plan.json --export-segments remotion/public   graded segments for the Remotion route

Schema: references/edit-plan.md. Paths in the plan are relative to the plan file.
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reav_common import (ceil_even, die, ff_escape, load_json, need, probe, run, safe_copy,  # noqa: E402
                         tonemap_chain)

XFADE_EFFECTS = {"fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown",
                 "slideleft", "slideright", "slideup", "slidedown", "smoothleft", "smoothright", "smoothup",
                 "smoothdown", "circlecrop", "rectcrop", "circleopen", "circleclose", "radial", "zoomin",
                 "hblur", "pixelize", "squeezeh", "squeezev", "distance", "diagtl", "diagtr", "hlslice",
                 "hrslice", "vuslice", "vdslice", "coverleft", "coverright", "revealleft", "revealright"}


class Plan:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        self.d = load_json(self.path)
        self.fps = self.d.get("fps", 30)
        self.W = self.d.get("width", 1080)
        self.H = self.d.get("height", 1920)
        if not self.d.get("segments"):
            die("plan has no segments")

    def p(self, rel: str | None) -> str | None:
        if not rel:
            return None
        return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(self.dir, rel))


def ease(expr_p: str, kind: str) -> str:
    if kind in ("inout", "ease", "easeinout"):
        return f"(0.5-0.5*cos(PI*{expr_p}))"
    if kind in ("out", "easeout"):
        return f"(1-pow(1-{expr_p},2))"
    if kind in ("in", "easein"):
        return f"pow({expr_p},2)"
    return expr_p


def reframe(seg: dict, info: dict, W: int, H: int, fps: float, n_total: int, uid: str) -> str:
    """Scale/crop the source onto the WxH canvas. fit: cover (default) | contain | blur."""
    dw, dh = info["display_width"], info["display_height"]
    fit = seg.get("fit", "cover")
    fx0, fy0 = (seg.get("focus") or [0.5, 0.5])
    fx1, fy1 = (seg.get("pan_to") or [fx0, fy0])
    z0 = float(seg.get("zoom", 1.0))
    z1 = float(seg.get("zoom_to", z0))
    if seg.get("rotate_deg"):
        pass  # rotation is applied before reframe in segment_chain
    cover = max(W / dw, H / dh)
    zooming = abs(z1 - z0) > 1e-4
    panning = abs(fx1 - fx0) > 1e-4 or abs(fy1 - fy0) > 1e-4
    last = max(n_total - 1, 1)

    def cover_chain():
        if not zooming:
            # static or pure pan: constant-size scale, crop window moves (crop keeps a fixed input size)
            sw, sh = max(ceil_even(dw * cover * z0), W), max(ceil_even(dh * cover * z0), H)
            if not panning:
                return f"scale={sw}:{sh}:flags=lanczos,crop={W}:{H}:{round((sw - W) * fx0)}:{round((sh - H) * fy0)}"
            p = ease(f"min(1\\,n/{last})", seg.get("ease", "linear"))
            return (f"scale={sw}:{sh}:flags=lanczos,crop={W}:{H}:"
                    f"x='{sw - W}*({fx0}+({fx1 - fx0:.6f})*{p})':y='{sh - H}*({fy0}+({fy1 - fy0:.6f})*{p})'")
        # zoom: pre-scale to a 2x canvas-aspect frame (sub-pixel-smooth window), then zoompan.
        # NB: scale eval=frame + crop does NOT work - crop keeps the first frame's size and pins top-left.
        W2, H2 = 2 * W, 2 * H
        sw, sh = max(ceil_even(dw * cover * 2), W2), max(ceil_even(dh * cover * 2), H2)
        p = ease(f"min(1\\,on/{last})", seg.get("ease", "linear"))
        Z = f"({z0}+({z1 - z0:.6f})*{p})"
        FX = f"({fx0}+({fx1 - fx0:.6f})*{p})"
        FY = f"({fy0}+({fy1 - fy0:.6f})*{p})"
        return (f"scale={sw}:{sh}:flags=lanczos,crop={W2}:{H2}:{round((sw - W2) * fx0)}:{round((sh - H2) * fy0)},"
                f"zoompan=z='{Z}':x='(iw-iw/zoom)*{FX}':y='(ih-ih/zoom)*{FY}':d=1:s={W}x{H}:fps={fps}")

    if fit == "cover":
        return cover_chain()
    contain = min(W / dw, H / dh) * z0
    cw, ch = ceil_even(dw * contain), ceil_even(dh * contain)
    cw, ch = min(cw, W), min(ch, H)
    if fit == "contain":
        bg = seg.get("background", "black")
        return (f"scale={cw}:{ch}:flags=lanczos,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bg}")
    if fit == "blur":
        return (f"split=2[{uid}bg][{uid}fg];[{uid}bg]{cover_chain()},boxblur=luma_radius=40:luma_power=2,"
                f"eq=brightness=-0.06[{uid}bgb];[{uid}fg]scale={cw}:{ch}:flags=lanczos[{uid}fgs];"
                f"[{uid}bgb][{uid}fgs]overlay=(W-w)/2:(H-h)/2")
    die(f"unknown fit '{fit}' (cover | contain | blur)")
    return ""


def grade_chain(lut: str | None, tmp: str) -> str:
    if not lut or lut == "none":
        return ""
    if not os.path.exists(lut):
        die(f"LUT not found: {lut}")
    lp = ff_escape(safe_copy(lut, tmp))
    return (f"scale=in_color_matrix=bt709:in_range=tv,format=gbrpf32le,lut3d=file='{lp}':interp=tetrahedral,"
            f"scale=out_color_matrix=bt709:out_range=tv,")


def wrap_text(text: str, width: int | None) -> str:
    if not width:
        return text
    out = []
    for para in text.split("\n"):
        line = ""
        for w in para.split(" "):
            if line and len(line) + 1 + len(w) > width:
                out.append(line)
                line = w
            else:
                line = f"{line} {w}" if line else w
        out.append(line)
    return "\n".join(out)


def pos_expr(v, axis: str, W: int, H: int) -> str:
    size = "text_w" if axis == "x" else "text_h"
    full = "w" if axis == "x" else "h"
    if v in (None, "center"):
        return f"({full}-{size})/2"
    if isinstance(v, str):
        return v  # raw ffmpeg expression
    v = float(v)
    if 0 <= v <= 1:
        return f"{full}*{v:.4f}-{size}/2"
    return f"{v:.1f}-{size}/2"


def text_chain(t: dict, plan: Plan, tmp: str, idx: int) -> str:
    fonts = plan.d.get("fonts", {})
    font = t.get("font")
    font = fonts.get(font, font)
    fontfile = plan.p(font) if font else None
    if fontfile and not os.path.exists(fontfile):
        die(f"font not found: {fontfile}")
    txt_path = os.path.join(tmp, f"text_{idx:03d}.txt")
    with open(txt_path, "w") as f:
        f.write(wrap_text(t["text"], t.get("wrap")))
    fps = plan.fps
    f0, f1 = int(t["from"]), int(t["to"])
    a, b = f0 / fps, f1 / fps
    fi, fo = t.get("fade_in", 0) / fps, t.get("fade_out", 0) / fps
    opts = [f"textfile='{ff_escape(txt_path)}'", "expansion=none", f"fontsize={t.get('size', 64)}",
            f"fontcolor={t.get('color', 'white')}", f"line_spacing={t.get('line_spacing', 8)}",
            f"x='{pos_expr(t.get('x', 'center'), 'x', plan.W, plan.H)}'",
            f"y='{pos_expr(t.get('y', 0.5), 'y', plan.W, plan.H)}'",
            f"text_align={ {'left': 'L', 'right': 'R'}.get(t.get('align', 'center'), 'C') }",
            f"enable='between(n\\,{f0}\\,{f1 - 1})'"]
    if fontfile:
        opts.insert(0, f"fontfile='{ff_escape(safe_copy(fontfile, tmp))}'")
    if fi or fo:
        up = f"if(lt(t\\,{a + fi:.4f})\\,(t-{a:.4f})/{max(fi, 1e-3):.4f}\\,1)" if fi else "1"
        down = f"if(gt(t\\,{b - fo:.4f})\\,({b:.4f}-t)/{max(fo, 1e-3):.4f}\\,1)" if fo else "1"
        opts.append(f"alpha='max(0\\,min({up}\\,{down}))'")
    box = t.get("box")
    if box:
        opts += ["box=1", f"boxcolor={box.get('color', 'white')}", f"boxborderw={box.get('pad', 16)}"]
    border = t.get("border")
    if border and border.get("width"):
        opts += [f"borderw={border['width']}", f"bordercolor={border.get('color', 'black')}"]
    sh = t.get("shadow")
    if sh:
        opts += [f"shadowx={sh.get('x', 2)}", f"shadowy={sh.get('y', 2)}", f"shadowcolor={sh.get('color', 'black@0.5')}"]
    return "drawtext=" + ":".join(opts)


def export_segments(a, plan: Plan, args, chains, labels, segs, tmp):
    """Write every footage segment (graded, reframed, with xfade handles) + plan.json + fonts into a
    Remotion project's public/ dir, for effects that ffmpeg can't do (see templates/remotion)."""
    import json
    pub = os.path.abspath(a.export_segments)
    os.makedirs(os.path.join(pub, "segments"), exist_ok=True)
    os.makedirs(os.path.join(pub, "fonts"), exist_ok=True)
    graph, outs = list(chains), []
    start = 0
    rsegs = []
    for i, s in enumerate(segs):
        rec = {"id": s["id"], "frames": s["frames"], "start": start, "head": s["_head"], "tail": s["_tail"]}
        for k in ("color", "transition_in", "fade_out", "fx"):
            if s.get(k) is not None:
                rec[k] = s[k]
        if not (s.get("color") or not s.get("src")):
            rel = f"segments/{s['id']}.mp4"
            rec["file"] = rel
            graph.append(f"[{labels[i]}]scale=out_color_matrix=bt709:out_range=tv:sws_dither=ed,format=yuv420p,"
                         f"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[e{i}]")
            outs += ["-map", f"[e{i}]", "-c:v", "libx264", "-preset", "medium", "-crf", "10", "-pix_fmt", "yuv420p",
                     "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709", "-r", str(plan.fps),
                     "-movflags", "+faststart", os.path.join(pub, rel)]
        else:
            # colour segments are drawn by Remotion; still consume the label
            graph.append(f"[{labels[i]}]nullsink")
        rsegs.append(rec)
        start += s["frames"]
    fonts = {}
    for name, f in (plan.d.get("fonts") or {}).items():
        src = plan.p(f)
        if src and os.path.exists(src):
            dst = os.path.join(pub, "fonts", os.path.basename(src))
            shutil.copy2(src, dst)
            fonts[name] = f"fonts/{os.path.basename(src)}"
    texts = plan.d.get("texts", [])
    rplan = {"fps": plan.fps, "width": plan.W, "height": plan.H, "total": start,
             "segments": rsegs, "texts": texts, "fonts": fonts}
    with open(os.path.join(pub, "plan.json"), "w") as f:
        json.dump(rplan, f, indent=2)
    print(f"Exporting {sum(1 for r in rsegs if 'file' in r)} segments -> {pub}/segments", file=sys.stderr)
    p = run(args + ["-filter_complex", ";\n".join(graph)] + outs, check=False)
    shutil.rmtree(tmp, ignore_errors=True)
    if p.returncode != 0:
        print((p.stderr or b"").decode(errors="replace")[-4000:], file=sys.stderr)
        die("segment export failed")
    print(f"done: {pub}/plan.json + segments/ + fonts/. Next (in the Remotion dir): npx remotion studio, "
          f"or npx remotion render Reel out/reel.mp4 --crf=12, then mux the audio (references/remotion-route.md)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--out", help="override output path")
    ap.add_argument("--preview", action="store_true", help="half resolution, fast encode")
    ap.add_argument("--frames", help="A-B timeline frames (end exclusive)")
    ap.add_argument("--still", type=int, help="render one timeline frame to an image")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--export-segments", metavar="REMOTION_PUBLIC_DIR",
                    help="write graded/reframed segments + plan.json + fonts for the Remotion template")
    a = ap.parse_args()
    need("ffmpeg")
    plan = Plan(a.plan)
    fps, W, H = plan.fps, plan.W, plan.H
    segs = plan.d["segments"]
    tmp = tempfile.mkdtemp(prefix="reav_render_")

    # ---- pass 1: resolve sources, in-points, transitions, handles
    prev_by_src: dict[str, tuple[float, int, float]] = {}
    infos: dict[str, dict] = {}
    for i, s in enumerate(segs):
        s.setdefault("id", f"S{i + 1:02d}")
        if "frames" not in s:
            die(f"{s['id']}: missing 'frames'")
        s["frames"] = int(s["frames"])
        s["_head"] = s["_tail"] = 0
        s["_flash_out"] = None
        if s.get("color") or not s.get("src"):
            continue
        src = plan.p(s["src"])
        if not os.path.exists(src):
            die(f"{s['id']}: source not found: {src}")
        s["_src"] = src
        if src not in infos:
            infos[src] = probe(src)
            if not infos[src].get("has_video"):
                die(f"{s['id']}: no video stream in {src}")
        speed = float(s.get("speed", 1.0))
        if s.get("in") == "continue":
            if src not in prev_by_src:
                die(f"{s['id']}: 'in': 'continue' but no earlier segment uses {os.path.basename(src)}")
            pin, pfr, psp = prev_by_src[src]
            s["in"] = pin + pfr / fps * psp
        s["in"] = float(s.get("in", 0.0))
        prev_by_src[src] = (s["in"], s["frames"], speed)

    for i, s in enumerate(segs):
        tr = s.get("transition_in") or {}
        typ = tr.get("type", "cut")
        if i == 0 or typ == "cut":
            continue
        k = int(tr.get("frames", 3 if typ == "flash" else 8))
        if typ == "xfade":
            eff = tr.get("effect", "fade")
            if eff not in XFADE_EFFECTS:
                die(f"{s['id']}: unknown xfade effect '{eff}'")
            s["_head"] = k // 2
            segs[i - 1]["_tail"] = k - k // 2
        elif typ in ("flash", "dip"):
            color = tr.get("color", "white" if typ == "flash" else "black")
            segs[i - 1]["_flash_out"] = (max(1, k // 2) if typ == "flash" else k, color)
        elif typ not in ("fade_in",):
            die(f"{s['id']}: unknown transition type '{typ}' (cut | flash | dip | fade_in | xfade)")

    # ---- pass 2: inputs + per-segment chains
    args = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-nostdin"]
    chains, labels = [], []
    idx = 0
    seg_input: dict[int, int] = {}
    for i, s in enumerate(segs):
        n_total = s["_head"] + s["frames"] + s["_tail"]
        lab = f"v{i}"
        if s.get("color") or not s.get("src"):
            c = s.get("color", "black")
            chains.append(f"color=c={c}:s={W}x{H}:r={fps}:d={n_total / fps + 0.1:.4f},format=yuv444p10le,"
                          f"setsar=1,trim=end_frame={n_total},setpts=PTS-STARTPTS[{lab}]")
            labels.append(lab)
            continue
        info = infos[s["_src"]]
        freeze = bool(s.get("freeze"))
        speed = 1.0 if freeze else float(s.get("speed", 1.0))
        need_s = 1.0 / fps if freeze else n_total / fps * speed
        start = s["in"] - s["_head"] / fps * speed
        pre_pad = 0
        if start < 0:
            pre_pad = int(math.ceil(-start / speed * fps))
            start = 0.0
        dur = info.get("duration")
        post_pad = 0
        if dur and not info["is_image"] and start + need_s > dur + 1e-3:
            short = start + need_s - dur
            post_pad = int(math.ceil(short / speed * fps)) + 1
            print(f"warning: {s['id']} needs {need_s:.2f}s from {start:.2f}s but "
                  f"{os.path.basename(s['_src'])} is {dur:.2f}s - last frame frozen for {post_pad} frames",
                  file=sys.stderr)
        if info["is_image"]:
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{n_total / fps + 0.5:.4f}", "-i", s["_src"]]
        else:
            args += ["-ss", f"{start:.5f}", "-t", f"{need_s + 0.5:.5f}", "-i", s["_src"]]
        seg_input[i] = idx
        ch = [f"[{idx}:v:0]setpts=(PTS-STARTPTS)/{speed},fps={fps}"]
        if freeze:  # one exact frame, held for the whole slot
            ch.append(f"trim=end_frame=1,tpad=stop={n_total - 1}:stop_mode=clone")
            pre_pad = post_pad = 0
        if pre_pad or post_pad:
            ch.append(f"tpad=start={pre_pad}:start_mode=clone:stop={post_pad}:stop_mode=clone")
        ch.append(f"trim=end_frame={n_total},setpts=PTS-STARTPTS")
        tm = tonemap_chain(info)
        if tm:
            ch.append(tm.rstrip(","))
        if s.get("hflip"):
            ch.append("hflip")
        ch.append(reframe(s, info, W, H, fps, n_total, f"r{i}"))
        lut = s.get("lut", plan.d.get("grade", {}).get("lut"))
        g = grade_chain(plan.p(lut) if lut and lut != "none" else None, tmp)
        if g:
            ch.append(g.rstrip(","))
        if s.get("filters"):
            ch.append(s["filters"])
        ch.append("format=yuv444p10le,setsar=1")
        chains.append(",".join(ch) + f"[{lab}]")
        labels.append(lab)
        idx += 1

    if a.export_segments:
        export_segments(a, plan, args, chains, labels, segs, tmp)
        return

    # fades that belong to a segment (flash/dip in-out, fade_in, explicit fade_out)
    for i, s in enumerate(segs):
        n_total = s["_head"] + s["frames"] + s["_tail"]
        extra = []
        tr = s.get("transition_in") or {}
        typ = tr.get("type", "cut")
        if i > 0 and typ in ("flash", "dip", "fade_in"):
            k = int(tr.get("frames", 3 if typ == "flash" else 8))
            color = tr.get("color", "white" if typ == "flash" else "black")
            extra.append(f"fade=t=in:s=0:n={k}:color={color}")
        if s["_flash_out"]:
            k, color = s["_flash_out"]
            extra.append(f"fade=t=out:s={n_total - k}:n={k}:color={color}")
        fo = s.get("fade_out")
        if fo:
            k = int(fo.get("frames", 8))
            extra.append(f"fade=t=out:s={n_total - k}:n={k}:color={fo.get('color', 'black')}")
        if extra:
            chains.append(f"[v{i}]" + ",".join(extra) + f"[v{i}f]")
            labels[i] = f"v{i}f"

    # join: runs of hard cuts -> concat, xfade between runs
    cur, cur_len = None, 0
    run_labels: list[str] = []
    run_len = 0
    j = 0

    def flush():
        nonlocal cur, cur_len, run_labels, run_len, j
        if not run_labels:
            return
        if len(run_labels) == 1:
            lab = run_labels[0]
        else:
            lab = f"c{j}"
            chains.append("".join(f"[{x}]" for x in run_labels) + f"concat=n={len(run_labels)}:v=1:a=0[{lab}]")
            j += 1
        if cur is None:
            cur, cur_len = lab, run_len
        else:
            lab2 = f"c{j}"
            j += 1
            chains.append(f"[{cur}][{lab}]concat=n=2:v=1:a=0[{lab2}]")
            cur, cur_len = lab2, cur_len + run_len
        run_labels, run_len = [], 0

    for i, s in enumerate(segs):
        n_total = s["_head"] + s["frames"] + s["_tail"]
        tr = s.get("transition_in") or {}
        if i > 0 and tr.get("type") == "xfade":
            flush()
            k = s["_head"] + segs[i - 1]["_tail"]
            lab = f"x{i}"
            off = (cur_len - k) / fps
            chains.append(f"[{cur}]settb=1/{fps}[{lab}a];[{labels[i]}]settb=1/{fps}[{lab}b];"
                          f"[{lab}a][{lab}b]xfade=transition={tr.get('effect', 'fade')}:"
                          f"duration={k / fps:.5f}:offset={off:.5f}[{lab}]")
            cur, cur_len = lab, cur_len + n_total - k
        else:
            run_labels.append(labels[i])
            run_len += n_total
    flush()
    total = sum(s["frames"] for s in segs)
    if cur_len != total:
        die(f"internal: joined length {cur_len} != {total}")

    # text + overlays on the joined timeline
    stage = cur
    post = []
    for t_i, t in enumerate(plan.d.get("texts", [])):
        post.append(text_chain(t, plan, tmp, t_i))
    if post:
        chains.append(f"[{stage}]" + ",".join(post) + "[txt]")
        stage = "txt"
    for o_i, o in enumerate(plan.d.get("overlays", [])):
        src = plan.p(o["src"])
        if not os.path.exists(src):
            die(f"overlay not found: {src}")
        f0, f1 = int(o.get("from", 0)), int(o.get("to", total))
        if os.path.splitext(src)[1].lower() in (".png", ".webp", ".jpg", ".jpeg"):
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{total / fps + 0.5:.4f}", "-i", src]
            shift = ""
        else:
            args += ["-i", src]
            shift = f",setpts=PTS-STARTPTS+{f0 / fps:.5f}/TB"
        x, y = o.get("x", 0), o.get("y", 0)
        sc = f",scale={o['scale']}" if o.get("scale") else ""
        chains.append(f"[{idx}:v]fps={fps}{shift}{sc},format=rgba,scale=out_color_matrix=bt709:out_range=tv,"
                      f"format=yuva444p10le[ov{o_i}]")
        chains.append(f"[{stage}][ov{o_i}]overlay=x={x}:y={y}:format=yuv444p10:eof_action=pass:"
                      f"enable='between(n\\,{f0}\\,{f1 - 1})'[o{o_i}]")
        stage = f"o{o_i}"
        idx += 1

    f_a, f_b = 0, total
    if a.frames:
        f_a, f_b = (int(x) for x in a.frames.split("-", 1))
        f_b = min(f_b, total)
    if a.still is not None:
        f_a, f_b = a.still, a.still + 1
    final = [f"[{stage}]"]
    if (f_a, f_b) != (0, total):
        final.append(f"trim=start_frame={f_a}:end_frame={f_b},setpts=PTS-STARTPTS,")
    if a.preview:
        final.append(f"scale={W // 2}:{ceil_even(H / 2)}:flags=bicubic,")
    final.append("scale=out_color_matrix=bt709:out_range=tv:sws_dither=ed,format=yuv420p,"
                  "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vout]")
    chains.append("".join(final))

    # ---- audio
    au = {} if a.still is not None else (plan.d.get("audio") or {})
    n_out = f_b - f_a
    T, Ta = n_out / fps, f_a / fps
    a_parts = []
    if au.get("track"):
        tr_path = plan.p(au["track"])
        if not os.path.exists(tr_path):
            die(f"audio track not found: {tr_path}")
        args += ["-ss", f"{float(au.get('track_start', 0)) + Ta:.5f}", "-i", tr_path]
        fo = float(au.get("fade_out_s", 0))
        fade = f",afade=t=out:st={max(0.0, (total / fps - Ta) - fo):.4f}:d={fo:.4f}" if fo else ""
        chains.append(f"[{idx}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                      f"volume={au.get('track_gain_db', 0)}dB{fade},apad,atrim=0:{T:.5f}[atrack]")
        a_parts.append("atrack")
        idx += 1
    if au.get("clip_audio"):
        pieces = []
        for i, s in enumerate(segs):
            d = s["frames"] / fps
            if i in seg_input and infos[s["_src"]].get("has_audio") and not s.get("mute"):
                speed = float(s.get("speed", 1.0))
                head_s = s["_head"] / fps * speed
                tempo = []
                sp = speed
                while sp > 2.0:
                    tempo.append("atempo=2.0"); sp /= 2.0
                while sp < 0.5:
                    tempo.append("atempo=0.5"); sp /= 0.5
                if abs(sp - 1.0) > 1e-3:
                    tempo.append(f"atempo={sp:.5f}")
                tch = ("," + ",".join(tempo)) if tempo else ""
                chains.append(f"[{seg_input[i]}:a:0]atrim=start={head_s:.5f},asetpts=PTS-STARTPTS{tch},"
                              f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                              f"volume={s.get('audio_gain_db', 0)}dB,apad,atrim=0:{d:.5f}[sa{i}]")
            else:
                chains.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{d:.5f}[sa{i}]")
            pieces.append(f"[sa{i}]")
        chains.append("".join(pieces) + f"concat=n={len(pieces)}:v=0:a=1,volume={au.get('clip_gain_db', 0)}dB,"
                      f"atrim=start={Ta:.5f},asetpts=PTS-STARTPTS,apad,atrim=0:{T:.5f}[aclips]")
        a_parts.append("aclips")
    has_audio = bool(a_parts) and a.still is None
    if has_audio:
        mix = (f"[{a_parts[0]}]anull" if len(a_parts) == 1 else
               "".join(f"[{x}]" for x in a_parts) + f"amix=inputs={len(a_parts)}:normalize=0:duration=longest")
        if au.get("loudnorm"):
            mix += f",loudnorm=I={au.get('lufs', -14)}:TP=-1.0:LRA=11"
        chains.append(mix + f",aresample=48000,atrim=0:{T:.5f}[aout]")

    graph = ";\n".join(chains)
    out = a.out or plan.p(plan.d.get("output", "out/final.mp4"))
    if a.preview and not a.out:
        root, ext = os.path.splitext(out)
        out = root + "_preview" + ext
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    gpath = os.path.join(os.path.dirname(plan.path), "build", "filtergraph.txt")
    os.makedirs(os.path.dirname(gpath), exist_ok=True)
    with open(gpath, "w") as f:
        f.write(graph + "\n")
    if a.dry_run:
        print(graph)
        print(f"\n{len(segs)} segments, {total} frames ({total / fps:.2f}s) @ {fps} fps -> {out}")
        shutil.rmtree(tmp, ignore_errors=True)
        return

    args += ["-filter_complex", graph, "-map", "[vout]"]
    if a.still is not None:
        args += ["-frames:v", "1", "-update", "1", "-q:v", "2", out]
    else:
        if has_audio:
            args += ["-map", "[aout]", "-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
        q = plan.d.get("quality", {})
        if a.preview:
            venc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24"]
        else:
            venc = ["-c:v", "libx264", "-preset", q.get("preset", "slower"), "-crf", str(q.get("crf", 14))]
            if q.get("tune", "film"):
                venc += ["-tune", q.get("tune", "film")]
        args += venc + ["-profile:v", "high", "-pix_fmt", "yuv420p",
                        "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709",
                        "-r", str(fps), "-fps_mode", "cfr", "-frames:v", str(n_out),
                        "-movflags", "+faststart", out]
    print(f"Rendering {len(segs)} segments, {n_out} frames ({n_out / fps:.2f}s) -> {out}", file=sys.stderr)
    p = run(args, check=False)
    shutil.rmtree(tmp, ignore_errors=True)
    if p.returncode != 0:
        err = (p.stderr or b"").decode(errors="replace")
        print(err[-4000:], file=sys.stderr)
        die(f"ffmpeg failed - filtergraph saved to {gpath}")
    print(f"done: {out}")


if __name__ == "__main__":
    main()
