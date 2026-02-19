"""
Unit tests for ada.core.bus.EventBus.

Covers:
- Subscribe and receive events
- Multiple subscribers for the same event type
- Publish with no subscribers (no crash)
- Bus start/stop lifecycle
- Queue overflow / backpressure handling

@decision DEC-TEST-001
@title Unit tests use real EventBus with asyncio.sleep drain instead of mocks
@status accepted
@rationale The EventBus is a pure asyncio component with no external I/O.
    Testing it with a real instance and timed sleeps (0.1–0.3s) gives
    faithful coverage of the queue-drain loop. Mocking asyncio internals
    would couple tests to implementation details and reduce confidence.
"""

from __future__ import annotations

import asyncio

import pytest

from ada.core.bus import EventBus
from ada.core.events import AdaEvent, EventTypes, MessageReceivedEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_type: str = EventTypes.MESSAGE_RECEIVED) -> AdaEvent:
    """Create a minimal event for testing."""
    if event_type == EventTypes.MESSAGE_RECEIVED:
        return MessageReceivedEvent(
            session_id="sess-1",
            patient_id="pat-1",
            content="hello",
            message_id="msg-1",
        )
    return AdaEvent(event_type=event_type)


# ---------------------------------------------------------------------------
# Subscribe and receive
# ---------------------------------------------------------------------------

async def test_subscribe_and_receive_event():
    """A subscribed handler receives a published event."""
    bus = EventBus()
    received: list[AdaEvent] = []

    async def handler(event: AdaEvent) -> None:
        received.append(event)

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, handler, "test-handler")
    await bus.start()

    event = _make_event(EventTypes.MESSAGE_RECEIVED)
    await bus.publish(event)

    # Allow the processing loop to drain the queue
    await asyncio.sleep(0.2)

    await bus.stop()
    assert len(received) == 1
    assert received[0] is event


async def test_multiple_subscribers_all_receive():
    """Two subscribers on the same event type both receive the event."""
    bus = EventBus()
    received_a: list[AdaEvent] = []
    received_b: list[AdaEvent] = []

    async def handler_a(event: AdaEvent) -> None:
        received_a.append(event)

    async def handler_b(event: AdaEvent) -> None:
        received_b.append(event)

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, handler_a, "handler-a")
    bus.subscribe(EventTypes.MESSAGE_RECEIVED, handler_b, "handler-b")
    await bus.start()

    event = _make_event(EventTypes.MESSAGE_RECEIVED)
    await bus.publish(event)
    await asyncio.sleep(0.2)

    await bus.stop()
    assert len(received_a) == 1
    assert len(received_b) == 1


async def test_multiple_events_received_in_order():
    """Multiple published events arrive to the handler in FIFO order."""
    bus = EventBus()
    received: list[str] = []

    async def handler(event: AdaEvent) -> None:
        assert isinstance(event, MessageReceivedEvent)
        received.append(event.content)

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, handler, "ordered-handler")
    await bus.start()

    for i in range(5):
        evt = MessageReceivedEvent(
            session_id="s", patient_id="p", content=str(i), message_id=str(i)
        )
        await bus.publish(evt)

    await asyncio.sleep(0.3)
    await bus.stop()

    assert received == ["0", "1", "2", "3", "4"]


# ---------------------------------------------------------------------------
# No subscribers — must not crash
# ---------------------------------------------------------------------------

async def test_publish_with_no_subscribers():
    """Publishing to an event type with no subscribers must not raise."""
    bus = EventBus()
    await bus.start()
    event = _make_event(EventTypes.MESSAGE_RECEIVED)
    # Should complete without raising
    await bus.publish(event)
    await bus.stop()


async def test_publish_before_start_does_not_crash():
    """Publishing before start() (no processing tasks) must not raise."""
    bus = EventBus()
    event = _make_event(EventTypes.MESSAGE_RECEIVED)
    await bus.publish(event)  # no crash expected


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def test_start_sets_running():
    """Bus is not running before start(), running after start()."""
    bus = EventBus()
    assert not bus.is_running
    await bus.start()
    assert bus.is_running
    await bus.stop()
    assert not bus.is_running


