import { Float, Stars } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMotionValueEvent, type MotionValue } from "framer-motion";
import { Suspense, useRef } from "react";
import type { Group } from "three";

function GymEmblem() {
  return (
    <Float speed={1.5} rotationIntensity={1.1} floatIntensity={1.4}>
      <mesh castShadow receiveShadow position={[-3.1, 1.9, -3.2]} scale={0.4}>
        <torusKnotGeometry args={[1.1, 0.34, 220, 32]} />
        <meshStandardMaterial color="#ff3d5a" metalness={0.85} roughness={0.18} emissive="#3a0912" emissiveIntensity={0.35} />
      </mesh>
    </Float>
  );
}

const PLATES = [
  { offset: 1.32, radius: 0.56 },
  { offset: 1.08, radius: 0.44 },
];

function Dumbbell({ scrollProgress }: { scrollProgress: MotionValue<number> }) {
  const group = useRef<Group>(null);
  const progress = useRef(0);
  useMotionValueEvent(scrollProgress, "change", (v) => {
    progress.current = v;
  });

  const baseX = 3.1;
  const baseY = -1.6;

  useFrame((state, delta) => {
    const node = group.current;
    if (!node) return;
    const p = progress.current;
    node.rotation.z += delta * (0.35 + p * 2.4);
    node.rotation.x = p * Math.PI * 1.3;
    node.position.y = baseY - p * 2.2 + Math.sin(state.clock.elapsedTime * 1.1) * 0.08;
    node.position.x = baseX + p * 1.8;
    const scale = Math.max(0.55 - p * 0.3, 0.22);
    node.scale.setScalar(scale);
  });

  return (
    <group ref={group} position={[baseX, baseY, -1.2]} rotation={[0.15, 0.5, 0.4]}>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[0.09, 0.09, 2.2, 20]} />
        <meshStandardMaterial color="#2b2b34" metalness={0.9} roughness={0.25} />
      </mesh>
      {PLATES.map(({ offset, radius }) => (
        <mesh key={`l-${offset}`} position={[-offset, 0, 0]} castShadow receiveShadow>
          <cylinderGeometry args={[radius, radius, 0.16, 28]} />
          <meshStandardMaterial color="#ff3d5a" metalness={0.75} roughness={0.28} emissive="#3a0912" emissiveIntensity={0.3} />
        </mesh>
      ))}
      {PLATES.map(({ offset, radius }) => (
        <mesh key={`r-${offset}`} position={[offset, 0, 0]} castShadow receiveShadow>
          <cylinderGeometry args={[radius, radius, 0.16, 28]} />
          <meshStandardMaterial color="#ffb020" metalness={0.75} roughness={0.28} emissive="#4a2c00" emissiveIntensity={0.3} />
        </mesh>
      ))}
    </group>
  );
}

export default function HeroScene({ scrollProgress }: { scrollProgress: MotionValue<number> }) {
  return (
    <Canvas
      camera={{ position: [0, 0, 5.5], fov: 45 }}
      dpr={[1, 1.75]}
      gl={{ antialias: true }}
      className="!absolute inset-0"
    >
      <Suspense fallback={null}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[4, 5, 3]} intensity={1.8} color="#ffb020" />
        <pointLight position={[-4, -2, -3]} intensity={0.7} color="#ff3d5a" />
        <pointLight position={[3, 3, 4]} intensity={0.35} color="#ffffff" />
        <Dumbbell scrollProgress={scrollProgress} />
        <GymEmblem />
        <Stars radius={40} depth={30} count={400} factor={2} fade speed={0.5} />
      </Suspense>
    </Canvas>
  );
}
