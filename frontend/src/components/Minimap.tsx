import { useMemo, useRef, useState } from "react";
import type { CameraTelemetry, ColliderDocument, POI, RouteResult, SceneManifest } from "../types";
import { isWalkableTarget, mapToWorld, worldToMap } from "../viewer/minimap";

const MAP_SIZE = 180;

export function Minimap({ manifest, colliders, telemetry, route, pois, onSelectPoi, onReposition }: {
  manifest: SceneManifest;
  colliders: ColliderDocument | null;
  telemetry: CameraTelemetry | null;
  route: RouteResult | null;
  pois: POI[];
  onSelectPoi: (poi: POI) => void;
  onReposition: (x: number, z: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [notice, setNotice] = useState("");
  const svgRef = useRef<SVGSVGElement>(null);
  const bounds = colliders?.walkable_bounds ?? manifest.bounding_box;
  const marker = telemetry ? worldToMap({ x: telemetry.position[0], z: telemetry.position[2] }, bounds, MAP_SIZE, MAP_SIZE) : null;
  const routePoints = route?.waypoints.map((point) => worldToMap({ x: point[0], z: point[2] }, bounds, MAP_SIZE, MAP_SIZE)) ?? [];
  const destination = route ? worldToMap({ x: route.destination.position[0], z: route.destination.position[2] }, bounds, MAP_SIZE, MAP_SIZE) : null;
  const poiMarkers = pois.map((poi) => ({ poi, point: worldToMap({ x: poi.position[0], z: poi.position[2] }, bounds, MAP_SIZE, MAP_SIZE) }));
  const obstacleRects = useMemo(() => colliders?.colliders.map((collider) => {
    const topLeft = worldToMap({ x: collider.minimum[0], z: collider.maximum[2] }, bounds, MAP_SIZE, MAP_SIZE);
    const bottomRight = worldToMap({ x: collider.maximum[0], z: collider.minimum[2] }, bounds, MAP_SIZE, MAP_SIZE);
    return { id: collider.id, x: topLeft.x, y: topLeft.y, width: bottomRight.x - topLeft.x, height: bottomRight.y - topLeft.y };
  }) ?? [], [bounds, colliders]);

  const reposition = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!colliders) { setNotice("No verified navigation geometry"); return; }
    const rect = svgRef.current!.getBoundingClientRect();
    const point = { x: ((event.clientX - rect.left) / rect.width) * MAP_SIZE, y: ((event.clientY - rect.top) / rect.height) * MAP_SIZE };
    const world = mapToWorld(point, bounds, MAP_SIZE, MAP_SIZE);
    if (!isWalkableTarget(world, colliders, manifest.navigation.collision_radius)) { setNotice("Choose a clear walkable area"); return; }
    setNotice("");
    onReposition(world.x, world.z);
  };

  return (
    <section className={`minimap ${expanded ? "expanded" : ""}`} aria-label="Scene minimap">
      <header><span>Overview</span><button onClick={() => setExpanded((value) => !value)} aria-label={expanded ? "Collapse minimap" : "Expand minimap"}>{expanded ? "−" : "+"}</button></header>
      <svg ref={svgRef} viewBox={`0 0 ${MAP_SIZE} ${MAP_SIZE}`} onClick={reposition} role="img" aria-label="Walkable scene map; select a clear area to reposition">
        <rect className="map-floor" x="1" y="1" width={MAP_SIZE - 2} height={MAP_SIZE - 2} rx="4" />
        {obstacleRects.map((rect) => <rect className="map-obstacle" key={rect.id} {...rect} />)}
        {routePoints.length > 1 && <polyline className="map-route" points={routePoints.map((point) => `${point.x},${point.y}`).join(" ")} />}
        {poiMarkers.map(({ poi, point }) => <g key={poi.id} className="map-poi" transform={`translate(${point.x} ${point.y})`} onClick={(event) => { event.stopPropagation(); onSelectPoi(poi); }} role="button" aria-label={`Navigate to ${poi.name}`}><circle r="5" /><circle r="1.8" /></g>)}
        {destination && <g transform={`translate(${destination.x} ${destination.y})`}><circle className="map-destination-halo" r="8" /><circle className="map-destination" r="3" /></g>}
        {marker && <g transform={`translate(${marker.x} ${marker.y}) rotate(${(-telemetry!.yaw * 180) / Math.PI})`}><circle className="map-position" r="6" /><path className="map-heading" d="M 0 -12 L -4 -4 L 4 -4 Z" /></g>}
      </svg>
      {notice && <small role="status">{notice}</small>}
    </section>
  );
}
