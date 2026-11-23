import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { Plan, TextItem } from "./plan";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Load every plan.fonts entry (public/fonts/...) as a FontFace named after its key. */
export function useFonts(plan: Plan | null) {
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    const fonts = Object.entries(plan?.fonts ?? {});
    Promise.all(
      fonts.map(async ([name, file]) => {
        const face = new FontFace(name, `url(${staticFile(file)})`);
        await face.load();
        document.fonts.add(face);
      }),
    )
      .catch((e) => console.error("font load failed", e))
      .finally(() => continueRender(handle));
  }, [plan, handle]);
}

function wrap(text: string, width?: number): string {
  if (!width) return text;
  return text
    .split("\n")
    .map((para) => {
      const lines: string[] = [];
      let line = "";
      for (const w of para.split(" ")) {
        if (line && line.length + 1 + w.length > width) {
          lines.push(line);
          line = w;
        } else line = line ? `${line} ${w}` : w;
      }
      lines.push(line);
      return lines.join("\n");
    })
    .join("\n");
}

const TextView: React.FC<{ t: TextItem }> = ({ t }) => {
  const frame = useCurrentFrame(); // 0 = t.from
  const { fps, width, height } = useVideoConfig();
  const dur = t.to - t.from;
  const n = t.anim_frames ?? 8;
  const raw = wrap(t.uppercase ? t.text.toUpperCase() : t.text, t.wrap);
  const words = raw.split(/(\s+)/);

  let opacity = 1;
  let transform = "";
  let shown = raw;
  const anim = t.anim ?? "none";
  if (anim === "fade") opacity = interpolate(frame, [0, n], [0, 1], clamp);
  if (anim === "pop") {
    const s = spring({ frame, fps, config: { damping: 12, stiffness: 180 }, durationInFrames: n * 2 });
    transform = `scale(${interpolate(s, [0, 1], [0.6, 1])})`;
    opacity = interpolate(frame, [0, 2], [0, 1], clamp);
  }
  if (anim === "punch") transform = `scale(${interpolate(frame, [0, 2, n], [1.35, 0.96, 1], clamp)})`;
  if (anim === "slide_up") {
    const s = spring({ frame, fps, config: { damping: 200 }, durationInFrames: n });
    transform = `translateY(${interpolate(s, [0, 1], [60, 0])}px)`;
    opacity = s;
  }
  if (anim === "typewriter") {
    const chars = Math.floor(interpolate(frame, [0, n * 3], [0, raw.length], clamp));
    shown = raw.slice(0, chars);
  }
  if (t.fade_out) opacity *= interpolate(frame, [dur - t.fade_out, dur], [1, 0], clamp);

  const per = Math.max(1, Math.floor(dur / Math.max(1, words.filter((w) => w.trim()).length)));
  let wi = -1;
  const body =
    anim === "words" || anim === "karaoke"
      ? words.map((w, i) => {
          if (!w.trim()) return <span key={i}>{w}</span>;
          wi += 1;
          const on = frame >= wi * per;
          if (anim === "words" && !on) return <span key={i} style={{ opacity: 0 }}>{w}</span>;
          const active = anim === "karaoke" && frame >= wi * per && frame < (wi + 1) * per;
          return (
            <span key={i} style={{ color: active ? t.highlight ?? "#FFE600" : undefined }}>
              {w}
            </span>
          );
        })
      : shown;

  const align = t.align ?? "center";
  const x = t.x === undefined || t.x === "center" ? 0.5 : t.x;
  const y = t.y ?? 0.5;
  const sh = t.shadow;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: x * width,
          top: y * height,
          transform: `translate(-50%, -50%) ${transform}`,
          opacity,
          width: "max-content", // absolute + left:50% would otherwise shrink-wrap to half the frame
          maxWidth: width * 0.9,
          whiteSpace: "pre-wrap",
          textAlign: align,
          fontFamily: t.font ?? "system-ui",
          fontWeight: t.weight ?? 700,
          fontSize: t.size ?? 64,
          lineHeight: t.line_height ?? 1.15,
          letterSpacing: t.letter_spacing ?? 0,
          color: t.color ?? "white",
          WebkitTextStroke: t.border?.width ? `${t.border.width}px ${t.border.color ?? "black"}` : undefined,
          paintOrder: "stroke fill",
          textShadow: sh ? `${sh.x ?? 2}px ${sh.y ?? 2}px ${sh.blur ?? 0}px ${sh.color ?? "rgba(0,0,0,0.5)"}` : undefined,
          backgroundColor: t.box?.color,
          padding: t.box ? `${(t.box.pad ?? 16) * 0.6}px ${t.box.pad ?? 16}px` : undefined,
          borderRadius: t.box?.radius ?? 0,
          boxDecorationBreak: "clone",
          WebkitBoxDecorationBreak: "clone",
        }}
      >
        {body}
      </div>
    </AbsoluteFill>
  );
};

export const Texts: React.FC<{ plan: Plan }> = ({ plan }) => (
  <>
    {(plan.texts ?? []).map((t, i) => (
      <Sequence key={i} from={t.from} durationInFrames={Math.max(1, t.to - t.from)} name={`text ${i + 1}`}>
        <TextView t={t} />
      </Sequence>
    ))}
  </>
);

/** Transparent text layer: npx remotion render TextLayer out/text.mov --codec=prores --prores-profile=4444 --pixel-format=yuva444p10le */
export const TextLayer: React.FC<{ plan: Plan | null }> = ({ plan }) => {
  useFonts(plan);
  if (!plan) return null;
  return (
    <AbsoluteFill>
      <Texts plan={plan} />
    </AbsoluteFill>
  );
};
