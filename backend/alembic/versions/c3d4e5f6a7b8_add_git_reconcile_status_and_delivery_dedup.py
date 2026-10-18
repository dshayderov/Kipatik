"""add_git_reconcile_status_and_delivery_dedup

Revision ID: c3d4e5f6a7b8
Revises: b7c1d2e3f4a5
Create Date: 2026-04-03 10:00:00.000000

Этап 1 — надёжность Git-интеграции:
  * git_repositories.last_sync_* — состояние периодической сверки,
    чтобы индикатор показывал реальный результат, а не «всё хорошо»;
  * git_repositories.last_event_at — время последнего события;
  * уникальное ограничение (repository_id, delivery_id) — защита от
    повторной обработки одной доставки вебхука.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b7c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('git_repositories', sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'git_repositories',
        sa.Column('last_sync_status', sa.String(), nullable=True, server_default='pending'),
    )
    op.add_column('git_repositories', sa.Column('last_sync_error', sa.Text(), nullable=True))
    op.add_column('git_repositories', sa.Column('last_event_at', sa.DateTime(timezone=True), nullable=True))

    # Перед добавлением ограничения убираем возможные дубликаты доставок,
    # иначе миграция упадёт на существующих данных.
    op.execute("""
        DELETE FROM git_events_log a
        USING git_events_log b
        WHERE a.id > b.id
          AND a.repository_id = b.repository_id
          AND a.delivery_id = b.delivery_id
          AND a.delivery_id IS NOT NULL
    """)

    op.create_unique_constraint(
        'uq_git_events_log_delivery',
        'git_events_log',
        ['repository_id', 'delivery_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_git_events_log_delivery', 'git_events_log', type_='unique')

    op.drop_column('git_repositories', 'last_event_at')
    op.drop_column('git_repositories', 'last_sync_error')
    op.drop_column('git_repositories', 'last_sync_status')
    op.drop_column('git_repositories', 'last_sync_at')
