/**
 * MoodChart — mood score visualization over sessions
 *
 * Uses recharts LineChart to plot mood scores (1-10) against session dates.
 * Fetches data from /api/mood-history on mount.
 *
 * @decision DEC-FRONTEND-007
 * @title Use recharts for MoodChart rather than raw SVG
 * @status accepted
 * @rationale Recharts provides accessible, responsive charts with minimal
 *   boilerplate. The mood-history endpoint returns a small dataset (one point
 *   per session), so recharts bundle cost (~50 kB gzipped) is justified by
 *   the time saved vs. hand-crafting axis scaling, tooltips, and responsive
 *   containers in raw SVG.
 */

import { useEffect, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { getMoodHistory } from '../api/client'
import type { MoodDataPoint } from '../types'

interface MoodChartProps {
  patientId: string
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function MoodChart({ patientId }: MoodChartProps) {
  const [data, setData] = useState<MoodDataPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getMoodHistory(patientId)
      .then((points) => {
        if (!cancelled) setData(points)
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load mood history')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [patientId])

  if (loading) {
    return (
      <div className="mood-chart mood-chart--loading" aria-busy="true">
        Loading mood history…
      </div>
    )
  }

  if (error) {
    return (
      <div className="mood-chart mood-chart--error" role="alert">
        {error}
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="mood-chart mood-chart--empty">
        No mood data yet. Complete a session to see your progress here.
      </div>
    )
  }

  const chartData = data.map((d) => ({
    date: formatDate(d.date),
    score: d.score,
    session_id: d.session_id,
  }))

  return (
    <section className="mood-chart" aria-label="Mood history chart">
      <h3 className="mood-chart__title">Mood Over Time</h3>
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
            domain={[1, 10]}
            ticks={[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}
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
            formatter={(value: number) => [`${value}/10`, 'Mood']}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="#6366f1"
            strokeWidth={2}
            dot={{ fill: '#6366f1', r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </section>
  )
}
