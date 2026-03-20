/**
 * MediaControls — mic toggle, camera toggle, and simulator preset selector.
 *
 * Placed in the chat header right-aligned. Each button shows active state
 * when the respective modality is running. The simulator dropdown is only
 * shown when neither audio nor video is the primary concern — it's a
 * dev/demo tool for testing without real hardware.
 *
 * @decision DEC-FRONTEND-017
 * @title MediaControls exposes simulator as a named preset dropdown
 * @status accepted
 * @rationale The simulator is a development/demo tool. Exposing it as a
 *   dropdown (relaxed / anxious / panic_attack) makes preset selection
 *   explicit and avoids a hidden default. The "Stop" action reuses the
 *   same button area to keep the control surface small. In production the
 *   simulator section would be hidden or removed.
 */

import type { SimulatorPreset } from '../hooks/useSensorSimulator'

interface MediaControlsProps {
  audioEnabled: boolean
  videoEnabled: boolean
  simulatorRunning: boolean
  onToggleAudio: () => void
  onToggleVideo: () => void
  onStartSimulator: (preset: SimulatorPreset) => void
  onStopSimulator: () => void
  mediaError: string | null
  simulatorError: string | null
  voiceEnabled?: boolean
  isSpeaking?: boolean
  onToggleVoice?: () => void
}

const PRESETS: { value: SimulatorPreset; label: string }[] = [
  { value: 'relaxed', label: 'Relaxed' },
  { value: 'anxious', label: 'Anxious' },
  { value: 'panic_attack', label: 'Panic' },
]

export function MediaControls({
  audioEnabled,
  videoEnabled,
  simulatorRunning,
  onToggleAudio,
  onToggleVideo,
  onStartSimulator,
  onStopSimulator,
  mediaError,
  simulatorError,
  voiceEnabled,
  isSpeaking,
  onToggleVoice,
}: MediaControlsProps) {
  function handlePresetChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const preset = e.target.value as SimulatorPreset
    if (preset) onStartSimulator(preset)
    // Reset select to placeholder after firing
    e.target.value = ''
  }

  return (
    <div className="media-controls" role="toolbar" aria-label="Media controls">
      {/* Microphone toggle */}
      <button
        className={`media-controls__btn ${audioEnabled ? 'media-controls__btn--active' : ''}`}
        onClick={onToggleAudio}
        title={audioEnabled ? 'Stop microphone' : 'Start microphone'}
        aria-pressed={audioEnabled}
        type="button"
      >
        {audioEnabled ? 'Mic ON' : 'Mic'}
      </button>

      {/* Camera toggle */}
      <button
        className={`media-controls__btn ${videoEnabled ? 'media-controls__btn--active' : ''}`}
        onClick={onToggleVideo}
        title={videoEnabled ? 'Stop camera' : 'Start camera'}
        aria-pressed={videoEnabled}
        type="button"
      >
        {videoEnabled ? 'Cam ON' : 'Cam'}
      </button>

      {/* Simulator controls */}
      {simulatorRunning ? (
        <button
          className="media-controls__btn media-controls__btn--active"
          onClick={onStopSimulator}
          title="Stop sensor simulator"
          type="button"
        >
          Sim ON
        </button>
      ) : (
        <select
          className="media-controls__select"
          defaultValue=""
          onChange={handlePresetChange}
          aria-label="Start sensor simulator with preset"
          title="Start sensor simulator"
        >
          <option value="" disabled>Sim</option>
          {PRESETS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
        </select>
      )}

      {/* Voice mode toggle */}
      {onToggleVoice && (
        <button
          className={`media-controls__btn ${voiceEnabled ? 'media-controls__btn--active' : ''}`}
          onClick={onToggleVoice}
          title={voiceEnabled ? 'Disable voice mode' : 'Enable voice mode'}
          aria-pressed={voiceEnabled}
          type="button"
        >
          {voiceEnabled ? (isSpeaking ? 'Speaking\u2026' : 'Voice ON') : 'Voice'}
        </button>
      )}

      {/* Error display */}
      {(mediaError || simulatorError) && (
        <span className="media-controls__error" role="alert">
          {mediaError || simulatorError}
        </span>
      )}
    </div>
  )
}
