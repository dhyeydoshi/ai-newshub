"""Add additional users metadata columns (created_at, preferences, etc.)"""

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = 'd6750a5d7950'
down_revision = '5c227a466e66'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ NULL;
        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS topic_preferences JSON DEFAULT '{}'::json;
        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS favorite_topics JSON DEFAULT '[]'::json;
        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS avg_session_duration DOUBLE PRECISION DEFAULT 0.0;
        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS total_articles_read INTEGER DEFAULT 0;

        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS data_processing_consent BOOLEAN DEFAULT FALSE;
        ALTER TABLE "users" ADD COLUMN IF NOT EXISTS consent_date TIMESTAMPTZ;
    """)


def downgrade():
    op.execute("""
        ALTER TABLE "users" DROP COLUMN IF EXISTS consent_date;
        ALTER TABLE "users" DROP COLUMN IF EXISTS data_processing_consent;
        ALTER TABLE "users" DROP COLUMN IF EXISTS total_articles_read;
        ALTER TABLE "users" DROP COLUMN IF EXISTS avg_session_duration;
        ALTER TABLE "users" DROP COLUMN IF EXISTS favorite_topics;
        ALTER TABLE "users" DROP COLUMN IF EXISTS topic_preferences;
        ALTER TABLE "users" DROP COLUMN IF EXISTS deleted_at;
        ALTER TABLE "users" DROP COLUMN IF EXISTS last_login_at;
        ALTER TABLE "users" DROP COLUMN IF EXISTS updated_at;
        ALTER TABLE "users" DROP COLUMN IF EXISTS created_at;
    """)
