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

import { useEffect, useRef, useCallback } from 'react'
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
  const panelRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  // Focus the close button when panel opens
  useEffect(() => {
    if (node) {
      closeButtonRef.current?.focus()
    }
  }, [node])

  // Focus trap: keep Tab within the panel
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
      return
    }

    if (e.key !== 'Tab') return

    const panel = panelRef.current
    if (!panel) return

    const focusableElements = panel.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    )
    if (focusableElements.length === 0) return

    const first = focusableElements[0]
    const last = focusableElements[focusableElements.length - 1]

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault()
        last.focus()
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
  }, [onClose])

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
    <div
      ref={panelRef}
      className="graph-detail-panel"
      role="dialog"
      aria-labelledby="graph-detail-panel-title"
      aria-modal="true"
      onKeyDown={handleKeyDown}
      style={{
        background: 'var(--color-bg-card)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-card)',
        padding: 'var(--space-md)',
        boxShadow: 'var(--shadow-elevated)',
        fontFamily: 'var(--font-body)',
      }}
    >
      <div className="graph-detail-panel__header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-sm)' }}>
        <h3 id="graph-detail-panel-title" className="graph-detail-panel__title" style={{ margin: 0, fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', color: 'var(--color-text-primary)' }}>{node.label}</h3>
        <button
          ref={closeButtonRef}
          type="button"
          className="graph-detail-panel__close"
          onClick={onClose}
          aria-label="Close detail panel"
          style={{
            background: 'var(--color-bg-elevated)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-button)',
            color: 'var(--color-text-muted)',
            cursor: 'pointer',
            minHeight: 'var(--touch-target-min)',
            minWidth: 'var(--touch-target-min)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--font-body)',
          }}
        >
          X
        </button>
      </div>

      <span
        className="graph-detail-panel__badge"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '2px 8px',
          borderRadius: '10px',
          fontSize: 'var(--size-xs)',
          fontWeight: 600,
          backgroundColor: color,
          color: '#fff',
          marginBottom: 'var(--space-md)',
        }}
      >
        {node.node_type}
      </span>

      <dl className="graph-detail-panel__stats" style={{ display: 'flex', gap: 'var(--space-lg)', margin: '0 0 var(--space-md)' }}>
        <div className="graph-detail-panel__stat">
          <dt style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)' }}>Mentions</dt>
          <dd style={{ margin: 0, fontWeight: 700, fontSize: 'var(--size-h2)', color: 'var(--color-text-primary)' }}>{node.mention_count}</dd>
        </div>
        <div className="graph-detail-panel__stat">
          <dt style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)' }}>Confidence</dt>
          <dd style={{ margin: 0, fontWeight: 700, fontSize: 'var(--size-h2)', color: 'var(--color-text-primary)' }}>{Math.round(node.confidence * 100)}%</dd>
        </div>
      </dl>

      {connectedNodes.length > 0 && (
        <div className="graph-detail-panel__connections">
          <h4 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-sm)', color: 'var(--color-text-secondary)', margin: '0 0 var(--space-sm)' }}>Connected Nodes</h4>
          <ul className="graph-detail-panel__list" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
            {connectedNodes.map((cn) => (
              <li key={cn.id}>
                <button
                  type="button"
                  className="graph-detail-panel__link"
                  onClick={() => onSelectNode(cn.id)}
                  style={{
                    color: NODE_COLORS[cn.node_type] ?? NODE_COLORS.other,
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-body)',
                    fontSize: 'var(--size-sm)',
                    padding: 'var(--space-xs) 0',
                    minHeight: 'var(--touch-target-min)',
                    display: 'flex',
                    alignItems: 'center',
                  }}
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
