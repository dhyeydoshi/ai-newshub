from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserAPIKey(Base):
    __tablename__ = "user_api_keys"
    __table_args__ = {"extend_existing": True}

    api_key_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)

    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    key_prefix = Column(String(20), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    scopes = Column(JSONB, nullable=False, default=lambda: ["feed:read"], server_default='["feed:read"]')
    rate_limit_per_hour = Column(Integer, nullable=False, default=1000, server_default="1000")

    last_used_at = Column(DateTime(timezone=True), nullable=True)
    request_count = Column(BigInteger, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")
    feeds = relationship("UserCustomFeed", back_populates="api_key", cascade="all, delete-orphan")
    bundles = relationship("UserFeedBundle", back_populates="api_key", cascade="all, delete-orphan")


class UserCustomFeed(Base):
    __tablename__ = "user_custom_feeds"
    __table_args__ = (
        CheckConstraint("default_format IN ('json', 'rss', 'atom')", name="ck_user_custom_feeds_default_format"),
        {"extend_existing": True},
    )

    feed_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    api_key_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_api_keys.api_key_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    slug = Column(String(140), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    filters = Column(JSONB, nullable=False, default=dict, server_default="{}")
    default_format = Column(String(10), nullable=False, default="json", server_default="json")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="custom_feeds")
    api_key = relationship("UserAPIKey", back_populates="feeds")
    webhooks = relationship("UserWebhook", back_populates="feed", cascade="all, delete-orphan")
    bundle_memberships = relationship("BundleFeedMembership", back_populates="feed", cascade="all, delete-orphan")


class UserFeedBundle(Base):
    __tablename__ = "user_feed_bundles"
    __table_args__ = (
        CheckConstraint("default_format IN ('json', 'rss', 'atom')", name="ck_user_feed_bundles_default_format"),
        {"extend_existing": True},
    )

    bundle_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    api_key_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_api_keys.api_key_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    slug = Column(String(140), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    default_format = Column(String(10), nullable=False, default="json", server_default="json")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="feed_bundles")
    api_key = relationship("UserAPIKey", back_populates="bundles")
    feed_memberships = relationship(
        "BundleFeedMembership",
        back_populates="bundle",
        cascade="all, delete-orphan",
    )
    webhooks = relationship("UserWebhook", back_populates="bundle", cascade="all, delete-orphan")


class BundleFeedMembership(Base):
    __tablename__ = "bundle_feed_memberships"
    __table_args__ = (
        UniqueConstraint("bundle_id", "feed_id", name="uq_bundle_feed_memberships_bundle_feed"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    bundle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_feed_bundles.bundle_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feed_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_custom_feeds.feed_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    bundle = relationship("UserFeedBundle", back_populates="feed_memberships")
    feed = relationship("UserCustomFeed", back_populates="bundle_memberships")


class UserWebhook(Base):
    __tablename__ = "user_webhooks"
    __table_args__ = (
        CheckConstraint(
            "(feed_id IS NOT NULL AND bundle_id IS NULL) OR (feed_id IS NULL AND bundle_id IS NOT NULL)",
            name="ck_user_webhooks_target_scope",
        ),
        {"extend_existing": True},
    )

    webhook_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)

    feed_id = Column(UUID(as_uuid=True), ForeignKey("user_custom_feeds.feed_id", ondelete="CASCADE"), nullable=True)
    bundle_id = Column(UUID(as_uuid=True), ForeignKey("user_feed_bundles.bundle_id", ondelete="CASCADE"), nullable=True)

    platform = Column(String(50), nullable=False)
    target_encrypted = Column(Text, nullable=False)
    secret_encrypted = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    batch_interval_minutes = Column(Integer, nullable=False, default=30, server_default="30")

    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    last_attempted_at = Column(DateTime(timezone=True), nullable=True)
    last_success_cursor_published_at = Column(DateTime(timezone=True), nullable=True)
    last_success_cursor_article_id = Column(UUID(as_uuid=True), nullable=True)

    failure_count = Column(Integer, nullable=False, default=0, server_default="0")
    max_failures = Column(Integer, nullable=False, default=5, server_default="5")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="webhooks")
    feed = relationship("UserCustomFeed", back_populates="webhooks")
    bundle = relationship("UserFeedBundle", back_populates="webhooks")
    delivery_jobs = relationship("WebhookDeliveryJob", back_populates="webhook", cascade="all, delete-orphan")


class WebhookDeliveryJob(Base):
    __tablename__ = "webhook_delivery_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'retry_pending', 'failed', 'dead_letter', 'cancelled')",
            name="ck_webhook_delivery_jobs_status",
        ),
        UniqueConstraint(
            "webhook_id",
            "window_end",
            "payload_digest",
            name="uq_webhook_delivery_jobs_idempotency",
        ),
        {"extend_existing": True},
    )

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    webhook_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_webhooks.webhook_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="pending", server_default="pending")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    payload_digest = Column(String(64), nullable=False)
    article_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    webhook = relationship("UserWebhook", back_populates="delivery_jobs")
    items = relationship("WebhookDeliveryItem", back_populates="job", cascade="all, delete-orphan")


class WebhookDeliveryItem(Base):
    __tablename__ = "webhook_delivery_items"
    __table_args__ = (
        UniqueConstraint("job_id", "article_id", name="uq_webhook_delivery_items_job_article"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("webhook_delivery_jobs.job_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.article_id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    job = relationship("WebhookDeliveryJob", back_populates="items")
    article = relationship("Article")
