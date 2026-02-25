"""
Tests for Phase 4b input event types: AudioChunkReceivedEvent, VideoFrameReceivedEvent.

@decision DEC-ML-004
@title Input events carry raw bytes for agent processing
@status accepted
@rationale Agents need the raw media bytes for feature extraction. Passing bytes
    through events keeps the data flow through EventBus consistent with the
    existing pattern. For large payloads in production, a reference-based
    approach (store bytes, pass ID) would be a future optimization.
"""

from __future__ import annotations

import asyncio

import pytest

from ada.core.bus import EventBus
from ada.core.events import (
    AudioChunkReceivedEvent,
    EventTypes,
    VideoFrameReceivedEvent,
)


class TestAudioChunkReceivedEvent:
    def test_default_values(self):
        evt = AudioChunkReceivedEvent()
        assert evt.event_type == EventTypes.AUDIO_CHUNK_RECEIVED
        assert evt.audio_bytes == b""
        assert evt.codec == "webm/opus"
        assert evt.sample_rate == 48000
        assert evt.chunk_id == ""

    def test_with_data(self):
        data = b"\x00\x01\x02\x03" * 100
        evt = AudioChunkReceivedEvent(
            session_id="s1",
            patient_id="p1",
            audio_bytes=data,
            codec="wav",
            sample_rate=16000,
            chunk_id="chunk-001",
        )
        assert evt.session_id == "s1"
        assert evt.patient_id == "p1"
        assert evt.audio_bytes == data
        assert evt.codec == "wav"
        assert evt.sample_rate == 16000
        assert evt.chunk_id == "chunk-001"

    @pytest.mark.asyncio
    async def test_event_bus_roundtrip(self):
        bus = EventBus()
        await bus.start()
        received = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.AUDIO_CHUNK_RECEIVED, collector, "test")

        await bus.publish(AudioChunkReceivedEvent(
            session_id="s1",
            patient_id="p1",
            audio_bytes=b"hello",
            chunk_id="c1",
        ))
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].audio_bytes == b"hello"
        assert received[0].chunk_id == "c1"
        await bus.stop()


class TestVideoFrameReceivedEvent:
    def test_default_values(self):
        evt = VideoFrameReceivedEvent()
        assert evt.event_type == EventTypes.VIDEO_FRAME_RECEIVED
        assert evt.frame_bytes == b""
        assert evt.format == "jpeg"
        assert evt.resolution == ""
        assert evt.frame_id == ""

    def test_with_data(self):
        data = b"\xff\xd8\xff" + b"\x00" * 100  # JPEG-like header
        evt = VideoFrameReceivedEvent(
            session_id="s1",
            patient_id="p1",
            frame_bytes=data,
            format="jpeg",
            resolution="640x480",
            frame_id="frame-001",
        )
        assert evt.frame_bytes == data
        assert evt.resolution == "640x480"
        assert evt.frame_id == "frame-001"

    @pytest.mark.asyncio
    async def test_event_bus_roundtrip(self):
        bus = EventBus()
        await bus.start()
        received = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.VIDEO_FRAME_RECEIVED, collector, "test")

        await bus.publish(VideoFrameReceivedEvent(
            session_id="s1",
            patient_id="p1",
            frame_bytes=b"frame-data",
            frame_id="f1",
        ))
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].frame_bytes == b"frame-data"
        await bus.stop()
