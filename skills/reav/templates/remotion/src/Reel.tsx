import React from "react";
import { Video } from "@remotion/media";
import { AbsoluteFill, Easing, Sequence, interpolate, random, staticFile, useCurrentFrame } from "remotion";
import { Texts, useFonts } from "./Texts";
import type { Fx, Plan, Segment } from "./plan";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** CSS for one effect at local frame f (0 = segment's first visible frame). */
function fxStyle(fx: Fx, f: number, w: number): { transform?: string; filter?: string } {
  const from = fx.from ?? 0;
  const n = fx.frames ?? 6;
  const t = f - from;
  if (t < 0 || t >= n) return {};
  const p = t / Math.max(n - 1, 1);
  const amt = fx.amount ?? 1;
  const sign = fx.dir?.startsWith("-") ? -1 : 1;
  const axis = fx.dir?.endsWith("y") ? "Y" : "X";
  switch (fx.type) {
    case "shake": {
      const dx = (random(`sx${t}`) - 0.5) * 40 * amt * (1 - p);
      const dy = (random(`sy${t}`) - 0.5) * 40 * amt * (1 - p);
      return { transform: `translate(${dx}px, ${dy}px) scale(${1 + 0.04 * amt})` };
    }
    case "whip": {
      const off = interpolate(p, [0, 1], [sign * w * 0.35 * amt, 0], { easing: Easing.out(Easing.cubic) });
      const blur = interpolate(p, [0, 1], [28 * amt, 0]);
      return { transform: `translate${axis}(${off}px)`, filter: `blur(${blur}px)` };
    }
    case "punch": {
      const s = interpolate(p, [0, 0.25, 1], [1, 1 + 0.12 * amt, 1], { easing: Easing.out(Easing.quad) });
      return { transform: `scale(${s})` };
    }
    case "invert":
      return { filter: "invert(1)" };
    case "bw":
      return { filter: "grayscale(1)" };
    case "blur":
      return { filter: `blur(${interpolate(p, [0, 1], [20 * amt, 0])}px)` };
    default:
      return {};
  }
}

const Overlay: React.FC<{ color: string; opacity: number }> = ({ color, opacity }) =>
  opacity > 0 ? <AbsoluteFill style={{ backgroundColor: color, opacity }} /> : null;

const SegmentView: React.FC<{ seg: Segment; next?: Segment; plan: Plan }> = ({ seg, next, plan }) => {
  const frame = useCurrentFrame(); // 0 = first frame of the head handle
  const f = frame - seg.head; // 0 = first visible frame
  const tr = seg.transition_in;
  const k = tr?.frames ?? (tr?.type === "flash" ? 3 : 8);

  // incoming xfade look (runs over the head handle + the same amount after the cut)
  let style: React.CSSProperties = {};
  if (tr?.type === "xfade" && seg.head > 0) {
    const p = interpolate(frame, [0, k], [0, 1], clamp);
    const e = tr.effect ?? "fade";
    if (e.startsWith("slide")) {
      const d = e.endsWith("left") ? 1 : e.endsWith("right") ? -1 : 0;
      const v = e.endsWith("up") ? 1 : e.endsWith("down") ? -1 : 0;
      style = { transform: `translate(${(1 - p) * d * plan.width}px, ${(1 - p) * v * plan.height}px)` };
    } else if (e === "zoomin") {
      style = { opacity: p, transform: `scale(${interpolate(p, [0, 1], [1.25, 1])})` };
    } else if (e === "whip") {
      style = {
        transform: `translateX(${(1 - p) * plan.width}px)`,
        filter: `blur(${(1 - p) * 30}px)`,
      };
    } else {
      style = { opacity: p };
    }
  }

  const fxs = (seg.fx ?? []).map((x) => fxStyle(x, f, plan.width));
  const transform = fxs.map((s) => s.transform).filter(Boolean).join(" ");
  const filter = fxs.map((s) => s.filter).filter(Boolean).join(" ");

  // flash / dip / fade_in on the way in, flash/dip of the NEXT segment on the way out, fade_out
  const visibleEnd = seg.frames;
  let inOpacity = 0;
  let inColor = "white";
  if (tr && (tr.type === "flash" || tr.type === "dip" || tr.type === "fade_in")) {
    inColor = tr.color ?? (tr.type === "flash" ? "white" : "black");
    inOpacity = interpolate(f, [0, k], [1, 0], clamp);
  }
  let outOpacity = 0;
  let outColor = "white";
  const ntr = next?.transition_in;
  if (ntr && (ntr.type === "flash" || ntr.type === "dip")) {
    const nk = ntr.type === "flash" ? Math.max(1, Math.floor((ntr.frames ?? 3) / 2)) : ntr.frames ?? 8;
    outColor = ntr.color ?? (ntr.type === "flash" ? "white" : "black");
    outOpacity = interpolate(f, [visibleEnd - nk, visibleEnd], [0, 1], clamp);
  }
  if (seg.fade_out) {
    const fk = seg.fade_out.frames ?? 8;
    outColor = seg.fade_out.color ?? "black";
    outOpacity = Math.max(outOpacity, interpolate(f, [visibleEnd - fk, visibleEnd], [0, 1], clamp));
  }

  return (
    <AbsoluteFill style={{ overflow: "hidden", ...style }}>
      <AbsoluteFill style={{ transform: transform || undefined, filter: filter || undefined }}>
        {seg.color || !seg.file ? (
          <AbsoluteFill style={{ backgroundColor: seg.color ?? "black" }} />
        ) : (
          <Video src={staticFile(seg.file)} muted style={{ width: "100%", height: "100%" }} />
        )}
      </AbsoluteFill>
      {(seg.fx ?? [])
        .filter((x) => x.type === "flash")
        .map((x, i) => (
          <Overlay
            key={i}
            color={x.color ?? "white"}
            opacity={interpolate(f - (x.from ?? 0), [0, x.frames ?? 3], [1, 0], clamp)}
          />
        ))}
      {(seg.fx ?? []).some((x) => x.type === "vignette") ? (
        <AbsoluteFill style={{ background: "radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)" }} />
      ) : null}
      <Overlay color={inColor} opacity={inOpacity} />
      <Overlay color={outColor} opacity={outOpacity} />
    </AbsoluteFill>
  );
};

export const Reel: React.FC<{ plan: Plan | null }> = ({ plan }) => {
  useFonts(plan);
  if (!plan) return null;
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {plan.segments.map((seg, i) => (
        <Sequence
          key={seg.id}
          from={seg.start - seg.head}
          durationInFrames={seg.head + seg.frames + seg.tail}
          name={seg.id}
        >
          <SegmentView seg={seg} next={plan.segments[i + 1]} plan={plan} />
        </Sequence>
      ))}
      <Texts plan={plan} />
    </AbsoluteFill>
  );
};
