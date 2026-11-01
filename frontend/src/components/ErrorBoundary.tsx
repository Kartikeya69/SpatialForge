import { Component, type ErrorInfo, type ReactNode } from "react";

export class ViewerErrorBoundary extends Component<
  { children: ReactNode; resetKey: string; onRetry: () => void },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("SpatialForge viewer failed", error, info.componentStack);
  }

  componentDidUpdate(previous: Readonly<{ resetKey: string }>) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="state-layer error-state" role="alert">
        <div className="error-icon">!</div>
        <strong>The scene could not be rendered</strong>
        <p>{this.state.error.message || "A 3D asset failed while loading."}</p>
        <button onClick={() => { this.setState({ error: null }); this.props.onRetry(); }}>Retry scene</button>
      </div>
    );
  }
}

export function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}
