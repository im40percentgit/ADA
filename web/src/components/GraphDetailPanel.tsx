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
 *
 * @decision DEC-MOTION-004
 * @title Dialog entrance/exit uses opacity + translateY(12px), duration-base, ease-out/ease-in
 * @status accepted
 * @rationale Enter: opacity 0→1 + translateY(12px)→0 over 240ms (--motion-duration-base)
 *   with ease-out for a natural settle. Exit: same properties reversed with ease-in so the
 *   panel accelerates out of frame. Mount/unmount coordination: a `isVisible` state flag
 *   keeps the element in the DOM during exit; a 240ms setTimeout fires after onClose to
 *   unmount once the CSS transition completes. Escape triggers onClose immediately so
 *   keyboard users never wait for animation. The Phase 13c blanket prefers-reduced-motion
 *   override in base.css zeroes all durations automatically — no per-rule handling needed.
 *   CSS class `ada-dialog` (default = closed style) + `ada-dialog--open` (open style) are
 *   defined in base.css at DEC-MOTION-004.
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import type { KnowledgeNode, KnowledgeEdge } from '../types'

/**
 * Duration must match --motion-duration-base (240ms) in tokens.css so that the
 * setTimeout fires after the CSS transition completes and the element unmounts
 * cleanly. If the token value changes, update this constant to match.
 */
const DIALOG_MOTION_DURATION_MS = 240

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

  /**
   * Mount/unmount coordination for exit animation.
   *
   * `visibleNode` holds the last non-null node so the panel can render its
   * content during the exit transition (after `node` becomes null).
   * `isOpen` drives the .ada-dialog--open class (enter) vs default .ada-dialog
   * (exit). Both flags are updated together to keep the state machine simple.
   *
   * State transitions:
   *   node: null → node  →  visibleNode = node, isOpen = true  (enter)
   *   node: node → null  →  isOpen = false (triggers exit CSS), then after
   *                         DIALOG_MOTION_DURATION_MS visibleNode = null (unmount)
   */
  const [isOpen, setIsOpen] = useState(false)
  const [visibleNode, setVisibleNode] = useState<KnowledgeNode | null>(null)
  const exitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (node) {
      // Cancel any in-flight exit timer (e.g., user re-selected before exit finished)
      if (exitTimerRef.current !== null) {
        clearTimeout(exitTimerRef.current)
        exitTimerRef.current = null
      }
      setVisibleNode(node)
      // A zero-delay setTimeout ensures the element is committed to the DOM
      // in the current paint before the open class is applied, giving the
      // browser a frame boundary to start the entrance CSS transition.
      // Using setTimeout(0) rather than requestAnimationFrame means this is
      // controllable by vi.useFakeTimers() in tests.
      setTimeout(() => {
        setIsOpen(true)
      }, 0)
    } else {
      // Trigger exit transition by removing the open class, then unmount
      setIsOpen(false)
      exitTimerRef.current = setTimeout(() => {
        setVisibleNode(null)
        exitTimerRef.current = null
      }, DIALOG_MOTION_DURATION_MS)
    }

    return () => {
      if (exitTimerRef.current !== null) {
        clearTimeout(exitTimerRef.current)
        exitTimerRef.current = null
      }
    }
  }, [node])

  // Focus the close button when panel enters open state
  useEffect(() => {
    if (isOpen) {
      closeButtonRef.current?.focus()
    }
  }, [isOpen])

  // Focus trap: keep Tab within the panel
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      // Close immediately — animation plays over still-mounted element
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

  if (!visibleNode) return null

  // Find connected nodes
  const connectedEdges = edges.filter(
    (e) => e.from_node === visibleNode.id || e.to_node === visibleNode.id,
  )
  const connectedNodeIds = connectedEdges.map((e) =>
    e.from_node === visibleNode.id ? e.to_node : e.from_node,
  )
  const nodeMap = new Map(allNodes.map((n) => [n.id, n]))
  const connectedNodes = connectedNodeIds
    .map((id) => nodeMap.get(id))
    .filter((n): n is KnowledgeNode => n !== undefined)

  const color = NODE_COLORS[visibleNode.node_type] ?? NODE_COLORS.other

  return (
    <div
      ref={panelRef}
      className={`graph-detail-panel ada-dialog${isOpen ? ' ada-dialog--open' : ''}`}
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
        <h3 id="graph-detail-panel-title" className="graph-detail-panel__title" style={{ margin: 0, fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', color: 'var(--color-text-primary)' }}>{visibleNode.label}</h3>
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
        {visibleNode.node_type}
      </span>

      <dl className="graph-detail-panel__stats" style={{ display: 'flex', gap: 'var(--space-lg)', margin: '0 0 var(--space-md)' }}>
        <div className="graph-detail-panel__stat">
          <dt style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)' }}>Mentions</dt>
          <dd style={{ margin: 0, fontWeight: 700, fontSize: 'var(--size-h2)', color: 'var(--color-text-primary)' }}>{visibleNode.mention_count}</dd>
        </div>
        <div className="graph-detail-panel__stat">
          <dt style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)' }}>Confidence</dt>
          <dd style={{ margin: 0, fontWeight: 700, fontSize: 'var(--size-h2)', color: 'var(--color-text-primary)' }}>{Math.round(visibleNode.confidence * 100)}%</dd>
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
