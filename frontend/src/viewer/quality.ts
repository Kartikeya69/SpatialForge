import type { QualityPreset } from "../types";

export interface QualitySettings {
  label: string;
  dpr: [number, number];
  antialias: boolean;
  shadows: boolean;
  pointBudget: number;
}

export const QUALITY_SETTINGS: Record<QualityPreset, QualitySettings> = {
  low: { label: "Low", dpr: [0.75, 1], antialias: false, shadows: false, pointBudget: 350_000 },
  balanced: { label: "Balanced", dpr: [1, 1.5], antialias: true, shadows: false, pointBudget: 1_000_000 },
  high: { label: "High", dpr: [1, 2], antialias: true, shadows: true, pointBudget: 3_000_000 },
};

export function qualitySettings(preset: QualityPreset): QualitySettings {
  return QUALITY_SETTINGS[preset];
}
