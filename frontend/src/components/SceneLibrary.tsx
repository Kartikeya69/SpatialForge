import { useEffect, useMemo, useRef, useState } from "react";
import { assetUrl } from "../api";
import type { SceneSummary } from "../types";

export function SceneLibrary({ scenes, selectedId, onSelect }: {
  scenes: SceneSummary[];
  selectedId: string;
  onSelect: (sceneId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const active = scenes.find((scene) => scene.scene_id === selectedId) ?? scenes[0];
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return scenes.filter((scene) => !needle || `${scene.scene_name} ${scene.description} ${scene.asset_types.join(" ")}`.toLowerCase().includes(needle));
  }, [query, scenes]);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="scene-library">
      <button className="scene-trigger" type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}>
        <span><small>Active scene</small><strong>{active?.scene_name ?? "Choose scene"}</strong></span>
        <span aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="library-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
          <section className="library-dialog" role="dialog" aria-modal="true" aria-labelledby="scene-library-title">
            <header>
              <div><span className="eyebrow">Scene library</span><h2 id="scene-library-title">Open a digital twin</h2></div>
              <button className="icon-button" onClick={() => setOpen(false)} aria-label="Close scene library">×</button>
            </header>
            <label className="library-search">
              <span aria-hidden="true">⌕</span>
              <input ref={searchRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search scenes or asset types" aria-label="Search scenes" />
            </label>
            <div className="scene-grid">
              {filtered.map((scene) => (
                <button
                  className={`scene-card ${scene.scene_id === selectedId ? "selected" : ""}`}
                  key={scene.scene_id}
                  onClick={() => { onSelect(scene.scene_id); setOpen(false); setQuery(""); }}
                >
                  <span className="scene-card-visual" aria-hidden="true">
                    {scene.thumbnail_path ? <img src={assetUrl(scene.scene_id, scene.thumbnail_path)} alt="" loading="lazy" /> : <span>{scene.synthetic_demo ? "DEMO" : "3D"}</span>}
                  </span>
                  <span className="scene-card-copy">
                    <strong>{scene.scene_name}</strong>
                    <small>{scene.description || "No description available"}</small>
                    <span className="asset-tags">{scene.asset_types.slice(0, 4).map((type) => <em key={type}>{type.toUpperCase()}</em>)}</span>
                  </span>
                  {scene.scene_id === selectedId && <span className="active-check" aria-label="Currently active">✓</span>}
                </button>
              ))}
              {filtered.length === 0 && <div className="library-empty"><strong>No matching scenes</strong><span>Try a different name or asset type.</span></div>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
