/**
 * KnowledgeGraph.test.tsx — component tests for the knowledge graph visualization.
 *
 * Tests verify component structure, loading states, callback wiring, and filter
 * rendering. The d3-force simulation runs in jsdom but SVG rendering is limited,
 * so we test component behavior and DOM structure rather than visual output.
 *
 * All data flows through MSW handlers — no hook mocking needed. The knowledge
 * graph handler returns a single node + edge from the factories, and the
 * trends handler returns two trend entries.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { KnowledgeGraph } from '../../src/components/KnowledgeGraph'

const PATIENT_ID = 'patient-1'

function renderGraph(props: { clinicalOverlay?: boolean; onBack?: () => void } = {}) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return render(
    <KnowledgeGraph
      patientId={PATIENT_ID}
      clinicalOverlay={props.clinicalOverlay}
      onBack={props.onBack ?? vi.fn()}
    />,
  )
}

describe('KnowledgeGraph', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders loading state initially', () => {
    renderGraph()
    expect(screen.getByText('Loading knowledge graph...')).toBeInTheDocument()
  })

  it('renders graph container after data loads', async () => {
    renderGraph()
    await waitFor(() => {
      expect(screen.getByTestId('knowledge-graph')).toBeInTheDocument()
    })
  })

  it('renders SVG element for the graph', async () => {
    renderGraph()
    await waitFor(() => {
      expect(screen.getByRole('img', { name: /Knowledge graph/i })).toBeInTheDocument()
    })
  })

  it('clicking back button calls onBack', async () => {
    const onBack = vi.fn()
    const user = userEvent.setup()
    renderGraph({ onBack })

    // Wait for graph to finish loading so the Back button is stable
    await waitFor(() => {
      expect(screen.getByTestId('knowledge-graph')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Back'))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('renders filter chips for each category', async () => {
    renderGraph()
    await waitFor(() => {
      expect(screen.getByTestId('knowledge-graph')).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /Filter Emotion/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter Activity/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter Symptom/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter Person/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter Medication/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter Other/i })).toBeInTheDocument()
  })

  it('renders time range buttons', async () => {
    renderGraph()
    await waitFor(() => {
      expect(screen.getByTestId('knowledge-graph')).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: '1W' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1M' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '3M' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'ALL' })).toBeInTheDocument()
  })

  it('renders search input', async () => {
    renderGraph()
    await waitFor(() => {
      expect(screen.getByTestId('knowledge-graph')).toBeInTheDocument()
    })

    expect(screen.getByLabelText('Search knowledge graph nodes')).toBeInTheDocument()
  })

  it('shows error state when API fails', async () => {
    server.use(
      http.get('/api/patients/:patientId/knowledge/graph', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )
    renderGraph()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('back button is present in error state', async () => {
    server.use(
      http.get('/api/patients/:patientId/knowledge/graph', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )
    const onBack = vi.fn()
    renderGraph({ onBack })
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.getByText('Back')).toBeInTheDocument()
  })
})
