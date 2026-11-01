import { Line } from "@react-three/drei";
import { useMemo } from "react";
import { DoubleSide, Vector3 } from "three";
import type { RouteResult } from "../types";

export function RouteOverlay({ route }: { route: RouteResult }) {
  const points = useMemo(() => route.waypoints.map(([x, y, z]) => new Vector3(x, y + 0.035, z)), [route]);
  const arrows = useMemo(() => {
    const result: { position: Vector3; angle: number }[] = [];
    for (let index = 0; index < points.length - 1; index += 3) {
      const a = points[index];
      const b = points[Math.min(points.length - 1, index + 1)];
      result.push({ position: a.clone().lerp(b, 0.5), angle: Math.atan2(b.x - a.x, b.z - a.z) });
    }
    return result;
  }, [points]);
  if (points.length < 2) return null;
  return (
    <group name="navigation-route">
      <Line points={points} color="#4adebc" lineWidth={4} transparent opacity={0.88} depthTest={false} />
      {arrows.map((arrow, index) => (
        <mesh key={index} position={arrow.position} rotation={[-Math.PI / 2, 0, arrow.angle]}>
          <coneGeometry args={[0.12, 0.28, 3]} />
          <meshBasicMaterial color="#d9fff4" side={DoubleSide} depthTest={false} />
        </mesh>
      ))}
      <mesh position={points[0]}><sphereGeometry args={[0.13, 14, 14]} /><meshBasicMaterial color="#ffffff" depthTest={false} /></mesh>
      <mesh position={points[points.length - 1]}><cylinderGeometry args={[0.17, 0.17, 0.5, 18]} /><meshStandardMaterial color="#ff9a57" emissive="#7a2f0b" emissiveIntensity={0.4} /></mesh>
    </group>
  );
}
