"""Tests for multimodal configuration."""

from __future__ import annotations

from ada.core.config import AdaConfig, MultimodalConfig


class TestMultimodalConfig:
    def test_default_disabled(self):
        config = AdaConfig()
        assert config.multimodal.enabled is False

    def test_sensor_simulator_defaults(self):
        config = AdaConfig()
        assert config.multimodal.sensor_simulator_preset == "relaxed"
        assert config.multimodal.sensor_simulator_interval == 1.0

    def test_media_ws_enabled_when_multimodal_enabled(self):
        config = AdaConfig(multimodal=MultimodalConfig(enabled=True))
        assert config.multimodal.enabled is True
