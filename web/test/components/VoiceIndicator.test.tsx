/**
 * VoiceIndicator.test.tsx — component tests for the VoiceIndicator canvas visualiser.
 *
 * # @mock-exempt: AudioContext, MediaStream, AnalyserNode are Web Audio API globals
 * # unavailable in jsdom. They are hardware/browser-API boundaries — mocking them
 * # is the only way to test this component in a unit test environment without a
 * # real browser. The rendering logic (null → no render, stream → canvas) is tested
 * # against the real VoiceIndicator component with a controlled mock stream.
 *
 * DEC-MOTION-006: VoiceIndicator uses canvas-based real-time visualisation driven
 * by the Web Audio API — no CSS animation is involved. The retimed STT pulse
 * (pulse-voice keyframe) lives on .chat__voice-btn--active in App.css, not here.
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { VoiceIndicator } from '../../src/components/VoiceIndicator'

// ---------------------------------------------------------------------------
// Mock Web Audio API — external browser hardware boundary
// ---------------------------------------------------------------------------

const mockGetByteFrequencyData = vi.fn()
const mockConnect = vi.fn()
const mockAnalyser = {
  fftSize: 0,
  frequencyBinCount: 16,
  getByteFrequencyData: mockGetByteFrequencyData,
}
const mockSource = { connect: mockConnect }
const mockAudioContext = {
  createAnalyser: vi.fn(() => mockAnalyser),
  createMediaStreamSource: vi.fn(() => mockSource),
  close: vi.fn(),
}

// Mock requestAnimationFrame to prevent infinite loop in jsdom
let rafCallback: FrameRequestCallback | null = null
const mockRaf = vi.fn((cb: FrameRequestCallback) => {
  rafCallback = cb
  return 1
})
const mockCancelRaf = vi.fn()

beforeEach(() => {
  vi.stubGlobal('AudioContext', vi.fn(() => mockAudioContext))
  vi.stubGlobal('requestAnimationFrame', mockRaf)
  vi.stubGlobal('cancelAnimationFrame', mockCancelRaf)
  mockGetByteFrequencyData.mockImplementation((arr: Uint8Array) => arr.fill(128))
})

afterEach(() => {
  vi.unstubAllGlobals()
  rafCallback = null
})

function makeMockStream(): MediaStream {
  return {} as MediaStream
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('VoiceIndicator', () => {
  it('renders nothing when stream is null', () => {
    const { container } = render(<VoiceIndicator stream={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders a canvas when stream is provided', () => {
    render(<VoiceIndicator stream={makeMockStream()} />)
    const canvas = screen.getByRole('img', { name: 'Microphone activity' })
    expect(canvas).toBeInTheDocument()
    expect(canvas.tagName).toBe('CANVAS')
  })

  it('canvas has correct dimensions', () => {
    render(<VoiceIndicator stream={makeMockStream()} />)
    const canvas = screen.getByRole('img', { name: 'Microphone activity' }) as HTMLCanvasElement
    expect(canvas.width).toBe(80)
    expect(canvas.height).toBe(32)
  })

  it('canvas has voice-indicator class', () => {
    render(<VoiceIndicator stream={makeMockStream()} />)
    const canvas = screen.getByRole('img', { name: 'Microphone activity' })
    expect(canvas).toHaveClass('voice-indicator')
  })

  it('creates AudioContext when stream is provided', () => {
    render(<VoiceIndicator stream={makeMockStream()} />)
    expect(AudioContext).toHaveBeenCalled()
  })

  it('closes AudioContext on unmount', () => {
    const { unmount } = render(<VoiceIndicator stream={makeMockStream()} />)
    unmount()
    expect(mockAudioContext.close).toHaveBeenCalled()
  })

  it('goes from canvas to nothing when stream changes to null', () => {
    const { rerender } = render(<VoiceIndicator stream={makeMockStream()} />)
    expect(screen.getByRole('img', { name: 'Microphone activity' })).toBeInTheDocument()

    rerender(<VoiceIndicator stream={null} />)
    expect(screen.queryByRole('img', { name: 'Microphone activity' })).not.toBeInTheDocument()
  })

  // DEC-MOTION-006: VoiceIndicator uses Web Audio canvas — no CSS pulse animation
  // on the canvas itself. The retimed pulse-voice keyframe applies to
  // .chat__voice-btn--active (App.css), not to this component.
  it('does not apply CSS animation class — visualisation is canvas-based (DEC-MOTION-006)', () => {
    render(<VoiceIndicator stream={makeMockStream()} />)
    const canvas = screen.getByRole('img', { name: 'Microphone activity' })
    // No inline animation style expected on the canvas
    expect(canvas).not.toHaveStyle({ animation: expect.stringContaining('pulse') })
  })
})
