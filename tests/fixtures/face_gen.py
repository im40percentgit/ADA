"""
Generate synthetic face images for testing.

@decision DEC-ML-008
@title Synthetic face fixtures via OpenCV drawing
@status accepted
@rationale Generating test faces programmatically avoids external file
    dependencies and ensures reproducibility. Haar cascade may not detect
    all synthetic faces reliably, so tests account for detection variability
    by testing both detection and no-detection paths.
"""

from __future__ import annotations

import cv2
import numpy as np


def generate_face_image(
    *,
    width: int = 200,
    height: int = 200,
) -> bytes:
    """
    Generate a synthetic image with an oval face shape that OpenCV's Haar
    cascade can detect.

    Creates a grayscale image with an elliptical shape plus basic facial
    features (two dark circles for eyes, a line for mouth) positioned
    to trigger the Haar cascade face detector.

    Returns:
        JPEG-encoded image as bytes.
    """
    img = np.ones((height, width, 3), dtype=np.uint8) * 200  # Light gray background

    cx, cy = width // 2, height // 2

    # Face oval (skin-toned)
    cv2.ellipse(img, (cx, cy), (60, 80), 0, 0, 360, (180, 160, 140), -1)

    # Eyes (dark circles)
    eye_y = cy - 15
    cv2.circle(img, (cx - 20, eye_y), 8, (40, 40, 40), -1)
    cv2.circle(img, (cx + 20, eye_y), 8, (40, 40, 40), -1)

    # Mouth (dark line)
    mouth_y = cy + 25
    cv2.line(img, (cx - 15, mouth_y), (cx + 15, mouth_y), (60, 60, 60), 2)

    # Encode as JPEG
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def generate_blank_image(
    *,
    width: int = 200,
    height: int = 200,
) -> bytes:
    """Generate a blank white image (no face)."""
    img = np.ones((height, width, 3), dtype=np.uint8) * 255
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()
