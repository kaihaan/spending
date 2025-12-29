import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import axios from 'axios'
import './index.css'
import App from './App'

// Configure axios defaults for session-based authentication
// CRITICAL: withCredentials must be true for Flask-Login session cookies
axios.defaults.withCredentials = true

const root = document.getElementById('root')
if (!root) throw new Error('Failed to find root element')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
