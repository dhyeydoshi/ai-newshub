"""
Cache Dependency for API Endpoints
Provides request-level caching before database queries
"""
import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
from fastapi import Request
from app.core.cache import get_cache_manager
import logging

logger = logging.getLogger(__name__)


class CacheConfig:
    """Cache configuration for different endpoint types"""

    # TTL configurations (in seconds) - Updated to 2 hours (7200 seconds)
    ARTICLES_LIST_TTL = 7200  # 2 hours
    ARTICLE_DETAIL_TTL = 7200  # 2 hours
    USER_PROFILE_TTL = 7200  # 2 hours
    RECOMMENDATIONS_TTL = 7200  # 2 hours
    TRENDING_TTL = 7200  # 2 hours
    SEARCH_TTL = 7200  # 2 hours
    USER_PREFERENCES_TTL = 7200  # 2 hours
    READING_HISTORY_TTL = 7200  # 2 hours


def generate_cache_key_from_request(request: Request, prefix: str = "") -> str:
    """
    Generate unique cache key from request parameters

    Args:
        request: FastAPI request object
        prefix: Cache key prefix (e.g., "articles", "user")

    Returns:
        Unique cache key based on endpoint and parameters
    """
    # Include path
    path = request.url.path

    # Include query parameters (sorted for consistency)
    params = dict(sorted(request.query_params.items()))

    # Include user ID from state if available (for user-specific caching)
    user_id = getattr(request.state, "user_id", None)

    # Create key components
    key_data = {
        "path": path,
        "params": params,
        "user_id": user_id
    }

    # Generate hash for complex queries
    key_hash = hashlib.sha256(
        json.dumps(key_data, sort_keys=True).encode()
    ).hexdigest()[:16]

    return f"{prefix}:request:{key_hash}"


async def get_cached_response(cache_key: str) -> Optional[dict]:
    """
    Get cached response from Redis

    Args:
        cache_key: Cache key to lookup

    Returns:
        Cached response data or None
    """
    cache_manager = get_cache_manager()
    if not cache_manager:
        return None

    try:
        cached = await cache_manager.get(cache_key)
        if cached:
            logger.info(f"Cache HIT: {cache_key}")
            return cached
        else:
            logger.info(f"Cache MISS: {cache_key}")
            return None
    except Exception as e:
        logger.error(f"Cache get error for {cache_key}: {e}")
        return None


async def set_cached_response(cache_key: str, data: Any, ttl: int) -> bool:
    """
    Set cached response in Redis

    Args:
        cache_key: Cache key
        data: Response data to cache
        ttl: Time to live in seconds

    Returns:
        True if successful
    """
    cache_manager = get_cache_manager()
    if not cache_manager:
        return False

    try:
        success = await cache_manager.set(cache_key, data, ttl=ttl)
        if success:
            logger.info(f"Cached response: {cache_key} (TTL: {ttl}s)")
        return success
    except Exception as e:
        logger.error(f"Cache set error for {cache_key}: {e}")
        return False


async def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalidate all cache keys matching pattern

    Args:
        pattern: Pattern to match (e.g., "articles:*", "user:123:*")

    Returns:
        Number of keys deleted
    """
    cache_manager = get_cache_manager()
    if not cache_manager:
        return 0

    try:
        deleted = await cache_manager.delete_pattern(pattern)
        logger.info(f"Invalidated {deleted} cache keys matching: {pattern}")
        return deleted
    except Exception as e:
        logger.error(f"Cache invalidation error for {pattern}: {e}")
        return 0


def cache_endpoint(
    prefix: str,
    ttl: int,
    key_builder: Optional[Callable] = None,
    user_specific: bool = True
):
    """
    Decorator to cache endpoint responses

    Usage:
        @router.get("/articles")
        @cache_endpoint(prefix="articles", ttl=300)
        async def get_articles(...):
            ...

    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
        key_builder: Custom function to build cache key
        user_specific: Include user ID in cache key
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from kwargs
            request = kwargs.get('request')
            if not request:
                # If no request in kwargs, execute without caching
                return await func(*args, **kwargs)

            # Build cache key
            if key_builder:
                cache_key = key_builder(request, *args, **kwargs)
            else:
                cache_key = generate_cache_key_from_request(request, prefix)

            # Try to get from cache
            cached_response = await get_cached_response(cache_key)
            if cached_response is not None:
                return cached_response

            # Execute function
            response = await func(*args, **kwargs)

            # Cache the response
            if response is not None:
                # Convert Pydantic models to dict if needed
                cache_data = response
                if hasattr(response, 'model_dump'):
                    cache_data = response.model_dump()
                elif hasattr(response, 'dict'):
                    cache_data = response.dict()

                await set_cached_response(cache_key, cache_data, ttl)

            return response

        return wrapper
    return decorator


# Specific cache key builders

def build_article_list_key(
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    topics: Optional[list] = None,
    language: str = "en",
    **kwargs
) -> str:
    """Build cache key for article list"""
    key_parts = [
        f"page:{page}",
        f"size:{page_size}",
        f"lang:{language}"
    ]
    if category:
        key_parts.append(f"cat:{category}")
    if topics:
        key_parts.append(f"topics:{','.join(sorted(topics))}")

    return f"articles:list:{':'.join(key_parts)}"


def build_article_detail_key(article_id: str, **kwargs) -> str:
    """Build cache key for article detail"""
    return f"articles:detail:{article_id}"


def build_user_profile_key(user_id: str, **kwargs) -> str:
    """Build cache key for user profile"""
    return f"user:profile:{user_id}"


def build_recommendations_key(
    user_id: str,
    limit: int = 10,
    exclude_read: bool = True,
    min_score: float = 0.0,
    **kwargs
) -> str:
    """Build cache key for recommendations"""
    return f"recommendations:{user_id}:{limit}:{exclude_read}:{min_score}"


def build_search_key(
    query: str,
    page: int = 1,
    page_size: int = 20,
    **kwargs
) -> str:
    """Build cache key for search results"""
    query_hash = hashlib.sha256(query.encode()).hexdigest()[:12]
    return f"search:{query_hash}:{page}:{page_size}"


# Cache invalidation helpers

async def invalidate_article_cache():
    """Invalidate all article-related cache"""
    await invalidate_cache_pattern("articles:*")


async def invalidate_user_cache(user_id: str):
    """Invalidate user-specific cache"""
    await invalidate_cache_pattern(f"user:*:{user_id}:*")
    await invalidate_cache_pattern(f"recommendations:{user_id}:*")


async def invalidate_search_cache():
    """Invalidate search cache"""
    await invalidate_cache_pattern("search:*")
