import { Component } from "react"

const API = "http://127.0.0.1:5000"

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, info: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error("REACT ERROR:", error?.message, "\nSTACK:", error?.stack)
    this.setState({ info })
    fetch(`${API}/api/log-error`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: error?.message || "?",
        stack: error?.stack || "",
      }),
    }).catch(() => {})
  }

  handleCopy = () => {
    const msg = this.state.error
      ? `ERROR: ${this.state.error.message}\n\nSTACK:\n${this.state.error.stack}`
      : ""
    navigator.clipboard.writeText(msg)
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            padding: 32,
            maxWidth: 800,
            margin: "40px auto",
            background: "#0d1625",
            border: "1px solid #ff4d6a",
            borderRadius: 12,
            fontFamily: "'IBM Plex Mono', 'Courier New', monospace",
            color: "#e2e8f0",
          }}
        >
          <h2 style={{ color: "#ff4d6a", margin: "0 0 20px", fontSize: 24 }}>
            ⚠️ Render Error
          </h2>

          <div
            style={{
              background: "#1a0a0a",
              border: "1px solid #ff4d6a44",
              borderRadius: 8,
              padding: 16,
              marginBottom: 20,
              fontSize: 14,
              lineHeight: 1.6,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
              maxHeight: 400,
              overflow: "auto",
            }}
          >
            <strong style={{ color: "#ff8a9e" }}>Message:</strong>
            <div style={{ marginTop: 4, marginBottom: 16 }}>
              {this.state.error.message}
            </div>
            <strong style={{ color: "#ff8a9e" }}>Stack:</strong>
            <div style={{ marginTop: 4, color: "#8b9bb5", fontSize: 12 }}>
              {this.state.error.stack}
            </div>
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={this.handleCopy}
              style={{
                padding: "8px 16px",
                background: "#1a2744",
                border: "1px solid #3b9eff",
                borderRadius: 6,
                color: "#3b9eff",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              📋 COPY ERROR
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: "8px 16px",
                background: "#3b9eff",
                border: "none",
                borderRadius: 6,
                color: "#fff",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              🔄 RELOAD
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

// Section-level error boundary - wraps individual sections so a crash
// in one section doesn't break the WHOLE page
const API_ERROR = "http://127.0.0.1:5000"

export class SectionBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  componentDidCatch(error, info) {
    try {
      fetch(`${API_ERROR}/api/log-error`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          error: `SectionBoundary[${this.props.name || "?"}]: ${error.message}`,
          stack: error.stack,
          componentStack: info?.componentStack || "",
        }),
      }).catch(() => {})
    } catch {}
  }
  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            padding: 12,
            margin: "8px 0",
            border: "1px dashed #ff4d6a44",
            borderRadius: 6,
            color: "#ff4d6a",
            fontSize: 12,
            fontFamily: "'IBM Plex Mono', monospace",
            background: "#1a0a0a55",
          }}
        >
          ⚠️ Section [{this.props.name || "?"}] crashed: {this.state.error.message}
          <button
            onClick={() => this.setState({ error: null })}
            style={{
              marginLeft: 8,
              background: "none",
              border: "1px solid #ff4d6a44",
              color: "#ff4d6a",
              cursor: "pointer",
              fontSize: 10,
              borderRadius: 4,
              padding: "2px 8px",
            }}
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}