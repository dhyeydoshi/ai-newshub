from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator
import redis.asyncio as aioredis
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.sanitizer import ContentSanitizer


from config import settings
from app.services.news_aggregator import get_news_aggregator, NewsAggregatorService
from app.services.news_ingestion_service import NewsIngestionService, news_ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["News Aggregation"])


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

    @field_validator("title", "content", "description", mode="before")
    @classmethod
    def sanitize_text_fields(cls, v):
        if v is None:
            return v
        return ContentSanitizer.sanitize_text(str(v))

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


async def get_redis_client() -> aioredis.Redis:
    """Get Redis client for news aggregation - reuses the global application-level client."""
    from main import redis_client
    if redis_client:
        return redis_client

    # Fallback: create a new connection if global client is unavailable
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


def get_ingestion_service() -> NewsIngestionService:
    return news_ingestion_service


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
    topics: Optional[List[str]] = Query(None, description="Topic filters used to select topic-specific RSS feeds"),
    category: Optional[str] = Query(None, description="Category for NewsAPI"),
    language: str = Query("en", max_length=2, description="Language code"),
    aggregator: NewsAggregatorService = Depends(get_aggregator_service),
    ingestion_service: NewsIngestionService = Depends(get_ingestion_service),
    save_to_db: bool = Query(True, description="Save fetched articles to database"),
    db: AsyncSession = Depends(get_db)


):
    try:
        result = await ingestion_service.aggregate_and_persist(
            aggregator=aggregator,
            db=db,
            query=query,
            sources=sources,
            limit=limit,
            deduplicate=deduplicate,
            use_cache=use_cache,
            topics=topics,
            category=category,
            language=language,
            save_to_db=save_to_db,
            auto_approve=True,
        )

        articles = result["articles"]
        sources_used = result["sources_used"]
        save_stats = result["save_stats"]
        pipeline_stats = result["pipeline_stats"]
        logger.info(
            "Aggregate request complete: sources=%s fetched=%s accepted=%s saved=%s",
            sources_used,
            pipeline_stats.get("input_count", 0),
            pipeline_stats.get("accepted_count", 0),
            save_stats.get("saved", 0),
        )

        return NewsResponse(
            total=len(articles),
            articles=articles,
            sources_used=sources_used,
            cached=False  # Would need to track this in the service
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error aggregating news: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to aggregate news")


@router.post("/rss/fetch", response_model=NewsResponse)
async def fetch_rss_feeds(
    query: RSSFeedQuery,
    aggregator: NewsAggregatorService = Depends(get_aggregator_service),
    ingestion_service: NewsIngestionService = Depends(get_ingestion_service),
):
    try:
        result = await ingestion_service.fetch_rss_and_prepare(
            aggregator=aggregator,
            feed_urls=query.feed_urls,
            limit_per_feed=query.limit_per_feed,
            deduplicate=query.deduplicate
        )
        articles = result["articles"]
        pipeline_stats = result["pipeline_stats"]
        logger.info(
            "RSS fetch request complete: input=%s accepted=%s dropped_invalid=%s dropped_duplicates=%s",
            pipeline_stats.get("input_count", 0),
            pipeline_stats.get("accepted_count", 0),
            pipeline_stats.get("dropped_invalid", 0),
            pipeline_stats.get("dropped_duplicates", 0),
        )

        return NewsResponse(
            total=len(articles),
            articles=articles,
            sources_used=["rss"],
            cached=False
        )

    except Exception as e:
        logger.error(f"Error fetching RSS feeds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch RSS feeds")


@router.get("/sources")
async def get_available_sources():
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

