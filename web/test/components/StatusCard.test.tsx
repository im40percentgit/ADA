/**
 * StatusCard.test.tsx — component tests for the "How They're Doing" caregiver card.
 *
 * StatusCard is a pure rendering component — no API calls, no MSW needed.
 * It derives trend from WHO-5 scores and last session time from sessions.
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StatusCard } from '../../src/components/StatusCard'
import type { CaregiverSession, CaregiverAssessmentEntry } from '../../src/types'

function makeSession(overrides: Partial<CaregiverSession> = {}): CaregiverSession {
  return {
    id: 'session-1',
    started_at: '2026-01-01T10:00:00Z',
    ended_at: '2026-01-01T11:00:00Z',
    summary: {
      subjective: 'Feeling better.',
      assessment: 'Stable.',
      plan: 'Continue current approach.',
      key_topics: ['sleep'],
      risk_flags: [],
    },
    ...overrides,
  }
}

function makeWho5(score: number, timestamp: string): CaregiverAssessmentEntry {
  return { total_score: score, severity: 'moderate', timestamp }
}

describe('StatusCard', () => {
  it('renders EmptyState with "No sessions yet" when sessions list is empty', () => {
    render(<StatusCard sessions={[]} who5Scores={[]} />)
    expect(screen.getByText('No sessions yet')).toBeInTheDocument()
    expect(screen.getByText(/Status will update after the first conversation/i)).toBeInTheDocument()
  })

  it('renders "How They\'re Doing" heading', () => {
    render(<StatusCard sessions={[makeSession()]} who5Scores={[]} />)
    expect(screen.getByText("How They're Doing")).toBeInTheDocument()
  })

  it('renders the plan from the latest session', () => {
    render(<StatusCard sessions={[makeSession()]} who5Scores={[]} />)
    expect(screen.getByText('Continue current approach.')).toBeInTheDocument()
  })

  it('shows improving trend arrow when latest WHO-5 is higher', () => {
    const scores = [
      makeWho5(12, '2026-01-01T00:00:00Z'),
      makeWho5(18, '2026-01-02T00:00:00Z'),
    ]
    render(<StatusCard sessions={[makeSession()]} who5Scores={scores} />)
    expect(screen.getByText(/Improving/i)).toBeInTheDocument()
  })

  it('shows declining trend when latest WHO-5 is lower', () => {
    const scores = [
      makeWho5(18, '2026-01-01T00:00:00Z'),
      makeWho5(12, '2026-01-02T00:00:00Z'),
    ]
    render(<StatusCard sessions={[makeSession()]} who5Scores={scores} />)
    expect(screen.getByText(/Declining/i)).toBeInTheDocument()
  })

  it('shows stable trend when WHO-5 scores are equal', () => {
    const scores = [
      makeWho5(15, '2026-01-01T00:00:00Z'),
      makeWho5(15, '2026-01-02T00:00:00Z'),
    ]
    render(<StatusCard sessions={[makeSession()]} who5Scores={scores} />)
    expect(screen.getByText(/Stable/i)).toBeInTheDocument()
  })

  it('shows "Last session" timestamp', () => {
    render(<StatusCard sessions={[makeSession()]} who5Scores={[]} />)
    expect(screen.getByText(/Last session:/i)).toBeInTheDocument()
  })
})
