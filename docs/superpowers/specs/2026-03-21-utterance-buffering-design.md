# VAD-Based Utterance Buffering

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Replace fixed-interval audio buffer with frontend speech-end detection for utterance-level transcription

---

## Problem

The current STT pipeline flushes audio every 2 seconds on a fixed timer (`AUDIO_BUFFER_INTERVAL` in `media.py`). Each chunk produces a separate transcription message, resulting in:

1. **Chatty output** — multiple partial transcriptions appear mid-sentence, cluttering the chat
2. **Fragmented input** — Whisper transcribes 2-second fragments instead of complete utterances, reducing accuracy

## Design

### Frontend: Speech State Machine

`useMediaCapture` must create a new `AudioContext` and `AnalyserNode` when audio starts (inside `toggleAudio`, alongside `MediaRecorder`). `VoiceIndicator` has its own private `AudioContext`/`AnalyserNode` — they cannot be shared.

**Setup** (inside `toggleAudio` when starting):
```typescript
const audioCtx = new AudioContext()
const analyser = audioCtx.createAnalyser()
const source = audioCtx.createMediaStreamSource(stream)
source.connect(analyser)
```

**RMS monitoring** — every ~100ms, compute RMS from `AnalyserNode.getByteFrequencyData()` (frequency domain, where silence = 0). Compare against a speech threshold (~10 on the 0-255 frequency byte scale). Using frequency data avoids the centering issue with time-domain data (which is centered at 128, not 0).

**State machine:**
```
idle → speaking (RMS > threshold)
speaking → silence_detected (RMS < threshold for 1.5s)
silence_detected → send end_of_utterance signal → idle
```

**Silence window constraint:** The 1.5s silence window must exceed the MediaRecorder `timeslice` (500ms) to ensure the last audio chunk is delivered before the `end_of_utterance` signal is sent. WebSocket frame ordering over TCP guarantees that if the audio frames are sent before the signal frame in JS, they arrive in the same order at the server. The current 1.5s value satisfies this with margin.

The `onEndOfUtterance` callback is called when the state transitions from `speaking` through `silence_detected`. This fires `useMediaWebSocket.sendEndOfUtterance()`.

**Audio chunks continue streaming** every 500ms as before — `MediaRecorder.ondataavailable` is unchanged. The speech detection is a parallel signal, not a replacement for the audio stream.

**Cleanup:** Close the `AudioContext` when audio is toggled off (alongside `MediaRecorder.stop()`).

### Media WebSocket: end_of_utterance Signal

`useMediaWebSocket` gets a new `sendEndOfUtterance()` method that sends:
```json
{"type": "end_of_utterance"}
```

This is a JSON text frame (no binary payload). The server handles it alongside existing message types (`audio_chunk`, `video_frame`, `sensor_data`).

The `UseMediaWebSocketReturn` interface must be extended with `sendEndOfUtterance: () => void`.

### Server: Signal-Based Flushing

In `ada/api/routes/media.py`, replace the fixed timer with signal-based flushing:

**Remove:** `AUDIO_BUFFER_INTERVAL` constant and the `time.monotonic()` comparison in the audio handling block.

**Add:** Handle `end_of_utterance` message type in the text message handler. When received, flush the accumulated audio buffer (EBML header + chunks) as a single `AudioChunkReceivedEvent`.

**Keep:** EBML header retention, chunk accumulation, `finally` block flush on disconnect.

**Safety fallback:** If no `end_of_utterance` signal arrives within 30 seconds of the first audio chunk, flush automatically to prevent unbounded memory growth. Reset the safety timer after each flush.

```python
MAX_UTTERANCE_DURATION = 30.0  # seconds — safety fallback

# In the message loop:
elif msg_type == "end_of_utterance":
    if audio_header:  # guard on header, not buffer — single-chunk utterances have empty buffer
        combined = audio_header + b"".join(audio_buffer)
        await _handle_audio(bus, session_id, audio_buffer_meta, combined, chunk_id)
        audio_buffer.clear()
        audio_buffer_start = time.monotonic()

# In the audio_chunk handler (replaces timer check):
if audio_buffer and time.monotonic() - audio_buffer_start >= MAX_UTTERANCE_DURATION:
    # Safety flush — user has been speaking for 30s straight
    combined = audio_header + b"".join(audio_buffer)
    await _handle_audio(bus, session_id, audio_buffer_meta, combined, chunk_id)
    audio_buffer.clear()
    audio_buffer_start = time.monotonic()
```

### Result

- One `AudioChunkReceivedEvent` per utterance (instead of per 2s chunk)
- TranscriptionAgent transcribes the full utterance → better Whisper accuracy
- One transcription message per utterance in the chat → clean UX
- 30s safety cap prevents edge cases

## Files Modified

| File | Change |
|------|--------|
| `web/src/hooks/useMediaCapture.ts` | Add RMS monitoring, speech state machine, `onEndOfUtterance` callback |
| `web/src/hooks/useMediaWebSocket.ts` | Add `sendEndOfUtterance()` method + update `UseMediaWebSocketReturn` interface |
| `web/src/components/Chat.tsx` | Wire `onEndOfUtterance` to `mediaWs.sendEndOfUtterance()` |
| `ada/api/routes/media.py` | Replace timer flush with `end_of_utterance` signal + 30s safety fallback |

## Verification

1. `uv run python -m pytest tests/ -q` — all tests pass
2. Start Ada, enable mic, speak a sentence, pause — one clean transcription appears after pause
3. Stay silent — no phantom transcriptions
4. Speak for >30s continuously — safety flush triggers, transcription appears at 30s mark
