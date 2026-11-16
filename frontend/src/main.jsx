import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'

// ── Global error logger ──
window.addEventListener('error', (event) => {
  console.error('GLOBAL ERROR:', event.error?.message, event.error?.stack)
  const el = document.getElementById('root-error')
  if (el) {
    el.textContent = `Runtime error: ${event.error?.message || 'Unknown'}`
    el.style.display = 'block'
  }
})
window.addEventListener('unhandledrejection', (event) => {
  console.error('UNHANDLED PROMISE:', event.reason?.message || event.reason)
  const el = document.getElementById('root-error')
  if (el) {
    el.textContent = `Unhandled promise: ${event.reason?.message || 'Unknown'}`
    el.style.display = 'block'
  }
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
