from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
import html
from uuid import UUID


class ArticleFeedbackRequest(BaseModel):
    """Article feedback submission"""
    article_id: UUID
    feedback_type: str = Field(..., pattern="^(positive|negative|neutral)$")
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)
    reason: Optional[str] = Field(None, max_length=255)

    @field_validator("comment", "reason")
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize text input"""
        if v is None:
            return v
        return html.escape(v).strip()


class SummaryFeedbackRequest(BaseModel):
    """Summary quality feedback"""
    article_id: UUID
    summary_helpful: bool
    accuracy_rating: int = Field(..., ge=1, le=5)
    completeness_rating: int = Field(..., ge=1, le=5)
    clarity_rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=500)

    @field_validator("comment")
    @classmethod
    def sanitize_comment(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize comment"""
        if v is None:
            return v
        return html.escape(v).strip()


class FeedbackResponse(BaseModel):
    """Feedback submission response"""
    id: int
    article_id: UUID
    feedback_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReadingInteractionRequest(BaseModel):
    """Track reading interaction"""
    article_id: UUID
    time_spent_seconds: float = Field(..., ge=0.0, le=7200.0)  # Max 2 hours
    scroll_depth_percent: float = Field(..., ge=0.0, le=100.0)
    completed_reading: bool = False
    clicked: bool = True
    device_type: Optional[str] = Field(None, pattern="^(desktop|mobile|tablet)$")

    @field_validator("device_type")
    @classmethod
    def sanitize_device(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize device type"""
        if v is None:
            return v
        return html.escape(v).strip()


class InteractionResponse(BaseModel):
    """Reading interaction response"""
    id: int
    article_id: UUID
    time_spent_seconds: float
    completed_reading: bool
    viewed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EngagementMetrics(BaseModel):
    """Article engagement metrics"""
    article_id: UUID
    total_views: int
    total_clicks: int
    avg_time_spent_seconds: float
    completion_rate: float
    positive_feedback_count: int
    negative_feedback_count: int
    avg_rating: Optional[float] = None


class UserEngagementAnalytics(BaseModel):
    """User engagement analytics"""
    user_id: str
    total_interactions: int
    avg_session_duration_minutes: float
    articles_read_count: int
    favorite_topics: List[str]
    engagement_score: float = Field(..., ge=0.0, le=100.0)
    last_active: datetime


class EngagementAnalyticsResponse(BaseModel):
    """Engagement analytics response"""
    timeframe: str
    total_users_active: int
    total_articles_viewed: int
    avg_engagement_score: float
    top_articles: List[EngagementMetrics] = Field(default_factory=list, max_length=10)
    top_topics: List[dict] = Field(default_factory=list, max_length=10)