async def test_double_start_is_idempotent():
    """Calling start() twice should not raise or create duplicate tasks."""
    bus = EventBus()
    await bus.start()
    await bus.start()  # second call should be a no-op
    assert bus.is_running
    await bus.stop()


async def test_stop_before_start_is_safe():
    """Calling stop() before start() must not raise."""
    bus = EventBus()
    await bus.stop()  # no crash expected


async def test_subscribe_after_start_receives_events():
    """Subscribing after start() should work — the bus starts a task immediately."""
    bus = EventBus()
    await bus.start()

    received: list[AdaEvent] = []

    async def handler(event: AdaEvent) -> None:
        received.append(event)

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, handler, "late-subscriber")
    event = _make_event(EventTypes.MESSAGE_RECEIVED)
    await bus.publish(event)
    await asyncio.sleep(0.2)
    await bus.stop()

    assert len(received) == 1


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------

async def test_subscriber_count():
    """subscriber_count() returns accurate counts."""
    bus = EventBus()
    assert bus.subscriber_count(EventTypes.MESSAGE_RECEIVED) == 0

    async def noop(event: AdaEvent) -> None:
        pass

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, noop, "sub-1")
    assert bus.subscriber_count(EventTypes.MESSAGE_RECEIVED) == 1

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, noop, "sub-2")
    assert bus.subscriber_count(EventTypes.MESSAGE_RECEIVED) == 2


async def test_unsubscribe_removes_subscriber():
    """unsubscribe() removes the named subscriber."""
    bus = EventBus()
    received: list[AdaEvent] = []

    async def handler(event: AdaEvent) -> None:
        received.append(event)

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, handler, "removable")
    await bus.start()

    bus.unsubscribe(EventTypes.MESSAGE_RECEIVED, "removable")
    assert bus.subscriber_count(EventTypes.MESSAGE_RECEIVED) == 0

    await bus.publish(_make_event())
    await asyncio.sleep(0.2)
    await bus.stop()

    assert received == []


# ---------------------------------------------------------------------------
# Queue overflow
# ---------------------------------------------------------------------------

async def test_queue_overflow_drops_events_without_crash():
    """
    When a subscriber's queue is full, excess events are dropped with a warning
    but the bus does not raise.

    We use queue_size=1 and a slow handler to force overflow.
    """
    bus = EventBus(queue_size=1)
    processed: list[AdaEvent] = []

    async def slow_handler(event: AdaEvent) -> None:
        await asyncio.sleep(0.5)  # deliberately slow
        processed.append(event)

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, slow_handler, "slow-sub")
    await bus.start()

    # Publish 5 events rapidly — most should be dropped (queue_size=1)
    for i in range(5):
        await bus.publish(
            MessageReceivedEvent(
                session_id="s", patient_id="p", content=str(i), message_id=str(i)
            )
        )

    # Give the first event time to be processed (slow: 0.5s)
    await asyncio.sleep(0.7)
    await bus.stop()

    # At most 2 events can be processed (1 in flight + 1 in queue)
    assert len(processed) <= 2


async def test_failing_handler_does_not_crash_bus():
    """
    A handler that raises an exception must not crash the bus or
    prevent other events from being processed.
    """
    bus = EventBus()
    processed: list[AdaEvent] = []

    async def bad_handler(event: AdaEvent) -> None:
        raise RuntimeError("intentional failure")

    async def good_handler(event: AdaEvent) -> None:
        processed.append(event)

    bus.subscribe(EventTypes.MESSAGE_RECEIVED, bad_handler, "bad-sub")
    bus.subscribe(EventTypes.MESSAGE_RECEIVED, good_handler, "good-sub")
    await bus.start()

    event = _make_event()
    await bus.publish(event)
    await asyncio.sleep(0.2)
    await bus.stop()

    # good_handler still received the event despite bad_handler failing
    assert len(processed) == 1
