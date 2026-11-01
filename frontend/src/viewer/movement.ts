export interface MovementInput {
  forward: boolean;
  backward: boolean;
  left: boolean;
  right: boolean;
}

export interface HorizontalVector {
  x: number;
  z: number;
}

export function movementVector(input: MovementInput, yaw: number): HorizontalVector {
  const forwardAmount = Number(input.forward) - Number(input.backward);
  const rightAmount = Number(input.right) - Number(input.left);
  if (forwardAmount === 0 && rightAmount === 0) return { x: 0, z: 0 };
  const length = Math.hypot(forwardAmount, rightAmount);
  const forwardX = -Math.sin(yaw);
  const forwardZ = -Math.cos(yaw);
  const rightX = Math.cos(yaw);
  const rightZ = -Math.sin(yaw);
  return {
    x: (forwardX * forwardAmount + rightX * rightAmount) / length,
    z: (forwardZ * forwardAmount + rightZ * rightAmount) / length,
  };
}
