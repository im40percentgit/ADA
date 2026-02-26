/**
 * FacePreview — floating video thumbnail showing the patient's camera feed.
 *
 * Renders a small fixed-position video element in the bottom-right corner
 * of the chat area when video is enabled. Accepts a RefObject<HTMLVideoElement>
 * from useMediaCapture (the same element used for canvas snapshots) so there
 * is only one MediaStream consumer.
 *
 * Hidden (renders null) when videoEnabled is false.
 */

import { RefObject } from 'react'

interface FacePreviewProps {
  videoRef: RefObject<HTMLVideoElement>
  videoEnabled: boolean
}

export function FacePreview({ videoRef, videoEnabled }: FacePreviewProps) {
  if (!videoEnabled) return null

  return (
    <div className="face-preview" aria-label="Camera preview">
      <video
        ref={videoRef}
        className="face-preview__video"
        autoPlay
        muted
        playsInline
        aria-hidden="true"
      />
      <span className="face-preview__label">CAM</span>
    </div>
  )
}
