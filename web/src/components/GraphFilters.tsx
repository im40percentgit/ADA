/**
 * GraphFilters — filter controls for the knowledge graph.
 *
 * Renders a row of category toggle chips (colored by node type), time range
 * pill buttons, and a search input. All state is owned by the parent via
 * the useKnowledgeGraph hook; this component is a pure presentation layer.
 *
 * @decision DEC-FRONTEND-051
 * @title Category chips use inline background color from NODE_COLORS map
 * @status accepted
 * @rationale Node type colors must match the graph circles. Using the same
 *   color constant for both chips and SVG circles guarantees visual
 *   consistency without a separate CSS class per type.
 */

const NODE_COLORS: Record<string, string> = {
  emotion: '#8b5cf6',
  activity: '#10b981',
  symptom: '#ef4444',
  person: '#3b82f6',
  medication: '#f59e0b',
  other: '#6b7280',
}

const CATEGORY_LABELS: Record<string, string> = {
  emotion: 'Emotion',
  activity: 'Activity',
  symptom: 'Symptom',
  person: 'Person',
  medication: 'Medication',
  other: 'Other',
}

const TIME_RANGES = ['1W', '1M', '3M', 'ALL']

interface GraphFiltersProps {
  categoryFilters: Set<string>
  setCategoryFilters: (filters: Set<string>) => void
  timeRange: string
  setTimeRange: (range: string) => void
  searchQuery: string
  setSearchQuery: (query: string) => void
}

export function GraphFilters({
  categoryFilters,
  setCategoryFilters,
  timeRange,
  setTimeRange,
  searchQuery,
  setSearchQuery,
}: GraphFiltersProps) {
  function toggleCategory(category: string) {
    const next = new Set(categoryFilters)
    if (next.has(category)) {
      next.delete(category)
    } else {
      next.add(category)
    }
    setCategoryFilters(next)
  }

  return (
    <div className="graph-filters" style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-sm)', alignItems: 'center' }}>
      <div className="graph-filters__categories" role="group" aria-label="Category filters" style={{ display: 'flex', gap: 'var(--space-xs)', flexWrap: 'wrap' }}>
        {Object.keys(NODE_COLORS).map((cat) => {
          const active = categoryFilters.has(cat)
          return (
            <button
              key={cat}
              type="button"
              className={`graph-filters__chip ${active ? 'graph-filters__chip--active' : ''}`}
              style={{
                backgroundColor: active ? NODE_COLORS[cat] : 'transparent',
                border: `1px solid ${NODE_COLORS[cat]}`,
                color: active ? '#fff' : NODE_COLORS[cat],
                borderRadius: '10px',
                padding: '2px 8px',
                fontSize: 'var(--size-xs)',
                fontWeight: 600,
                cursor: 'pointer',
                fontFamily: 'var(--font-body)',
                minHeight: 'var(--touch-target-min)',
                display: 'inline-flex',
                alignItems: 'center',
              }}
              onClick={() => toggleCategory(cat)}
              aria-pressed={active}
              aria-label={`Filter ${CATEGORY_LABELS[cat]}`}
            >
              {CATEGORY_LABELS[cat]}
            </button>
          )
        })}
      </div>

      <div className="graph-filters__time" role="group" aria-label="Time range" style={{ display: 'flex', gap: 'var(--space-xs)' }}>
        {TIME_RANGES.map((range) => (
          <button
            key={range}
            type="button"
            className={`graph-filters__pill ${timeRange === range ? 'graph-filters__pill--active' : ''}`}
            onClick={() => setTimeRange(range)}
            aria-pressed={timeRange === range}
            style={{
              padding: '4px 12px',
              borderRadius: 'var(--radius-card)',
              fontSize: 'var(--size-xs)',
              fontWeight: 600,
              cursor: 'pointer',
              border: 'none',
              fontFamily: 'var(--font-body)',
              minHeight: 'var(--touch-target-min)',
              background: timeRange === range ? 'var(--color-primary)' : 'var(--color-bg-elevated)',
              color: timeRange === range ? '#fff' : 'var(--color-text-muted)',
            }}
          >
            {range}
          </button>
        ))}
      </div>

      <input
        className="graph-filters__search"
        type="search"
        placeholder="Search nodes..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        aria-label="Search knowledge graph nodes"
        style={{
          background: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-input)',
          height: 'var(--touch-target-min)',
          padding: '0 var(--space-sm)',
          color: 'var(--color-text-primary)',
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--size-sm)',
        }}
      />
    </div>
  )
}
