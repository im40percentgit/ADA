"""
EventBus — async publish/subscribe message bus for Ada agents.

Adapted from the CerebrumCoin EventBus pattern. Key differences:
- String-based event types (not an enum) for loose coupling between agents
- Per-subscriber async queues with configurable backpressure
- Graceful error isolation: a failing handler logs and continues

@decision DEC-CORE-001
@title String-based event types over enum
@status accepted
@rationale See ada/core/events.py for full rationale.

@decision DEC-CORE-002
@title Per-subscriber queues with asyncio.Queue
@status accepted
@rationale Isolates slow subscribers from fast publishers. A slow crisis monitor
    does not block the therapist from processing the next user message. Queue
    size of 1000 is generous for a single-patient session; can be tuned via config.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

from ada.core.events import AdaEvent

logger = logging.getLogger(__name__)

# Handler type: any async callable that accepts an AdaEvent
Handler = Callable[[AdaEvent], Coroutine[Any, Any, None]]


class EventBus:
    """
    Async publish/subscribe event bus.

    Usage::

        bus = EventBus()
        await bus.start()

        async def on_message(event: AdaEvent) -> None:
            print(event)

        bus.subscribe("message.received", on_message, "my-handler")
        await bus.publish(MessageReceivedEvent(...))
        await bus.stop()
    """

    def __init__(self, queue_size: int = 1000) -> None:
        # {event_type: [(subscriber_name, queue)]}
        self._subscribers: dict[str, list[tuple[str, asyncio.Queue]]] = defaultdict(list)
        # {subscriber_name: handler}
        self._handlers: dict[str, Handler] = {}
        self._queue_size = queue_size
        self._running = False
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        handler: Handler,
        subscriber_name: str,
    ) -> None:
        """
        Register a handler for a given event type.

        Multiple handlers may subscribe to the same event type. Each gets
        its own queue so they run concurrently without blocking each other.

        Args:
            event_type: String event type constant (e.g. EventTypes.MESSAGE_RECEIVED).
            handler: Async callable receiving an AdaEvent.
            subscriber_name: Unique name for this subscription (used in logs).
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers[event_type].append((subscriber_name, queue))
        self._handlers[subscriber_name] = handler
        logger.debug("EventBus: %s subscribed to %s", subscriber_name, event_type)

        # If already running, start processing task for this new subscriber
        if self._running:
            task = asyncio.create_task(
                self._process_queue(subscriber_name, handler, queue),
                name=f"bus-{subscriber_name}",
            )
            self._tasks.append(task)

    def unsubscribe(self, event_type: str, subscriber_name: str) -> None:
        """Remove a subscriber from an event type."""
        self._subscribers[event_type] = [
            (name, q) for name, q in self._subscribers[event_type]
            if name != subscriber_name
        ]
        self._handlers.pop(subscriber_name, None)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: AdaEvent) -> None:
        """
        Publish an event to all subscribers of its event_type.

        Non-blocking: places the event in each subscriber's queue.
        If a queue is full, the event is dropped with a warning.
        """
        subscribers = self._subscribers.get(event.event_type, [])
        if not subscribers:
            logger.debug("EventBus: no subscribers for %s", event.event_type)
            return

        for name, queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "EventBus: queue full for subscriber %s (event %s dropped)",
                    name,
                    event.event_type,
                )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start processing tasks for all registered subscribers."""
        if self._running:
            return
        self._running = True
        logger.info("EventBus: starting")

        for event_type, subs in self._subscribers.items():
            for name, queue in subs:
                handler = self._handlers.get(name)
                if handler is None:
                    continue
                task = asyncio.create_task(
                    self._process_queue(name, handler, queue),
                    name=f"bus-{name}",
                )
                self._tasks.append(task)

    async def stop(self) -> None:
        """Stop all processing tasks gracefully."""
        if not self._running:
            return
        self._running = False
        logger.info("EventBus: stopping")

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _process_queue(
        self,
        name: str,
        handler: Handler,
        queue: asyncio.Queue,
    ) -> None:
        """Continuously drain a subscriber's queue, calling the handler for each event."""
        while self._running:
            try:
                # Wait up to 0.1s so we can check _running periodically
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await handler(event)
            except Exception:
                logger.exception("EventBus: handler %s raised an exception", name)
            finally:
                queue.task_done()

    # ------------------------------------------------------------------
    # Introspection (useful for tests)
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    def subscriber_count(self, event_type: str) -> int:
        return len(self._subscribers.get(event_type, []))
