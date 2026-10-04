"""
Async Event Bus implementation for Loose Coupling architecture.
Supports both dict payload and kwargs for backward compatibility.
"""
import asyncio
import logging
from typing import Callable, Dict, List, Any, Awaitable, Optional

logger = logging.getLogger("runtimeforce.core.events.event_bus")


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[..., Awaitable[None]]]] = {}

    def subscribe(self, event_name: str, handler: Callable[..., Awaitable[None]]):
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        if handler not in self._subscribers[event_name]:
            self._subscribers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Callable[..., Awaitable[None]]):
        if event_name in self._subscribers and handler in self._subscribers[event_name]:
            self._subscribers[event_name].remove(handler)

    async def publish(
        self,
        event_name: str,
        payload: Optional[Any] = None,
        **kwargs: Any
    ):
        """
        Publish event with flexible payload signature.
        Supports:
            - publish("event", {"key": "value"})          # dict positional
            - publish("event", key="value")               # kwargs
            - publish("event", {"a": 1}, b=2)             # mixed (kwargs override)
        """
        handlers = self._subscribers.get(event_name, [])
        if not handlers:
            return

        # Merge payload dict and kwargs into single flat dict for handlers
        merged_payload: Dict[str, Any] = {}
        if isinstance(payload, dict):
            merged_payload.update(payload)
        elif payload is not None:
            # Fallback: wrap non-dict payload under "data" key
            merged_payload["data"] = payload
        merged_payload.update(kwargs)

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(**merged_payload)
                else:
                    handler(**merged_payload)
            except Exception as e:
                logger.error(f"Error handling event '{event_name}': {e}")