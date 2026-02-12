import time
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import redis.asyncio as aioredis
from app.core.redis_keys import redis_key
from config import settings
import logging

logger = logging.getLogger(__name__)


class RateLimiter:

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.rate_limit = settings.RATE_LIMIT_PER_MINUTE
        self.burst = settings.RATE_LIMIT_BURST
        self.backoff_base = settings.RATE_LIMIT_BACKOFF_BASE
        self.max_violations = settings.RATE_LIMIT_MAX_VIOLATIONS
        self.ban_duration = settings.RATE_LIMIT_BAN_DURATION_MINUTES

    async def check_rate_limit(self, identifier: str) -> tuple[bool, Dict[str, Any]]:
        current_time = int(time.time())
        minute_key = redis_key("rate_limit", identifier, current_time // 60)
        violation_key = redis_key("violations", identifier)
        ban_key = redis_key("ban", identifier)

        # Check if user is banned
        is_banned = await self.redis.exists(ban_key)
        if is_banned:
            ban_ttl = await self.redis.ttl(ban_key)
            return False, {
                "error": "Too many violations - temporary ban",
                "retry_after": ban_ttl,
                "reason": "repeated_violations",
                "banned": True
            }

        # Get current request count
        count = await self.redis.get(minute_key)
        current_count = int(count) if count else 0

        # Get violation count
        violations = await self.redis.get(violation_key)
        violation_count = int(violations) if violations else 0

        # Calculate dynamic limit with exponential backoff
        effective_limit = self.rate_limit
        if violation_count > 0:
            # Reduce limit exponentially based on violations
            effective_limit = max(
                10,  # Minimum 10 requests/min
                int(self.rate_limit / (self.backoff_base ** violation_count))
            )

        # Check limit
        if current_count >= effective_limit:
            # Increment violation counter
            await self.redis.incr(violation_key)
            await self.redis.expire(violation_key, 3600)  # 1 hour expiry

            new_violation_count = violation_count + 1

            # Ban if too many violations
            if new_violation_count >= self.max_violations:
                await self.redis.setex(
                    ban_key,
                    self.ban_duration * 60,
                    "banned"
                )
                logger.warning(f"Rate limiter: {identifier} banned for {self.ban_duration} minutes")
                return False, {
                    "error": "Rate limit exceeded - banned",
                    "retry_after": self.ban_duration * 60,
                    "reason": "max_violations_reached",
                    "banned": True,
                    "violations": new_violation_count
                }

            # Calculate backoff time
            backoff_seconds = int(60 * (self.backoff_base ** violation_count))

            logger.warning(f"Rate limiter: {identifier} exceeded limit (violation {new_violation_count})")
            return False, {
                "error": "Rate limit exceeded",
                "limit": effective_limit,
                "remaining": 0,
                "retry_after": backoff_seconds,
                "violations": new_violation_count,
                "reason": "rate_limit_exceeded"
            }

        # Increment counter
        await self.redis.incr(minute_key)
        await self.redis.expire(minute_key, 60)

        # Reset violations on successful request within limit (if user has improved behavior)
        if violation_count > 0 and current_count < (effective_limit * 0.5):
            await self.redis.decr(violation_key)
            logger.debug(f"Rate limiter: {identifier} violation count reduced to {violation_count - 1}")

        # Request allowed
        return True, {
            "limit": effective_limit,
            "remaining": effective_limit - current_count - 1,
            "reset": ((current_time // 60) + 1) * 60
        }

    async def get_user_stats(self, identifier: str) -> Dict[str, Any]:
        current_time = int(time.time())
        minute_key = redis_key("rate_limit", identifier, current_time // 60)
        violation_key = redis_key("violations", identifier)
        ban_key = redis_key("ban", identifier)

        count = await self.redis.get(minute_key)
        violations = await self.redis.get(violation_key)
        is_banned = await self.redis.exists(ban_key)

        stats = {
            "identifier": identifier,
            "current_count": int(count) if count else 0,
            "violation_count": int(violations) if violations else 0,
            "is_banned": bool(is_banned),
            "rate_limit": self.rate_limit
        }

        if is_banned:
            stats["ban_ttl"] = await self.redis.ttl(ban_key)

        return stats

    async def reset_user_limits(self, identifier: str) -> bool:
        current_time = int(time.time())
        minute_key = redis_key("rate_limit", identifier, current_time // 60)
        violation_key = redis_key("violations", identifier)
        ban_key = redis_key("ban", identifier)

        await self.redis.delete(minute_key, violation_key, ban_key)
        logger.info(f"Rate limiter: Reset all limits for {identifier}")
        return True


# Legacy compatibility - for any code that might import these
__all__ = ['RateLimiter']
