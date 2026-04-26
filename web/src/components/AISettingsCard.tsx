/**
 * AISettingsCard — LLM mode selector for the Settings page.
 *
 * Renders a Card with three segmented buttons (Claude / Offline / Dual) that
 * control how Ada routes LLM calls. In Dual mode an expandable per-agent
 * panel shows the current agent→tier mapping (read-only in v1).
 *
 * API surface: GET /api/admin/settings/llm-mode on mount; PUT on mode change.
 * Requires caregiver auth (the parent page enforces this).
 *
 * Mode semantics (DEC-LLM-005):
 *   claude  — all agents → Claude tiers (Opus/Sonnet/Haiku)
 *   offline — all agents → local llama.cpp endpoint
 *   dual    — per-agent routing from system_settings/TOML (default)
 *
 * @decision DEC-FRONTEND-078
 * @title AISettingsCard: segmented mode selector + read-only per-agent panel
 * @status accepted
 * @rationale A three-button segmented control (matching the existing
 *   TwoOptionToggle pattern) gives the caregiver a one-tap mode flip without
 *   exposing TOML files. Dual mode shows the live agent_mapping so the user
 *   can understand what each tier does. Per-agent editing in v1 is out of
 *   scope — the collapsible panel is read-only. Mounted between Companion and
 *   Account cards to match card ordering (config → identity → account).
 */

import { type CSSProperties, useCallback, useEffect, useState } from 'react'
import { Card } from './ui/Card'
import { getLLMMode, setLLMMode, type LLMMode, type LLMModeStatus } from '../api/client'


// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AISettingsCardProps {
  /** Called after a successful mode change (for parent to react if needed). */
  onModeChange?: (newMode: LLMMode) => void
}


// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const headingStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-h2)',
  fontWeight: 700,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-xs) 0',
}

const descriptionStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-caption)',
  color: 'var(--color-text-muted)',
  margin: '0 0 var(--space-md) 0',
}

const segmentedRowStyle: CSSProperties = {
  display: 'flex',
  gap: 0,
  borderRadius: 'var(--radius-button)',
  overflow: 'hidden',
  border: '1px solid var(--color-border)',
}

const activeSegmentStyle: CSSProperties = {
  flex: 1,
  background: 'var(--color-primary)',
  color: '#ffffff',
  border: 'none',
  padding: '0 var(--space-sm)',
  height: 'var(--touch-target-min)',
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-sm)',
  fontWeight: 600,
}

const inactiveSegmentStyle: CSSProperties = {
  ...activeSegmentStyle,
  background: 'var(--color-bg-elevated)',
  color: 'var(--color-text-muted)',
  cursor: 'pointer',
}

const disabledSegmentStyle: CSSProperties = {
  ...inactiveSegmentStyle,
  opacity: 0.5,
  cursor: 'default',
}

const statusTextStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-caption)',
  color: 'var(--color-text-muted)',
  marginTop: 'var(--space-xs)',
  minHeight: '1.2em',
}

const errorTextStyle: CSSProperties = {
  ...statusTextStyle,
  color: 'var(--color-danger, #c0392b)',
}

const expandToggleStyle: CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-caption)',
  color: 'var(--color-primary)',
  padding: 0,
  marginTop: 'var(--space-sm)',
  textDecoration: 'underline',
  textUnderlineOffset: '2px',
}

const agentPanelStyle: CSSProperties = {
  marginTop: 'var(--space-sm)',
  borderTop: '1px solid var(--color-border)',
  paddingTop: 'var(--space-sm)',
}

const agentTableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse' as const,
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-caption)',
}

const agentCellStyle: CSSProperties = {
  padding: '2px var(--space-xs)',
  color: 'var(--color-text-primary)',
  verticalAlign: 'top' as const,
}

const tierCellStyle: CSSProperties = {
  ...agentCellStyle,
  color: 'var(--color-text-muted)',
  textAlign: 'right' as const,
}

const panelHeadingStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-caption)',
  fontWeight: 600,
  color: 'var(--color-text-muted)',
  margin: '0 0 var(--space-xs) 0',
  textTransform: 'uppercase' as const,
  letterSpacing: '0.05em',
}


