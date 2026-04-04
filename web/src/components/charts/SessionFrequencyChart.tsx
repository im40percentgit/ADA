/**
 * SessionFrequencyChart — bar chart of session counts per week.
 *
 * Uses Recharts BarChart. X-axis: week labels (e.g. "2026-W01").
 * Y-axis: session count. Simple, single-series bar chart.
 *
 * @decision DEC-FRONTEND-052
 * @title Session frequency uses BarChart for discrete weekly counts
 * @status accepted
 * @rationale Bar charts are the natural choice for discrete count data
 *   grouped by time period. The week labels from the API are ISO week
 *   identifiers which we display as-is.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

interface SessionFrequencyChartProps {
  data: { week: string; count: number }[]
}

export function SessionFrequencyChart({ data }: SessionFrequencyChartProps) {
  if (data.length === 0) {
    return <p className="patient-dash__empty">No session data available</p>
  }

  return (
    <section aria-label="Session frequency chart">
      <h4>Sessions per Week</h4>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart
          data={data}
          margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e8eaf0" />
          <XAxis
            dataKey="week"
            tick={{ fontSize: 12, fill: '#6b7280' }}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 12, fill: '#6b7280' }}
            tickLine={false}
            axisLine={false}
            width={24}
          />
          <Tooltip
            contentStyle={{
              background: '#fff',
              border: '1px solid #e8eaf0',
              borderRadius: '8px',
              fontSize: '13px',
            }}
            formatter={(value: number) => [`${value}`, 'Sessions']}
          />
          <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  )
}
