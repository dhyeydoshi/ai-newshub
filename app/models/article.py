"""
Article Model for News Recommendation System
Stores news articles with content, topics, and metadata
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, Float, ARRAY, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.core.database import Base


class Article(Base):
    """News article model"""
    __tablename__ = "articles"

    # Primary key
    article_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)


    # Article content
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    excerpt = Column(Text, nullable=True)
    url = Column(String(2048), unique=True, nullable=False)

    # Source information
    source_name = Column(String(255), nullable=False)
    source_url = Column(String(2048), nullable=True)
    author = Column(String(255), nullable=True)

    # Categorization
    category = Column(String(100), nullable=True)
    topics = Column(ARRAY(Text), default=list, server_default='{}')
    tags = Column(ARRAY(Text), default=list, server_default='{}')
    language = Column(String(10), default='en', server_default='en')

    meta_data = Column(JSONB, default=dict, server_default='{}')

    # Publishing information
    published_date = Column(DateTime(timezone=True), nullable=False)
    scraped_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          server_default='CURRENT_TIMESTAMP')

    # summary = Column(Text, nullable=True)
    #
    # # Metadata
    # author = Column(String(255), nullable=True)
    # source = Column(String(255), nullable=False)
    # url = Column(String(1000), unique=True, nullable=False)
    image_url = Column(String(1000), nullable=True)
    #
    # # Categorization
    # topics = Column(JSON, default=list)  # ["technology", "ai", "business"]
    # category = Column(String(100), nullable=True)
    # tags = Column(JSON, default=list)

    # Publishing info
    # published_at = Column(DateTime(timezone=True), nullable=False)
    # scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Content metrics
    word_count = Column(Integer, default=0)
    reading_time_minutes = Column(Integer, default=0)
    content_hash = Column(String(64), unique=True, nullable=True)

    # Engagement metrics
    total_views = Column(Integer, default=0)
    total_clicks = Column(Integer, default=0)
    avg_time_spent = Column(Float, default=0.0)
    click_through_rate = Column(Float, default=0.0)

    # Status
    is_active = Column(Boolean, default=True, server_default='true')
    moderation_status = Column(
        String(20),
        default='pending',
        server_default='pending',
        nullable=False
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "moderation_status IN ('pending', 'approved', 'rejected')",
            name='check_moderation_status'
        ),
    )

    # Relationships - OPTIMIZED with lazy loading
    # Use lazy='dynamic' for large collections that may need filtering
    reading_history = relationship(
        "ReadingHistory",
        back_populates="article",
        lazy='dynamic'  # Returns query object - allows filtering without loading all records
    )
    feedback = relationship(
        "UserFeedback",
        back_populates="article",
        lazy='dynamic'  # Returns query object - good for potentially large feedback collections
    )

    def __repr__(self):
        return f"<Article(id={self.article_id}, title={self.title[:50]})>"

    def to_dict(self):
        """Convert to dictionary for RL service"""
        return {
            'article_id': self.article_id,
            'title': self.title,
            'content': self.content,
            'excerpt': self.excerpt,
            'author': self.author,
            'source': self.source_name,
            'source_url': self.source_url,
            'url': self.url,
            'topics': self.topics or [],
            'tags': self.tags or [],
            'category': self.category,
            'language': self.language,
            'published_date': self.published_date,
            'word_count': self.word_count or (len(self.content.split()) if self.content else 0),
            'reading_time_minutes': self.reading_time_minutes,
            'metadata': self.metadata or {}

        }


class UserPreference(Base):
    """User topic preferences for personalization"""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    topic = Column(String(100), nullable=False, index=True)
    preference_score = Column(Float, default=0.5)  # 0.0 to 1.0

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id}, topic={self.topic}, score={self.preference_score})>"
