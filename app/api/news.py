"""
News Aggregation API Endpoints
Provides endpoints for fetching and aggregating news from multiple sources
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator
import redis.asyncio as aioredis
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.article_persistence import article_persistence_service


from config import settings
from app.services.news_aggregator import get_news_aggregator, NewsAggregatorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["News Aggregation"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class NewsQuery(BaseModel):
    """News aggregation query parameters"""
    query: Optional[str] = Field(None, max_length=500, description="Search query")
    sources: Optional[List[str]] = Field(
        None,
        description="List of sources to fetch from (newsapi, gdelt, rss)"
    )
    limit: int = Field(20, ge=1, le=100, description="Maximum number of articles")
    deduplicate: bool = Field(True, description="Remove duplicate articles")
    use_cache: bool = Field(True, description="Use cached results")
    category: Optional[str] = Field(None, description="News category (for NewsAPI)")
    language: str = Field("en", max_length=2, description="Language code")

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v):
        if v is not None:
            valid_sources = {"newsapi", "gdelt", "rss"}
            invalid = set(v) - valid_sources
            if invalid:
                raise ValueError(f"Invalid sources: {invalid}. Valid: {valid_sources}")
        return v


class RSSFeedQuery(BaseModel):
    """RSS feed query parameters"""
    feed_urls: List[str] = Field(..., min_length=1, max_length=10)
    limit_per_feed: int = Field(10, ge=1, le=50)
    deduplicate: bool = Field(True)

    @field_validator("feed_urls")
    @classmethod
    def validate_urls(cls, v):
        for url in v:
            if not url.startswith(('http://', 'https://')):
                raise ValueError(f"Invalid URL: {url}")
        return v


class ArticleResponse(BaseModel):
    """Article response model"""
    title: str
    content: str
    description: Optional[str] = None
    url: str
    source: str
    author: Optional[str] = None
    published_date: str
    image_url: Optional[str] = None
    content_hash: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator("published_date", mode="before")
    @classmethod
    def convert_datetime_to_string(cls, v):
        """Convert datetime to ISO format string"""
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, str):
            # Already a string, return as-is
            return v
        return str(v)


class NewsResponse(BaseModel):
    """News aggregation response"""
    total: int
    articles: List[ArticleResponse]
    sources_used: List[str]
    cached: bool = False


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

async def get_redis_client() -> aioredis.Redis:
    """Get Redis client for news aggregation"""
    try:
        redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS
        )
        await redis.ping()
        return redis
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise HTTPException(status_code=503, detail="Cache service unavailable")





async def get_aggregator_service(
    redis: aioredis.Redis = Depends(get_redis_client)
) -> NewsAggregatorService:
    """Get news aggregator service instance"""
    return get_news_aggregator(
        redis_client=redis,
        newsapi_key=settings.NEWSAPI_KEY
    )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/aggregate", response_model=NewsResponse)
async def aggregate_news(
    query: Optional[str] = Query(None, max_length=500, description="Search query"),
    sources: Optional[str] = Query(
        None,
        description="Comma-separated sources (newsapi,gdelt,rss)"
    ),
    limit: int = Query(20, ge=1, le=100, description="Max articles"),
    deduplicate: bool = Query(True, description="Remove duplicates"),
    use_cache: bool = Query(True, description="Use cache"),
    category: Optional[str] = Query(None, description="Category for NewsAPI"),
    language: str = Query("en", max_length=2, description="Language code"),
    aggregator: NewsAggregatorService = Depends(get_aggregator_service),
    save_to_db: bool = Query(True, description="Save fetched articles to database"),
    db: AsyncSession = Depends(get_db)


):
    """
    Aggregate news from multiple sources

    This endpoint fetches news articles from various sources (NewsAPI, GDELT, RSS)
    and returns deduplicated, sanitized results with 15-minute caching.

    **Features:**
    - Multi-source aggregation
    - Content deduplication (80% similarity threshold)
    - XSS prevention and content sanitization
    - Circuit breaker pattern for API failures
    - Exponential backoff retry logic
    - Redis caching (15-minute TTL)
    """
    try:
        # Parse sources
        source_list = None
        if sources:
            source_list = [s.strip() for s in sources.split(",")]
            valid_sources = {"newsapi", "gdelt", "rss"}
            invalid = set(source_list) - valid_sources
            if invalid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sources: {invalid}. Valid: {valid_sources}"
                )
        else:
            source_list = list(settings.NEWS_SOURCES)
            if settings.ENABLE_RSS_FEEDS and "rss" not in source_list:
                source_list.append("rss")

        feed_urls = settings.RSS_FEED_URLS if "rss" in source_list and settings.RSS_FEED_URLS else None

        # Fetch articles
        articles = await aggregator.aggregate_news(
            query=query,
            sources=source_list,
            limit=limit,
            deduplicate=deduplicate,
            use_cache=use_cache,
            category=category,
            language=language,
            feed_urls=feed_urls
        )

        # Save to database if requested
        if save_to_db and articles:
            save_result = await article_persistence_service.save_articles(
                articles=articles,
                db=db,
                auto_approve=True
            )
            logger.info(f"Saved articles: {save_result}")


        # Determine which sources were used
        sources_used = source_list or ["newsapi", "gdelt", "rss"]

        return NewsResponse(
            total=len(articles),
            articles=articles,
            sources_used=sources_used,
            cached=False  # Would need to track this in the service
        )

    except Exception as e:
        logger.error(f"Error aggregating news: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to aggregate news: {str(e)}")


@router.post("/rss/fetch", response_model=NewsResponse)
async def fetch_rss_feeds(
    query: RSSFeedQuery,
    aggregator: NewsAggregatorService = Depends(get_aggregator_service)
):
    """
    Fetch articles from multiple RSS feeds

    This endpoint allows you to fetch news from custom RSS feed URLs
    with automatic content sanitization and deduplication.

    **Example RSS feeds:**
    - BBC News: http://feeds.bbci.co.uk/news/rss.xml
    - CNN: http://rss.cnn.com/rss/edition.rss
    - Reuters: http://feeds.reuters.com/reuters/topNews
    """
    try:
        articles = await aggregator.fetch_from_rss_feeds(
            feed_urls=query.feed_urls,
            limit_per_feed=query.limit_per_feed,
            deduplicate=query.deduplicate
        )

        return NewsResponse(
            total=len(articles),
            articles=articles,
            sources_used=["rss"],
            cached=False
        )

    except Exception as e:
        logger.error(f"Error fetching RSS feeds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch RSS feeds: {str(e)}")


@router.get("/sources")
async def get_available_sources():
    """
    Get list of available news sources

    Returns information about supported news aggregation sources
    """
    return {
        "sources": [
            {
                "id": "newsapi",
                "name": "NewsAPI",
                "description": "News from NewsAPI.org - requires API key",
                "enabled": settings.NEWSAPI_KEY is not None,
                "features": ["categories", "languages", "search"]
            },
            {
                "id": "gdelt",
                "name": "GDELT Project",
                "description": "Global Database of Events, Language, and Tone",
                "enabled": True,
                "features": ["search", "global_coverage"]
            },
            {
                "id": "rss",
                "name": "RSS Feeds",
                "description": "Custom RSS feed aggregation",
                "enabled": settings.ENABLE_RSS_FEEDS and bool(settings.RSS_FEED_URLS),
                "features": ["custom_feeds", "any_source"]
            }
        ],
        "config": {
            "cache_ttl_seconds": settings.NEWS_CACHE_TTL,
            "deduplication_threshold": settings.NEWS_DEDUPLICATION_THRESHOLD,
            "circuit_breaker_threshold": settings.NEWS_CIRCUIT_BREAKER_THRESHOLD,
            "max_articles_per_source": settings.NEWS_MAX_ARTICLES_PER_SOURCE
        }
    }


@router.get("/health")
async def health_check(
    redis: aioredis.Redis = Depends(get_redis_client)
):
    """
    Check health of news aggregation service

    Verifies Redis connection and service availability
    """
    try:
        # Check Redis
        await redis.ping()
        redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if redis_status == "healthy" else "degraded",
        "components": {
            "redis": redis_status,
            "newsapi": "configured" if settings.NEWSAPI_KEY else "not_configured"
        }
    }

