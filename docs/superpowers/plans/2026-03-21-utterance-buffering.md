# Utterance Buffering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixed-interval audio flushing with frontend speech-end detection so Whisper transcribes complete utterances instead of 2-second fragments.

**Architecture:** Frontend creates an AnalyserNode alongside MediaRecorder, monitors RMS every 100ms, and sends `end_of_utterance` signal via media WS when 1.5s of silence follows speech. Server flushes accumulated audio buffer on this signal instead of a timer.

**Tech Stack:** Web Audio API (AnalyserNode), TypeScript/React hooks, Python/FastAPI WebSocket

**Spec:** `docs/superpowers/specs/2026-03-21-utterance-buffering-design.md`

---

### Task 1: Add `sendEndOfUtterance` to useMediaWebSocket

**Files:**
- Modify: `web/src/hooks/useMediaWebSocket.ts:31-36` (interface), `web/src/hooks/useMediaWebSocket.ts:158-163` (return)

- [ ] **Step 1: Add `sendEndOfUtterance` to `UseMediaWebSocketReturn` interface**

In `web/src/hooks/useMediaWebSocket.ts`, add to the interface (line 35):

```typescript
export interface UseMediaWebSocketReturn {
  connected: boolean
  sendAudioChunk: (blob: Blob, patientId?: string) => void
  sendVideoFrame: (blob: Blob, patientId?: string) => void
  sendEndOfUtterance: () => void
  close: () => void
}
```

- [ ] **Step 2: Implement `sendEndOfUtterance`**

After the `sendVideoFrame` callback (line 149), add:

```typescript
  const sendEndOfUtterance = useCallback(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'end_of_utterance' }))
  }, [])
```

- [ ] **Step 3: Add to return object**

Update the return (line 158):

```typescript
  return {
    get connected() { return connectedRef.current },
    sendAudioChunk,
    sendVideoFrame,
    sendEndOfUtterance,
    close,
  }
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd web && npx tsc --noEmit 2>&1 | head -20
```

Expected: No new errors (existing errors may appear)

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useMediaWebSocket.ts
git commit -m "feat(media): add sendEndOfUtterance to media WebSocket hook"
```

---

### Task 2: Add speech state machine to useMediaCapture

**Files:**
- Modify: `web/src/hooks/useMediaCapture.ts`

This is the core frontend change. Add an AnalyserNode and RMS-based speech detection alongside MediaRecorder.

- [ ] **Step 1: Add `onEndOfUtterance` to options and return interfaces**

```typescript
export interface UseMediaCaptureOptions {
  onAudioChunk: (blob: Blob) => void
  onVideoFrame: (blob: Blob) => void
  onEndOfUtterance?: () => void
}
```

No return interface changes needed — the callback fires internally.

- [ ] **Step 2: Add refs for the new audio analysis state**

After the existing refs (line 57), add:

```typescript
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const vadTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const speechStartRef = useRef<number>(0)  // timestamp when speech started
  const silenceStartRef = useRef<number>(0) // timestamp when silence started
  const isSpeakingRef = useRef(false)
```

- [ ] **Step 3: Add speech detection constants and RMS helper**

After the refs, add:

```typescript
  const SPEECH_THRESHOLD = 10    // frequency bin amplitude (0-255 scale)
  const SILENCE_WINDOW = 1500    // ms of silence before end-of-utterance
  const VAD_POLL_INTERVAL = 100  // ms between RMS checks
```

- [ ] **Step 4: Create the VAD start/stop functions**

Add before `stopAudio`:

```typescript
  const stopVad = useCallback(() => {
    if (vadTimerRef.current) {
      clearInterval(vadTimerRef.current)
      vadTimerRef.current = null
    }
    analyserRef.current?.disconnect()
    analyserRef.current = null
    audioCtxRef.current?.close()
    audioCtxRef.current = null
    isSpeakingRef.current = false
    speechStartRef.current = 0
    silenceStartRef.current = 0
  }, [])

  const startVad = useCallback((stream: MediaStream) => {
    const audioCtx = new AudioContext()
    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = 256
    const source = audioCtx.createMediaStreamSource(stream)
    source.connect(analyser)
    audioCtxRef.current = audioCtx
    analyserRef.current = analyser

    const freqData = new Uint8Array(analyser.frequencyBinCount)

    vadTimerRef.current = setInterval(() => {
      if (!analyserRef.current) return
      analyserRef.current.getByteFrequencyData(freqData)

      // RMS of frequency bins
      let sum = 0
      for (let i = 0; i < freqData.length; i++) {
        sum += freqData[i] * freqData[i]
      }
      const rms = Math.sqrt(sum / freqData.length)
      const now = Date.now()

      if (rms > SPEECH_THRESHOLD) {
        // Speech detected
        if (!isSpeakingRef.current) {
          isSpeakingRef.current = true
          speechStartRef.current = now
        }
        silenceStartRef.current = 0 // reset silence timer
      } else if (isSpeakingRef.current) {
        // Silence after speech
        if (silenceStartRef.current === 0) {
          silenceStartRef.current = now
        } else if (now - silenceStartRef.current >= SILENCE_WINDOW) {
          // End of utterance — silence held long enough
          isSpeakingRef.current = false
          speechStartRef.current = 0
          silenceStartRef.current = 0
          onEndOfUtterance?.()
        }
      }
    }, VAD_POLL_INTERVAL)
  }, [onEndOfUtterance])
