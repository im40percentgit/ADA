/**
 * SettingsPage — companion personalization and account management.
 *
 * Renders two Card sections:
 *   1. Companion — name input, voice selection, personality toggles (warmth,
 *      verbosity, formality). Changes are batched and submitted via the Save
 *      button, which calls useCompanionPreferences().update().
 *   2. Account — read-only email display and a logout button.
 *
 * Local form state mirrors the remote CompanionPreferences so the user can
 * edit freely before committing. On initial load the local state is seeded
 * from the fetched preferences. While loading, inputs are disabled.
 *
 * @decision DEC-UI-013
 * @title SettingsPage uses local form state, not live-bound hook state
 * @status accepted
 * @rationale Binding every input directly to update() would fire a network
 *   request on each keystroke. A local copy seeded on load lets the user
 *   freely edit and only persists on explicit Save. This matches standard
 *   settings-form UX and keeps the MSW handler count deterministic in tests.
 */

import { type CSSProperties, useEffect, useState } from 'react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'
import { useCompanionPreferences } from '../hooks/useCompanionPreferences'
import type { CompanionPreferences } from '../types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SettingsPageProps {
  /** Called when the user clicks the Logout button. */
  onLogout: () => void
  /** Email address to display in the Account section. */
  email?: string
}

type Voice = CompanionPreferences['voice']

// ---------------------------------------------------------------------------
// Inline styles (all reference design tokens)
// ---------------------------------------------------------------------------

const pageStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-lg)',
  padding: 'var(--space-lg)',
  maxWidth: '480px',
  margin: '0 auto',
}

const sectionHeadingStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-h2)',
  fontWeight: 700,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-md) 0',
}

const fieldGroupStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-md)',
}

const fieldLabelStyle: CSSProperties = {
  fontSize: 'var(--size-caption)',
  color: 'var(--color-text-muted)',
  marginBottom: '4px',
  display: 'block',
}

const voiceRowStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-sm)',
}

const personalityRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 'var(--space-md)',
}

const twoOptionRowStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-xs, 4px)',
  borderRadius: 'var(--radius-button)',
  overflow: 'hidden',
  border: '1px solid var(--color-border)',
}

const accountRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 'var(--space-md)',
}

const emailStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-muted)',
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Segmented-button group for a two-option personality trait. */
function TwoOptionToggle({
  labelA,
  labelB,
  value,
  onChange,
  disabled,
}: {
  labelA: string
  labelB: string
  value: string
  onChange: (v: string) => void
  disabled?: boolean
}) {
  const activeStyle: CSSProperties = {
    background: 'var(--color-primary)',
    color: '#ffffff',
    border: 'none',
    padding: '0 var(--space-sm)',
    height: 'var(--touch-target-min)',
    cursor: 'pointer',
    fontFamily: 'var(--font-body)',
    fontSize: 'var(--size-sm)',
    fontWeight: 600,
    flex: 1,
  }
  const inactiveStyle: CSSProperties = {
    ...activeStyle,
    background: 'var(--color-bg-elevated)',
    color: 'var(--color-text-muted)',
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  }

  return (
    <div style={twoOptionRowStyle} aria-label={`${labelA} or ${labelB}`}>
      <button
        type="button"
        style={value === labelA.toLowerCase() ? activeStyle : inactiveStyle}
        onClick={() => !disabled && onChange(labelA.toLowerCase())}
        aria-pressed={value === labelA.toLowerCase()}
        disabled={disabled}
      >
        {labelA}
      </button>
      <button
        type="button"
        style={value === labelB.toLowerCase() ? activeStyle : inactiveStyle}
        onClick={() => !disabled && onChange(labelB.toLowerCase())}
        aria-pressed={value === labelB.toLowerCase()}
        disabled={disabled}
      >
        {labelB}
      </button>
    </div>
  )
}

