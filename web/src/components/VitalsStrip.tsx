/**
 * VitalsStrip — inline physiological metrics display.
 *
 * Shows HR (bpm), GSR (μS), and SpO2 (%) in a compact horizontal row.
 * Renders nothing until at least one vitals value has been received.
 * Each metric is individually null-checked so the strip shows partial
 * data (e.g. HR only) while the other sensors catch up.
 *
 * @decision DEC-FRONTEND-015
 * @title VitalsStrip renders null until first sensor reading arrives
 * @status accepted
 * @rationale Showing placeholder dashes for missing vitals adds visual
 *   noise before the simulator or real sensors are active. Rendering null
 *   keeps the header clean during text-only sessions and avoids implying
 *   that monitoring is active when it is not.
 */

import type { CurrentVitals } from '../hooks/useChat'

interface VitalsStripProps {
  vitals: CurrentVitals
}

interface MetricProps {
  label: string
  value: number | null
  unit: string
  decimals?: number
}

function Metric({ label, value, unit, decimals = 0 }: MetricProps) {
  if (value === null) return null
  return (
    <span className="vitals-strip__metric">
      <span className="vitals-strip__label">{label}</span>
      <span className="vitals-strip__value">{value.toFixed(decimals)}</span>
      <span className="vitals-strip__unit">{unit}</span>
    </span>
  )
}

export function VitalsStrip({ vitals }: VitalsStripProps) {
  const hasAny = vitals.hr !== null || vitals.gsr !== null || vitals.spo2 !== null
  if (!hasAny) return null

  return (
    <div
      className="vitals-strip"
      role="status"
      aria-label="Physiological vitals"
      aria-live="polite"
      aria-atomic="false"
    >
      <Metric label="HR" value={vitals.hr} unit="bpm" />
      <Metric label="GSR" value={vitals.gsr} unit="μS" decimals={1} />
      <Metric label="SpO₂" value={vitals.spo2} unit="%" decimals={1} />
    </div>
  )
}
