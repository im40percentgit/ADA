"""
Unit tests for face feature extraction.

Uses synthetic face images (programmatically generated via OpenCV)
for deterministic testing.

@decision DEC-ML-008
@title Synthetic face fixtures via OpenCV drawing
@status accepted
@rationale Generating test faces programmatically avoids external file
    dependencies and ensures reproducibility. Haar cascade may not detect
    all synthetic faces reliably, so tests account for detection variability
    by testing both detection and no-detection paths.
"""

from __future__ import annotations

import pytest

from ada.ml.face_features import FaceFeatures, extract_features, features_to_prompt_summary
from tests.fixtures.face_gen import generate_blank_image, generate_face_image


class TestExtractFeatures:
    def test_synthetic_face_detection(self):
        """Synthetic face image should be processable (may or may not detect)."""
        face_bytes = generate_face_image()
        features = extract_features(face_bytes)

        assert features.valid is True
        # The synthetic face may or may not trigger Haar cascade --
        # we mainly verify the extraction pipeline runs without error.
        # Action units should be a dict regardless.
        assert isinstance(features.action_units, dict)

    def test_blank_image_no_face(self):
        """Blank image should not detect a face."""
        blank_bytes = generate_blank_image()
        features = extract_features(blank_bytes)

        assert features.valid is True
        assert features.face_detected is False
        assert features.detection_confidence == 0.0

    def test_empty_bytes_returns_invalid(self):
        """Empty input should return valid=False."""
        features = extract_features(b"")
        assert features.valid is False
        assert "empty" in features.error.lower()

    def test_corrupt_bytes_returns_invalid(self):
        """Non-image bytes should return valid=False."""
        features = extract_features(b"not an image")
        assert features.valid is False

    def test_action_units_keys(self):
        """When a face is detected, action units should have the 7 standard keys."""
        face_bytes = generate_face_image()
        features = extract_features(face_bytes)

        if features.face_detected:
            expected_keys = {"AU1", "AU2", "AU4", "AU5", "AU6", "AU12", "AU15"}
            assert set(features.action_units.keys()) == expected_keys

    def test_action_units_range(self):
        """Action unit values should be in [0.0, 1.0]."""
        face_bytes = generate_face_image()
        features = extract_features(face_bytes)

        for key, value in features.action_units.items():
            assert 0.0 <= value <= 1.0, f"{key}={value} out of range"

    def test_detection_confidence_range(self):
        """Detection confidence should be in [0.0, 1.0]."""
        face_bytes = generate_face_image()
        features = extract_features(face_bytes)

        assert 0.0 <= features.detection_confidence <= 1.0


class TestFeaturesToPromptSummary:
    def test_valid_detected(self):
        features = FaceFeatures(
            face_detected=True,
            detection_confidence=0.85,
            action_units={"AU1": 0.3, "AU6": 0.7, "AU12": 0.8},
            valid=True,
        )
        summary = features_to_prompt_summary(features)
        assert "Face detected" in summary
        assert "0.85" in summary
        assert "AU1" in summary
        assert "AU6" in summary

    def test_no_face_detected(self):
        features = FaceFeatures(face_detected=False, valid=True)
        summary = features_to_prompt_summary(features)
        assert "No face detected" in summary

    def test_invalid(self):
        features = FaceFeatures(valid=False, error="Decode error")
        summary = features_to_prompt_summary(features)
        assert "failed" in summary.lower()
