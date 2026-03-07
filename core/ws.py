import asyncio
import json
from collections import defaultdict
from fastapi import WebSocket


class ConnectionManager:
    """Manages per-run WebSocket connections and broadcasts state updates."""

    def __init__(self):
        # run_id -> set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[run_id].add(ws)

    def disconnect(self, run_id: str, ws: WebSocket) -> None:
        self._connections[run_id].discard(ws)

    async def broadcast(self, run_id: str, event: dict) -> None:
        """Send a JSON event to every client watching this run."""
        dead = set()
        for ws in self._connections.get(run_id, set()):
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections[run_id].discard(ws)

    async def broadcast_log(self, run_id: str, agent: str, message: str, level: str = "info") -> None:
        await self.broadcast(run_id, {
            "type": "log",
            "agent": agent,
            "level": level,
            "message": message,
        })

    async def broadcast_state(self, run_id: str, state: dict) -> None:
        await self.broadcast(run_id, {"type": "state", "data": state})

    async def broadcast_done(self, run_id: str, state: dict) -> None:
        await self.broadcast(run_id, {"type": "done", "data": state})

    async def broadcast_error(self, run_id: str, error: str) -> None:
        await self.broadcast(run_id, {"type": "error", "message": error})


manager = ConnectionManager()
