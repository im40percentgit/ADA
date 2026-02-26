/**
 * useMediaCapture — browser microphone and camera capture.
 *
 * Manages getUserMedia streams, MediaRecorder for audio, and a canvas-based
 * snapshot loop for video. Exposes toggle functions so the user can
 * independently enable/disable each modality.
 *
 * Audio pipeline:
 *   getUserMedia({audio: true}) → MediaRecorder (timeslice=500ms) → ondataavailable
 *   → onAudioChunk(blob) callback
 *
 * Video pipeline:
 *   getUserMedia({video: {width: 320}}) → drawImage() onto offscreen canvas
 *   → canvas.toBlob('image/jpeg') at 1fps → onVideoFrame(blob) callback
 *   The video preview is surfaced via videoRef for the FacePreview component.
 *
 * @decision DEC-FRONTEND-011
 * @title useMediaCapture manages raw browser media; transport is a separate concern
 * @status accepted
 * @rationale Separating capture (this hook) from transport (useMediaWebSocket)
 *   means each can be tested independently and the video preview can be
 *   displayed regardless of WebSocket connectivity. The onAudioChunk and
 *   onVideoFrame callbacks are the boundary between the two layers.
 */

import { useState, useRef, useCallback, useEffect, RefObject } from 'react'

export interface UseMediaCaptureOptions {
  onAudioChunk: (blob: Blob) => void
  onVideoFrame: (blob: Blob) => void
}

export interface UseMediaCaptureReturn {
  audioEnabled: boolean
  videoEnabled: boolean
  toggleAudio: () => Promise<void>
  toggleVideo: () => Promise<void>
  stopAll: () => void
  audioStream: MediaStream | null
  videoRef: RefObject<HTMLVideoElement>
  error: string | null
}

export function useMediaCapture({
  onAudioChunk,
  onVideoFrame,
}: UseMediaCaptureOptions): UseMediaCaptureReturn {
  const [audioEnabled, setAudioEnabled] = useState(false)
  const [videoEnabled, setVideoEnabled] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const audioStreamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const videoStreamRef = useRef<MediaStream | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const frameTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // Lazily create the offscreen canvas for video snapshots
  const getCanvas = useCallback((): HTMLCanvasElement => {
    if (!canvasRef.current) {
      canvasRef.current = document.createElement('canvas')
      canvasRef.current.width = 320
      canvasRef.current.height = 240
    }
    return canvasRef.current
  }, [])

  const stopAudio = useCallback(() => {
    recorderRef.current?.stop()
    recorderRef.current = null
    audioStreamRef.current?.getTracks().forEach((t) => t.stop())
    audioStreamRef.current = null
    setAudioEnabled(false)
  }, [])

  const stopVideo = useCallback(() => {
    if (frameTimerRef.current) {
      clearInterval(frameTimerRef.current)
      frameTimerRef.current = null
    }
    videoStreamRef.current?.getTracks().forEach((t) => t.stop())
    videoStreamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setVideoEnabled(false)
  }, [])

  const toggleAudio = useCallback(async () => {
    if (audioEnabled) {
      stopAudio()
      return
    }

    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioStreamRef.current = stream

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
      recorderRef.current = recorder

      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data && e.data.size > 0) {
          onAudioChunk(e.data)
        }
      }

      recorder.onerror = () => {
        setError('Audio recording error')
        stopAudio()
      }

      recorder.start(500) // Emit chunk every 500ms
      setAudioEnabled(true)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Microphone access denied: ${msg}`)
    }
  }, [audioEnabled, onAudioChunk, stopAudio])

  const toggleVideo = useCallback(async () => {
    if (videoEnabled) {
      stopVideo()
      return
    }

    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 320 }, height: { ideal: 240 }, facingMode: 'user' },
      })
      videoStreamRef.current = stream

      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => {
          // Autoplay may be blocked — user gesture will trigger it
        })
      }

      const canvas = getCanvas()
      const ctx = canvas.getContext('2d')

      frameTimerRef.current = setInterval(() => {
        if (!videoRef.current || !ctx) return
        if (videoRef.current.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return

        ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height)
        canvas.toBlob(
          (blob) => {
            if (blob) onVideoFrame(blob)
          },
          'image/jpeg',
          0.7, // 70% quality — adequate for emotion analysis, small payload
        )
      }, 1000) // 1 fps

      setVideoEnabled(true)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Camera access denied: ${msg}`)
    }
  }, [videoEnabled, onVideoFrame, stopVideo, getCanvas])

  const stopAll = useCallback(() => {
    stopAudio()
    stopVideo()
  }, [stopAudio, stopVideo])

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopAll()
    }
  }, [stopAll])

  return {
    audioEnabled,
    videoEnabled,
    toggleAudio,
    toggleVideo,
    stopAll,
    audioStream: audioStreamRef.current,
    videoRef: videoRef as RefObject<HTMLVideoElement>,
    error,
  }
}
