/**
 * ConsentManager — card with toggle controls for privacy consent settings.
 *
 * Fetches the user's current consent records on mount and renders four
 * toggles: data collection, AI analysis, data sharing, and research
 * participation. Each toggle change calls setConsent() to persist the
 * change immediately via PUT /api/consent.
 *
 * @decision DEC-FRONTEND-077
 * @title ConsentManager persists each toggle change immediately
 * @status accepted
 * @rationale Consent state changes are legally significant — batching
 *   them risks the user navigating away before the batch is saved, which
 *   could leave consent state out of sync. Persisting each toggle
 *   individually ensures the audit trail accurately reflects user intent.
 */

import { type CSSProperties, useCallback, useEffect, useState } from 'react'
import { Card } from './ui/Card'
import { Toggle } from './ui/Toggle'
import { getUserConsents, setConsent } from '../api/client'
import type { ConsentType } from '../types'

const headingStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-h2)',
  fontWeight: 700,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-sm) 0',
}

const descriptionStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-muted)',
  margin: '0 0 var(--space-md) 0',
}

const toggleGroupStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-md)',
}

const CONSENT_LABELS: { type: ConsentType; label: string; description: string }[] = [
  {
    type: 'data_collection',
    label: 'Data Collection',
    description: 'Allow collection of session data and assessments for your care',
  },
  {
    type: 'ai_analysis',
    label: 'AI Analysis',
    description: 'Allow AI-powered analysis to generate insights and recommendations',
  },
  {
    type: 'data_sharing',
    label: 'Data Sharing',
    description: 'Allow sharing anonymized data with your care team',
  },
  {
    type: 'research',
    label: 'Research Participation',
    description: 'Allow anonymized data use for mental health research',
  },
]

export function ConsentManager() {
  const [consents, setConsents] = useState<Record<ConsentType, boolean>>({
    data_collection: false,
    ai_analysis: false,
    data_sharing: false,
    research: false,
  })
  const [loading, setLoading] = useState(true)

  const fetchConsents = useCallback(async () => {
    setLoading(true)
    try {
      const records = await getUserConsents()
      const map: Record<ConsentType, boolean> = {
        data_collection: false,
        ai_analysis: false,
        data_sharing: false,
        research: false,
      }
      for (const record of records) {
        map[record.consent_type] = record.granted
      }
      setConsents(map)
    } catch {
      // Failed to fetch — defaults remain
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConsents()
  }, [fetchConsents])

  const handleToggle = async (type: ConsentType, granted: boolean) => {
    // Optimistic update
    setConsents((prev) => ({ ...prev, [type]: granted }))
    try {
      await setConsent(type, granted)
    } catch {
      // Revert on failure
      setConsents((prev) => ({ ...prev, [type]: !granted }))
    }
  }

  return (
    <Card>
      <h2 style={headingStyle}>Privacy & Consent</h2>
      <p style={descriptionStyle}>
        Manage how your data is collected, analyzed, and shared. Changes take effect immediately.
      </p>
      <div style={toggleGroupStyle}>
        {CONSENT_LABELS.map(({ type, label, description }) => (
          <div key={type} data-testid={`consent-${type}`}>
            <Toggle
              checked={consents[type]}
              onChange={(checked) => handleToggle(type, checked)}
              label={label}
              disabled={loading}
            />
            <p
              style={{
                margin: '4px 0 0 52px',
                fontSize: 'var(--size-caption)',
                color: 'var(--color-text-muted)',
              }}
            >
              {description}
            </p>
          </div>
        ))}
      </div>
    </Card>
  )
}
