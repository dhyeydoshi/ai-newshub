from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'perf_indexes_001'
down_revision = 'fbbe6c428671'  # Updated to point to create_user_sessions_table
branch_labels = None
depends_on = None


def upgrade():
    """Add performance indexes"""

    # Use raw SQL with IF NOT EXISTS for better compatibility
    conn = op.get_bind()

    # Users table - optimize login and user lookup queries
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_users_email_active 
        ON users (email, is_active)
    """))

    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_users_username_active 
        ON users (username, is_active)
    """))

    # Articles table - optimize article listing queries
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_articles_published_status 
        ON articles (published_date DESC, is_active, moderation_status)
    """))

    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_articles_content_hash 
        ON articles (content_hash)
    """))

    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_articles_source_published 
        ON articles (source_name, published_date)
    """))

    # Articles table - GIN index for full-text search on title
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_articles_title_search 
        ON articles 
        USING gin(to_tsvector('english', title))
    """))

    # Articles table - GIN index for array columns (topics, tags)
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_articles_topics 
        ON articles 
        USING gin(topics)
    """))

    # User sessions table - optimize session cleanup and lookup
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user_created 
        ON user_sessions (user_id, created_at)
    """))

    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_sessions_expires 
        ON user_sessions (expires_at)
    """))

    # User feedback table - optimize user feedback queries (if table exists)
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_feedback') THEN
                CREATE INDEX IF NOT EXISTS idx_feedback_user_article 
                ON user_feedback (user_id, article_id);
                
                CREATE INDEX IF NOT EXISTS idx_feedback_article_created 
                ON user_feedback (article_id, created_at);
            END IF;
        END $$;
    """))

    print(" Performance indexes created successfully!")


def downgrade():
    """Remove performance indexes"""

    # Drop indexes in reverse order
    op.drop_index('idx_feedback_article_created', table_name='user_feedback')
    op.drop_index('idx_feedback_user_article', table_name='user_feedback')
    op.drop_index('idx_sessions_expires', table_name='user_sessions')
    op.drop_index('idx_sessions_user_created', table_name='user_sessions')
    op.drop_index('idx_articles_topics', table_name='articles')
    op.execute('DROP INDEX IF EXISTS idx_articles_title_search')
    op.drop_index('idx_articles_source_published', table_name='articles')
    op.drop_index('idx_articles_content_hash', table_name='articles')
    op.drop_index('idx_articles_published_status', table_name='articles')
    op.drop_index('idx_users_username_active', table_name='users')
    op.drop_index('idx_users_email_active', table_name='users')

    print(" Performance indexes removed")

