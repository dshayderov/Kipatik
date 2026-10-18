"""add_project_rules

Revision ID: f1a2b3c4d5e6
Revises: 01d2cc17a18a
Create Date: 2026-04-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '644382ea7aa9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('rules', sa.JSON(), nullable=True, server_default='{"required_fields": ["title"], "auto_assign_on_move": false, "column_role_locks": {}, "start_date_logic": "created_at"}'))


def downgrade() -> None:
    op.drop_column('projects', 'rules')
