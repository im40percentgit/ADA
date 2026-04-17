/**
 * SessionsCard.test.tsx — component tests for the caregiver session summary card.
 *
 * SessionsCard is a pure rendering component — no API calls, no MSW needed.
 * It receives a sessions array and optional onViewSession callback as props.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { SessionsCard } from '../../src/components/SessionsCard'
import type { CaregiverSession } from '../../src/types'

function makeSession(overrides: Partial<CaregiverSession> = {}): CaregiverSession {
  return {
    id: 'session-1',
    started_at: '2026-01-01T10:00:00Z',
    ended_at: '2026-01-01T11:00:00Z',
    summary: {
      subjective: 'Feeling better.',
      assessment: 'Stable.',
      plan: 'Continue current approach.',
      key_topics: ['sleep', 'mood'],
      risk_flags: [],
    },
    ...overrides,
  }
}

describe('SessionsCard', () => {
  it('renders EmptyState with "No sessions yet" when sessions list is empty', () => {
    render(<SessionsCard sessions={[]} />)
    expect(screen.getByText('No sessions yet')).toBeInTheDocument()
    expect(screen.getByText(/Session summaries will appear here/i)).toBeInTheDocument()
  })

  it('renders session date when sessions are present', () => {
    render(<SessionsCard sessions={[makeSession()]} />)
    // Date formatted as "Jan 1" or similar — just check the date renders without crashing
    expect(screen.getByText(/Jan/i)).toBeInTheDocument()
  })

  it('renders Next Steps (plan) from session summary', () => {
    render(<SessionsCard sessions={[makeSession()]} />)
    expect(screen.getByText('Next Steps')).toBeInTheDocument()
    expect(screen.getByText('Continue current approach.')).toBeInTheDocument()
  })

  it('renders Topics Discussed from key_topics', () => {
    render(<SessionsCard sessions={[makeSession()]} />)
    expect(screen.getByText('Topics Discussed')).toBeInTheDocument()
    expect(screen.getByText('sleep')).toBeInTheDocument()
    expect(screen.getByText('mood')).toBeInTheDocument()
  })

  it('renders risk flags when present', () => {
    const session = makeSession({
      summary: {
        subjective: '',
        assessment: '',
        plan: 'Watch closely',
        key_topics: [],
        risk_flags: ['self-harm ideation'],
      },
    })
    render(<SessionsCard sessions={[session]} />)
    expect(screen.getByText('Things to Watch')).toBeInTheDocument()
    expect(screen.getByText('self-harm ideation')).toBeInTheDocument()
  })

  it('shows "Session in progress" when summary is null', () => {
    render(<SessionsCard sessions={[makeSession({ summary: null })]} />)
    expect(screen.getByText(/Session in progress or summary pending/i)).toBeInTheDocument()
  })

  it('calls onViewSession when a session is clicked', async () => {
    const onViewSession = vi.fn()
    const user = userEvent.setup()
    render(<SessionsCard sessions={[makeSession()]} onViewSession={onViewSession} />)

    await user.click(screen.getByRole('button', { name: /View session summary/i }))
    expect(onViewSession).toHaveBeenCalledWith('session-1')
  })
})
