"""
Tiny WebSocket fan-out for the seller dashboard.

The dashboard opens `/ws/sessions` and receives a JSON message every time a
session is created, priced, or completed - so the live session table updates
without polling.

Message shape:
    {"type": "session.created" | "session.priced" | "session.completed"
             | "session.abandoned" | "hello",
     "session": { ...session row... },
     "ts": "<iso8601>"}
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from .logging_util import log


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log(f"ws client connected ({len(self._clients)} total)")

    async def disconnect(self, ws) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log(f"ws client disconnected ({len(self._clients)} total)")

    async def broadcast(self, kind: str, session: dict | None = None) -> None:
        msg = json.dumps({
            "type": kind,
            "session": session,
            "ts": datetime.now(timezone.utc).isoformat(),
        }, default=str)
        async with self._lock:
            targets = list(self._clients)
        dead = []
        for ws in targets:
            try:
                await ws.send_text(msg)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    @property
    def count(self) -> int:
        return len(self._clients)


manager = ConnectionManager()
