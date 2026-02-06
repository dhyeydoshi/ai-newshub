from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


# revision identifiers, used by Alembic.
revision: str = '20260205_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        'users',
        sa.Column('user_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('username', sa.String(100), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),

        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verification_token', sa.String(255), nullable=True, unique=True),
        sa.Column('verification_token_expires', sa.DateTime(timezone=True), nullable=True),

        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_failed_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_password_change', sa.DateTime(timezone=True), nullable=True),

        sa.Column('reset_token', sa.String(255), nullable=True, unique=True),
        sa.Column('reset_token_expires', sa.DateTime(timezone=True), nullable=True),

        sa.Column('topic_preferences', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('favorite_topics', JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('avg_session_duration', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('total_articles_read', sa.Integer(), nullable=False, server_default=sa.text('0')),

        sa.Column('data_processing_consent', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('consent_date', sa.DateTime(timezone=True), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'articles',
        sa.Column('article_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('url', sa.String(2048), nullable=False, unique=True),

        sa.Column('source_name', sa.String(255), nullable=False),
        sa.Column('source_url', sa.String(2048), nullable=True),
        sa.Column('author', sa.String(255), nullable=True),

        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('topics', ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('tags', ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('language', sa.String(10), nullable=False, server_default=sa.text("'en'")),

        sa.Column('meta_data', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),

        sa.Column('published_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scraped_date', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.Column('image_url', sa.String(1000), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('reading_time_minutes', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('content_hash', sa.String(64), nullable=True, unique=True),

        sa.Column('total_views', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('total_clicks', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('avg_time_spent', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('click_through_rate', sa.Float(), nullable=False, server_default=sa.text('0.0')),

        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('TRUE')),
        sa.Column('moderation_status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),

        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),

        sa.CheckConstraint(
            "moderation_status IN ('pending', 'approved', 'rejected')",
            name='check_moderation_status'
        ),
    )

    op.create_table(
        'reading_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('article_id', UUID(as_uuid=True), nullable=False),
        sa.Column('clicked', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('time_spent_seconds', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('scroll_depth_percent', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('completed_reading', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('device_type', sa.String(50), nullable=True),
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['article_id'], ['articles.article_id'], ondelete='CASCADE'),
    )

    op.create_table(
        'user_feedback',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('article_id', UUID(as_uuid=True), nullable=False),
        sa.Column('feedback_type', sa.String(50), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('reason', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['article_id'], ['articles.article_id'], ondelete='CASCADE'),
    )


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS user_feedback CASCADE')
    op.execute('DROP TABLE IF EXISTS reading_history CASCADE')
    op.execute('DROP TABLE IF EXISTS articles CASCADE')
    op.execute('DROP TABLE IF EXISTS users CASCADE')
