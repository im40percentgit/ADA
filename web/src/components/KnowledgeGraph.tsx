/**
 * KnowledgeGraph — interactive force-directed graph of patient knowledge entities.
 *
 * Renders a d3 force simulation inside an SVG element. Nodes are circles sized
 * by mention count, colored by node type. Edges are lines with stroke-width
 * proportional to weight. A clinical overlay mode adds trend arrows and
 * sentiment-based edge coloring.
 *
 * Layout: GraphFilters at top, SVG graph area in center, GraphDetailPanel
 * slides in from the right when a node is selected.
 *
 * @decision DEC-FRONTEND-053
 * @title d3-force for graph layout, React for DOM structure
 * @status accepted
 * @rationale d3-force provides a proven force-directed layout algorithm.
 *   Rather than letting d3 manage the DOM (which conflicts with React),
 *   we use d3-force only for position computation in a useEffect, then
 *   render SVG elements declaratively in JSX. d3-selection is used only
 *   for simulation tick updates to node/edge positions via ref, avoiding
 *   a full React re-render on every tick.
 */

import { useEffect, useRef, useCallback } from 'react'
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'
import { select } from 'd3-selection'
import { useKnowledgeGraph } from '../hooks/useKnowledgeGraph'
import { GraphFilters } from './GraphFilters'
import { GraphDetailPanel } from './GraphDetailPanel'
import type { KnowledgeNode, KnowledgeEdge, KnowledgeTrend } from '../types'

const NODE_COLORS: Record<string, string> = {
  emotion: '#8b5cf6',
  activity: '#10b981',
  symptom: '#ef4444',
  person: '#3b82f6',
  medication: '#f59e0b',
  other: '#6b7280',
}

interface KnowledgeGraphProps {
  patientId: string
  clinicalOverlay?: boolean
  onBack: () => void
}

// d3-force augments node objects with x, y, vx, vy
interface SimNode extends KnowledgeNode {
  x?: number
  y?: number
  vx?: number
  vy?: number
}

interface SimLink {
  source: string | SimNode
  target: string | SimNode
  weight: number
  relation: string
}

function nodeRadius(mentionCount: number): number {
  return Math.max(8, Math.sqrt(mentionCount) * 4)
}

function getTrendArrow(nodeId: string, trends: KnowledgeTrend[]): string | null {
  const trend = trends.find((t) => t.node_id === nodeId)
  if (!trend) return null
  if (trend.direction === 'improving') return '\u2191'
  if (trend.direction === 'declining') return '\u2193'
  return null
}

