/**
 * VoiceIndicator — real-time audio level visualisation.
 *
 * Uses Web Audio API AnalyserNode FFT data to draw a small bar chart
 * showing microphone input levels. Renders nothing when the audio stream
 * is inactive (stream prop is null).
 *
 * The canvas is 80x32px — small enough to fit in the chat header without
 * dominating the layout. Bars are drawn in the primary colour with 50%
 * opacity to stay visually calm in a therapeutic context.
 *
 * @decision DEC-FRONTEND-016
 * @title VoiceIndicator creates its own AudioContext per mount
 * @status accepted
 * @rationale Creating an AudioContext inside the component (not shared)
 *   keeps the audio visualisation self-contained. The context is closed
 *   on unmount to release resources. The alternative (shared AudioContext
 *   in a higher scope) would add cross-component coupling with no benefit
 *   at this scale — there is only one VoiceIndicator in the UI.
 */

import { useEffect, useRef } from 'react'

interface VoiceIndicatorProps {
  stream: MediaStream | null
}

const WIDTH = 80
const HEIGHT = 32
const BAR_COUNT = 16

export function VoiceIndicator({ stream }: VoiceIndicatorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)

  useEffect(() => {
    if (!stream) {
      // No stream — clear canvas and stop animation
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      const ctx = canvasRef.current?.getContext('2d')
      if (ctx) ctx.clearRect(0, 0, WIDTH, HEIGHT)
      return
    }

    const audioCtx = new AudioContext()
    audioCtxRef.current = audioCtx

    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = BAR_COUNT * 2
    analyserRef.current = analyser

    const source = audioCtx.createMediaStreamSource(stream)
    source.connect(analyser)

    const dataArray = new Uint8Array(analyser.frequencyBinCount)

    function draw() {
      if (!canvasRef.current) return
      const ctx2d = canvasRef.current.getContext('2d')
      if (!ctx2d) return

      analyser.getByteFrequencyData(dataArray)

      ctx2d.clearRect(0, 0, WIDTH, HEIGHT)
      ctx2d.fillStyle = 'rgba(99, 102, 241, 0.6)'

      const barWidth = WIDTH / BAR_COUNT - 1
      for (let i = 0; i < BAR_COUNT; i++) {
        const barHeight = (dataArray[i] / 255) * HEIGHT
        const x = i * (barWidth + 1)
        const y = HEIGHT - barHeight
        ctx2d.fillRect(x, y, barWidth, barHeight)
      }

      rafRef.current = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      audioCtx.close()
    }
  }, [stream])

  if (!stream) return null

  return (
    <canvas
      ref={canvasRef}
      width={WIDTH}
      height={HEIGHT}
      className="voice-indicator"
      aria-label="Microphone activity"
      role="img"
    />
  )
}
