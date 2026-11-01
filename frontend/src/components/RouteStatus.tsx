import type { POI, RouteResult } from "../types";

export function RouteStatus({ route, destination, progress, status, onCancel }: {
  route: RouteResult | null;
  destination: POI | null;
  progress: number;
  status: "routing" | "active" | "arrived" | "error";
  onCancel: () => void;
}) {
  if (!destination) return null;
  return (
    <section className={`route-status ${status}`} aria-live="polite">
      <div className="route-icon" aria-hidden="true">↗</div>
      <div>
        <small>{status === "routing" ? "Calculating route" : status === "arrived" ? "You have arrived" : status === "error" ? "Route unavailable" : `${Math.round(progress * 100)}% complete`}</small>
        <strong>{destination.name}</strong>
        {route && <span>{Math.max(0, route.route_length * (1 - progress)).toFixed(1)} {route.distance_units === "meter" ? "m" : "scene units"} remaining</span>}
      </div>
      <button onClick={onCancel} aria-label="Cancel route">×</button>
      {route && <i style={{ width: `${Math.round(progress * 100)}%` }} />}
    </section>
  );
}