export function KnowledgeGraph({ patientId, clinicalOverlay = false, onBack }: KnowledgeGraphProps) {
  const {
    nodes,
    edges,
    trends,
    selectedNode,
    setSelectedNode,
    categoryFilters,
    setCategoryFilters,
    timeRange,
    setTimeRange,
    searchQuery,
    setSearchQuery,
    loading,
    error,
  } = useKnowledgeGraph(patientId)

  const svgRef = useRef<SVGSVGElement>(null)

  // Find a node by id and select it
  const handleSelectNodeById = useCallback(
    (id: string) => {
      const node = nodes.find((n) => n.id === id) ?? null
      setSelectedNode(node)
    },
    [nodes, setSelectedNode],
  )

  // Run d3 force simulation
  useEffect(() => {
    const svg = svgRef.current
    if (!svg || nodes.length === 0) return

    const width = svg.clientWidth || 600
    const height = svg.clientHeight || 400

    // Build simulation data
    const simNodes: SimNode[] = nodes.map((n) => ({ ...n }))
    const nodeById = new Map(simNodes.map((n) => [n.id, n]))
    const simLinks: SimLink[] = edges
      .filter((e) => nodeById.has(e.from_node) && nodeById.has(e.to_node))
      .map((e) => ({
        source: e.from_node,
        target: e.to_node,
        weight: e.weight,
        relation: e.relation,
      }))

    const simulation = forceSimulation<SimNode>(simNodes)
      .force(
        'link',
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(80),
      )
      .force('charge', forceManyBody().strength(-120))
      .force('center', forceCenter(width / 2, height / 2))
      .force('collide', forceCollide<SimNode>().radius((d) => nodeRadius(d.mention_count) + 4))

    const svgSel = select(svg)

    // Update positions on each tick
    simulation.on('tick', () => {
      svgSel
        .selectAll<SVGLineElement, SimLink>('.kg-edge')
        .attr('x1', (d) => ((d.source as SimNode).x ?? 0).toString())
        .attr('y1', (d) => ((d.source as SimNode).y ?? 0).toString())
        .attr('x2', (d) => ((d.target as SimNode).x ?? 0).toString())
        .attr('y2', (d) => ((d.target as SimNode).y ?? 0).toString())

      svgSel
        .selectAll<SVGCircleElement, SimNode>('.kg-node')
        .attr('cx', (d) => (d.x ?? 0).toString())
        .attr('cy', (d) => (d.y ?? 0).toString())

      svgSel
        .selectAll<SVGTextElement, SimNode>('.kg-label')
        .attr('x', (d) => (d.x ?? 0).toString())
        .attr('y', (d) => ((d.y ?? 0) + nodeRadius(d.mention_count) + 12).toString())

      if (clinicalOverlay) {
        svgSel
          .selectAll<SVGTextElement, SimNode>('.kg-trend')
          .attr('x', (d) => ((d.x ?? 0) + nodeRadius(d.mention_count) + 4).toString())
          .attr('y', (d) => ((d.y ?? 0) - 4).toString())
      }
    })

    // Bindedges
    const edgeSel = svgSel
      .select('.kg-edges')
      .selectAll<SVGLineElement, SimLink>('.kg-edge')
      .data(simLinks, (_d, i) => `link-${i}`)

    edgeSel.exit().remove()

    edgeSel
      .enter()
      .append('line')
      .attr('class', 'kg-edge')
      .merge(edgeSel)
      .attr('stroke', clinicalOverlay ? '#ef4444' : '#cbd5e1')
      .attr('stroke-width', (d) => Math.max(1, d.weight * 3))
      .attr('stroke-opacity', 0.6)

    // Bind nodes
    const nodeSel = svgSel
      .select('.kg-nodes')
      .selectAll<SVGCircleElement, SimNode>('.kg-node')
      .data(simNodes, (d) => d.id)

    nodeSel.exit().remove()

    nodeSel
      .enter()
      .append('circle')
      .attr('class', 'kg-node')
      .attr('cursor', 'pointer')
      .merge(nodeSel)
      .attr('r', (d) => nodeRadius(d.mention_count))
      .attr('fill', (d) => NODE_COLORS[d.node_type] ?? NODE_COLORS.other)
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .on('click', (_event, d) => {
        const original = nodes.find((n) => n.id === d.id) ?? null
        setSelectedNode(original)
      })

    // Bind labels
    const labelSel = svgSel
      .select('.kg-labels')
      .selectAll<SVGTextElement, SimNode>('.kg-label')
      .data(simNodes, (d) => d.id)

    labelSel.exit().remove()

    labelSel
      .enter()
      .append('text')
      .attr('class', 'kg-label')
      .merge(labelSel)
      .text((d) => d.label)
      .attr('text-anchor', 'middle')
      .attr('font-size', '10')
      .attr('fill', '#374151')

    // Bind trend arrows (clinical overlay)
    if (clinicalOverlay) {
      const trendSel = svgSel
        .select('.kg-trends')
        .selectAll<SVGTextElement, SimNode>('.kg-trend')
        .data(simNodes, (d) => d.id)

      trendSel.exit().remove()

      trendSel
        .enter()
        .append('text')
        .attr('class', 'kg-trend')
        .merge(trendSel)
        .text((d) => getTrendArrow(d.id, trends) ?? '')
        .attr('font-size', '14')
        .attr('fill', (d) => {
          const trend = trends.find((t) => t.node_id === d.id)
          if (trend?.direction === 'improving') return '#10b981'
          if (trend?.direction === 'declining') return '#ef4444'
          return '#6b7280'
        })
    }

    return () => {
      simulation.stop()
    }
  }, [nodes, edges, trends, clinicalOverlay, setSelectedNode])

  if (loading) {
    return (
      <div className="knowledge-graph knowledge-graph--loading" aria-busy="true">
        <button type="button" className="knowledge-graph__back" onClick={onBack}>
          Back
        </button>
        <p>Loading knowledge graph...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="knowledge-graph knowledge-graph--error" role="alert">
        <button type="button" className="knowledge-graph__back" onClick={onBack}>
          Back
        </button>
        <p>{error}</p>
      </div>
    )
  }

  return (
    <div className="knowledge-graph" data-testid="knowledge-graph">
      <div className="knowledge-graph__toolbar">
        <button type="button" className="knowledge-graph__back" onClick={onBack}>
          Back
        </button>
        <GraphFilters
          categoryFilters={categoryFilters}
          setCategoryFilters={setCategoryFilters}
          timeRange={timeRange}
          setTimeRange={setTimeRange}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
        />
      </div>

      <div className="knowledge-graph__container">
        <svg
          ref={svgRef}
          className="knowledge-graph__svg"
          width="100%"
          height="100%"
          aria-label="Knowledge graph visualization"
        >
          <g className="kg-edges" />
          <g className="kg-nodes" />
          <g className="kg-labels" />
          <g className="kg-trends" />
        </svg>

        <GraphDetailPanel
          node={selectedNode}
          edges={edges}
          allNodes={nodes}
          onSelectNode={handleSelectNodeById}
          onClose={() => setSelectedNode(null)}
        />
      </div>
    </div>
  )
}
