from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.feedback import UserFeedback, ReadingHistory
from app.models.article import Article
from app.models.user import User
from app.schemas.feedback import (
    ArticleFeedbackRequest,
    SummaryFeedbackRequest,
    FeedbackResponse,
    ReadingInteractionRequest,
    InteractionResponse
)
from app.schemas.auth import MessageResponse
from app.api.auth import get_current_user_id
from app.services.rl_service import rl_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["Feedback & Interactions"])


@router.post("/article", response_model=FeedbackResponse)
async def submit_article_feedback(
    feedback: ArticleFeedbackRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    # Verify article exists
    article_result = await db.execute(
        select(Article).where(Article.article_id == feedback.article_id)
    )
    article = article_result.scalar_one_or_none()

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

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

    # Check if feedback already exists
    existing_feedback = await db.execute(
        select(UserFeedback).where(
            and_(
                UserFeedback.user_id == user.user_id,
                UserFeedback.article_id == feedback.article_id
            )
        )
    )
    existing = existing_feedback.scalar_one_or_none()

    if existing:
        # Update existing feedback
        existing.feedback_type = feedback.feedback_type
        existing.rating = feedback.rating
        existing.comment = feedback.comment
        existing.reason = feedback.reason
        existing.created_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return FeedbackResponse.model_validate(existing)

    # Create new feedback
    new_feedback = UserFeedback(
        user_id=user.user_id,
        article_id=feedback.article_id,
        feedback_type=feedback.feedback_type,
        rating=feedback.rating,
        comment=feedback.comment,
        reason=feedback.reason,
        created_at=datetime.now(timezone.utc)
    )

    db.add(new_feedback)
    await db.commit()
    await db.refresh(new_feedback)

    # Update RL preferences from explicit feedback
    try:
        await rl_service.update_from_feedback(
            user_id=str(user.user_id),
            article_id=str(article.article_id),
            topics=article.topics or [],
            feedback=feedback.feedback_type,
            engagement_metrics=None
        )
    except Exception as e:
        logger.warning(f"RL update failed (feedback): {e}")

    logger.info(f"Feedback submitted - User: {user.user_id}, Article: {feedback.article_id}, Type: {feedback.feedback_type}")

    return FeedbackResponse.model_validate(new_feedback)


@router.post("/summary", response_model=MessageResponse)
async def submit_summary_feedback(
    feedback: SummaryFeedbackRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    # Verify article exists
    article_result = await db.execute(
        select(Article).where(Article.article_id == feedback.article_id)
    )
    article = article_result.scalar_one_or_none()

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    logger.info(
        f"Summary feedback - Article: {feedback.article_id}, "
        f"Helpful: {feedback.summary_helpful}, "
        f"Accuracy: {feedback.accuracy_rating}, "
        f"Completeness: {feedback.completeness_rating}, "
        f"Clarity: {feedback.clarity_rating}"
    )

    return MessageResponse(
        message="Summary feedback submitted successfully",
        success=True
    )


@router.post("/interaction", response_model=InteractionResponse)
async def track_reading_interaction(
    interaction: ReadingInteractionRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    # Verify article exists
    article_result = await db.execute(
        select(Article).where(Article.article_id == interaction.article_id)
    )
    article = article_result.scalar_one_or_none()

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

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

    # Check if interaction already exists for this session
    session_id = request.headers.get("X-Session-ID")

    existing = None
    if session_id:
        existing_result = await db.execute(
            select(ReadingHistory).where(
                and_(
                    ReadingHistory.user_id == user.user_id,
                    ReadingHistory.article_id == interaction.article_id,
                    ReadingHistory.session_id == session_id
                )
            )
        )
        existing = existing_result.scalar_one_or_none()

    if existing:
        # Update existing interaction
        existing.time_spent_seconds = max(existing.time_spent_seconds, interaction.time_spent_seconds)
        existing.scroll_depth_percent = max(existing.scroll_depth_percent, interaction.scroll_depth_percent)
        existing.completed_reading = existing.completed_reading or interaction.completed_reading
        existing.clicked = existing.clicked or interaction.clicked
        await db.commit()
        await db.refresh(existing)

        # Update article metrics
        await update_article_metrics(article.article_id, db)

        return InteractionResponse.model_validate(existing)

    # Create new interaction record
    new_interaction = ReadingHistory(
        user_id=user.user_id,
        article_id=interaction.article_id,
        clicked=interaction.clicked,
        time_spent_seconds=interaction.time_spent_seconds,
        scroll_depth_percent=interaction.scroll_depth_percent,
        completed_reading=interaction.completed_reading,
        device_type=interaction.device_type,
        session_id=session_id,
        viewed_at=datetime.now(timezone.utc)
    )

    db.add(new_interaction)

    # Update user statistics
    user.total_articles_read = (user.total_articles_read or 0) + (1 if interaction.completed_reading else 0)

    # Update article click count
    if interaction.clicked:
        article.total_clicks += 1

    await db.commit()
    await db.refresh(new_interaction)

    # Update article engagement metrics (async)
    await update_article_metrics(article.article_id, db)

    # Update RL preferences from interaction signal
    try:
        if interaction.completed_reading or interaction.time_spent_seconds >= 30:
            inferred_feedback = "positive"
        elif interaction.clicked:
            inferred_feedback = "neutral"
        else:
            inferred_feedback = "negative"

        await rl_service.update_from_feedback(
            user_id=str(user.user_id),
            article_id=str(article.article_id),
            topics=article.topics or [],
            feedback=inferred_feedback,
            engagement_metrics={"time_spent_seconds": interaction.time_spent_seconds}
        )
    except Exception as e:
        logger.warning(f"RL update failed (interaction): {e}")

    logger.info(f"Interaction tracked - User: {user.user_id}, Article: {interaction.article_id}, Time: {interaction.time_spent_seconds}s")

    return InteractionResponse.model_validate(new_interaction)


async def update_article_metrics(article_id, db: AsyncSession):
    # Calculate average time spent
    avg_time_result = await db.execute(
        select(func.avg(ReadingHistory.time_spent_seconds))
        .where(ReadingHistory.article_id == article_id)
    )
    avg_time = avg_time_result.scalar() or 0.0

    # Calculate completion rate
    total_views_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(ReadingHistory.article_id == article_id)
    )
    total_views = total_views_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count(ReadingHistory.id))
        .where(and_(
            ReadingHistory.article_id == article_id,
            ReadingHistory.completed_reading == True
        ))
    )
    completed = completed_result.scalar() or 0

    # Get article
    article_result = await db.execute(
        select(Article).where(Article.article_id == article_id)
    )
    article = article_result.scalar_one_or_none()

    if article:
        article.avg_time_spent = avg_time
        article.total_views = total_views

        # Calculate CTR (clicks / views)
        if total_views > 0:
            article.click_through_rate = article.total_clicks / total_views

        await db.commit()


@router.post("/batch-interactions", response_model=MessageResponse)
async def submit_batch_interactions(
    interactions: List[ReadingInteractionRequest],
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    if len(interactions) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 interactions per batch"
        )

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

    # Process each interaction
    created_count = 0
    for interaction in interactions:
        # Verify article exists
        article_result = await db.execute(
            select(Article).where(Article.article_id == interaction.article_id)
        )
        if not article_result.scalar_one_or_none():
            continue  # Skip invalid articles

        # Create interaction record
        new_interaction = ReadingHistory(
            user_id=user.user_id,
            article_id=interaction.article_id,
            clicked=interaction.clicked,
            time_spent_seconds=interaction.time_spent_seconds,
            scroll_depth_percent=interaction.scroll_depth_percent,
            completed_reading=interaction.completed_reading,
            device_type=interaction.device_type,
            viewed_at=datetime.now(timezone.utc)
        )
        db.add(new_interaction)
        created_count += 1

    await db.commit()

    logger.info(f"Batch interactions submitted - User: {user.user_id}, Count: {created_count}")

    return MessageResponse(
        message=f"Successfully processed {created_count} interactions",
        success=True
    )
