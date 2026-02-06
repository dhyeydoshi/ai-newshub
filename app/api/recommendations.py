from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.models.article import Article
from app.models.user import User
from app.models.feedback import ReadingHistory
from app.schemas.article import ArticleResponse
from app.api.auth import get_current_user_id
from app.services.rl_service import rl_service
from app.dependencies.cache import (
    get_cached_response,
    set_cached_response,
    CacheConfig,
    build_recommendations_key
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/", response_model=List[ArticleResponse])
async def get_recommendations(
    limit: int = Query(10, ge=1, le=50),
    exclude_read: bool = Query(True),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    # Build cache key
    cache_key = build_recommendations_key(
        user_id=user_id,
        limit=limit,
        exclude_read=exclude_read,
        min_score=min_score
    )

    # Check cache first
    cached_response = await get_cached_response(cache_key)
    if cached_response:
        logger.info(f" Cache HIT for recommendations: {user_id}")
        return [ArticleResponse(**item) for item in cached_response]

    logger.info(f" Cache MISS for recommendations: {user_id} - Computing recommendations")

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

    # Get candidate articles (recent, unread)
    query = select(Article).where(Article.is_active == True)

    # Exclude read articles if requested
    if exclude_read:
        read_articles_subquery = (
            select(ReadingHistory.article_id)
            .where(ReadingHistory.user_id == user.user_id)
        )
        query = query.where(Article.article_id.not_in(read_articles_subquery))

    # Get recent articles (last 7 days)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    query = query.where(Article.published_date >= week_ago)

    # Limit candidates for performance
    query = query.order_by(desc(Article.published_date)).limit(100)

    result = await db.execute(query)
    candidate_articles = list(result.scalars().all())

    if not candidate_articles:
        return []

    # Get RL recommendations
    try:
        article_map = {str(article.article_id): article for article in candidate_articles}
        recommendations = await rl_service.get_recommendations(
            user_id=str(user.user_id),
            candidate_articles=[article.to_dict() for article in candidate_articles],
            top_k=limit
        )

        filtered_articles = []
        for rec in recommendations:
            if rec.get('score', 0.0) < min_score:
                continue
            article = article_map.get(rec.get('article_id'))
            if article:
                filtered_articles.append(ArticleResponse.model_validate(article))

        # Cache the response
        await set_cached_response(
            cache_key,
            [item.model_dump() for item in filtered_articles],
            CacheConfig.RECOMMENDATIONS_TTL
        )

        return filtered_articles

    except Exception as e:
        logger.error(f"RL service error: {e}")
        # Fallback to simple personalization
        user_preferences = user.topic_preferences or {}
        favorite_topics = user.favorite_topics or []

        # Simple scoring
        scored_articles = []
        for article in candidate_articles:
            score = 0.0
            article_topics = article.topics or []

            for topic in article_topics:
                if topic in favorite_topics:
                    score += 1.0
                elif topic in user_preferences:
                    score += user_preferences[topic]

            if article_topics:
                score = score / len(article_topics)

            if score >= min_score:
                scored_articles.append((article, score))

        # Sort and limit
        scored_articles.sort(key=lambda x: x[1], reverse=True)
        fallback_recommendations = [
            ArticleResponse.model_validate(article)
            for article, _ in scored_articles[:limit]
        ]

        # Cache fallback results with shorter TTL
        await set_cached_response(
            cache_key,
            [item.model_dump() for item in fallback_recommendations],
            60  # 1 minute for fallback
        )

        return fallback_recommendations

