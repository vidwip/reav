// Types for public/plan.json, written by `render.py edit-plan.json --export-segments <remotion>/public`.
// Same schema as edit-plan.json (references/edit-plan.md) plus `file`, `start`, `head`, `tail` per segment.

export type Transition = {
  type: "cut" | "flash" | "dip" | "fade_in" | "xfade";
  frames?: number;
  color?: string;
  /** xfade look in Remotion: fade | slideleft | slideright | slideup | slidedown | zoomin | whip */
  effect?: string;
};

/** Per-segment effect, frames relative to the segment's first visible frame. */
export type Fx = {
  type: "shake" | "whip" | "punch" | "invert" | "bw" | "blur" | "vignette" | "flash";
  from?: number;
  frames?: number;
  amount?: number;
  dir?: "x" | "y" | "-x" | "-y";
  color?: string;
};

export type Segment = {
  id: string;
  frames: number;
  color?: string;
  file?: string; // public/segments/<id>.mp4, already graded + reframed by ffmpeg
  start: number; // timeline frame of the first visible frame
  head: number; // extra frames before start (xfade handle)
  tail: number; // extra frames after the end (xfade handle)
  transition_in?: Transition;
  fade_out?: { frames?: number; color?: string };
  fx?: Fx[];
};

export type TextAnim = "none" | "fade" | "pop" | "slide_up" | "typewriter" | "words" | "karaoke" | "punch";

export type TextItem = {
  text: string;
  from: number;
  to: number;
  font?: string;
  size?: number;
  weight?: number;
  color?: string;
  x?: number | "center";
  y?: number;
  align?: "left" | "center" | "right";
  wrap?: number;
  uppercase?: boolean;
  letter_spacing?: number;
  line_height?: number;
  box?: { color?: string; pad?: number; radius?: number };
  border?: { width?: number; color?: string };
  shadow?: { x?: number; y?: number; blur?: number; color?: string };
  anim?: TextAnim;
  anim_frames?: number;
  highlight?: string;
  fade_out?: number;
};

export type Plan = {
  fps: number;
  width: number;
  height: number;
  total: number;
  segments: Segment[];
  texts?: TextItem[];
  fonts?: Record<string, string>; // name -> public/fonts/<file>
};
