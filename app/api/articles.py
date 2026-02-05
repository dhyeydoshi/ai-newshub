"""
Articles API Router
Complete article and news endpoints with personalization and security
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from datetime import datetime, timezone, timedelta
from config import settings

from app.core.database import get_db
from app.models.article import Article
from app.models.user import User
from app.models.feedback import ReadingHistory
from app.schemas.article import (
    ArticleResponse,
    ArticleListResponse,
    ArticleDetailResponse,
    TrendingArticlesResponse,
    SearchResultsResponse,
    PersonalizedFeedResponse
)
from app.api.auth import get_current_user_id
from app.dependencies.cache import (
    get_cached_response,
    set_cached_response,
    CacheConfig,
    build_article_list_key
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["News & Articles"])


# ============================================================================
# ARTICLE LISTING FROM DATABASE WITH CACHING
# ============================================================================

@router.get("/articles", response_model=ArticleListResponse)
async def get_articles(
    page: int = Query(1, ge=1, le=100),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, max_length=100),
    topics: Optional[List[str]] = Query(None),
    language: str = Query("en", max_length=10),
    db: AsyncSession = Depends(get_db)
):
    """
    Get articles from database (cached and fetched by scheduler)

    Features:
    - Redis caching (2 hours TTL)
    - Pagination support
    - Filter by category, topics, language
    - Returns approved articles only
    - Sorted by published date
    """
    # Build cache key
    cache_key = build_article_list_key(
        page=page,
        page_size=page_size,
        category=category,
        topics=topics,
        language=language
    )

    # Check cache first
    cached_response = await get_cached_response(cache_key)
    if cached_response:
        logger.info(f" Cache HIT for articles list (page {page})")
        return ArticleListResponse(**cached_response)

    logger.info(f" Cache MISS for articles list (page {page}) - Querying database")

    from app.services.article_persistence import article_persistence_service

    # Get articles from database
    articles = await article_persistence_service.get_recent_articles(
        db=db,
        limit=page_size,
        offset=(page - 1) * page_size,
        category=category,
        topics=topics,
        language=language
    )

    # Get total count
    total = await article_persistence_service.get_article_count(
        db=db,
        category=category,
        topics=topics
    )

    # Convert to response format
    article_responses = []
    for article in articles:
        try:
            article_dict = {
                'article_id': str(article.article_id),
                'title': article.title,
                'content': article.content,
                'description': getattr(article, 'description', None),
                'source_url': str(article.source_url) if article.source_url else None,
                'source_name': article.source_name,  # Explicitly include source name
                'author': getattr(article, 'author', None),
                'image_url': str(article.image_url) if getattr(article, 'image_url', None) else None,
                'topics': article.topics or [],
                'category': getattr(article, 'category', None),
                'tags': getattr(article, 'tags', []),
                'published_date': article.published_date,  # Explicitly include published date
                'word_count': getattr(article, 'word_count', 0),
                'reading_time_minutes': getattr(article, 'reading_time_minutes', 0),
                'total_views': getattr(article, 'total_views', 0),
                'total_clicks': getattr(article, 'total_clicks', 0),
                'avg_time_spent': getattr(article, 'avg_time_spent', 0.0),
                'is_featured': getattr(article, 'is_featured', False),
                'created_at': article.created_at
            }
            article_responses.append(ArticleResponse.model_validate(article_dict))
        except Exception as e:
            logger.error(f"Validation error for article {getattr(article, 'article_id', 'unknown')}: {e}")
            continue

    response = ArticleListResponse(
        total=total,
        page=page,
        page_size=page_size,
        articles=article_responses,
        has_next=(page * page_size) < total,
        has_previous=page > 1
    )

    # Cache the response
    await set_cached_response(cache_key, response.model_dump(), CacheConfig.ARTICLES_LIST_TTL)

    return response


# ============================================================================
# MANUAL NEWS FETCH ENDPOINT (ADMIN)
# ============================================================================

@router.post("/fetch-now")
async def fetch_news_now(
    queries: Optional[List[str]] = Query(None, description="Search queries"),
    sources: Optional[List[str]] = Query(None, description="News sources"),
    limit: int = Query(50, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger news fetch using Celery task queue

    This endpoint queues a Celery task for immediate news fetching.
    The task runs asynchronously in the background.

    Returns task ID for tracking.
    """
    try:
        from app.utils.celery_helpers import trigger_manual_fetch

        # Trigger Celery task
        logger.info(f"Manual fetch triggered by user {user_id}")

        # Use first query if multiple provided
        query = queries[0] if queries else None

        result = await trigger_manual_fetch(
            query=query,
            sources=sources,
            limit=limit
        )

        if result.get('success'):
            return {
                "success": True,
                "message": "News fetch task queued successfully",
                "task_id": result['task_id'],
                "status": result['status'],
                "note": "Use /api/v1/news/task-status/{task_id} to check progress"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to queue task: {result.get('error')}"
            )

    except Exception as e:
        logger.error(f"Error in manual news fetch: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger news fetch: {str(e)}"
        )


