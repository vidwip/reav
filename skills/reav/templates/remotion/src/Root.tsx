import { CalculateMetadataFunction, Composition, staticFile } from "remotion";
import { Reel } from "./Reel";
import { TextLayer } from "./Texts";
import type { Plan } from "./plan";

type Props = { plan: Plan | null };

const loadPlan: CalculateMetadataFunction<Props> = async () => {
  const res = await fetch(staticFile("plan.json"));
  if (!res.ok) {
    throw new Error("public/plan.json missing - run: render.py edit-plan.json --export-segments <this dir>/public");
  }
  const plan = (await res.json()) as Plan;
  return {
    durationInFrames: plan.total,
    fps: plan.fps,
    width: plan.width,
    height: plan.height,
    props: { plan },
  };
};

export const RemotionRoot: React.FC = () => (
  <>
    {/* Full edit with React effects over ffmpeg-graded segments */}
    <Composition
      id="Reel"
      component={Reel}
      defaultProps={{ plan: null } as Props}
      calculateMetadata={loadPlan}
      durationInFrames={30}
      fps={30}
      width={1080}
      height={1920}
    />
    {/* Animated text only, transparent: render as ProRes 4444 and add to edit-plan "overlays" */}
    <Composition
      id="TextLayer"
      component={TextLayer}
      defaultProps={{ plan: null } as Props}
      calculateMetadata={loadPlan}
      durationInFrames={30}
      fps={30}
      width={1080}
      height={1920}
    />
  </>
);
