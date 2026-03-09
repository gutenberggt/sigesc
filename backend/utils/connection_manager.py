"""
Utilitários de WebSocket e rastreamento de sessões ativas.
Extraído de server.py durante a refatoração modular.
"""

from fastapi import WebSocket
from typing import Dict, List
from datetime import datetime, timezone, timedelta
import threading
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gerenciador de conexões WebSocket para mensagens em tempo real"""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"WebSocket conectado: user_id={user_id}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WebSocket desconectado: user_id={user_id}")

    async def send_message(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Erro ao enviar mensagem WebSocket: {e}")
                    disconnected.append(connection)
            for conn in disconnected:
                self.active_connections[user_id].remove(conn)

    async def send_notification(self, user_id: str, notification: dict):
        await self.send_message(user_id, notification)

    async def broadcast(self, message: dict, exclude_user_id: str = None):
        for user_id in list(self.active_connections.keys()):
            if user_id != exclude_user_id:
                await self.send_message(user_id, message)


class ActiveSessionsTracker:
    """Rastreia usuários ativos baseado em atividade HTTP"""

    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def update(self, user_id: str, user_data: dict):
        with self._lock:
            self._sessions[user_id] = {
                "last_activity": datetime.now(timezone.utc),
                "user_data": {
                    "id": user_data.get("id"),
                    "full_name": user_data.get("full_name"),
                    "email": user_data.get("email"),
                    "role": user_data.get("role"),
                    "avatar_url": user_data.get("avatar_url"),
                    "school_ids": user_data.get("school_ids", []),
                    "school_links": user_data.get("school_links", []),
                }
            }

    def get_online(self, threshold_minutes=5):
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
        with self._lock:
            return {
                uid: data for uid, data in self._sessions.items()
                if data["last_activity"] >= cutoff
            }

    def remove(self, user_id: str):
        with self._lock:
            self._sessions.pop(user_id, None)