# ============================================================================
# TASK STATUS ENDPOINT
# ============================================================================

@router.get("/task-status/{task_id}")
async def get_task_status_endpoint(task_id: str):
    """Get status of a Celery task"""
    try:
        from app.utils.celery_helpers import get_task_status

        status_info = await get_task_status(task_id)
        return status_info

    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# SCHEDULER STATUS ENDPOINT
# ============================================================================

@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get Celery worker and scheduler status"""
    try:
        from app.utils.celery_helpers import get_celery_status, get_last_fetch_time
        import redis.asyncio as aioredis

        # Get Celery status
        celery_status = await get_celery_status()

        # Get last fetch time from Redis
        try:
            redis_client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            last_fetch = await get_last_fetch_time(redis_client)
            await redis_client.close()
        except Exception as e:
            logger.error(f"Error getting last fetch time: {e}")
            last_fetch = None

        return {
            "celery": celery_status,
            "last_fetch": last_fetch.isoformat() if last_fetch else None,
            "scheduler_type": "Celery Beat",
            "message": "News fetching runs automatically via Celery worker"
        }

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        return {
            "enabled": settings.ENABLE_NEWS_SCHEDULER,
            "error": str(e),
            "message": "Make sure Celery worker is running"
        }


# ============================================================================
# SCHEDULED TASKS INFO ENDPOINT
# ============================================================================

@router.get("/scheduler/tasks")
async def get_scheduled_tasks():
    """Get information about scheduled periodic tasks"""
    try:
        from app.utils.celery_helpers import get_scheduled_tasks_info

        return get_scheduled_tasks_info()

    except Exception as e:
        logger.error(f"Error getting scheduled tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# PERSONALIZED NEWS FEED
# ============================================================================

@router.get("/personalized", response_model=PersonalizedFeedResponse)
async def get_personalized_news(
    page: int = Query(1, ge=1, le=100),
    page_size: int = Query(20, ge=1, le=100),
    include_read: bool = Query(False),
    min_relevance_score: float = Query(0.0, ge=0.0, le=1.0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get personalized news feed using RL-based recommendations

    Features:
    - Personalized ranking based on user preferences
    - RL model recommendations
    - Filters out already-read articles (optional)
    - Relevance score filtering

    Security:
    - User authentication required
    - Rate limited per user
    - Input validation
    """
    # Get user
    user_result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Build query for active articles
    query = select(Article).where(Article.is_active == True)

    # Exclude read articles if requested
    if not include_read:
        read_articles_subquery = (
            select(ReadingHistory.article_id)
            .where(ReadingHistory.user_id == user.user_id)
        )
        query = query.where(Article.article_id.not_in(read_articles_subquery))

    # Get recent articles (last 7 days)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    query = query.where(Article.published_date >= week_ago)

    # Execute query to get candidate articles
    result = await db.execute(query.order_by(desc(Article.published_date)).limit(100))
    articles = result.scalars().all()

    if not articles:
        return PersonalizedFeedResponse(
            articles=[],
            total=0,
            page=page,
            page_size=page_size,
            user_preferences=user.topic_preferences or {},
            relevance_scores={}
        )

    # RL-based scoring (core personalization)
    from app.services.rl_service import rl_service

    try:
        article_map = {str(article.article_id): article for article in articles}
        recommendations = await rl_service.get_recommendations(
            user_id=str(user.user_id),
            candidate_articles=[article.to_dict() for article in articles],
            top_k=len(articles)
        )

        scored_articles = []
        relevance_scores = {}
        for rec in recommendations:
            score = rec.get("score", 0.0)
            if score < min_relevance_score:
                continue
            article_id = rec.get("article_id")
            article = article_map.get(article_id)
            if article:
                scored_articles.append((article, score))
                relevance_scores[str(article.article_id)] = score
    except Exception as e:
        logger.error(f"RL personalization error: {e}")
        # Fallback: simple scoring based on user preferences
        user_preferences = user.topic_preferences or {}
        favorite_topics = user.favorite_topics or []
        relevance_scores = {}
        scored_articles = []
        for article in articles:
            score = 0.0
            article_topics = article.topics or []

            for topic in article_topics:
                if topic in favorite_topics:
                    score += 1.0
                elif topic in user_preferences:
                    score += user_preferences[topic]

            if article_topics:
                score = score / len(article_topics)

            if score >= min_relevance_score:
                scored_articles.append((article, score))
                relevance_scores[str(article.article_id)] = score

    # Sort by score (if RL didn't already)
    scored_articles.sort(key=lambda x: x[1], reverse=True)

    # Pagination
    total = len(scored_articles)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = [article for article, _ in scored_articles[start:end]]

    # Format response
    article_responses = [
        ArticleResponse.model_validate(article)
        for article in paginated
    ]

    return PersonalizedFeedResponse(
        articles=article_responses,
        total=total,
        page=page,
        page_size=page_size,
        user_preferences=user.topic_preferences or {},
        relevance_scores={
            str(article.article_id): relevance_scores.get(str(article.article_id), 0.0)
            for article in paginated
        }
    )


