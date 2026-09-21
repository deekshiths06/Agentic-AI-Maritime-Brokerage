import React from "react";

// =========================================================
// ERROR BOUNDARY
// =========================================================
// Catches render errors in the map page (and any child) so a
// single component failure can never blank the whole app.
// Shows a non-blocking error card with a recovery action
// instead of a white screen.
// =========================================================

const DEFAULT_FALLBACK = (error, onRetry) => (
  <div className="route-map-error" role="alert">
    <strong>The interactive map is temporarily unavailable.</strong>
    <span>
      Your route details remain available below. You can try loading
      the map again.
    </span>
    {typeof onRetry === "function" && (
      <button
        type="button"
        className="secondary-button"
        onClick={onRetry}
      >
        Try Again
      </button>
    )}
  </div>
);

export default class MapErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onRetry) {
      this.props.onRetry();
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback(
          this.state.error,
          this.handleRetry
        );
      }
      return DEFAULT_FALLBACK(
        this.state.error,
        this.props.onRetry ? this.handleRetry : null
      );
    }

    return this.props.children;
  }
}