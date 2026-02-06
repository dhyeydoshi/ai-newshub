from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '696afe48e5b4'
down_revision: Union[str, None] = '4aab0de15346'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'login_attempts',
        sa.Column('attempt_id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=False),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('failure_reason', sa.String(255), nullable=True),
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )

    # Create indexes
    op.create_index('idx_login_attempts_email', 'login_attempts', ['email'])
    op.create_index('idx_login_attempts_attempted_at', 'login_attempts', ['attempted_at'])
    op.create_index('idx_login_attempts_success', 'login_attempts', ['success'])
    op.create_index('idx_login_attempts_ip_address', 'login_attempts', ['ip_address'])

    # Composite index for common queries
    op.create_index(
        'idx_login_attempts_email_attempted_at',
        'login_attempts',
        ['email', sa.text('attempted_at DESC')]
    )

def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_login_attempts_email_attempted_at', 'login_attempts')
    op.drop_index('idx_login_attempts_ip_address', 'login_attempts')
    op.drop_index('idx_login_attempts_success', 'login_attempts')
    op.drop_index('idx_login_attempts_attempted_at', 'login_attempts')
    op.drop_index('idx_login_attempts_email', 'login_attempts')

    # Drop table
    op.drop_table('login_attempts')