// ---------------------------------------------------------------------------
// Mode label helpers
// ---------------------------------------------------------------------------

const MODE_LABELS: Record<LLMMode, string> = {
  claude: 'Claude',
  offline: 'Offline',
  dual: 'Dual',
}

const MODE_DESCRIPTIONS: Record<LLMMode, string> = {
  claude: 'All agents use Claude (Opus · Sonnet · Haiku)',
  offline: 'All agents use the local model (llama.cpp)',
  dual: 'Per-agent routing — cloud for clinical, local available',
}

const MODES: LLMMode[] = ['claude', 'offline', 'dual']


// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AISettingsCard({ onModeChange }: AISettingsCardProps) {
  const [status, setStatus] = useState<LLMModeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [agentPanelOpen, setAgentPanelOpen] = useState(false)

  // -- Load current mode on mount -----------------------------------------------

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getLLMMode()
      .then((s) => { if (!cancelled) { setStatus(s); setLoading(false) } })
      .catch((e) => { if (!cancelled) { setError(String(e)); setLoading(false) } })
    return () => { cancelled = true }
  }, [])

  // -- Mode change handler -------------------------------------------------------

  const handleModeChange = useCallback(async (mode: LLMMode) => {
    if (saving || loading) return
    if (status?.mode === mode) return

    setSaving(true)
    setError(null)
    try {
      await setLLMMode(mode)
      // Refresh full status (agent_mapping may have changed based on mode)
      const updated = await getLLMMode()
      setStatus(updated)
      onModeChange?.(mode)
    } catch (e) {
      setError(`Failed to switch mode: ${String(e)}`)
    } finally {
      setSaving(false)
    }
  }, [saving, loading, status, onModeChange])

  // -- Render -------------------------------------------------------------------

  const currentMode = status?.mode ?? 'dual'
  const disabled = loading || saving

  const agentEntries = status
    ? Object.entries(status.agent_mapping).sort(([a], [b]) => a.localeCompare(b))
    : []

  return (
    <Card>
      <h2 style={headingStyle}>AI Mode</h2>
      <p style={descriptionStyle}>
        {loading ? 'Loading…' : MODE_DESCRIPTIONS[currentMode]} {/* lint-empty-states:allow */}
      </p>

      {/* Segmented control */}
      <div
        style={segmentedRowStyle}
        role="group"
        aria-label="LLM mode selector"
        data-testid="ai-mode-selector"
      >
        {MODES.map((mode) => {
          const isActive = currentMode === mode
          const buttonStyle = disabled
            ? disabledSegmentStyle
            : isActive
              ? activeSegmentStyle
              : inactiveSegmentStyle
          return (
            <button
              key={mode}
              type="button"
              style={buttonStyle}
              aria-pressed={isActive}
              disabled={disabled}
              onClick={() => handleModeChange(mode)}
              data-testid={`ai-mode-btn-${mode}`}
            >
              {MODE_LABELS[mode]}
            </button>
          )
        })}
      </div>

      {/* Status / error line */}
      {error ? (
        <p style={errorTextStyle} role="alert">{error}</p>
      ) : (
        <p style={statusTextStyle}>
          {saving ? 'Applying…' : loading ? '' : `Active: ${MODE_LABELS[currentMode]}`}
        </p>
      )}

      {/* Per-agent panel (dual mode or always visible for inspection) */}
      {!loading && agentEntries.length > 0 && (
        <>
          <button
            type="button"
            style={expandToggleStyle}
            onClick={() => setAgentPanelOpen((o) => !o)}
            aria-expanded={agentPanelOpen}
            data-testid="ai-agent-panel-toggle"
          >
            {agentPanelOpen ? 'Hide agent routing ▲' : 'Show agent routing ▼'}
          </button>

          {agentPanelOpen && (
            <div style={agentPanelStyle} data-testid="ai-agent-panel">
              <p style={panelHeadingStyle}>Agent → Tier (read-only)</p>
              <table style={agentTableStyle}>
                <tbody>
                  {agentEntries.map(([agent, tier]) => (
                    <tr key={agent}>
                      <td style={agentCellStyle}>{agent}</td>
                      <td style={tierCellStyle}>{tier}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Card>
  )
}
