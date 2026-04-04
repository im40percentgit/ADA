/**
 * useKnowledgeGraph — fetches and manages knowledge graph state.
 *
 * Loads graph data (nodes + edges) and trend information from the API,
 * then provides client-side filtering by category, time range, and search
 * query. Consumers get pre-filtered nodes/edges plus state setters for
 * interactive exploration.
 *
 * @decision DEC-FRONTEND-050
 * @title Client-side filtering for knowledge graph display
 * @status accepted
 * @rationale The knowledge graph for a single patient is small enough
 *   (typically <200 nodes) to filter in the browser. This avoids extra
 *   round-trips when toggling category chips or typing a search query.
 *   If graph sizes grow significantly, server-side filtering can be added
 *   to the /knowledge/graph endpoint.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { getKnowledgeGraph, getKnowledgeTrends } from '../api/client'
import type { KnowledgeNode, KnowledgeEdge, KnowledgeTrend } from '../types'

const ALL_CATEGORIES = new Set(['emotion', 'activity', 'symptom', 'person', 'medication', 'other'])

export interface UseKnowledgeGraphResult {
  nodes: KnowledgeNode[]
  edges: KnowledgeEdge[]
  trends: KnowledgeTrend[]
  selectedNode: KnowledgeNode | null
  setSelectedNode: (node: KnowledgeNode | null) => void
  categoryFilters: Set<string>
  setCategoryFilters: (filters: Set<string>) => void
  timeRange: string
  setTimeRange: (range: string) => void
  searchQuery: string
  setSearchQuery: (query: string) => void
  loading: boolean
  error: string | null
}

export function useKnowledgeGraph(patientId: string): UseKnowledgeGraphResult {
  const [allNodes, setAllNodes] = useState<KnowledgeNode[]>([])
  const [allEdges, setAllEdges] = useState<KnowledgeEdge[]>([])
  const [trends, setTrends] = useState<KnowledgeTrend[]>([])
  const [selectedNode, setSelectedNode] = useState<KnowledgeNode | null>(null)
  const [categoryFilters, setCategoryFilters] = useState<Set<string>>(new Set(ALL_CATEGORIES))
  const [timeRange, setTimeRange] = useState('ALL')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch graph data on mount / patientId change
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      getKnowledgeGraph(patientId),
      getKnowledgeTrends(patientId, timeRange === 'ALL' ? '1y' : timeRange),
    ])
      .then(([graphData, trendData]) => {
        if (!cancelled) {
          setAllNodes(graphData.nodes)
          setAllEdges(graphData.edges)
          setTrends(trendData)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load knowledge graph')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [patientId, timeRange])

  // Filter nodes by category + search
  const nodes = useMemo(() => {
    const lowerQuery = searchQuery.toLowerCase()
    return allNodes.filter((node) => {
      if (!categoryFilters.has(node.node_type)) return false
      if (lowerQuery && !node.label.toLowerCase().includes(lowerQuery)) return false
      return true
    })
  }, [allNodes, categoryFilters, searchQuery])

  // Filter edges to only include edges between visible nodes
  const edges = useMemo(() => {
    const visibleIds = new Set(nodes.map((n) => n.id))
    return allEdges.filter(
      (edge) => visibleIds.has(edge.from_node) && visibleIds.has(edge.to_node),
    )
  }, [allEdges, nodes])

  const handleSetSelectedNode = useCallback((node: KnowledgeNode | null) => {
    setSelectedNode(node)
  }, [])

  const handleSetCategoryFilters = useCallback((filters: Set<string>) => {
    setCategoryFilters(filters)
  }, [])

  const handleSetTimeRange = useCallback((range: string) => {
    setTimeRange(range)
  }, [])

  const handleSetSearchQuery = useCallback((query: string) => {
    setSearchQuery(query)
  }, [])

  return {
    nodes,
    edges,
    trends,
    selectedNode,
    setSelectedNode: handleSetSelectedNode,
    categoryFilters,
    setCategoryFilters: handleSetCategoryFilters,
    timeRange,
    setTimeRange: handleSetTimeRange,
    searchQuery,
    setSearchQuery: handleSetSearchQuery,
    loading,
    error,
  }
}
