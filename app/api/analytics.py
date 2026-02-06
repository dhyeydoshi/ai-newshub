from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.models.feedback import ReadingHistory, UserFeedback
from app.models.article import Article
from app.models.user import User
from app.schemas.feedback import (
    EngagementMetrics,
    UserEngagementAnalytics,
    EngagementAnalyticsResponse
)
from app.api.auth import get_current_user_id
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/engagement", response_model=EngagementAnalyticsResponse)
async def get_engagement_analytics(
    timeframe: str = Query("7d", pattern="^(24h|7d|30d|90d)$"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    # Calculate time threshold
    if timeframe == "24h":
        threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    elif timeframe == "7d":
        threshold = datetime.now(timezone.utc) - timedelta(days=7)
    elif timeframe == "30d":
        threshold = datetime.now(timezone.utc) - timedelta(days=30)
    else:  # 90d
        threshold = datetime.now(timezone.utc) - timedelta(days=90)

    # Total active users in timeframe
    active_users_result = await db.execute(
        select(func.count(func.distinct(ReadingHistory.user_id)))
        .where(ReadingHistory.viewed_at >= threshold)
    )
    total_users_active = active_users_result.scalar() or 0

    # Total articles viewed
    total_views_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(ReadingHistory.viewed_at >= threshold)
    )
    total_articles_viewed = total_views_result.scalar() or 0

    completed_reads_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(and_(
            ReadingHistory.viewed_at >= threshold,
            ReadingHistory.completed_reading == True
        ))
    )
    completed_reads = completed_reads_result.scalar() or 0
    avg_engagement_score = (completed_reads / total_articles_viewed * 100) if total_articles_viewed > 0 else 0.0

    # Top articles by engagement
    top_articles_query = (
        select(
            Article.article_id,
            func.count(ReadingHistory.id).label('total_views'),
            func.count(func.nullif(ReadingHistory.clicked, False)).label('total_clicks'),
            func.avg(ReadingHistory.time_spent_seconds).label('avg_time_spent'),
            func.count(func.nullif(ReadingHistory.completed_reading, False)).label('completions')
        )
        .join(ReadingHistory, Article.article_id == ReadingHistory.article_id)
        .where(ReadingHistory.viewed_at >= threshold)
        .group_by(Article.article_id)
        .order_by(desc('total_views'))
        .limit(10)
    )

    top_articles_result = await db.execute(top_articles_query)
    top_articles_data = top_articles_result.all()

    # Get feedback counts for top articles
    top_articles = []
    for article_data in top_articles_data:
        article_id = article_data.article_id

        # Positive feedback count
        positive_feedback_result = await db.execute(
            select(func.count(UserFeedback.id))
            .where(and_(
                UserFeedback.article_id == article_id,
                UserFeedback.feedback_type == 'positive'
            ))
        )
        positive_count = positive_feedback_result.scalar() or 0

        # Negative feedback count
        negative_feedback_result = await db.execute(
            select(func.count(UserFeedback.id))
            .where(and_(
                UserFeedback.article_id == article_id,
                UserFeedback.feedback_type == 'negative'
            ))
        )
        negative_count = negative_feedback_result.scalar() or 0

        # Average rating
        avg_rating_result = await db.execute(
            select(func.avg(UserFeedback.rating))
            .where(UserFeedback.article_id == article_id)
        )
        avg_rating = avg_rating_result.scalar()

        # Calculate completion rate
        completion_rate = (article_data.completions / article_data.total_views) if article_data.total_views > 0 else 0.0

        top_articles.append(
            EngagementMetrics(
                article_id=article_id,
                total_views=article_data.total_views,
                total_clicks=article_data.total_clicks,
                avg_time_spent_seconds=float(article_data.avg_time_spent or 0.0),
                completion_rate=completion_rate,
                positive_feedback_count=positive_count,
                negative_feedback_count=negative_count,
                avg_rating=float(avg_rating) if avg_rating else None
            )
        )

    # Top topics by engagement
    top_topics_query = (
        select(Article.topics)
        .join(ReadingHistory, Article.article_id == ReadingHistory.article_id)
        .where(ReadingHistory.viewed_at >= threshold)
    )
    topics_result = await db.execute(top_topics_query)

    # Count topics
    topic_counts = {}
    for (topics,) in topics_result:
        if topics:
            for topic in topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    # Get top 10 topics
    top_topics = [
        {"topic": topic, "count": count}
        for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    return EngagementAnalyticsResponse(
        timeframe=timeframe,
        total_users_active=total_users_active,
        total_articles_viewed=total_articles_viewed,
        avg_engagement_score=avg_engagement_score,
        top_articles=top_articles,
        top_topics=top_topics
    )


@router.get("/user/engagement", response_model=UserEngagementAnalytics)
async def get_user_engagement_analytics(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
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

    # Total interactions
    total_interactions_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(ReadingHistory.user_id == user.user_id)
    )
    total_interactions = total_interactions_result.scalar() or 0

    # Average session duration
    avg_duration_result = await db.execute(
        select(func.avg(ReadingHistory.time_spent_seconds))
        .where(ReadingHistory.user_id == user.user_id)
    )
    avg_duration_seconds = avg_duration_result.scalar() or 0.0
    avg_session_duration_minutes = avg_duration_seconds / 60.0

    # Articles read count
    articles_read_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(and_(
            ReadingHistory.user_id == user.user_id,
            ReadingHistory.completed_reading == True
        ))
    )
    articles_read_count = articles_read_result.scalar() or 0

    # Favorite topics (from reading history)
    topics_query = (
        select(Article.topics)
        .join(ReadingHistory, Article.article_id == ReadingHistory.article_id)
        .where(ReadingHistory.user_id == user.user_id)
    )
    topics_result = await db.execute(topics_query)

    # Count topics
    topic_counts = {}
    for (topics,) in topics_result:
        if topics:
            for topic in topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    # Get top 5 topics
    favorite_topics = [
        topic for topic, _ in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    # Calculate engagement score (0-100)
    engagement_score = 0.0
    if total_interactions > 0:
        completion_rate = articles_read_count / total_interactions

        # Recent activity bonus (last 7 days)
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_activity_result = await db.execute(
            select(func.count(ReadingHistory.id))
            .where(and_(
                ReadingHistory.user_id == user.user_id,
                ReadingHistory.viewed_at >= week_ago
            ))
        )
        recent_activity = recent_activity_result.scalar() or 0
        recency_factor = min(recent_activity / 10.0, 1.0)

        engagement_score = (completion_rate * 50) + (min(total_interactions / 100.0, 1.0) * 30) + (recency_factor * 20)

    # Last active
    last_active_result = await db.execute(
        select(func.max(ReadingHistory.viewed_at))
        .where(ReadingHistory.user_id == user.user_id)
    )
    last_active = last_active_result.scalar()

    return UserEngagementAnalytics(
        user_id=str(user.user_id),
        total_interactions=total_interactions,
        avg_session_duration_minutes=avg_session_duration_minutes,
        articles_read_count=articles_read_count,
        favorite_topics=favorite_topics,
        engagement_score=engagement_score,
        last_active=last_active
    )


@router.get("/article/{article_id}", response_model=EngagementMetrics)
async def get_article_analytics(
    article_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    # Verify article exists
    from uuid import UUID

    try:
        uuid_article_id = UUID(article_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid article ID format"
        )

    article_result = await db.execute(
        select(Article).where(Article.article_id == uuid_article_id)
    )
    article = article_result.scalar_one_or_none()

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    # Total views
    total_views_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(ReadingHistory.article_id == uuid_article_id)
    )
    total_views = total_views_result.scalar() or 0

    # Total clicks
    total_clicks_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(and_(
            ReadingHistory.article_id == uuid_article_id,
            ReadingHistory.clicked == True
        ))
    )
    total_clicks = total_clicks_result.scalar() or 0

    # Average time spent
    avg_time_result = await db.execute(
        select(func.avg(ReadingHistory.time_spent_seconds))
        .where(ReadingHistory.article_id == uuid_article_id)
    )
    avg_time_spent = float(avg_time_result.scalar() or 0.0)

    # Completion rate
    completions_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(and_(
            ReadingHistory.article_id == uuid_article_id,
            ReadingHistory.completed_reading == True
        ))
    )
    completions = completions_result.scalar() or 0
    completion_rate = (completions / total_views) if total_views > 0 else 0.0

    # Positive feedback count
    positive_feedback_result = await db.execute(
        select(func.count(UserFeedback.id))
        .where(and_(
            UserFeedback.article_id == uuid_article_id,
            UserFeedback.feedback_type == 'positive'
        ))
    )
    positive_count = positive_feedback_result.scalar() or 0

    # Negative feedback count
    negative_feedback_result = await db.execute(
        select(func.count(UserFeedback.id))
        .where(and_(
            UserFeedback.article_id == uuid_article_id,
            UserFeedback.feedback_type == 'negative'
        ))
    )
    negative_count = negative_feedback_result.scalar() or 0

    # Average rating
    avg_rating_result = await db.execute(
        select(func.avg(UserFeedback.rating))
        .where(UserFeedback.article_id == uuid_article_id)
    )
    avg_rating = avg_rating_result.scalar()

    return EngagementMetrics(
        article_id=uuid_article_id,
        total_views=total_views,
        total_clicks=total_clicks,
        avg_time_spent_seconds=avg_time_spent,
        completion_rate=completion_rate,
        positive_feedback_count=positive_count,
        negative_feedback_count=negative_count,
        avg_rating=float(avg_rating) if avg_rating else None
    )
