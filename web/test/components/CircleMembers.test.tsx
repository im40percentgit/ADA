/**
 * CircleMembers.test.tsx — component tests for the Care Team member list.
 *
 * CircleMembers fetches GET /api/circles/:circleId/members via REST (MSW).
 * Role-gated UI: primary_caregiver and clinician see "Add Member"; only
 * primary_caregiver sees "Remove" buttons.
 *
 * Phase 13e-04 states (DEC-BOARDS-STATES-001):
 *   - empty path: EmptyState renders when members list is empty
 *   - error path: ErrorState renders when fetch fails
 *   - populated path: member rows render correctly
 *   - role gating: canManage / canRemove gates work as expected
 */

import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { CircleMembers } from '../../src/components/CircleMembers'

const CIRCLE_ID = 'circle-test-1'

function renderMembers(role = 'primary_caregiver') {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return render(<CircleMembers circleId={CIRCLE_ID} currentUserRole={role} />)
}

describe('CircleMembers', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders the Care Team heading', async () => {
    renderMembers()
    expect(screen.getByText(/Care Team/i)).toBeInTheDocument()
  })

  it('renders member email after data loads', async () => {
    renderMembers()
    await waitFor(() => {
      expect(screen.getByText(/caregiver@example.com/i)).toBeInTheDocument()
    })
  })

  it('shows EmptyState when member list is empty (DEC-BOARDS-STATES-001)', async () => {
    server.use(
      http.get('/api/circles/:circleId/members', () => {
        return HttpResponse.json([])
      }),
    )
    renderMembers()
    await waitFor(() => {
      expect(screen.getByText(/No members invited yet/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/Invite family members or caregivers/i)).toBeInTheDocument()
  })

  it('shows ErrorState when member fetch fails (DEC-BOARDS-STATES-001)', async () => {
    server.use(
      http.get('/api/circles/:circleId/members', () => {
        return HttpResponse.json({ detail: 'Internal error' }, { status: 500 })
      }),
    )
    renderMembers()
    await waitFor(() => {
      expect(screen.getByText(/Could not load members/i)).toBeInTheDocument()
    })
  })

  it('does not show EmptyState when members are present', async () => {
    renderMembers()
    await waitFor(() => {
      expect(screen.getByText(/caregiver@example.com/i)).toBeInTheDocument()
    })
    expect(screen.queryByText(/No members invited yet/i)).not.toBeInTheDocument()
  })

  it('shows Add Member button for primary_caregiver role', async () => {
    renderMembers('primary_caregiver')
    expect(screen.getByRole('button', { name: /Add Member/i })).toBeInTheDocument()
  })

  it('shows Add Member button for clinician role', async () => {
    renderMembers('clinician')
    expect(screen.getByRole('button', { name: /Add Member/i })).toBeInTheDocument()
  })

  it('does not show Add Member button for family role', async () => {
    renderMembers('family')
    expect(screen.queryByRole('button', { name: /Add Member/i })).not.toBeInTheDocument()
  })

  it('shows Remove button for primary_caregiver when non-primary members exist', async () => {
    server.use(
      http.get('/api/circles/:circleId/members', () => {
        return HttpResponse.json([
          { id: 'mem-1', user_id: 'user-1', email: 'family@example.com', role: 'family', created_at: '2026-01-01T00:00:00Z' },
        ])
      }),
    )
    renderMembers('primary_caregiver')
    await waitFor(() => {
      expect(screen.getByText(/family@example.com/i)).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /Remove family@example.com/i })).toBeInTheDocument()
  })

  it('does not show Remove button for clinician role', async () => {
    server.use(
      http.get('/api/circles/:circleId/members', () => {
        return HttpResponse.json([
          { id: 'mem-1', user_id: 'user-1', email: 'family@example.com', role: 'family', created_at: '2026-01-01T00:00:00Z' },
        ])
      }),
    )
    renderMembers('clinician')
    await waitFor(() => {
      expect(screen.getByText(/family@example.com/i)).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: /Remove/i })).not.toBeInTheDocument()
  })
})
