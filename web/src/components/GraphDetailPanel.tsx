/**
 * GraphDetailPanel — slide-in detail panel for a selected knowledge graph node.
 *
 * Positioned absolutely on the right side of the graph container. Shows the
 * node's label, type badge (colored), mention count, confidence percentage,
 * and a list of connected nodes (clickable to navigate). The panel is hidden
 * when no node is selected.
 *
 * @decision DEC-FRONTEND-052
 * @title GraphDetailPanel uses absolute positioning over graph SVG
 * @status accepted
 * @rationale A slide-in panel overlaying the graph keeps context visible
 *   (the selected node remains in the graph behind the panel). This avoids
 *   a full-page navigation or modal that would lose the spatial context
 *   of the graph exploration.
 */

import type { KnowledgeNode, KnowledgeEdge } from '../types'

const NODE_COLORS: Record<string, string> = {
  emotion: '#8b5cf6',
  activity: '#10b981',
  symptom: '#ef4444',
  person: '#3b82f6',
  medication: '#f59e0b',
  other: '#6b7280',
}

interface GraphDetailPanelProps {
  node: KnowledgeNode | null
  edges: KnowledgeEdge[]
  allNodes: KnowledgeNode[]
  onSelectNode: (id: string) => void
  onClose: () => void
}

export function GraphDetailPanel({
  node,
  edges,
  allNodes,
  onSelectNode,
  onClose,
}: GraphDetailPanelProps) {
  if (!node) return null

  // Find connected nodes
  const connectedEdges = edges.filter(
    (e) => e.from_node === node.id || e.to_node === node.id,
  )
  const connectedNodeIds = connectedEdges.map((e) =>
    e.from_node === node.id ? e.to_node : e.from_node,
  )
  const nodeMap = new Map(allNodes.map((n) => [n.id, n]))
  const connectedNodes = connectedNodeIds
    .map((id) => nodeMap.get(id))
    .filter((n): n is KnowledgeNode => n !== undefined)

  const color = NODE_COLORS[node.node_type] ?? NODE_COLORS.other

  return (
    <div className="graph-detail-panel" role="complementary" aria-label="Node details">
      <div className="graph-detail-panel__header">
        <h3 className="graph-detail-panel__title">{node.label}</h3>
        <button
          type="button"
          className="graph-detail-panel__close"
          onClick={onClose}
          aria-label="Close detail panel"
        >
          X
        </button>
      </div>

      <span
        className="graph-detail-panel__badge"
        style={{ backgroundColor: color }}
      >
        {node.node_type}
      </span>

      <dl className="graph-detail-panel__stats">
        <div className="graph-detail-panel__stat">
          <dt>Mentions</dt>
          <dd>{node.mention_count}</dd>
        </div>
        <div className="graph-detail-panel__stat">
          <dt>Confidence</dt>
          <dd>{Math.round(node.confidence * 100)}%</dd>
        </div>
      </dl>

      {connectedNodes.length > 0 && (
        <div className="graph-detail-panel__connections">
          <h4>Connected Nodes</h4>
          <ul className="graph-detail-panel__list">
            {connectedNodes.map((cn) => (
              <li key={cn.id}>
                <button
                  type="button"
                  className="graph-detail-panel__link"
                  onClick={() => onSelectNode(cn.id)}
                  style={{ color: NODE_COLORS[cn.node_type] ?? NODE_COLORS.other }}
                >
                  {cn.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
