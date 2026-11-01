import type { SceneManifest } from "../types";

export function SceneDetails({ manifest, onClose }: { manifest: SceneManifest; onClose: () => void }) {
  return (
    <aside className="details-panel" role="dialog" aria-modal="false" aria-labelledby="scene-details-title">
      <div className="details-header">
        <div className="eyebrow">Scene intelligence</div>
        <button type="button" onClick={onClose} aria-label="Close scene information">Close</button>
      </div>
      <h2 id="scene-details-title">{manifest.scene_name}</h2>
      <p>{manifest.description}</p>
      {manifest.synthetic_demo && <div className="demo-notice">Synthetic demonstration — not reconstructed data</div>}
      <dl className="metric-grid">
        <div><dt>Schema</dt><dd>{manifest.schema_version}</dd></div>
        <div><dt>Source</dt><dd>{manifest.reconstruction.source}</dd></div>
        <div><dt>Scale</dt><dd>{manifest.units.metric_scale_status}</dd></div>
        <div><dt>Assets</dt><dd>{manifest.assets.length}</dd></div>
        <div><dt>Zones</dt><dd>{manifest.navigation.zones.length}</dd></div>
        <div><dt>POIs</dt><dd>{manifest.poi_metadata.count}</dd></div>
      </dl>
      <div className="coordinate-card">
        <span>World convention</span>
        <strong>Right-handed · Y up · −Z forward</strong>
        <small>{manifest.coordinate_system.source_convention}</small>
      </div>
    </aside>
  );
}
