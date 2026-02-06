from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ReadingHistory(Base):
    """User reading history for RL training"""
    __tablename__ = "reading_history"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.article_id"), nullable=False, index=True)

    # Interaction data
    clicked = Column(Boolean, default=False)
    time_spent_seconds = Column(Float, default=0.0)
    scroll_depth_percent = Column(Float, default=0.0)
    completed_reading = Column(Boolean, default=False)

    # Context
    device_type = Column(String(50), nullable=True)  # desktop, mobile, tablet
    session_id = Column(String(255), nullable=True)

    # Timestamps
    viewed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user = relationship("User", back_populates="reading_history")
    article = relationship("Article", back_populates="reading_history")

    def __repr__(self):
        return f"<ReadingHistory(user_id={self.user_id}, article_id={self.article_id}, clicked={self.clicked})>"

    def to_dict(self):
        """Convert to dictionary for RL service"""
        return {
            'article_id': str(self.article_id),
            'topics': self.article.topics if self.article else [],
            'time_spent_seconds': self.time_spent_seconds or 0.0,
            'clicked': self.clicked,
            'timestamp': self.viewed_at
        }


class UserFeedback(Base):
    """Explicit user feedback (likes, dislikes, ratings)"""
    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.article_id"), nullable=False, index=True)

    # Feedback data
    feedback_type = Column(String(50), nullable=False)  # positive, negative, neutral
    rating = Column(Integer, nullable=True)  # 1-5 stars
    comment = Column(Text, nullable=True)

    # Reasons (for negative feedback)
    reason = Column(String(255), nullable=True)  # not_interesting, misleading, offensive, etc.

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user = relationship("User", back_populates="feedback")
    article = relationship("Article", back_populates="feedback")

    def __repr__(self):
        return f"<UserFeedback(user_id={self.user_id}, article_id={self.article_id}, type={self.feedback_type})>"

    def to_dict(self):
        """Convert to dictionary for RL service"""
        return {
            'feedback_type': self.feedback_type,
            'article_topics': self.article.topics if self.article else [],
            'rating': self.rating,
            'timestamp': self.created_at
        }


