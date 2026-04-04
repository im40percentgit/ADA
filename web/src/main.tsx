/**
 * @file main.tsx
 * @description React application entry point. Mounts the root App component
 *   into the #root DOM element defined in index.html.
 * @rationale StrictMode is enabled to surface potential issues during
 *   development (double-invoked effects, deprecated API warnings) without
 *   affecting production behavior.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.tsx'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('Root element #root not found in DOM')

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
