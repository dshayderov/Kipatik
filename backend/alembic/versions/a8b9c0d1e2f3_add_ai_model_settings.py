"""add_ai_model_settings

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-10-15 14:00:00.000000

Настройки включения нейросетевых моделей.

Включение модели задавалось только флагами окружения
(CODE_MODEL_ENABLED, CODE_MODEL_CLASSIFY, PROGRESS_ENABLED), поэтому
переключить модель можно было лишь правкой .env и перезапуском
приложения. Администратору нужна возможность сделать это из панели
управления.

Таблица хранит решение администратора, действующее поверх значений
из окружения: пока строки нет, работает то, что задано при запуске.

updated_by_id ссылается на пользователя с SET NULL: после удаления
администратора настройка остаётся, но её авторство теряется — как и
у любой другой справочной ссылки на пользователя в этом проекте.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_model_settings',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['updated_by_id'], ['users.id'], ondelete='SET NULL'
        ),
    )


def downgrade() -> None:
    op.drop_table('ai_model_settings')