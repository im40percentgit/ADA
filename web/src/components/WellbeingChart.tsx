/**
 * WellbeingChart — WHO-5 wellbeing trend for the caregiver dashboard.
 *
 * Shows WHO-5 percentage scores over time using Recharts LineChart.
 * WHO-5 raw total is 0-25; percentage is (raw / 25) * 100.
 * Shows "Not enough data yet" when fewer than 2 data points.
 *
 * @decision DEC-FRONTEND-024
 * @title WellbeingChart displays WHO-5 as percentage (0-100), not raw score (0-25)
 * @status accepted
 * @rationale The WHO-5 raw score (0-25) is unfamiliar to non-clinical caregivers.
 *   Converting to a 0-100% scale makes the Y-axis immediately intuitive —
 *   "75%" reads as "doing well" without requiring knowledge of the instrument.
 *   The tooltip labels the value as "WHO-5" to preserve clinical traceability
 *   for caregivers who want to look up the instrument. Consistent with the
 *   existing MoodChart pattern which also normalises scores for display.
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
import type { CaregiverAssessmentEntry } from '../types'

interface WellbeingChartProps {
  who5Scores: CaregiverAssessmentEntry[]
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function WellbeingChart({ who5Scores }: WellbeingChartProps) {
  if (who5Scores.length < 2) {
    return (
      <section className="cg-card cg-wellbeing" aria-label="Wellbeing trend">
        <h2 className="cg-card__title">Wellbeing Trend</h2>
        <p className="cg-card__empty">Not enough data yet</p>
      </section>
    )
  }

  const sorted = [...who5Scores].sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  const chartData = sorted.map((entry) => ({
    date: formatDate(entry.timestamp),
    score: Math.round((entry.total_score / 25) * 100),
  }))

  return (
    <section className="cg-card cg-wellbeing" aria-label="Wellbeing trend">
      <h2 className="cg-card__title">Wellbeing Trend</h2>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e8eaf0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: '#6b7280' }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tick={{ fontSize: 12, fill: '#6b7280' }}
            tickLine={false}
            axisLine={false}
            width={32}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              background: '#fff',
              border: '1px solid #e8eaf0',
              borderRadius: '8px',
              fontSize: '13px',
            }}
            formatter={(value: number) => [`${value}%`, 'WHO-5']}
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
    </section>
  )
}
