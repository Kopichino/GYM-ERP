import { Environment, Float, Stars } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Suspense } from "react";

function GymEmblem() {
  return (
    <Float speed={1.5} rotationIntensity={1.1} floatIntensity={1.4}>
      <mesh castShadow receiveShadow>
        <torusKnotGeometry args={[1.1, 0.34, 220, 32]} />
        <meshStandardMaterial color="#ff3d5a" metalness={0.85} roughness={0.18} emissive="#3a0912" emissiveIntensity={0.4} />
      </mesh>
    </Float>
  );
}

export default function HeroScene() {
  return (
    <Canvas
      camera={{ position: [0, 0, 5.5], fov: 45 }}
      dpr={[1, 1.75]}
      gl={{ antialias: true }}
      className="!absolute inset-0"
    >
      <Suspense fallback={null}>
        <ambientLight intensity={0.4} />
        <directionalLight position={[4, 5, 3]} intensity={1.8} color="#ffb020" />
        <pointLight position={[-4, -2, -3]} intensity={0.6} color="#ff3d5a" />
        <GymEmblem />
        <Stars radius={40} depth={30} count={1200} factor={2} fade speed={0.5} />
        <Environment preset="city" />
      </Suspense>
    </Canvas>
  );
}
