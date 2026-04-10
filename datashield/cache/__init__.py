"""
Кэш консистентности замен.
Обеспечивает детерминированное маскирование: один вход → всегда один выход.
Поддерживает Redis Cluster и in-memory fallback.
"""
from __future__ import annotations
import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import Any


class BaseCache(ABC):
    """Базовый интерфейс кэша."""

    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def flush(self) -> None: ...

    @abstractmethod
    def stats(self) -> dict: ...

    def make_key(self, service: str, input_value: str) -> str:
        """Детерминированный ключ кэша: hash(service + input)."""
        raw = f"{service}:{input_value}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MemoryCache(BaseCache):
    """In-memory кэш с TTL. Используется без Redis."""

    def __init__(self, ttl: int = 86400 * 30):
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._default_ttl = ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        if key not in self._store:
            self._misses += 1
            return None
        value, expires_at = self._store[key]
        if expires_at is not None and time.time() > expires_at:
            del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + effective_ttl if effective_ttl > 0 else None
        self._store[key] = (value, expires_at)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def flush(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "backend": "memory",
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0.0,
        }


class RedisCache(BaseCache):
    """Redis-based кэш. При недоступности — fallback на MemoryCache."""

    def __init__(self, url: str = "redis://localhost:6379", ttl: int = 86400 * 30, prefix: str = "ds:"):
        self._url = url
        self._default_ttl = ttl
        self._prefix = prefix
        self._client = None
        self._fallback = MemoryCache(ttl=ttl)
        self._use_fallback = False
        self._hits = 0
        self._misses = 0
        self._connect()

    def _connect(self):
        try:
            import redis as redis_lib
            self._client = redis_lib.Redis.from_url(self._url, decode_responses=True, socket_connect_timeout=2)
            self._client.ping()
            self._use_fallback = False
        except Exception as e:
            print(f"[Cache] Redis недоступен ({e}), используется in-memory fallback")
            self._use_fallback = True

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def get(self, key: str) -> Any | None:
        if self._use_fallback:
            return self._fallback.get(key)
        try:
            raw = self._client.get(self._full_key(key))
            if raw is None:
                self._misses += 1
                return None
            self._hits += 1
            return json.loads(raw)
        except Exception:
            self._use_fallback = True
            return self._fallback.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if self._use_fallback:
            self._fallback.set(key, value, ttl)
            return
        try:
            effective_ttl = ttl if ttl is not None else self._default_ttl
            self._client.set(self._full_key(key), json.dumps(value, ensure_ascii=False), ex=effective_ttl)
        except Exception:
            self._use_fallback = True
            self._fallback.set(key, value, ttl)

    def exists(self, key: str) -> bool:
        if self._use_fallback:
            return self._fallback.exists(key)
        try:
            return bool(self._client.exists(self._full_key(key)))
        except Exception:
            self._use_fallback = True
            return self._fallback.exists(key)

    def flush(self) -> None:
        if self._use_fallback:
            self._fallback.flush()
            return
        try:
            keys = self._client.keys(f"{self._prefix}*")
            if keys:
                self._client.delete(*keys)
        except Exception:
            self._fallback.flush()

    def stats(self) -> dict:
        if self._use_fallback:
            s = self._fallback.stats()
            s["backend"] = "memory(fallback)"
            return s
        total = self._hits + self._misses
        try:
            info = self._client.info("memory")
            return {
                "backend": "redis",
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0.0,
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            }
        except Exception:
            return {"backend": "redis(error)", "hits": self._hits, "misses": self._misses}


def create_cache(config: dict | None) -> BaseCache:
    """Create cache from either root config or direct cache config."""
    config = config or {}
    cache_cfg = config.get("cache", config)
    backend = cache_cfg.get("backend", "memory")
    ttl = cache_cfg.get("ttl", 86400 * 30)
    if backend == "redis":
        url = cache_cfg.get("url", "redis://localhost:6379")
        prefix = cache_cfg.get("prefix", "ds:")
        return RedisCache(url=url, ttl=ttl, prefix=prefix)
    return MemoryCache(ttl=ttl)
