
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Float, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Text

from app.core.database import Base


class User(Base):
    """User account model"""
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}

    # Primary key
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)


    # Authentication
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    full_name = Column(String(255))


    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    # is_superuser = Column(Boolean, default=False)
    email_verified_at = Column(DateTime(timezone=True))
    verification_token = Column(String(255), unique=True, index=True)
    verification_token_expires = Column(DateTime(timezone=True))

    is_locked = Column(Boolean, default=False)
    locked_until = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, default=0)
    last_failed_login = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    last_password_change = Column(DateTime(timezone=True))

    reset_token = Column(String(255), unique=True, index=True)
    reset_token_expires = Column(DateTime(timezone=True))




    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime(timezone=True))


    # RL-specific fields
    topic_preferences = Column(JSON, default=dict)  # {"technology": 0.9, "sports": 0.5}
    favorite_topics = Column(JSON, default=list)  # ["technology", "science"]
    avg_session_duration = Column(Float, default=0.0)  # Average time per session in seconds
    total_articles_read = Column(Integer, default=0)

    # GDPR compliance
    data_processing_consent = Column(Boolean, default=False)
    consent_date = Column(DateTime(timezone=True))

    # Relationships
    reading_history = relationship("ReadingHistory", back_populates="user", cascade="all, delete-orphan")
    feedback = relationship("UserFeedback", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")  #  Add this

    def __repr__(self):
        return f"<User(id={self.user_id}, username={self.username}, email={self.email})>"

    def to_dict(self):
        """Convert to dictionary for RL service"""
        return {
            'user_id': str(self.user_id),
            'username': self.username,
            'email': self.email,
            'topic_preferences': self.topic_preferences or {},
            'favorite_topics': self.favorite_topics or [],
            'avg_session_duration': self.avg_session_duration or 0.0,
            'total_articles_read': self.total_articles_read or 0
        }

class UserSession(Base):
    """User session tracking model"""
    __tablename__ = "user_sessions"
    __table_args__ = {'extend_existing': True}

    # Primary key
    session_id = Column(UUID(as_uuid=True), primary_key=True, index=True)

    # Foreign key to users table
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)

    # Device and security info
    device_info = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Session status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship
    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<UserSession(id={self.session_id}, user_id={self.user_id}, active={self.is_active})>"


class LoginAttempt(Base):
    """Track login attempts for security monitoring"""

    __tablename__ = "login_attempts"
    __table_args__ = {'extend_existing': True}


    attempt_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Attempt Details
    email = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(Text)

    # Result
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String(255))

    # Timestamps
    attempted_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<LoginAttempt {self.email} at {self.attempted_at}>"


