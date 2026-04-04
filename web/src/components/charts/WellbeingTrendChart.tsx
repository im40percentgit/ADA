/**
 * WellbeingTrendChart — WHO-5 wellbeing score trend over time.
 *
 * Uses Recharts LineChart following the same pattern as MoodChart.
 * X-axis: dates. Y-axis: 0-100 (WHO-5 percentage). Shows delta
 * annotation comparing first and last data points.
 *
 * @decision DEC-FRONTEND-051
 * @title WHO-5 trend uses LineChart with 0-100 Y-axis range
 * @status accepted
 * @rationale WHO-5 raw scores (0-25) are conventionally multiplied by 4
 *   and displayed as a percentage. The API returns pre-computed scores
 *   which we display directly — the Y-axis range of 0-100 accommodates
 *   both raw and percentage values.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

interface WellbeingTrendChartProps {
  data: { date: string; score: number }[]
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function WellbeingTrendChart({ data }: WellbeingTrendChartProps) {
  if (data.length === 0) {
    return <p className="patient-dash__empty">No WHO-5 data available</p>
  }

  const chartData = data.map((d) => ({
    date: formatDate(d.date),
    score: d.score,
  }))

  const first = data[0].score
  const last = data[data.length - 1].score
  const delta = last - first
  const deltaLabel = delta > 0 ? `+${delta}` : `${delta}`

  return (
    <section aria-label="Wellbeing trend chart">
      <h4>WHO-5 Wellbeing Trend</h4>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart
          data={chartData}
          margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e8eaf0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: '#6b7280' }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 12, fill: '#6b7280' }}
            tickLine={false}
            axisLine={false}
            width={32}
          />
          <Tooltip
            contentStyle={{
              background: '#fff',
              border: '1px solid #e8eaf0',
              borderRadius: '8px',
              fontSize: '13px',
            }}
            formatter={(value: number) => [`${value}`, 'WHO-5']}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="#10b981"
            strokeWidth={2}
            dot={{ fill: '#10b981', r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
      {data.length >= 2 && (
        <p
          style={{
            textAlign: 'center',
            fontSize: '13px',
            color: delta >= 0 ? '#059669' : '#dc2626',
            margin: '4px 0 0',
          }}
        >
          Change: {deltaLabel} points
        </p>
      )}
    </section>
  )
}
