import { useState } from "react";
import type { Vector3Tuple } from "../types";

export function PoiAuthorDialog({ position, onSave, onClose }: {
  position: Vector3Tuple;
  onSave: (name: string, category: string, aliases: string[]) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("place");
  const [aliases, setAliases] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <form className="poi-author" role="dialog" aria-modal="true" aria-labelledby="poi-author-title" onSubmit={async (event) => {
        event.preventDefault(); setSaving(true); setError("");
        try { await onSave(name.trim(), category.trim(), aliases.split(",").map((value) => value.trim()).filter(Boolean)); onClose(); }
        catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save POI"); }
        finally { setSaving(false); }
      }}>
        <header><div><span className="eyebrow">POI authoring</span><h2 id="poi-author-title">Label current location</h2></div><button type="button" onClick={onClose} aria-label="Close">×</button></header>
        <p>Move to the desired walkable position, then save it as a destination. Coordinates: <code>{position[0].toFixed(2)}, {position[2].toFixed(2)}</code></p>
        <label>Name<input autoFocus required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Design desk" /></label>
        <label>Category<input required maxLength={60} value={category} onChange={(event) => setCategory(event.target.value)} /></label>
        <label>Search aliases<input value={aliases} onChange={(event) => setAliases(event.target.value)} placeholder="desk, workstation" /></label>
        {error && <div className="author-error" role="alert">{error}</div>}
        <footer><button type="button" onClick={onClose}>Cancel</button><button type="submit" disabled={saving || !name.trim()}>{saving ? "Saving…" : "Save POI"}</button></footer>
      </form>
    </div>
  );
}
