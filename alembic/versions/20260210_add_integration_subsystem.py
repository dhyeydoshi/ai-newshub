"""Add integration subsystem tables (API keys, feeds, bundles, webhooks, delivery jobs)

Revision ID: 20260210_integrations
Revises: a1b2c3d4e5f6
Create Date: 2026-02-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260210_integrations"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_api_keys",
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='["feed:read"]'),
        sa.Column("rate_limit_per_hour", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("key_hash", name="uq_user_api_keys_key_hash"),
    )
    op.create_index("ix_user_api_keys_api_key_id", "user_api_keys", ["api_key_id"])
    op.create_index("ix_user_api_keys_key_hash", "user_api_keys", ["key_hash"])
    op.create_index("ix_user_api_keys_key_prefix", "user_api_keys", ["key_prefix"])
    op.create_index(
        "idx_user_api_keys_user_active",
        "user_api_keys",
        ["user_id"],
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "user_custom_feeds",
        sa.Column("feed_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("default_format", sa.String(length=10), nullable=False, server_default="json"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("default_format IN ('json', 'rss', 'atom')", name="ck_user_custom_feeds_default_format"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["api_key_id"], ["user_api_keys.api_key_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("slug", name="uq_user_custom_feeds_slug"),
    )
    op.create_index("ix_user_custom_feeds_feed_id", "user_custom_feeds", ["feed_id"])
    op.create_index("ix_user_custom_feeds_slug", "user_custom_feeds", ["slug"])
    op.create_index("ix_user_custom_feeds_user_id", "user_custom_feeds", ["user_id"])
    op.create_index("ix_user_custom_feeds_api_key_id", "user_custom_feeds", ["api_key_id"])
    op.create_index(
        "idx_user_custom_feeds_user_active",
        "user_custom_feeds",
        ["user_id"],
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "user_feed_bundles",
        sa.Column("bundle_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_format", sa.String(length=10), nullable=False, server_default="json"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("default_format IN ('json', 'rss', 'atom')", name="ck_user_feed_bundles_default_format"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["api_key_id"], ["user_api_keys.api_key_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("slug", name="uq_user_feed_bundles_slug"),
    )
    op.create_index("ix_user_feed_bundles_bundle_id", "user_feed_bundles", ["bundle_id"])
    op.create_index("ix_user_feed_bundles_slug", "user_feed_bundles", ["slug"])
    op.create_index("ix_user_feed_bundles_user_id", "user_feed_bundles", ["user_id"])
    op.create_index("ix_user_feed_bundles_api_key_id", "user_feed_bundles", ["api_key_id"])
    op.create_index(
        "idx_user_feed_bundles_user_active",
        "user_feed_bundles",
        ["user_id"],
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "bundle_feed_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("bundle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feed_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["bundle_id"], ["user_feed_bundles.bundle_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feed_id"], ["user_custom_feeds.feed_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("bundle_id", "feed_id", name="uq_bundle_feed_memberships_bundle_feed"),
    )
    op.create_index("ix_bundle_feed_memberships_id", "bundle_feed_memberships", ["id"])
    op.create_index("ix_bundle_feed_memberships_bundle_id", "bundle_feed_memberships", ["bundle_id"])
    op.create_index("ix_bundle_feed_memberships_feed_id", "bundle_feed_memberships", ["feed_id"])

    op.create_table(
        "user_webhooks",
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feed_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bundle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("target_encrypted", sa.Text(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("batch_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_cursor_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_cursor_article_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_failures", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "(feed_id IS NOT NULL AND bundle_id IS NULL) OR (feed_id IS NULL AND bundle_id IS NOT NULL)",
            name="ck_user_webhooks_target_scope",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feed_id"], ["user_custom_feeds.feed_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bundle_id"], ["user_feed_bundles.bundle_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_webhooks_webhook_id", "user_webhooks", ["webhook_id"])
    op.create_index("ix_user_webhooks_user_id", "user_webhooks", ["user_id"])
    op.create_index(
        "idx_user_webhooks_due",
        "user_webhooks",
        ["is_active", "last_attempted_at"],
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "webhook_delivery_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'retry_pending', 'failed', 'dead_letter', 'cancelled')",
            name="ck_webhook_delivery_jobs_status",
        ),
        sa.ForeignKeyConstraint(["webhook_id"], ["user_webhooks.webhook_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("webhook_id", "window_end", "payload_digest", name="uq_webhook_delivery_jobs_idempotency"),
    )
    op.create_index("ix_webhook_delivery_jobs_job_id", "webhook_delivery_jobs", ["job_id"])
    op.create_index("ix_webhook_delivery_jobs_webhook_id", "webhook_delivery_jobs", ["webhook_id"])
    op.create_index(
        "idx_webhook_delivery_jobs_due",
        "webhook_delivery_jobs",
        ["status", "next_retry_at"],
        postgresql_where=sa.text("status IN ('pending', 'retry_pending')"),
    )

    op.create_table(
        "webhook_delivery_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["webhook_delivery_jobs.job_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["articles.article_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("job_id", "article_id", name="uq_webhook_delivery_items_job_article"),
    )
    op.create_index("ix_webhook_delivery_items_id", "webhook_delivery_items", ["id"])
    op.create_index("ix_webhook_delivery_items_job_id", "webhook_delivery_items", ["job_id"])
    op.create_index("ix_webhook_delivery_items_article_id", "webhook_delivery_items", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_delivery_items_article_id", table_name="webhook_delivery_items")
    op.drop_index("ix_webhook_delivery_items_job_id", table_name="webhook_delivery_items")
    op.drop_index("ix_webhook_delivery_items_id", table_name="webhook_delivery_items")
    op.drop_table("webhook_delivery_items")

    op.drop_index("idx_webhook_delivery_jobs_due", table_name="webhook_delivery_jobs")
    op.drop_index("ix_webhook_delivery_jobs_webhook_id", table_name="webhook_delivery_jobs")
    op.drop_index("ix_webhook_delivery_jobs_job_id", table_name="webhook_delivery_jobs")
    op.drop_table("webhook_delivery_jobs")

    op.drop_index("idx_user_webhooks_due", table_name="user_webhooks")
    op.drop_index("ix_user_webhooks_user_id", table_name="user_webhooks")
    op.drop_index("ix_user_webhooks_webhook_id", table_name="user_webhooks")
    op.drop_table("user_webhooks")

    op.drop_index("ix_bundle_feed_memberships_feed_id", table_name="bundle_feed_memberships")
    op.drop_index("ix_bundle_feed_memberships_bundle_id", table_name="bundle_feed_memberships")
    op.drop_index("ix_bundle_feed_memberships_id", table_name="bundle_feed_memberships")
    op.drop_table("bundle_feed_memberships")

    op.drop_index("idx_user_feed_bundles_user_active", table_name="user_feed_bundles")
    op.drop_index("ix_user_feed_bundles_api_key_id", table_name="user_feed_bundles")
    op.drop_index("ix_user_feed_bundles_user_id", table_name="user_feed_bundles")
    op.drop_index("ix_user_feed_bundles_slug", table_name="user_feed_bundles")
    op.drop_index("ix_user_feed_bundles_bundle_id", table_name="user_feed_bundles")
    op.drop_table("user_feed_bundles")

    op.drop_index("idx_user_custom_feeds_user_active", table_name="user_custom_feeds")
    op.drop_index("ix_user_custom_feeds_api_key_id", table_name="user_custom_feeds")
    op.drop_index("ix_user_custom_feeds_user_id", table_name="user_custom_feeds")
    op.drop_index("ix_user_custom_feeds_slug", table_name="user_custom_feeds")
    op.drop_index("ix_user_custom_feeds_feed_id", table_name="user_custom_feeds")
    op.drop_table("user_custom_feeds")

    op.drop_index("idx_user_api_keys_user_active", table_name="user_api_keys")
    op.drop_index("ix_user_api_keys_key_prefix", table_name="user_api_keys")
    op.drop_index("ix_user_api_keys_key_hash", table_name="user_api_keys")
    op.drop_index("ix_user_api_keys_api_key_id", table_name="user_api_keys")
    op.drop_table("user_api_keys")
