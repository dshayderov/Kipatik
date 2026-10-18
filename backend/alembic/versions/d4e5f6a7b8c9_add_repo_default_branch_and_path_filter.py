"""add_repo_default_branch_and_path_filter

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-04 10:00:00.000000

Этап 2 — мастер подключения и мульти-репозитории:
  * git_repositories.default_branch — ветка по умолчанию (main);
  * git_repositories.path_filter — фильтр по путям для монорепозиториев.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'git_repositories',
        sa.Column('default_branch', sa.String(), nullable=True, server_default='main'),
    )
    op.add_column('git_repositories', sa.Column('path_filter', sa.String(), nullable=True))
    op.execute("UPDATE git_repositories SET default_branch = 'main' WHERE default_branch IS NULL")


def downgrade() -> None:
    op.drop_column('git_repositories', 'path_filter')
    op.drop_column('git_repositories', 'default_branch')
