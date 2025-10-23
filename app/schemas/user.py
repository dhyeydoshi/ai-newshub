from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from uuid import UUID
import html


# ============================================================================
# Profile Schemas
# ============================================================================

class UserProfileResponse(BaseModel):
    """User profile response"""
    user_id: UUID
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    is_verified: bool
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    total_articles_read: int = 0
    avg_session_duration: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    """User profile update request"""
    full_name: Optional[str] = Field(None, max_length=255)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None

    @field_validator("full_name", "username")
    @classmethod
    def sanitize_strings(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize user input"""
        if v is None:
            return v
        return html.escape(v).strip()


# ============================================================================
# Preferences Schemas
# ============================================================================

class TopicPreference(BaseModel):
    """Topic preference item"""
    topic: str = Field(..., min_length=1, max_length=100)
    score: float = Field(..., ge=0.0, le=1.0)

    @field_validator("topic")
    @classmethod
    def sanitize_topic(cls, v: str) -> str:
        """Sanitize topic name"""
        return html.escape(v).strip().lower()


class UserPreferencesResponse(BaseModel):
    """User preferences response"""
    user_id: UUID
    topic_preferences: Dict[str, float] = Field(default_factory=dict)
    favorite_topics: List[str] = Field(default_factory=list)
    blocked_sources: List[str] = Field(default_factory=list)
    preferred_languages: List[str] = Field(default_factory=list, max_length=5)
    email_notifications: bool = True
    push_notifications: bool = True

    model_config = ConfigDict(from_attributes=True)


class UserPreferencesUpdate(BaseModel):
    """User preferences update request"""
    topic_preferences: Optional[Dict[str, float]] = None
    favorite_topics: Optional[List[str]] = Field(None, max_length=20)
    blocked_sources: Optional[List[str]] = Field(None, max_length=50)
    preferred_languages: Optional[List[str]] = Field(None, max_length=5)
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None

    @field_validator("topic_preferences")
    @classmethod
    def validate_topic_preferences(cls, v: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
        """Validate topic preferences"""
        if v is None:
            return v
        validated = {}
        for topic, score in v.items():
            clean_topic = html.escape(topic).strip()[:100]
            if 0.0 <= score <= 1.0:
                validated[clean_topic] = score
        return validated

    @field_validator("favorite_topics", "blocked_sources", "preferred_languages")
    @classmethod
    def sanitize_lists(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Sanitize list items"""
        if v is None:
            return v
        return [html.escape(item).strip()[:100] for item in v if item.strip()]


# ============================================================================
# Analytics Schemas
# ============================================================================

class UserEngagementStats(BaseModel):
    """User engagement statistics"""
    total_articles_viewed: int
    total_articles_read: int
    total_time_spent_minutes: float
    avg_reading_time_minutes: float
    most_read_topics: List[Dict[str, Any]] = Field(default_factory=list)
    reading_streak_days: int = 0
    last_active: Optional[datetime] = None


class ReadingHistoryItem(BaseModel):
    """Reading history item"""
    article_id: int
    article_title: str
    article_url: str
    topics: List[str]
    time_spent_seconds: float
    completed_reading: bool
    viewed_at: datetime


class ReadingHistoryResponse(BaseModel):
    """Reading history response"""
    total: int
    page: int
    page_size: int
    items: List[ReadingHistoryItem]


# ============================================================================
# Account Management Schemas
# ============================================================================

class AccountDeletionRequest(BaseModel):
    """Account deletion request"""
    password: str
    confirmation: str = Field(..., pattern="^DELETE MY ACCOUNT$")
    reason: Optional[str] = Field(None, max_length=500)

    @field_validator("reason")
    @classmethod
    def sanitize_reason(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize deletion reason"""
        if v is None:
            return v
        return html.escape(v).strip()


class DataExportRequest(BaseModel):
    """GDPR data export request"""
    include_reading_history: bool = True
    include_preferences: bool = True
    include_feedback: bool = True
    format: str = Field("json", pattern="^(json|csv)$")


class DataExportResponse(BaseModel):
    """Data export response"""
    user_data: Dict[str, Any]
    export_date: datetime
    format: str
