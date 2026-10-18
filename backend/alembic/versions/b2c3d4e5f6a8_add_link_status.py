"""Добавляет статус связи задачи с объектом Git.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-10-10 13:00:00.000000

Этап 4 — трассировка по смыслу изменений как предложение, а не факт.

Модель сопоставляет коммит с задачей по сходству представлений и часто
ошибается. Поэтому её вывод сохраняется как предложение: связь получает
status='proposed' и не попадает ни в блок «Разработка», ни в оценку
прогресса, пока пользователь её не подтвердит.

Существующие связи считаем подтверждёнными — иначе после миграции
исчезла бы вся накопленная привязка по регулярным выражениям.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_git_links",
        sa.Column("status", sa.String(), nullable=True, server_default="confirmed"),
    )
    op.add_column(
        "task_git_links",
        sa.Column("reason", sa.String(), nullable=True),
    )

    # server_default ставим только на время миграции: дальше приложение
    # пишет значение само, и молчаливый дефолт в схеме скрыл бы забытый
    # статус у новых вставок.
    op.alter_column("task_git_links", "status", server_default=None)

    # Вся существующая привязка сделана правилами и вручную — она факт.
    op.execute("UPDATE task_git_links SET status = 'confirmed' WHERE status IS NULL")

    op.create_index(
        "ix_task_git_links_status", "task_git_links", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_task_git_links_status", table_name="task_git_links")
    op.drop_column("task_git_links", "reason")
    op.drop_column("task_git_links", "status")