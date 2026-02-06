from typing import Optional
from fastapi import Request, HTTPException, status
from datetime import datetime
import logging
from app.middleware.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


async def get_rate_limiter():
    from main import redis_client
    from config import settings

    if not redis_client or not settings.RATE_LIMIT_ENABLED:
        # Rate limiting disabled - allow all requests
        return None

    return RateLimiter(redis_client)


async def check_rate_limit(request: Request, limiter: Optional[RateLimiter] = None):
    if limiter is None:
        limiter = await get_rate_limiter()

    # If rate limiting is disabled, allow request
    if limiter is None:
        return None

    # Skip rate limiting for health/docs endpoints
    if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
        return None

    # Get identifier (user ID from state or IP address)
    identifier = _get_identifier(request)

    # Check rate limit
    allowed, metadata = await limiter.check_rate_limit(identifier)

    if not allowed:
        logger.warning(
            f"Rate limit exceeded for {identifier}: {metadata.get('reason')}"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=metadata.get("error", "Rate limit exceeded"),
            headers={
                "Retry-After": str(metadata.get("retry_after", 60)),
                "X-RateLimit-Limit": str(metadata.get("limit", 0)),
                "X-RateLimit-Remaining": "0",
            }
        )

    # Add rate limit headers to response
    request.state.rate_limit_metadata = metadata
    return None


def _get_identifier(request: Request) -> str:
    """Extract rate limit identifier from request"""
    # Try to get user ID from JWT token (set by auth middleware)
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    return f"ip:{ip}"


# Decorator approach for cleaner syntax
def rate_limit():
    async def dependency(request: Request):
        return await check_rate_limit(request)

    return dependency


# Pre-configured rate limiters for different use cases
class RateLimitPresets:
    """Pre-configured rate limit dependencies.

    Each preset creates a dedicated RateLimiter with its own limit,
    avoiding mutation of shared state (which caused race conditions).
    """

    @staticmethod
    async def strict(request: Request):
        """Strict rate limiting (10 req/min) - use for auth endpoints"""
        from main import redis_client
        from config import settings

        if not redis_client or not settings.RATE_LIMIT_ENABLED:
            return None

        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return None

        identifier = _get_identifier(request)
        limiter = RateLimiter(redis_client)
        # Override per-minute limit for this check only (no shared state mutation)
        original_limit = limiter.rate_limit
        limiter.rate_limit = 10
        allowed, metadata = await limiter.check_rate_limit(f"strict:{identifier}")
        limiter.rate_limit = original_limit

        if not allowed:
            logger.warning(f"Strict rate limit exceeded for {identifier}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=metadata.get("error", "Rate limit exceeded"),
                headers={
                    "Retry-After": str(metadata.get("retry_after", 60)),
                    "X-RateLimit-Limit": str(metadata.get("limit", 0)),
                    "X-RateLimit-Remaining": "0",
                }
            )
        return None

    @staticmethod
    async def lenient(request: Request):
        """Lenient rate limiting (200 req/min)"""
        from main import redis_client
        from config import settings

        if not redis_client or not settings.RATE_LIMIT_ENABLED:
            return None

        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return None

        identifier = _get_identifier(request)
        limiter = RateLimiter(redis_client)
        original_limit = limiter.rate_limit
        limiter.rate_limit = 200
        allowed, metadata = await limiter.check_rate_limit(f"lenient:{identifier}")
        limiter.rate_limit = original_limit

        if not allowed:
            logger.warning(f"Lenient rate limit exceeded for {identifier}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=metadata.get("error", "Rate limit exceeded"),
                headers={
                    "Retry-After": str(metadata.get("retry_after", 60)),
                    "X-RateLimit-Limit": str(metadata.get("limit", 0)),
                    "X-RateLimit-Remaining": "0",
                }
            )
        return None

    @staticmethod
    async def standard(request: Request):
        """Standard rate limiting (configured default)"""
        return await check_rate_limit(request)

