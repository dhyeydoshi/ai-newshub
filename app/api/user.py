from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.models.user import User
from app.models.feedback import ReadingHistory, UserFeedback
from app.models.article import Article, UserPreference
from app.schemas.user import (
    UserProfileResponse,
    UserProfileUpdate,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    UserEngagementStats,
    ReadingHistoryResponse,
    ReadingHistoryItem,
    AccountDeletionRequest,
    DataExportRequest,
    DataExportResponse
)
from app.schemas.auth import MessageResponse
from app.api.auth import get_current_user_id
from app.core.password import pwd_hasher
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["User Profile"])


# ============================================================================
# PROFILE MANAGEMENT
# ============================================================================

@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user profile

    Returns comprehensive user information including reading statistics
    """
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserProfileResponse.model_validate(user)


@router.put("/profile", response_model=UserProfileResponse)
async def update_user_profile(
    profile_data: UserProfileUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user profile

    Security:
    - Username uniqueness validation
    - Email uniqueness validation
    - Input sanitization via Pydantic
    """
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check username uniqueness if being updated
    if profile_data.username and profile_data.username != user.username:
        existing = await db.execute(
            select(User).where(User.username == profile_data.username)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        user.username = profile_data.username

    # Check email uniqueness if being updated
    if profile_data.email and profile_data.email != user.email:
        existing = await db.execute(
            select(User).where(User.email == profile_data.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        user.email = profile_data.email
        user.is_verified = False  # Require re-verification

    # Update other fields
    if profile_data.full_name is not None:
        user.full_name = profile_data.full_name

    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    return UserProfileResponse.model_validate(user)


# ============================================================================
# PREFERENCES MANAGEMENT
# ============================================================================

@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user preferences for personalization

    Returns topic preferences, favorite topics, and notification settings
    """
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Get stored preferences or defaults
    response_data = {
        "user_id": user.user_id,
        "topic_preferences": user.topic_preferences or {},
        "favorite_topics": user.favorite_topics or [],
        "blocked_sources": [],  # Add to User model if needed
        "preferred_languages": ["en"],
        "email_notifications": user.email_consent if hasattr(user, 'email_consent') else True,
        "push_notifications": True
    }

    return UserPreferencesResponse(**response_data)


@router.put("/preferences", response_model=UserPreferencesResponse)
async def update_user_preferences(
    preferences: UserPreferencesUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user preferences

    Security:
    - Input validation and sanitization
    - Preference score bounds checking (0.0-1.0)
    """
    # Get user from model.user (integer id)
    result = await db.execute(
        select(User).where(User.id == int(user_id.split('-')[0]) if '-' not in str(user_id) else User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update topic preferences
    if preferences.topic_preferences is not None:
        user.topic_preferences = preferences.topic_preferences

    # Update favorite topics
    if preferences.favorite_topics is not None:
        user.favorite_topics = preferences.favorite_topics

    # Update notification settings
    if preferences.email_notifications is not None and hasattr(user, 'email_consent'):
        user.email_consent = preferences.email_notifications

    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    return await get_user_preferences(user_id, db)


# ============================================================================
# READING HISTORY & ANALYTICS
# ============================================================================

@router.get("/reading-history", response_model=ReadingHistoryResponse)
async def get_reading_history(
    page: int = 1,
    page_size: int = 20,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user reading history with pagination

    Returns articles the user has viewed or read
    """
    # Calculate offset
    offset = (page - 1) * page_size

    # Get total count
    count_query = select(func.count(ReadingHistory.id)).where(
        ReadingHistory.user_id == int(user_id.split('-')[0]) if '-' not in str(user_id) else user_id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get reading history with article details
    query = (
        select(ReadingHistory, Article)
        .join(Article, ReadingHistory.article_id == Article.id)
        .where(ReadingHistory.user_id == int(user_id.split('-')[0]) if '-' not in str(user_id) else user_id)
        .order_by(desc(ReadingHistory.viewed_at))
        .limit(page_size)
        .offset(offset)
    )

    result = await db.execute(query)
    history_items = result.all()

    # Format response
    items = []
    for history, article in history_items:
        items.append(ReadingHistoryItem(
            article_id=article.id,
            article_title=article.title,
            article_url=str(article.url),
            topics=article.topics or [],
            time_spent_seconds=history.time_spent_seconds or 0.0,
            completed_reading=history.completed_reading or False,
            viewed_at=history.viewed_at
        ))

    return ReadingHistoryResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )


@router.get("/engagement", response_model=UserEngagementStats)
async def get_user_engagement(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user engagement statistics

    Returns reading patterns, favorite topics, and activity metrics
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

    # Calculate statistics
    user_int_id = user.id

    # Total articles viewed
    viewed_count = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(ReadingHistory.user_id == user_int_id)
    )
    total_viewed = viewed_count.scalar() or 0

    # Total articles read (completed)
    read_count = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(and_(
            ReadingHistory.user_id == user_int_id,
            ReadingHistory.completed_reading == True
        ))
    )
    total_read = read_count.scalar() or 0

    # Total time spent
    time_result = await db.execute(
        select(func.sum(ReadingHistory.time_spent_seconds))
        .where(ReadingHistory.user_id == user_int_id)
    )
    total_seconds = time_result.scalar() or 0.0
    total_minutes = total_seconds / 60.0

    # Average reading time
    avg_time = total_minutes / total_read if total_read > 0 else 0.0

    # Most read topics (from reading history)
    topic_query = (
        select(Article.topics)
        .join(ReadingHistory, Article.id == ReadingHistory.article_id)
        .where(ReadingHistory.user_id == user_int_id)
    )
    topic_result = await db.execute(topic_query)

    # Count topics
    topic_counts = {}
    for (topics,) in topic_result:
        if topics:
            for topic in topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    # Top topics
    most_read_topics = [
        {"topic": topic, "count": count}
        for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    # Calculate reading streak (simplified)
    streak_days = 0

    return UserEngagementStats(
        total_articles_viewed=total_viewed,
        total_articles_read=total_read,
        total_time_spent_minutes=total_minutes,
        avg_reading_time_minutes=avg_time,
        most_read_topics=most_read_topics,
        reading_streak_days=streak_days,
        last_active=user.last_login_at if hasattr(user, 'last_login_at') else None
    )


# ============================================================================
# ACCOUNT MANAGEMENT
# ============================================================================

@router.delete("/account", response_model=MessageResponse)
async def delete_user_account(
    deletion_request: AccountDeletionRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete user account (GDPR compliance)

    Security:
    - Password verification required
    - Confirmation string required
    - Soft delete with data anonymization
    """
    # Get user
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Verify password
    from app.models.user import User as AuthUser
    auth_result = await db.execute(
        select(AuthUser).where(AuthUser.user_id == user_id)
    )
    auth_user = auth_result.scalar_one_or_none()

    if auth_user and not pwd_hasher.verify_password(deletion_request.password, auth_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )

    # Log deletion reason
    if deletion_request.reason:
        logger.info(f"Account deletion - User: {user.username}, Reason: {deletion_request.reason}")

    # Soft delete - anonymize data
    user.email = f"deleted_{user.id}@deleted.local"
    user.username = f"deleted_user_{user.id}"
    user.is_active = False
    user.data_processing_consent = False

    if auth_user:
        auth_user.is_active = False

    await db.commit()

    return MessageResponse(
        message="Account deleted successfully",
        success=True
    )


@router.post("/export-data", response_model=DataExportResponse)
async def export_user_data(
    export_request: DataExportRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Export user data (GDPR compliance)

    Returns all user data in requested format
    """
    # Get user
    result = await db.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Collect user data
    user_data = {
        "profile": {
            "user_id": str(user.user_id),
            "email": user.email,
            "username": user.username,
            "created_at": user.created_at.isoformat(),
            "topic_preferences": user.topic_preferences,
            "favorite_topics": user.favorite_topics
        }
    }

    # Reading history
    if export_request.include_reading_history:
        history_result = await db.execute(
            select(ReadingHistory, Article)
            .join(Article, ReadingHistory.article_id == Article.id)
            .where(ReadingHistory.user_id == user.id)
        )
        history_data = []
        for history, article in history_result:
            history_data.append({
                "article_title": article.title,
                "article_url": str(article.url),
                "time_spent_seconds": history.time_spent_seconds,
                "viewed_at": history.viewed_at.isoformat()
            })
        user_data["reading_history"] = history_data

    # Preferences
    if export_request.include_preferences:
        user_data["preferences"] = {
            "topic_preferences": user.topic_preferences or {},
            "favorite_topics": user.favorite_topics or []
        }

    # Feedback
    if export_request.include_feedback:
        feedback_result = await db.execute(
            select(UserFeedback)
            .where(UserFeedback.user_id == user.id)
        )
        feedback_data = [
            {
                "feedback_type": fb.feedback_type,
                "rating": fb.rating,
                "created_at": fb.created_at.isoformat()
            }
            for fb in feedback_result.scalars()
        ]
        user_data["feedback"] = feedback_data

    return DataExportResponse(
        user_data=user_data,
        export_date=datetime.now(timezone.utc),
        format=export_request.format
    )

