import { MathUtils } from "three";

export interface LookAngles {
  yaw: number;
  pitch: number;
}

const DEFAULT_SENSITIVITY = 0.0022;
const DEFAULT_PITCH_LIMIT = MathUtils.degToRad(86);

export function applyLookDelta(
  angles: LookAngles,
  deltaX: number,
  deltaY: number,
  sensitivity = DEFAULT_SENSITIVITY,
  pitchLimit = DEFAULT_PITCH_LIMIT,
): LookAngles {
  return {
    yaw: angles.yaw - deltaX * sensitivity,
    pitch: MathUtils.clamp(angles.pitch - deltaY * sensitivity, -pitchLimit, pitchLimit),
  };
}
