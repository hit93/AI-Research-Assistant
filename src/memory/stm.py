"""
Redis Short-Term Memory (STM) with seamless in-memory fallback.
"""

import json
from typing import Any
from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("memory.stm")


class ShortTermMemory:
    """Stores session and research progress state using Redis or in-memory fallback."""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis = None
        self._fallback_store: dict[str, str] = {}

        try:
            import redis
            client = redis.from_url(self.redis_url, decode_responses=True, socket_timeout=1.0)
            client.ping()
            self._redis = client
            logger.info("ShortTermMemory connected to Redis successfully.")
        except Exception:
            logger.info("Redis not reachable. ShortTermMemory using in-memory fallback.")

    @property
    def is_redis_active(self) -> bool:
        return self._redis is not None

    def set_session(self, session_id: str, data: dict[str, Any], ttl_seconds: int = 3600) -> None:
        """Store session state with TTL."""
        payload = json.dumps(data)
        if self._redis:
            try:
                self._redis.setex(f"stm:{session_id}", ttl_seconds, payload)
                return
            except Exception as e:
                logger.warning(f"Redis set failed: {e}. Falling back to in-memory.")
        self._fallback_store[session_id] = payload

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve stored session state."""
        raw = None
        if self._redis:
            try:
                raw = self._redis.get(f"stm:{session_id}")
            except Exception as e:
                logger.warning(f"Redis get failed: {e}.")
        if raw is None:
            raw = self._fallback_store.get(session_id)
        return json.loads(raw) if raw else None

    def update_session(self, session_id: str, key: str, value: Any) -> None:
        """Update a specific key inside session state."""
        current = self.get_session(session_id) or {}
        current[key] = value
        self.set_session(session_id, current)

    def clear_session(self, session_id: str) -> None:
        """Delete session data."""
        if self._redis:
            try:
                self._redis.delete(f"stm:{session_id}")
            except Exception:
                pass
        self._fallback_store.pop(session_id, None)


_stm_instance: ShortTermMemory | None = None


def get_stm() -> ShortTermMemory:
    """Return shared ShortTermMemory singleton."""
    global _stm_instance
    if _stm_instance is None:
        _stm_instance = ShortTermMemory()
    return _stm_instance
