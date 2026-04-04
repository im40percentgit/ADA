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
    <div className="graph-filters">
      <div className="graph-filters__categories" role="group" aria-label="Category filters">
        {Object.keys(NODE_COLORS).map((cat) => {
          const active = categoryFilters.has(cat)
          return (
            <button
              key={cat}
              type="button"
              className={`graph-filters__chip ${active ? 'graph-filters__chip--active' : ''}`}
              style={{
                backgroundColor: active ? NODE_COLORS[cat] : 'transparent',
                borderColor: NODE_COLORS[cat],
                color: active ? '#fff' : NODE_COLORS[cat],
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

      <div className="graph-filters__time" role="group" aria-label="Time range">
        {TIME_RANGES.map((range) => (
          <button
            key={range}
            type="button"
            className={`graph-filters__pill ${timeRange === range ? 'graph-filters__pill--active' : ''}`}
            onClick={() => setTimeRange(range)}
            aria-pressed={timeRange === range}
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
      />
    </div>
  )
}
