import { useEffect, useMemo, useState } from "react";
import type { POI } from "../types";

export function NavigationSearch({ pois, loading, error, activePoiId, onSelect, onAuthor }: {
  pois: POI[];
  loading: boolean;
  error: string | null;
  activePoiId: string | null;
  onSelect: (poi: POI) => void;
  onAuthor: () => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return pois;
    return pois.filter((poi) => [poi.name, poi.category, poi.description, ...poi.aliases].join(" ").toLowerCase().includes(needle));
  }, [pois, query]);
  useEffect(() => setActiveIndex(0), [query]);

  return (
    <section className="navigation-search" aria-label="Destination search">
      <div className="search-row">
        <span aria-hidden="true">⌕</span>
        <input
          value={query}
          placeholder="Where do you want to go?"
          aria-label="Search rooms, objects, or categories"
          aria-expanded={open}
          onFocus={() => setOpen(true)}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") { event.preventDefault(); setActiveIndex((value) => Math.min(results.length - 1, value + 1)); }
            if (event.key === "ArrowUp") { event.preventDefault(); setActiveIndex((value) => Math.max(0, value - 1)); }
            if (event.key === "Enter" && results[activeIndex]) { event.preventDefault(); onSelect(results[activeIndex]); setOpen(false); }
            if (event.key === "Escape") { setOpen(false); event.currentTarget.blur(); }
          }}
        />
        <button onClick={onAuthor} title="Add a POI" aria-label="Add a point of interest">＋</button>
      </div>
      {open && (
        <div className="search-results" role="listbox" aria-label="Destination results">
          {loading && <div className="search-message">Loading destinations…</div>}
          {error && <div className="search-message error" role="alert">{error}</div>}
          {!loading && !error && results.length === 0 && <div className="search-message">No matching destinations</div>}
          {!loading && !error && results.map((poi, index) => (
            <button
              key={poi.id}
              role="option"
              aria-selected={activePoiId === poi.id}
              className={`${index === activeIndex ? "highlighted" : ""} ${activePoiId === poi.id ? "selected" : ""}`}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => { onSelect(poi); setOpen(false); setQuery(poi.name); }}
            >
              <span><strong>{poi.name}</strong><small>{poi.description || poi.category}</small></span>
              <em>{poi.category}</em>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
