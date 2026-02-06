"""Add refresh_token_jti column to user_sessions for token replay protection

Revision ID: a1b2c3d4e5f6
Revises: 20260205_align_schema
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None  # Will be auto-determined by Alembic
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_sessions',
        sa.Column('refresh_token_jti', sa.String(255), nullable=True)
    )
    op.create_index(
        'ix_user_sessions_refresh_token_jti',
        'user_sessions',
        ['refresh_token_jti']
    )


def downgrade() -> None:
    op.drop_index('ix_user_sessions_refresh_token_jti', table_name='user_sessions')
    op.drop_column('user_sessions', 'refresh_token_jti')