# ============================================================================
# ARTICLE DETAILS
# ============================================================================

@router.get("/article/{article_id}", response_model=ArticleDetailResponse)
async def get_article_detail(
    article_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed article information with summary

    Includes:
    - Full article content
    - Generated summary
    - Related articles
    - Engagement metrics
    """
    from uuid import UUID

    try:
        uuid_article_id = UUID(article_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid article ID format"
        )
    # Get article
    result = await db.execute(
        select(Article).where(and_(
            Article.article_id == uuid_article_id,
            Article.is_active == True
        ))
    )
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    # Track view (asynchronously log this)
    article.total_views += 1

    # Get related articles (same topics)
    related_articles = []
    if article.topics:
        related_query = (
            select(Article)
            .where(and_(
                Article.article_id != uuid_article_id,
                Article.is_active == True,
                Article.topics.op('&&')(article.topics)  # PostgreSQL array overlap operator
            ))
            .order_by(desc(Article.published_date))
            .limit(5)
        )
        related_result = await db.execute(related_query)
        related_articles = [
            ArticleResponse.model_validate(a)
            for a in related_result.scalars()
        ]

    await db.commit()

    # Build response
    response_data = {
        'article_id': str(article.article_id),
        'title': article.title,
        'content': article.content,
        'description': getattr(article, 'description', None),
        'source_url': str(article.source_url) if article.source_url else None,
        'source_name': article.source_name,
        'author': getattr(article, 'author', None),
        'image_url': str(article.image_url) if getattr(article, 'image_url', None) else None,
        'topics': article.topics or [],
        'category': getattr(article, 'category', None),
        'tags': getattr(article, 'tags', []),
        'published_date': article.published_date,
        'word_count': getattr(article, 'word_count', 0),
        'reading_time_minutes': getattr(article, 'reading_time_minutes', 0),
        'total_views': getattr(article, 'total_views', 0),
        'total_clicks': getattr(article, 'total_clicks', 0),
        'avg_time_spent': getattr(article, 'avg_time_spent', 0.0),
        'is_featured': getattr(article, 'is_featured', False),
        'created_at': article.created_at,
        'related_articles': related_articles
    }

    return ArticleDetailResponse(**response_data)


@router.get("/summary/{article_id}")
async def get_article_summary(
    article_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get article summary (generated or cached)

    Generates a simple extractive summary on-demand
    """
    from uuid import UUID

    try:
        uuid_article_id = UUID(article_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid article ID format"
        )

    # Get article
    result = await db.execute(
        select(Article).where(and_(
            Article.article_id == uuid_article_id,
            Article.is_active == True
        ))
    )
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    # Return cached summary if available
    if article.excerpt:
        return {
            "article_id": article.article_id,
            "excerpt": article.excerpt,
            "word_count": len(article.excerpt.split()),
            "cached": True
        }

    # Simple extraction of first few sentences
    sentences = article.content.split('.')[:3]
    simple_summary = '. '.join(s.strip() for s in sentences if s.strip()) + '.'

    return {
        "article_id": article.article_id,
        "excerpt": simple_summary,
        "word_count": len(simple_summary.split()),
        "cached": False,
        "model_used": "simple_extraction"
    }


# ============================================================================
# TRENDING ARTICLES
# ============================================================================

@router.get("/trending", response_model=TrendingArticlesResponse)
async def get_trending_articles(
    timeframe: str = Query("24h", pattern="^(24h|7d|30d)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """
    Get trending articles based on engagement metrics

    Timeframes:
    - 24h: Last 24 hours
    - 7d: Last 7 days
    - 30d: Last 30 days

    Ranking factors:
    - Total views
    - Click-through rate
    - Average time spent
    - Recency
    """
    # Calculate time threshold
    if timeframe == "24h":
        threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    elif timeframe == "7d":
        threshold = datetime.now(timezone.utc) - timedelta(days=7)
    else:  # 30d
        threshold = datetime.now(timezone.utc) - timedelta(days=30)

    # Query trending articles
    query = (
        select(Article)
        .where(and_(
            Article.is_active == True,
            Article.published_date >= threshold
        ))
        .order_by(
            desc(Article.total_views),
            desc(Article.click_through_rate),
            desc(Article.avg_time_spent)
        )
        .limit(limit)
    )

    result = await db.execute(query)
    articles = result.scalars().all()

    return TrendingArticlesResponse(
        trending=[ArticleResponse.model_validate(a) for a in articles],
        timeframe=timeframe,
        generated_at=datetime.now(timezone.utc)
    )


# ============================================================================
# SEARCH
# ============================================================================

@router.get("/search", response_model=SearchResultsResponse)
async def search_articles(
    query: str = Query(..., min_length=1, max_length=500),
    topics: Optional[List[str]] = Query(None),
    sources: Optional[List[str]] = Query(None),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    page: int = Query(1, ge=1, le=100),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("relevance", pattern="^(relevance|date|popularity)$"),
    db: AsyncSession = Depends(get_db)
):
    """
    Search articles with filters

    Features:
    - Full-text search in title and content
    - Topic filtering
    - Source filtering
    - Date range filtering
    - Multiple sort options

    Security:
    - Input sanitization (via Pydantic)
    - SQL injection prevention (parameterized queries)
    - Rate limiting applied
    """
    # Build search query
    search_query = select(Article).where(Article.is_active == True)

    # Text search (case-insensitive) - sanitize query
    safe_query = query.replace("%", "").replace("_", "").strip()
    search_query = search_query.where(
        or_(
            Article.title.ilike(f"%{safe_query}%"),
            Article.content.ilike(f"%{safe_query}%")
        )
    )

    # Topic filter
    if topics:
        safe_topics = [t.strip()[:50] for t in topics if t.strip()]
        if safe_topics:
            search_query = search_query.where(Article.topics.op('&&')(safe_topics))

    # Source filter
    if sources:
        safe_sources = [s.strip()[:100] for s in sources if s.strip()]
        if safe_sources:
            search_query = search_query.where(Article.source_name.in_(safe_sources))

    # Date range filter
    if from_date:
        search_query = search_query.where(Article.published_date >= from_date)
    if to_date:
        search_query = search_query.where(Article.published_date <= to_date)

    # Apply sorting
    if sort_by == "date":
        search_query = search_query.order_by(desc(Article.published_date))
    elif sort_by == "popularity":
        search_query = search_query.order_by(desc(Article.total_views))
    else:  # relevance
        search_query = search_query.order_by(desc(Article.published_date))

    # Get total count
    count_query = select(func.count()).select_from(search_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    search_query = search_query.limit(page_size).offset(offset)

    # Execute search
    result = await db.execute(search_query)
    articles = result.scalars().all()

    # Generate search suggestions
    suggestions = []
    if total == 0:
        suggestions = ["Try different keywords", "Check spelling"]

    # Generate facets
    facets = {}
    if articles:
        all_topics = {}
        all_sources = {}
        for article in articles:
            for topic in (article.topics or []):
                all_topics[topic] = all_topics.get(topic, 0) + 1
            all_sources[article.source_name] = all_sources.get(article.source_name, 0) + 1
        facets['topics'] = all_topics
        facets['sources'] = all_sources

    return SearchResultsResponse(
        query=query,
        total=total,
        results=[ArticleResponse.model_validate(a) for a in articles],
        suggestions=suggestions,
        facets=facets
    )

