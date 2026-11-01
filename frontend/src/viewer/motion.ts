export function smoothingAlpha(deltaSeconds: number, response: number): number {
  if (response <= 0) return 1;
  return 1 - Math.exp(-response * Math.max(0, deltaSeconds));
}

export function movementDistance(speed: number, deltaSeconds: number, sprintMultiplier = 1): number {
  return speed * sprintMultiplier * Math.max(0, Math.min(deltaSeconds, 0.1));
}
