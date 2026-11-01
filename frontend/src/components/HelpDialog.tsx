import { useEffect } from "react";

export function HelpDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="controls-title">
        <header><div><span className="eyebrow">Keyboard guide</span><h2 id="controls-title">Explore SpatialForge</h2></div><button onClick={onClose} aria-label="Close keyboard guide">×</button></header>
        <div className="shortcut-grid">
          <div><kbd>W A S D</kbd><span><strong>Move</strong><small>Walk through the scene</small></span></div>
          <div><kbd>Mouse</kbd><span><strong>Look</strong><small>Click, drag, or double-click</small></span></div>
          <div><kbd>Shift</kbd><span><strong>Sprint</strong><small>Move at increased speed</small></span></div>
          <div><kbd>R</kbd><span><strong>Reset</strong><small>Return to the mode start</small></span></div>
          <div><kbd>Esc</kbd><span><strong>Release</strong><small>Exit mouse look or close a panel</small></span></div>
          <div><kbd>?</kbd><span><strong>Help</strong><small>Open this keyboard guide</small></span></div>
        </div>
        <p>Collision-safe exploration requires an explicit collider asset. Sparse point clouds are visual diagnostics only.</p>
      </section>
    </div>
  );
}
