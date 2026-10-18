"""add_commit_type

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-10-11 10:00:00.000000

Этап B8 — бейдж типа коммита в карточке задачи.

Тип определяется моделью (ЛР №3) один раз, когда коммит привязывается
к задаче, и хранится в самом коммите. Пересчитывать при открытии
карточки нельзя: классификация на CPU занимает сотни миллисекунд
на коммит, и карточка с пятью коммитами грузилась бы на секунды дольше.

Все поля nullable: старые коммиты остаются без типа, пока их не
обработает дозаполнение.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("git_commits", sa.Column("commit_type", sa.String(), nullable=True))
    op.add_column("git_commits", sa.Column("commit_type_confidence", sa.Float(), nullable=True))
    op.add_column(
        "git_commits",
        sa.Column("commit_type_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Частичный индекс: запросы идут по привязанным коммитам без типа
    op.create_index(
        "ix_git_commits_type_missing",
        "git_commits",
        ["id"],
        unique=False,
        postgresql_where=sa.text("commit_type IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_git_commits_type_missing", table_name="git_commits")
    op.drop_column("git_commits", "commit_type_at")
    op.drop_column("git_commits", "commit_type_confidence")
    op.drop_column("git_commits", "commit_type")