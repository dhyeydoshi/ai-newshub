from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.redis_keys import redis_key, redis_pattern
from app.models.integration import UserAPIKey
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ValidatedIntegrationKey:
    api_key_id: UUID
    user_id: UUID
    scopes: List[str]
    rate_limit_per_hour: int
    name: str
    expires_at: Optional[datetime]


class APIKeyService:
    KEY_PREFIX = "nwsint"
    VALIDATION_CACHE_TTL_SECONDS = 300
    USAGE_COUNTER_TTL_SECONDS = 172800

    @staticmethod
    def _hash_key(plain_key: str) -> str:
        return hashlib.sha256(plain_key.encode("utf-8")).hexdigest()

    @classmethod
    def generate_key(cls) -> Tuple[str, str, str]:
        secret = secrets.token_urlsafe(36)
        plain_key = f"{cls.KEY_PREFIX}_{secret}"
        key_hash = cls._hash_key(plain_key)
        key_prefix = f"{cls.KEY_PREFIX}_{secret[:10]}"
        return plain_key, key_hash, key_prefix

    @staticmethod
    async def _get_redis_client():
        try:
            from main import redis_client

            return redis_client
        except Exception:
            return None

    @classmethod
    async def _invalidate_validation_cache(cls, *key_hashes: str) -> None:
        redis_client = await cls._get_redis_client()
        if not redis_client:
            return

        keys = [redis_key("integration", "api_key", "valid", key_hash) for key_hash in key_hashes if key_hash]
        if keys:
            await redis_client.delete(*keys)

    @classmethod
    async def create_key(
        cls,
        *,
        user_id: UUID,
        name: str,
        scopes: Optional[List[str]],
        expires_in_days: int,
        db: AsyncSession,
    ) -> Tuple[str, UserAPIKey]:
        limits = settings.integration_limits
        active_key_count_result = await db.execute(
            select(func.count(UserAPIKey.api_key_id)).where(
                UserAPIKey.user_id == user_id,
                UserAPIKey.is_active.is_(True),
            )
        )
        active_count = active_key_count_result.scalar() or 0
        if active_count >= limits["max_api_keys_per_user"]:
            raise ValueError(f"Maximum active API keys reached ({limits['max_api_keys_per_user']})")

        plain_key, key_hash, key_prefix = cls.generate_key()
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        key = UserAPIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            scopes=scopes or ["feed:read"],
            rate_limit_per_hour=settings.INTEGRATION_DEFAULT_RATE_LIMIT_PER_HOUR,
            expires_at=expires_at,
            is_active=True,
        )
        db.add(key)
        await db.commit()
        await db.refresh(key)
        return plain_key, key

    @classmethod
    async def list_keys(cls, *, user_id: UUID, db: AsyncSession) -> List[UserAPIKey]:
        result = await db.execute(
            select(UserAPIKey)
            .where(UserAPIKey.user_id == user_id)
            .order_by(UserAPIKey.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def revoke_key(cls, *, key_id: UUID, user_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            select(UserAPIKey).where(
                UserAPIKey.api_key_id == key_id,
                UserAPIKey.user_id == user_id,
                UserAPIKey.is_active.is_(True),
            )
        )
        key = result.scalar_one_or_none()
        if not key:
            return False

        key.is_active = False
        key.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        await cls._invalidate_validation_cache(key.key_hash)
        return True

    @classmethod
    async def rotate_key(cls, *, key_id: UUID, user_id: UUID, db: AsyncSession) -> Tuple[str, UserAPIKey]:
        result = await db.execute(
            select(UserAPIKey).where(
                UserAPIKey.api_key_id == key_id,
                UserAPIKey.user_id == user_id,
                UserAPIKey.is_active.is_(True),
            )
        )
        key = result.scalar_one_or_none()
        if not key:
            raise ValueError("API key not found")

        old_hash = key.key_hash
        plain_key, new_hash, new_prefix = cls.generate_key()
        key.key_hash = new_hash
        key.key_prefix = new_prefix
        key.expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        key.revoked_at = None

        await db.commit()
        await db.refresh(key)
        await cls._invalidate_validation_cache(old_hash, new_hash)
        return plain_key, key

    @classmethod
    async def validate_key(cls, *, plain_key: str, db: AsyncSession) -> Optional[ValidatedIntegrationKey]:
        if not plain_key:
            return None

        key_hash = cls._hash_key(plain_key)
        cache_key = redis_key("integration", "api_key", "valid", key_hash)
        redis_client = await cls._get_redis_client()

        if redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                try:
                    payload = json.loads(cached)
                    expires_at = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
                    if expires_at and expires_at < datetime.now(timezone.utc):
                        await redis_client.delete(cache_key)
                        return None
                    return ValidatedIntegrationKey(
                        api_key_id=UUID(payload["api_key_id"]),
                        user_id=UUID(payload["user_id"]),
                        scopes=list(payload.get("scopes", ["feed:read"])),
                        rate_limit_per_hour=int(payload.get("rate_limit_per_hour", settings.INTEGRATION_DEFAULT_RATE_LIMIT_PER_HOUR)),
                        name=payload.get("name", ""),
                        expires_at=expires_at,
                    )
                except Exception:
                    await redis_client.delete(cache_key)

        result = await db.execute(
            select(UserAPIKey).where(
                UserAPIKey.key_hash == key_hash,
                UserAPIKey.is_active.is_(True),
            )
        )
        key = result.scalar_one_or_none()
        if not key:
            return None

        if key.expires_at and key.expires_at < datetime.now(timezone.utc):
            return None

        validated = ValidatedIntegrationKey(
            api_key_id=key.api_key_id,
            user_id=key.user_id,
            scopes=list(key.scopes or ["feed:read"]),
            rate_limit_per_hour=key.rate_limit_per_hour or settings.INTEGRATION_DEFAULT_RATE_LIMIT_PER_HOUR,
            name=key.name,
            expires_at=key.expires_at,
        )

        if redis_client:
            payload = {
                "api_key_id": str(validated.api_key_id),
                "user_id": str(validated.user_id),
                "scopes": validated.scopes,
                "rate_limit_per_hour": validated.rate_limit_per_hour,
                "name": validated.name,
                "expires_at": validated.expires_at.isoformat() if validated.expires_at else None,
            }
            await redis_client.setex(cache_key, cls.VALIDATION_CACHE_TTL_SECONDS, json.dumps(payload))

        return validated

    @classmethod
    async def increment_usage(cls, api_key_id: UUID) -> None:
        redis_client = await cls._get_redis_client()
        if not redis_client:
            return

        usage_key = redis_key("integration", "api_key", "usage", api_key_id)
        await redis_client.incr(usage_key)
        await redis_client.expire(usage_key, cls.USAGE_COUNTER_TTL_SECONDS)

    @classmethod
    async def flush_usage_to_db(cls, db: AsyncSession) -> Dict[str, int]:
        redis_client = await cls._get_redis_client()
        if not redis_client:
            return {"keys_processed": 0, "total_increment": 0}

        cursor = 0
        usage_updates: Dict[UUID, int] = {}
        redis_keys: List[str] = []
        usage_pattern = redis_pattern("integration", "api_key", "usage", "*")

        while True:
            cursor, keys = await redis_client.scan(cursor=cursor, match=usage_pattern, count=200)
            for key in keys:
                try:
                    raw_value = await redis_client.get(key)
                    if not raw_value:
                        continue
                    key_id = UUID(key.rsplit(":", 1)[-1])
                    usage_updates[key_id] = usage_updates.get(key_id, 0) + int(raw_value)
                    redis_keys.append(key)
                except Exception:
                    continue
            if cursor == 0:
                break

        if not usage_updates:
            return {"keys_processed": 0, "total_increment": 0}

        now = datetime.now(timezone.utc)
        total_increment = 0
        for key_id, delta in usage_updates.items():
            total_increment += delta
            await db.execute(
                update(UserAPIKey)
                .where(UserAPIKey.api_key_id == key_id)
                .values(
                    request_count=UserAPIKey.request_count + delta,
                    last_used_at=now,
                )
            )
        await db.commit()

        if redis_keys:
            await redis_client.delete(*redis_keys)

        logger.info(
            "Flushed integration API key usage to database: keys=%s increment=%s",
            len(usage_updates),
            total_increment,
        )
        return {"keys_processed": len(usage_updates), "total_increment": total_increment}


api_key_service = APIKeyService()
