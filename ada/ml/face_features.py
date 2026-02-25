"""
Face feature extraction using OpenCV.

Detects faces using OpenCV's Haar cascade face detector, then estimates
Facial Action Coding System (FACS) action units from landmark
geometry ratios. In this initial implementation, action units are
estimated via heuristic geometry since full landmark detection
requires dlib or mediapipe (deferred).

@decision DEC-ML-007
@title OpenCV Haar cascade + geometric AU estimation
@status accepted
@rationale OpenCV's Haar cascade provides a built-in, CPU-only face detector
    that ships with opencv-python-headless. Full facial landmark detection
    (68-point) would require dlib or mediapipe as additional deps. For Phase
    4b, we use the face bounding box geometry to produce basic AU estimates.
    The AU interface is stable -- swap in real landmark-based AU coding later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Pre-built face detection model shipped with OpenCV
_FACE_CASCADE: cv2.CascadeClassifier | None = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    """Lazy-load the Haar cascade face detector."""
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _FACE_CASCADE = cv2.CascadeClassifier(cascade_path)
    return _FACE_CASCADE


@dataclass
class FaceFeatures:
    """Extracted facial features for emotion classification."""

    face_detected: bool = False
    detection_confidence: float = 0.0
    # Action unit estimates (0.0-1.0)
    action_units: dict[str, float] = field(default_factory=dict)
    # Face bounding box (x, y, w, h) as fractions of image dimensions
    face_bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    valid: bool = True
    error: str = ""


def extract_features(frame_bytes: bytes) -> FaceFeatures:
    """
    Extract facial features from a JPEG/PNG frame.

    Args:
        frame_bytes: Raw image data (JPEG, PNG, etc.).

    Returns:
        FaceFeatures with detection results and action unit estimates.
    """
    if not frame_bytes:
        return FaceFeatures(valid=False, error="Empty frame data")

    try:
        # Decode image
        nparr = np.frombuffer(frame_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return FaceFeatures(valid=False, error="Failed to decode image")

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Detect faces
        cascade = _get_face_cascade()
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30),
        )

        if len(faces) == 0:
            return FaceFeatures(
                face_detected=False,
                detection_confidence=0.0,
                valid=True,
            )

        # Use the largest detected face
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        face_area_ratio = (fw * fh) / (w * h)

        # Normalize bbox to image dimensions
        bbox = (x / w, y / h, fw / w, fh / h)

        # Heuristic action unit estimation from face geometry
        # These are placeholder estimates based on face aspect ratio and position.
        # Real AU coding requires facial landmark detection (deferred).
        aspect_ratio = fw / fh if fh > 0 else 1.0
        vertical_position = y / h  # Higher face = more likely raised brows

        action_units = _estimate_action_units(
            aspect_ratio=aspect_ratio,
            vertical_position=vertical_position,
            face_area_ratio=face_area_ratio,
        )

        # Confidence based on face area (larger face = higher confidence)
        detection_confidence = min(1.0, face_area_ratio * 10)

        return FaceFeatures(
            face_detected=True,
            detection_confidence=round(detection_confidence, 3),
            action_units=action_units,
            face_bbox=tuple(round(v, 4) for v in bbox),
            valid=True,
        )

    except Exception as exc:
        logger.warning("Face feature extraction failed: %s", exc)
        return FaceFeatures(valid=False, error=str(exc))


def _estimate_action_units(
    *,
    aspect_ratio: float,
    vertical_position: float,
    face_area_ratio: float,
) -> dict[str, float]:
    """
    Heuristic action unit estimation.

    These are geometric approximations -- not clinical-grade AU coding.
    The interface is designed for the LLM classification prompt and will
    be replaced with real landmark-based detection in a future phase.
    """
    # Baseline neutral values
    aus = {
        "AU1": 0.0,   # Inner brow raise
        "AU2": 0.0,   # Outer brow raise
        "AU4": 0.0,   # Brow lowerer
        "AU5": 0.0,   # Upper lid raise
        "AU6": 0.0,   # Cheek raise
        "AU12": 0.0,  # Lip corner pull (smile)
        "AU15": 0.0,  # Lip corner depress (frown)
    }

    # Wider face = possible smile (AU6, AU12)
    if aspect_ratio > 1.05:
        aus["AU6"] = min(1.0, (aspect_ratio - 1.0) * 2)
        aus["AU12"] = min(1.0, (aspect_ratio - 1.0) * 2)

    # Taller face = possible brow furrow (AU4)
    if aspect_ratio < 0.95:
        aus["AU4"] = min(1.0, (1.0 - aspect_ratio) * 2)
        aus["AU15"] = min(1.0, (1.0 - aspect_ratio))

    # Higher vertical position = possible brow raise
    if vertical_position < 0.3:
        aus["AU1"] = min(1.0, (0.3 - vertical_position) * 2)
        aus["AU2"] = min(1.0, (0.3 - vertical_position) * 1.5)
        aus["AU5"] = min(1.0, (0.3 - vertical_position) * 1.5)

    # Round all values
    return {k: round(v, 3) for k, v in aus.items()}


def features_to_prompt_summary(features: FaceFeatures) -> str:
    """Format FaceFeatures for inclusion in an LLM classification prompt."""
    if not features.valid:
        return f"Face feature extraction failed: {features.error}"
    if not features.face_detected:
        return "No face detected in frame"

    au_parts = [f"{k} ({_au_name(k)}): {v}" for k, v in features.action_units.items()]
    au_str = ", ".join(au_parts)

    return (
        f"Face detected: confidence={features.detection_confidence}, "
        f"Action units: {au_str}"
    )


_AU_NAMES = {
    "AU1": "inner brow raise", "AU2": "outer brow raise",
    "AU4": "brow lowerer", "AU5": "upper lid raise",
    "AU6": "cheek raise", "AU12": "lip corner pull",
    "AU15": "lip corner depress",
}


def _au_name(au: str) -> str:
    return _AU_NAMES.get(au, au)
