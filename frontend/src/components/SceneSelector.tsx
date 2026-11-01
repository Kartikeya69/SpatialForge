import type { SceneSummary } from "../types";

export function SceneSelector({
  scenes,
  selectedId,
  onSelect,
}: {
  scenes: SceneSummary[];
  selectedId: string;
  onSelect: (sceneId: string) => void;
}) {
  return (
    <label className="scene-picker">
      <span>Active scene</span>
      <select value={selectedId} onChange={(event) => onSelect(event.target.value)} aria-label="Active scene">
        {scenes.map((scene) => (
          <option value={scene.scene_id} key={scene.scene_id}>
            {scene.scene_name}{scene.synthetic_demo ? " · Demo" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