```

- [ ] **Step 5: Wire VAD into toggleAudio**

In `toggleAudio`, after `recorder.start(500)` (line 113) and before `setAudioEnabled(true)` (line 114), add:

```typescript
      startVad(stream)
```

- [ ] **Step 6: Wire VAD cleanup into stopAudio**

In `stopAudio`, before `setAudioEnabled(false)` (line 74), add:

```typescript
    stopVad()
```

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd web && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 8: Commit**

```bash
git add web/src/hooks/useMediaCapture.ts
git commit -m "feat(media): add speech state machine with AnalyserNode VAD to useMediaCapture"
```

---

### Task 3: Wire `onEndOfUtterance` in Chat.tsx

**Files:**
- Modify: `web/src/components/Chat.tsx:91` (useMediaWebSocket destructure), `web/src/components/Chat.tsx:102-111` (useMediaCapture options)

- [ ] **Step 1: Destructure `sendEndOfUtterance` from useMediaWebSocket**

Change line 91:

```typescript
  const { sendAudioChunk, sendVideoFrame, sendEndOfUtterance } = useMediaWebSocket({ sessionId })
```

- [ ] **Step 2: Pass `onEndOfUtterance` to useMediaCapture**

Add to the useMediaCapture options (after `onVideoFrame`, line 110):

```typescript
    onEndOfUtterance: useCallback(
      () => sendEndOfUtterance(),
      [sendEndOfUtterance],
    ),
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd web && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
git add web/src/components/Chat.tsx
git commit -m "feat(media): wire end-of-utterance signal from capture to media WS"
```

---

### Task 4: Server-side signal-based flushing

**Files:**
- Modify: `ada/api/routes/media.py:86-154`

- [ ] **Step 1: Read the current media.py to confirm line numbers**

Read `ada/api/routes/media.py` lines 86-154 fully.

- [ ] **Step 2: Replace `AUDIO_BUFFER_INTERVAL` with `MAX_UTTERANCE_DURATION`**

Change line 91:

```python
    MAX_UTTERANCE_DURATION = 30.0  # Safety fallback — flush if no end_of_utterance signal
```

- [ ] **Step 3: Handle `end_of_utterance` message type**

In the text message handler (after the `elif msg_type in ("audio_chunk", "video_frame"):` block, around line 112), add:

```python
                elif msg_type == "end_of_utterance":
                    if audio_header:
                        flush_id = str(uuid.uuid4())
                        combined = audio_header + b"".join(audio_buffer)
                        await _handle_audio(bus, session_id, audio_buffer_meta, combined, flush_id)
                        audio_buffer.clear()
                        audio_buffer_start = time.monotonic()
```

- [ ] **Step 4: Change the timer-based flush to safety-only fallback**

Replace the existing timer check in the audio_chunk binary handler (around line 132):

```python
                    # Safety fallback: flush if user speaks > 30s without pause
                    if audio_buffer and time.monotonic() - audio_buffer_start >= MAX_UTTERANCE_DURATION:
                        combined = audio_header + b"".join(audio_buffer)
                        await _handle_audio(bus, session_id, audio_buffer_meta, combined, chunk_id)
                        audio_buffer.clear()
                        audio_buffer_start = time.monotonic()
```

- [ ] **Step 5: Update the `finally` block guard**

Change the guard in the finally block (around line 147) from `if audio_buffer and audio_header:` to:

```python
        if audio_header:
```

- [ ] **Step 6: Run backend tests**

```bash
uv run python -m pytest tests/unit/test_stt.py tests/unit/test_transcription_agent.py tests/integration/test_stt_pipeline.py -v
```

Expected: ALL PASS

- [ ] **Step 7: Run full test suite**

```bash
uv run python -m pytest tests/ -q
```

Expected: 825+ tests pass, 0 failures

- [ ] **Step 8: Commit**

```bash
git add ada/api/routes/media.py
git commit -m "feat(media): replace timer flush with end_of_utterance signal + 30s safety fallback"
```

---

### Task 5: Verification

- [ ] **Step 1: Run full test suite**

```bash
uv run python -m pytest tests/ -q
```

Expected: ALL PASS

- [ ] **Step 2: Verify frontend builds**

```bash
cd web && npx tsc --noEmit && npm run build
```

Expected: No errors

- [ ] **Step 3: Manual test (if servers available)**

Start backend + frontend, enable mic, speak a sentence, pause — one clean transcription should appear after the pause, not multiple fragments during speech.
