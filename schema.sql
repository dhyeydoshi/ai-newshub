-- ============================================================================
-- PostgreSQL Database Schema for News Summarizer (Simplified)
-- Aligns with current SQLAlchemy models (UUID core entities + int row IDs)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- USERS
-- ============================================================================
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),

    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMPTZ,
    verification_token VARCHAR(255) UNIQUE,
    verification_token_expires TIMESTAMPTZ,

    is_locked BOOLEAN DEFAULT FALSE,
    locked_until TIMESTAMPTZ,
    failed_login_attempts INTEGER DEFAULT 0,
    last_failed_login TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    last_password_change TIMESTAMPTZ,

    reset_token VARCHAR(255) UNIQUE,
    reset_token_expires TIMESTAMPTZ,

    topic_preferences JSONB DEFAULT '{}'::JSONB,
    favorite_topics JSONB DEFAULT '[]'::JSONB,
    avg_session_duration DOUBLE PRECISION DEFAULT 0.0,
    total_articles_read INTEGER DEFAULT 0,

    data_processing_consent BOOLEAN DEFAULT FALSE,
    consent_date TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_username ON users(username) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_active ON users(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_created_at ON users(created_at);

-- ============================================================================
-- ARTICLES
-- ============================================================================
CREATE TABLE articles (
    article_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    title TEXT NOT NULL,
    content TEXT NOT NULL,
    excerpt TEXT,
    url VARCHAR(2048) UNIQUE NOT NULL,

    source_name VARCHAR(255) NOT NULL,
    source_url VARCHAR(2048),
    author VARCHAR(255),

    category VARCHAR(100),
    topics TEXT[] DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    language VARCHAR(10) DEFAULT 'en',

    meta_data JSONB DEFAULT '{}'::JSONB,

    published_date TIMESTAMPTZ NOT NULL,
    scraped_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    image_url VARCHAR(1000),
    word_count INTEGER DEFAULT 0,
    reading_time_minutes INTEGER DEFAULT 0,
    content_hash VARCHAR(64) UNIQUE,

    total_views INTEGER DEFAULT 0,
    total_clicks INTEGER DEFAULT 0,
    avg_time_spent DOUBLE PRECISION DEFAULT 0.0,
    click_through_rate DOUBLE PRECISION DEFAULT 0.0,

    is_active BOOLEAN DEFAULT TRUE,
    moderation_status VARCHAR(20) DEFAULT 'pending' CHECK (moderation_status IN ('pending', 'approved', 'rejected')),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_articles_published_date ON articles(published_date DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_articles_source_name ON articles(source_name) WHERE deleted_at IS NULL;
CREATE INDEX idx_articles_category ON articles(category) WHERE deleted_at IS NULL;
CREATE INDEX idx_articles_topics ON articles USING GIN (topics);
CREATE INDEX idx_articles_tags ON articles USING GIN (tags);
CREATE INDEX idx_articles_language ON articles(language) WHERE deleted_at IS NULL;
CREATE INDEX idx_articles_title_trgm ON articles USING GIN (title gin_trgm_ops);
CREATE INDEX idx_articles_content_trgm ON articles USING GIN (content gin_trgm_ops);
CREATE INDEX idx_articles_meta_data ON articles USING GIN (meta_data);
CREATE INDEX idx_articles_active_published ON articles(is_active, published_date DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_articles_content_hash ON articles(content_hash) WHERE deleted_at IS NULL;

-- ============================================================================
-- USER SESSIONS
-- ============================================================================
CREATE TABLE user_sessions (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    refresh_token_jti VARCHAR(255),

    device_info VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),

    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_used_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id) WHERE is_active = TRUE;
CREATE INDEX idx_user_sessions_created_at ON user_sessions(created_at DESC);

-- ============================================================================
-- LOGIN ATTEMPTS
-- ============================================================================
CREATE TABLE login_attempts (
    attempt_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    user_agent TEXT,
    success BOOLEAN NOT NULL,
    failure_reason VARCHAR(255),
    attempted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX idx_login_attempts_email ON login_attempts(email);
CREATE INDEX idx_login_attempts_attempted_at ON login_attempts(attempted_at DESC);

-- ============================================================================
-- READING HISTORY
-- ============================================================================
CREATE TABLE reading_history (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    article_id UUID NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,

    clicked BOOLEAN DEFAULT FALSE,
    time_spent_seconds DOUBLE PRECISION DEFAULT 0.0,
    scroll_depth_percent DOUBLE PRECISION DEFAULT 0.0,
    completed_reading BOOLEAN DEFAULT FALSE,

    device_type VARCHAR(50),
    session_id VARCHAR(255),

    viewed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX idx_reading_history_user_id ON reading_history(user_id, viewed_at DESC);
CREATE INDEX idx_reading_history_article_id ON reading_history(article_id);
CREATE INDEX idx_reading_history_viewed_at ON reading_history(viewed_at DESC);

-- ============================================================================
-- USER FEEDBACK
-- ============================================================================
CREATE TABLE user_feedback (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    article_id UUID NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,

    feedback_type VARCHAR(50) NOT NULL,
    rating INTEGER,
    comment TEXT,
    reason VARCHAR(255),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX idx_user_feedback_user_id ON user_feedback(user_id);
CREATE INDEX idx_user_feedback_article_id ON user_feedback(article_id);
CREATE INDEX idx_user_feedback_created_at ON user_feedback(created_at DESC);
CREATE INDEX idx_user_feedback_type ON user_feedback(feedback_type);

-- ============================================================================
-- INTEGRATION API
-- ============================================================================
CREATE TABLE user_api_keys (
    api_key_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_prefix VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    scopes JSONB NOT NULL DEFAULT '["feed:read"]'::JSONB,
    rate_limit_per_hour INTEGER NOT NULL DEFAULT 1000,

    last_used_at TIMESTAMPTZ,
    request_count BIGINT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX idx_user_api_keys_hash ON user_api_keys(key_hash) WHERE is_active = TRUE;
CREATE INDEX idx_user_api_keys_user ON user_api_keys(user_id) WHERE is_active = TRUE;
CREATE INDEX idx_user_api_keys_prefix ON user_api_keys(key_prefix);

CREATE TABLE user_custom_feeds (
    feed_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    api_key_id UUID NOT NULL REFERENCES user_api_keys(api_key_id) ON DELETE CASCADE,

    slug VARCHAR(140) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    filters JSONB NOT NULL DEFAULT '{}'::JSONB,
    default_format VARCHAR(10) NOT NULL DEFAULT 'json' CHECK (default_format IN ('json', 'rss', 'atom')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX idx_user_custom_feeds_user ON user_custom_feeds(user_id) WHERE is_active = TRUE;
CREATE INDEX idx_user_custom_feeds_api_key ON user_custom_feeds(api_key_id);
CREATE INDEX idx_user_custom_feeds_slug ON user_custom_feeds(slug);

CREATE TABLE user_feed_bundles (
    bundle_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    api_key_id UUID NOT NULL REFERENCES user_api_keys(api_key_id) ON DELETE CASCADE,

    slug VARCHAR(140) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    default_format VARCHAR(10) NOT NULL DEFAULT 'json' CHECK (default_format IN ('json', 'rss', 'atom')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX idx_user_feed_bundles_user ON user_feed_bundles(user_id) WHERE is_active = TRUE;
CREATE INDEX idx_user_feed_bundles_api_key ON user_feed_bundles(api_key_id);
CREATE INDEX idx_user_feed_bundles_slug ON user_feed_bundles(slug);

CREATE TABLE bundle_feed_memberships (
    id SERIAL PRIMARY KEY,
    bundle_id UUID NOT NULL REFERENCES user_feed_bundles(bundle_id) ON DELETE CASCADE,
    feed_id UUID NOT NULL REFERENCES user_custom_feeds(feed_id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT uq_bundle_feed_memberships_bundle_feed UNIQUE (bundle_id, feed_id)
);

CREATE INDEX idx_bundle_feed_memberships_bundle ON bundle_feed_memberships(bundle_id);
CREATE INDEX idx_bundle_feed_memberships_feed ON bundle_feed_memberships(feed_id);

CREATE TABLE user_webhooks (
    webhook_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    feed_id UUID REFERENCES user_custom_feeds(feed_id) ON DELETE CASCADE,
    bundle_id UUID REFERENCES user_feed_bundles(bundle_id) ON DELETE CASCADE,

    platform VARCHAR(50) NOT NULL,
    target_encrypted TEXT NOT NULL,
    secret_encrypted TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    batch_interval_minutes INTEGER NOT NULL DEFAULT 30,

    last_triggered_at TIMESTAMPTZ,
    last_attempted_at TIMESTAMPTZ,
    last_success_cursor_published_at TIMESTAMPTZ,
    last_success_cursor_article_id UUID,

    failure_count INTEGER NOT NULL DEFAULT 0,
    max_failures INTEGER NOT NULL DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT ck_user_webhooks_target_scope CHECK (
        (feed_id IS NOT NULL AND bundle_id IS NULL)
        OR (feed_id IS NULL AND bundle_id IS NOT NULL)
    )
);

CREATE INDEX idx_user_webhooks_user_active ON user_webhooks(user_id) WHERE is_active = TRUE;
CREATE INDEX idx_user_webhooks_feed ON user_webhooks(feed_id);
CREATE INDEX idx_user_webhooks_bundle ON user_webhooks(bundle_id);
CREATE INDEX idx_user_webhooks_due ON user_webhooks(is_active, last_triggered_at)
WHERE is_active = TRUE AND failure_count < max_failures;

CREATE TABLE webhook_delivery_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    webhook_id UUID NOT NULL REFERENCES user_webhooks(webhook_id) ON DELETE CASCADE,

    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'processing', 'delivered', 'retry_pending', 'failed', 'dead_letter', 'cancelled')
    ),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMPTZ,
    payload_digest VARCHAR(64) NOT NULL,
    article_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT uq_webhook_delivery_jobs_idempotency UNIQUE (webhook_id, window_end, payload_digest)
);

CREATE INDEX idx_webhook_delivery_jobs_webhook ON webhook_delivery_jobs(webhook_id);
CREATE INDEX idx_webhook_delivery_jobs_status ON webhook_delivery_jobs(status);
CREATE INDEX idx_webhook_delivery_jobs_retry ON webhook_delivery_jobs(next_retry_at)
WHERE status IN ('retry_pending', 'failed');

CREATE TABLE webhook_delivery_items (
    id SERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES webhook_delivery_jobs(job_id) ON DELETE CASCADE,
    article_id UUID NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT uq_webhook_delivery_items_job_article UNIQUE (job_id, article_id)
);

CREATE INDEX idx_webhook_delivery_items_job ON webhook_delivery_items(job_id);
CREATE INDEX idx_webhook_delivery_items_article ON webhook_delivery_items(article_id);

-- ============================================================================
-- UPDATED_AT TRIGGERS
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_articles_updated_at BEFORE UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_custom_feeds_updated_at BEFORE UPDATE ON user_custom_feeds
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_feed_bundles_updated_at BEFORE UPDATE ON user_feed_bundles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_webhook_delivery_jobs_updated_at BEFORE UPDATE ON webhook_delivery_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
