from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260205_align_schema'
down_revision: Union[str, None] = 'perf_indexes_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Extensions
    conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
    conn.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))

    # Drop legacy tables/views not in simplified schema
    conn.execute(sa.text('DROP MATERIALIZED VIEW IF EXISTS mv_article_popularity'))
    conn.execute(sa.text('DROP VIEW IF EXISTS v_user_activity_summary'))
    conn.execute(sa.text('DROP TABLE IF EXISTS summaries'))
    conn.execute(sa.text('DROP TABLE IF EXISTS user_preferences'))
    conn.execute(sa.text('DROP TABLE IF EXISTS rl_state_tracking'))
    conn.execute(sa.text('DROP TABLE IF EXISTS rl_training_data'))

    # Users table - add missing columns and normalize types
    conn.execute(sa.text('''
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token VARCHAR(255);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token_expires TIMESTAMPTZ;

        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT FALSE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_failed_login TIMESTAMPTZ;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_password_change TIMESTAMPTZ;

        ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(255);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMPTZ;

        ALTER TABLE users ADD COLUMN IF NOT EXISTS topic_preferences JSONB DEFAULT '{}'::JSONB;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS favorite_topics JSONB DEFAULT '[]'::JSONB;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS avg_session_duration DOUBLE PRECISION DEFAULT 0.0;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_articles_read INTEGER DEFAULT 0;

        ALTER TABLE users ADD COLUMN IF NOT EXISTS data_processing_consent BOOLEAN DEFAULT FALSE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_date TIMESTAMPTZ;
    '''))

    # Normalize JSON -> JSONB if needed
    conn.execute(sa.text('''
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'topic_preferences'
                AND data_type = 'json'
            ) THEN
                ALTER TABLE users ALTER COLUMN topic_preferences TYPE JSONB USING topic_preferences::jsonb;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'favorite_topics'
                AND data_type = 'json'
            ) THEN
                ALTER TABLE users ALTER COLUMN favorite_topics TYPE JSONB USING favorite_topics::jsonb;
            END IF;
        END $$;
    '''))

    # Articles table - rename metadata column and add missing columns
    conn.execute(sa.text('''
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'articles' AND column_name = 'metadata'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'articles' AND column_name = 'meta_data'
            ) THEN
                ALTER TABLE articles RENAME COLUMN metadata TO meta_data;
            END IF;
        END $$;
    '''))

    conn.execute(sa.text('''
        ALTER TABLE articles ADD COLUMN IF NOT EXISTS image_url VARCHAR(1000);
        ALTER TABLE articles ADD COLUMN IF NOT EXISTS total_views INTEGER DEFAULT 0;
        ALTER TABLE articles ADD COLUMN IF NOT EXISTS total_clicks INTEGER DEFAULT 0;
        ALTER TABLE articles ADD COLUMN IF NOT EXISTS avg_time_spent DOUBLE PRECISION DEFAULT 0.0;
        ALTER TABLE articles ADD COLUMN IF NOT EXISTS click_through_rate DOUBLE PRECISION DEFAULT 0.0;
        ALTER TABLE articles ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(20) DEFAULT 'pending';
        ALTER TABLE articles ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
    '''))

    # User sessions table - remove unused token columns and align names
    conn.execute(sa.text('''
        ALTER TABLE user_sessions DROP COLUMN IF EXISTS session_token;
        ALTER TABLE user_sessions DROP COLUMN IF EXISTS refresh_token;
        ALTER TABLE user_sessions DROP COLUMN IF EXISTS refresh_token_jti;
        ALTER TABLE user_sessions DROP COLUMN IF EXISTS last_activity;

        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;
    '''))

    # Login attempts table
    conn.execute(sa.text('''
        CREATE TABLE IF NOT EXISTS login_attempts (
            attempt_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email VARCHAR(255) NOT NULL,
            ip_address VARCHAR(45) NOT NULL,
            user_agent TEXT,
            success BOOLEAN NOT NULL,
            failure_reason VARCHAR(255),
            attempted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
        );
    '''))

    # Reading history table - drop legacy columns and add required ones
    conn.execute(sa.text('''
        ALTER TABLE reading_history DROP COLUMN IF EXISTS summary_id;
        ALTER TABLE reading_history DROP COLUMN IF EXISTS started_at;
        ALTER TABLE reading_history DROP COLUMN IF EXISTS completed_at;
        ALTER TABLE reading_history DROP COLUMN IF EXISTS progress_percentage;
        ALTER TABLE reading_history DROP COLUMN IF EXISTS created_at;
        ALTER TABLE reading_history DROP COLUMN IF EXISTS updated_at;
        ALTER TABLE reading_history DROP COLUMN IF EXISTS deleted_at;

        ALTER TABLE reading_history ADD COLUMN IF NOT EXISTS clicked BOOLEAN DEFAULT FALSE;
        ALTER TABLE reading_history ADD COLUMN IF NOT EXISTS time_spent_seconds DOUBLE PRECISION DEFAULT 0.0;
        ALTER TABLE reading_history ADD COLUMN IF NOT EXISTS scroll_depth_percent DOUBLE PRECISION DEFAULT 0.0;
        ALTER TABLE reading_history ADD COLUMN IF NOT EXISTS completed_reading BOOLEAN DEFAULT FALSE;
        ALTER TABLE reading_history ADD COLUMN IF NOT EXISTS device_type VARCHAR(50);
        ALTER TABLE reading_history ADD COLUMN IF NOT EXISTS session_id VARCHAR(255);
        ALTER TABLE reading_history ADD COLUMN IF NOT EXISTS viewed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
    '''))

    # User feedback table - drop legacy columns and align
    conn.execute(sa.text('''
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS summary_id;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS clicked;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS time_spent_seconds;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS scroll_depth_percentage;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS feedback_text;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS is_saved;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS is_shared;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS completed_reading;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS returned_to_article;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS device_type;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS session_id;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS recommendation_source;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS position_in_feed;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS interaction_timestamp;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS updated_at;
        ALTER TABLE user_feedback DROP COLUMN IF EXISTS deleted_at;

        ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS feedback_type VARCHAR(50);
        ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS rating INTEGER;
        ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS comment TEXT;
        ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS reason VARCHAR(255);
        ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
    '''))

    # Indexes aligned to schema.sql
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE deleted_at IS NULL'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE deleted_at IS NULL'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active) WHERE deleted_at IS NULL'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)'))

    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles(published_date DESC) WHERE deleted_at IS NULL'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_source_name ON articles(source_name) WHERE deleted_at IS NULL'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category) WHERE deleted_at IS NULL'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_topics ON articles USING GIN (topics)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_tags ON articles USING GIN (tags)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_language ON articles(language) WHERE deleted_at IS NULL'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING GIN (title gin_trgm_ops)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_content_trgm ON articles USING GIN (content gin_trgm_ops)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_meta_data ON articles USING GIN (meta_data)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_active_published ON articles(is_active, published_date DESC) WHERE deleted_at IS NULL'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash) WHERE deleted_at IS NULL'))

    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id) WHERE is_active = TRUE'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_user_sessions_created_at ON user_sessions(created_at DESC)'))

    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_login_attempts_attempted_at ON login_attempts(attempted_at DESC)'))

    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_reading_history_user_id ON reading_history(user_id, viewed_at DESC)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_reading_history_article_id ON reading_history(article_id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_reading_history_viewed_at ON reading_history(viewed_at DESC)'))

    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_user_feedback_user_id ON user_feedback(user_id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_user_feedback_article_id ON user_feedback(article_id)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_user_feedback_created_at ON user_feedback(created_at DESC)'))
    conn.execute(sa.text('CREATE INDEX IF NOT EXISTS idx_user_feedback_type ON user_feedback(feedback_type)'))


def downgrade() -> None:
    # Irreversible simplification migration
    pass