/** Pill-style radio button for voice selection. */
function VoiceButton({
  label,
  active,
  onClick,
  disabled,
}: {
  label: string
  active: boolean
  onClick: () => void
  disabled?: boolean
}) {
  const style: CSSProperties = {
    flex: 1,
    height: 'var(--touch-target-min)',
    borderRadius: 'var(--radius-button)',
    border: active
      ? '2px solid var(--color-primary)'
      : '1px solid var(--color-border)',
    background: active ? 'var(--color-primary)' : 'var(--color-bg-elevated)',
    color: active ? '#ffffff' : 'var(--color-text-muted)',
    fontFamily: 'var(--font-body)',
    fontSize: 'var(--size-body)',
    fontWeight: active ? 600 : 400,
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  }

  return (
    <button
      type="button"
      style={style}
      onClick={onClick}
      aria-pressed={active}
      disabled={disabled}
    >
      {label}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SettingsPage({ onLogout, email }: SettingsPageProps) {
  const { preferences, loading, update } = useCompanionPreferences()

  // Local form state — seeded from fetched preferences
  const [name, setName] = useState('')
  const [voice, setVoice] = useState<Voice>('female')
  const [warmth, setWarmth] = useState('warm')
  const [verbosity, setVerbosity] = useState('balanced')
  const [formality, setFormality] = useState('casual')

  // Seed local state once preferences load
  useEffect(() => {
    if (preferences) {
      setName(preferences.name)
      setVoice(preferences.voice)
      setWarmth(preferences.personality.warmth)
      setVerbosity(preferences.personality.verbosity)
      setFormality(preferences.personality.formality)
    }
  }, [preferences])

  const handleSave = async () => {
    await update({
      name,
      voice,
      personality: { warmth, verbosity, formality },
    })
  }

  return (
    <div style={pageStyle} data-testid="settings-page">
      <h1 className="sr-only">Settings</h1>

      {/* ─��� Companion Section ───────────────────��─────────────── */}
      <Card>
        <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
          <legend style={sectionHeadingStyle}>Companion Settings</legend>

          <div style={fieldGroupStyle}>

            {/* Name */}
            <Input
              label="What would you like to call your companion?"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={loading}
              data-testid="companion-name-input"
            />

            {/* Voice */}
            <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
              <legend style={fieldLabelStyle}>Voice</legend>
              <div style={voiceRowStyle} role="radiogroup" aria-label="Voice selection">
                <VoiceButton
                  label="Female"
                  active={voice === 'female'}
                  onClick={() => setVoice('female')}
                  disabled={loading}
                />
                <VoiceButton
                  label="Male"
                  active={voice === 'male'}
                  onClick={() => setVoice('male')}
                  disabled={loading}
                />
                <VoiceButton
                  label="Neutral"
                  active={voice === 'neutral'}
                  onClick={() => setVoice('neutral')}
                  disabled={loading}
                />
              </div>
            </fieldset>

          {/* Personality */}
          <div>
            <span style={fieldLabelStyle}>Personality</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>

              <div style={personalityRowStyle}>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: 'var(--size-body)', color: 'var(--color-text-primary)', minWidth: '80px' }}>
                  Warmth
                </span>
                <TwoOptionToggle
                  labelA="Warm"
                  labelB="Professional"
                  value={warmth}
                  onChange={setWarmth}
                  disabled={loading}
                />
              </div>

              <div style={personalityRowStyle}>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: 'var(--size-body)', color: 'var(--color-text-primary)', minWidth: '80px' }}>
                  Verbosity
                </span>
                <TwoOptionToggle
                  labelA="Chatty"
                  labelB="Concise"
                  value={verbosity}
                  onChange={setVerbosity}
                  disabled={loading}
                />
              </div>

              <div style={personalityRowStyle}>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: 'var(--size-body)', color: 'var(--color-text-primary)', minWidth: '80px' }}>
                  Formality
                </span>
                <TwoOptionToggle
                  labelA="Casual"
                  labelB="Formal"
                  value={formality}
                  onChange={setFormality}
                  disabled={loading}
                />
              </div>

            </div>
          </div>

          {/* Save */}
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={loading}
          >
            Save
          </Button>

          </div>
        </fieldset>
      </Card>

      {/* ── Account Section ───────────────────────────────────── */}
      <Card>
        <h2 style={sectionHeadingStyle}>Account</h2>

        <div style={fieldGroupStyle}>
          {email && (
            <div style={accountRowStyle}>
              <span style={emailStyle} data-testid="account-email">{email}</span>
            </div>
          )}

          <Button
            variant="ghost"
            onClick={onLogout}
            className="ada-settings-logout"
          >
            Log out
          </Button>
        </div>
      </Card>

    </div>
  )
}
