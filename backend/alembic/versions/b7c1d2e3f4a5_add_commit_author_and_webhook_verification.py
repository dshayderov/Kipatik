"""add_commit_author_and_webhook_verification

Revision ID: b7c1d2e3f4a5
Revises: f1a2b3c4d5e6
Create Date: 2026-04-02 10:00:00.000000

Этап 0 — устранение блокеров Git-интеграции:
  * git_commits.author_id — атрибуция автора коммита. Поле использовалось в
    TaskLinkingService.link_commit_to_tasks, но отсутствовало в модели,
    из-за чего привязка коммитов к задачам падала с TypeError.
  * git_events_log.signature_verified / delivery_id — реальные признаки
    проверки подписи вебхука и идентификатор доставки (основа дедупликации).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c1d2e3f4a5'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('git_commits', sa.Column('author_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_git_commits_author_id'), 'git_commits', ['author_id'], unique=False)
    op.create_foreign_key(
        'fk_git_commits_author_id_users',
        'git_commits',
        'users',
        ['author_id'],
        ['id'],
    )

    op.add_column(
        'git_events_log',
        sa.Column('signature_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('git_events_log', sa.Column('delivery_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_git_events_log_delivery_id'), 'git_events_log', ['delivery_id'], unique=False)

    # Существующие события не проходили проверку подписи
    op.execute("UPDATE git_events_log SET signature_verified = false WHERE signature_verified IS NULL")


def downgrade() -> None:
    op.drop_index(op.f('ix_git_events_log_delivery_id'), table_name='git_events_log')
    op.drop_column('git_events_log', 'delivery_id')
    op.drop_column('git_events_log', 'signature_verified')

    op.drop_constraint('fk_git_commits_author_id_users', 'git_commits', type_='foreignkey')
    op.drop_index(op.f('ix_git_commits_author_id'), table_name='git_commits')
    op.drop_column('git_commits', 'author_id')
