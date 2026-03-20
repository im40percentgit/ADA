/**
 * useAudioPlayback — queue-based audio playback via Web Audio API
 *
 * Manages AudioContext lifecycle (created on first user gesture),
 * decodes WAV audio, and plays sentences in order via a queue.
 *
 * @decision DEC-FRONTEND-020
 * @title Queue-based audio playback via Web Audio API
 * @status accepted
 * @rationale AudioContext must be created after a user gesture (autoplay
 *   policy). Queue-based playback ensures sentences play in order even if
 *   they arrive out of order. interrupt() stops current playback and clears
 *   the queue for immediate response to user input.
 */

import { useRef, useCallback } from 'react'

interface AudioQueueItem {
  audioData: ArrayBuffer
  sampleRate: number
}

export interface UseAudioPlaybackReturn {
  queueAudio: (audioData: ArrayBuffer, sampleRate?: number) => void
  interrupt: () => void
  isSpeaking: boolean
}

export function useAudioPlayback(): UseAudioPlaybackReturn {
  const ctxRef = useRef<AudioContext | null>(null)
  const queueRef = useRef<AudioQueueItem[]>([])
  const playingRef = useRef(false)
  const currentSourceRef = useRef<AudioBufferSourceNode | null>(null)
  const speakingRef = useRef(false)

  const getContext = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext()
    }
    if (ctxRef.current.state === 'suspended') {
      ctxRef.current.resume()
    }
    return ctxRef.current
  }, [])

  const playNext = useCallback(async () => {
    if (playingRef.current || queueRef.current.length === 0) {
      if (queueRef.current.length === 0) {
        speakingRef.current = false
      }
      return
    }

    playingRef.current = true
    speakingRef.current = true
    const item = queueRef.current.shift()!

    try {
      const ctx = getContext()
      const audioBuffer = await ctx.decodeAudioData(item.audioData.slice(0))
      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)
      currentSourceRef.current = source

      source.onended = () => {
        currentSourceRef.current = null
        playingRef.current = false
        playNext()
      }

      source.start(0)
    } catch {
      playingRef.current = false
      playNext()
    }
  }, [getContext])

  const queueAudio = useCallback(
    (audioData: ArrayBuffer, sampleRate = 22050) => {
      queueRef.current.push({ audioData, sampleRate })
      if (!playingRef.current) {
        playNext()
      }
    },
    [playNext],
  )

  const interrupt = useCallback(() => {
    queueRef.current = []
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.stop()
      } catch {
        // Already stopped
      }
      currentSourceRef.current = null
    }
    playingRef.current = false
    speakingRef.current = false
  }, [])

  return {
    queueAudio,
    interrupt,
    isSpeaking: speakingRef.current,
  }
}
