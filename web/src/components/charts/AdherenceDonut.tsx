/**
 * AdherenceDonut — medication adherence as a donut chart.
 *
 * Uses Recharts PieChart with two segments (taken/missed). Center label
 * shows the adherence percentage. Below the chart: list of missed dates.
 *
 * @decision DEC-FRONTEND-054
 * @title AdherenceDonut uses PieChart with inner radius for donut effect
 * @status accepted
 * @rationale A donut chart is the conventional visualization for
 *   "X out of Y" metrics. The center label provides the key number
 *   at a glance. Missed dates listed below give actionable detail
 *   without cluttering the chart.
 */

import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'

interface AdherenceDonutProps {
  data: {
    taken: number
    total: number
    missed_dates: string[]
  }
}

const COLORS = ['#10b981', '#ef4444']

export function AdherenceDonut({ data }: AdherenceDonutProps) {
  const { taken, total, missed_dates } = data
  const missed = total - taken
  const pct = total > 0 ? Math.round((taken / total) * 100) : 0

  const chartData = [
    { name: 'Taken', value: taken },
    { name: 'Missed', value: missed },
  ]

  return (
    <section aria-label="Medication adherence">
      <h4>Medication Adherence</h4>
      <div style={{ position: 'relative', width: '100%', height: 200 }}>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={80}
              dataKey="value"
              startAngle={90}
              endAngle={-270}
              stroke="none"
            >
              {chartData.map((_entry, index) => (
                <Cell key={index} fill={COLORS[index]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            textAlign: 'center',
            pointerEvents: 'none',
          }}
        >
          <span style={{ fontSize: '24px', fontWeight: 700, color: '#111827' }}>
            {pct}%
          </span>
        </div>
      </div>
      {missed_dates.length > 0 && (
        <div style={{ marginTop: '8px' }}>
          <p style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>
            Missed dates:
          </p>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: '13px' }}>
            {missed_dates.map((date) => (
              <li key={date} style={{ color: '#ef4444' }}>
                {date}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
