"""Authenticated WebSocket notification connections."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from threading import RLock

from fastapi import WebSocket, WebSocketDisconnect

LOGGER = logging.getLogger(__name__)


class NotificationConnectionManager:
    """对应 Java：NotificationWebSocketHandler.java。"""

    def __init__(self) -> None:
        self._connections: dict[int, list[tuple[WebSocket, asyncio.AbstractEventLoop]]] = defaultdict(list)
        self._lock = RLock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._connections[user_id].append((websocket, loop))
        await websocket.send_json({"type": "connected", "message": "连接成功"})

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        with self._lock:
            items = self._connections.get(user_id, [])
            self._connections[user_id] = [item for item in items if item[0] is not websocket]
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)

    async def listen(self, user_id: int, websocket: WebSocket) -> None:
        try:
            while True:
                message = await websocket.receive_text()
                if message == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            self.disconnect(user_id, websocket)

    def send_to_user(self, user_id: int, payload: dict) -> None:
        with self._lock:
            targets = list(self._connections.get(user_id, []))
        message = {"type": "notification", "data": payload}
        for websocket, loop in targets:
            if loop.is_closed():
                self.disconnect(user_id, websocket)
                continue
            future = asyncio.run_coroutine_threadsafe(websocket.send_json(message), loop)
            future.add_done_callback(lambda done: self._log_send_error(done))

    @staticmethod
    def _log_send_error(future: asyncio.Future) -> None:
        try:
            future.result()
        except Exception as exc:  # pragma: no cover - depends on a disconnected client
            LOGGER.debug("WebSocket notification send failed: %s", exc)

    @property
    def online_count(self) -> int:
        with self._lock:
            return len(self._connections)


notification_manager = NotificationConnectionManager()
