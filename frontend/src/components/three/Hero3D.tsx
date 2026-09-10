import type { MotionValue } from "framer-motion";
import { lazy, Suspense, useState } from "react";

const HeroScene = lazy(() => import("./HeroScene"));

function supportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function StaticFallback() {
  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(255,61,90,0.35),transparent_60%)]" />
  );
}

export default function Hero3D({ scrollProgress }: { scrollProgress: MotionValue<number> }) {
  // Probed once via a lazy initialiser rather than in an effect. Detecting it
  // after mount meant the first paint always assumed "no WebGL", so every
  // visitor saw the flat fallback flash before the scene replaced it.
  const [canRender3D] = useState(supportsWebGL);

  if (!canRender3D) return <StaticFallback />;

  return (
    <Suspense fallback={<StaticFallback />}>
      <HeroScene scrollProgress={scrollProgress} />
    </Suspense>
  );
}
