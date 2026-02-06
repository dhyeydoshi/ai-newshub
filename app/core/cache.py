import json
import gzip
import hashlib
from datetime import date, datetime
from typing import Any, Optional, List, Dict, Callable
import redis.asyncio as aioredis
import logging
from functools import wraps
from uuid import UUID

logger = logging.getLogger(__name__)


class CacheManager:

    def __init__(
        self,
        redis_client: aioredis.Redis,
        default_ttl: int = 900,
        compression_threshold: int = 1024,
        key_prefix: str = "app"
    ):
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.compression_threshold = compression_threshold
        self.key_prefix = key_prefix

    def _make_key(self, key: str) -> str:
        """Generate prefixed cache key"""
        return f"{self.key_prefix}:{key}"

    def _hash_key(self, data: Any) -> str:
        """Generate hash for complex objects"""
        key_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        return str(value)

    async def get(
        self,
        key: str,
        default: Any = None,
        deserializer: Callable = json.loads
    ) -> Any:
        try:
            full_key = self._make_key(key)
            value = await self.redis.execute_command("GET", full_key, NEVER_DECODE=True)

            if value is None:
                logger.debug(f"Cache miss: {key}")
                return default

            # Normalize to bytes if needed
            if isinstance(value, memoryview):
                value = value.tobytes()
            elif isinstance(value, bytearray):
                value = bytes(value)

            # Check if compressed
            if isinstance(value, bytes) and value.startswith(b'\x1f\x8b'):
                value = gzip.decompress(value)

            # Deserialize
            if isinstance(value, bytes):
                value = value.decode('utf-8')

            result = deserializer(value)
            logger.debug(f"Cache hit: {key}")
            return result

        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        serializer: Callable = json.dumps,
        compress: Optional[bool] = None
    ) -> bool:
        try:
            full_key = self._make_key(key)
            ttl = ttl or self.default_ttl

            # Serialize
            if serializer is json.dumps:
                serialized = json.dumps(value, default=self._json_default)
            else:
                serialized = serializer(value)
            if isinstance(serialized, str):
                serialized = serialized.encode('utf-8')

            # Compress if needed
            if compress or (compress is None and len(serialized) > self.compression_threshold):
                serialized = gzip.compress(serialized, compresslevel=6)
                logger.debug(f"Compressed cache value for {key}")

            # Store with TTL
            await self.redis.setex(full_key, ttl, serialized)
            logger.debug(f"Cached {key} with TTL {ttl}s")
            return True

        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            full_key = self._make_key(key)
            await self.redis.delete(full_key)
            logger.debug(f"Deleted cache key: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete error for {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        try:
            full_pattern = self._make_key(pattern)
            cursor = 0
            deleted = 0

            # Scan and delete in batches
            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match=full_pattern,
                    count=100
                )
                if keys:
                    deleted += await self.redis.delete(*keys)

                if cursor == 0:
                    break

            logger.info(f"Deleted {deleted} keys matching {pattern}")
            return deleted

        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0

    async def get_many(
        self,
        keys: List[str],
        deserializer: Callable = json.loads
    ) -> Dict[str, Any]:
        try:
            if not keys:
                return {}

            full_keys = [self._make_key(k) for k in keys]
            values = await self.redis.execute_command("MGET", *full_keys, NEVER_DECODE=True)

            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        if isinstance(value, memoryview):
                            value = value.tobytes()
                        elif isinstance(value, bytearray):
                            value = bytes(value)

                        # Decompress if needed
                        if isinstance(value, bytes) and value.startswith(b'\x1f\x8b'):
                            value = gzip.decompress(value)

                        if isinstance(value, bytes):
                            value = value.decode('utf-8')

                        result[key] = deserializer(value)
                    except Exception as e:
                        logger.error(f"Error deserializing {key}: {e}")

            logger.debug(f"Batch get: {len(result)}/{len(keys)} hits")
            return result

        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}

    async def set_many(
        self,
        items: Dict[str, Any],
        ttl: Optional[int] = None,
        serializer: Callable = json.dumps
    ) -> int:
        try:
            if not items:
                return 0

            ttl = ttl or self.default_ttl
            pipe = self.redis.pipeline()

            for key, value in items.items():
                full_key = self._make_key(key)
                if serializer is json.dumps:
                    serialized = json.dumps(value, default=self._json_default)
                else:
                    serialized = serializer(value)
                if isinstance(serialized, str):
                    serialized = serialized.encode('utf-8')

                # Compress large values
                if len(serialized) > self.compression_threshold:
                    serialized = gzip.compress(serialized, compresslevel=6)

                pipe.setex(full_key, ttl, serialized)

            await pipe.execute()
            logger.debug(f"Batch set: {len(items)} items")
            return len(items)

        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            full_key = self._make_key(key)
            return await self.redis.exists(full_key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for {key}: {e}")
            return False

    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL for key in seconds"""
        try:
            full_key = self._make_key(key)
            return await self.redis.ttl(full_key)
        except Exception as e:
            logger.error(f"Cache get_ttl error for {key}: {e}")
            return -2

    async def expire(self, key: str, ttl: int) -> bool:
        """Update TTL for existing key"""
        try:
            full_key = self._make_key(key)
            return await self.redis.expire(full_key, ttl)
        except Exception as e:
            logger.error(f"Cache expire error for {key}: {e}")
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter"""
        try:
            full_key = self._make_key(key)
            return await self.redis.incrby(full_key, amount)
        except Exception as e:
            logger.error(f"Cache increment error for {key}: {e}")
            return 0

    async def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement counter"""
        try:
            full_key = self._make_key(key)
            return await self.redis.decrby(full_key, amount)
        except Exception as e:
            logger.error(f"Cache decrement error for {key}: {e}")
            return 0

    def cache_result(
        self,
        key_prefix: str,
        ttl: Optional[int] = None,
        key_builder: Optional[Callable] = None
    ):
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Build cache key
                if key_builder:
                    cache_key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
                else:
                    # Use function args as key
                    key_parts = [str(arg) for arg in args]
                    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
                    cache_key = f"{key_prefix}:{':'.join(key_parts)}"

                # Try to get from cache
                cached = await self.get(cache_key)
                if cached is not None:
                    return cached

                # Execute function
                result = await func(*args, **kwargs)

                # Cache result
                if result is not None:
                    await self.set(cache_key, result, ttl=ttl)

                return result

            return wrapper
        return decorator


# Singleton instance (to be initialized with Redis client)
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> Optional[CacheManager]:
    """Get the global cache manager instance"""
    return _cache_manager


def init_cache_manager(redis_client: aioredis.Redis, **kwargs) -> CacheManager:
    """Initialize the global cache manager"""
    global _cache_manager
    _cache_manager = CacheManager(redis_client, **kwargs)
    logger.info("Cache manager initialized")
    return _cache_manager
