"""
EventBus: bridges the synchronous simulation engine (running in a thread)
to async WebSocket handlers.

Each WebSocket connection subscribes to get its own asyncio.Queue.
The engine thread calls emit_sync(), which safely puts events into all
queues using call_soon_threadsafe().
"""

import asyncio
from typing import Optional


class EventBus:
    def __init__(self):
        self._queues: list[asyncio.Queue] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the event loop. Must be called from the async context."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        """Create and return a new subscriber queue for one WebSocket client."""
        q: asyncio.Queue = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue when a client disconnects."""
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    def emit_sync(self, event: dict) -> None:
        """
        Emit an event from a synchronous context (the engine thread).
        Safely schedules the put on the event loop.
        """
        if self._loop is None or not self._queues:
            return
        for q in list(self._queues):
            self._loop.call_soon_threadsafe(q.put_nowait, event)
