from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4aab0de15346'
down_revision: Union[str, None] = 'd6750a5d7950'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS verification_token VARCHAR (255);
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS verification_token_expires TIMESTAMPTZ;
               """)

    # Add security fields
    op.execute("""
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT FALSE;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS last_failed_login TIMESTAMPTZ;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS last_password_change TIMESTAMPTZ;
               """)

    # Add password reset fields
    op.execute("""
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS reset_token VARCHAR (255);
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMPTZ;
               """)

    # Add timestamp fields
    op.execute("""
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
               """)

    # Add RL-specific fields
    op.execute("""
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS topic_preferences JSON DEFAULT '{}'::json;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS favorite_topics JSON DEFAULT '[]'::json;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS avg_session_duration DOUBLE PRECISION DEFAULT 0.0;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS total_articles_read INTEGER DEFAULT 0;
               """)

    # Add GDPR compliance fields
    op.execute("""
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS data_processing_consent BOOLEAN DEFAULT FALSE;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS consent_date TIMESTAMPTZ;
               ALTER TABLE "users"
                   ADD COLUMN IF NOT EXISTS email_consent BOOLEAN DEFAULT FALSE;
               """)


def downgrade() -> None:
    # Drop UUID extension
    op.execute("""
               ALTER TABLE "users" DROP COLUMN IF EXISTS email_consent;
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
               ALTER TABLE "users" DROP COLUMN IF EXISTS reset_token_expires;
               ALTER TABLE "users" DROP COLUMN IF EXISTS reset_token;
               ALTER TABLE "users" DROP COLUMN IF EXISTS last_password_change;
               ALTER TABLE "users" DROP COLUMN IF EXISTS last_failed_login;
               ALTER TABLE "users" DROP COLUMN IF EXISTS failed_login_attempts;
               ALTER TABLE "users" DROP COLUMN IF EXISTS locked_until;
               ALTER TABLE "users" DROP COLUMN IF EXISTS is_locked;
               ALTER TABLE "users" DROP COLUMN IF EXISTS is_active;
               ALTER TABLE "users" DROP COLUMN IF EXISTS verification_token_expires;
               ALTER TABLE "users" DROP COLUMN IF EXISTS verification_token;
               ALTER TABLE "users" DROP COLUMN IF EXISTS email_verified_at;
               ALTER TABLE "users" DROP COLUMN IF EXISTS is_verified;
               """)

