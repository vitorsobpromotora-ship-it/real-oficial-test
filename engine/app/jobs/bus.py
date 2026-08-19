"""EventBus para SSE: fan-out em memória com ring buffer para replay (Last-Event-ID).

`publish()` é thread-safe: pode ser chamado de workers em thread (asyncio.to_thread)
ou do próprio event loop; a entrega às filas dos assinantes sempre acontece no loop.
"""

from __future__ import annotations

import asyncio
import itertools
import threading
from collections import deque


class EventBus:
    def __init__(self, history: int = 500):
        self._subs: dict[int, asyncio.Queue] = {}
        self._sub_ids = itertools.count(1)
        self._next_event_id = 1
        self._history: deque = deque(maxlen=history)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event: str, data: dict) -> None:
        with self._lock:
            eid = self._next_event_id
            self._next_event_id += 1
            item = {"id": eid, "event": event, "data": data}
            self._history.append(item)
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._fanout, item)

    def _fanout(self, item: dict) -> None:
        for q in list(self._subs.values()):
            if q.qsize() < 1000:  # descarta se o assinante estiver travado
                q.put_nowait(item)

    def subscribe(self, last_event_id: int | None = None) -> tuple[int, asyncio.Queue]:
        q: asyncio.Queue = asyncio.Queue()
        sid = next(self._sub_ids)
        with self._lock:
            self._subs[sid] = q
            replay = [e for e in self._history if last_event_id is not None and e["id"] > last_event_id]
        for e in replay:
            q.put_nowait(e)
        return sid, q

    def unsubscribe(self, sid: int) -> None:
        self._subs.pop(sid, None)
