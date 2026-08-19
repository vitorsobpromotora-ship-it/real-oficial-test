"""Stream SSE de eventos (progresso de jobs/renders) com replay via Last-Event-ID."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from .deps import require_token_query

router = APIRouter()


@router.get("/events", dependencies=[Depends(require_token_query)])
async def events(request: Request,
                 last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
                 last_event_id: int | None = Query(default=None),
                 max_events: int | None = Query(default=None, ge=1)):
    """SSE. `max_events` encerra o stream após N eventos (debug/testes)."""
    bus = request.app.state.bus
    last_id = last_event_id
    if last_id is None and last_event_id_header and last_event_id_header.isdigit():
        last_id = int(last_event_id_header)
    sid, queue = bus.subscribe(last_id)

    async def gen():
        enviados = 0
        try:
            yield ": conectado\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except (asyncio.TimeoutError, TimeoutError):
                    yield ": ping\n\n"
                    continue
                data = json.dumps(item["data"], ensure_ascii=False)
                yield f"id: {item['id']}\nevent: {item['event']}\ndata: {data}\n\n"
                enviados += 1
                if max_events is not None and enviados >= max_events:
                    return
        finally:
            bus.unsubscribe(sid)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
