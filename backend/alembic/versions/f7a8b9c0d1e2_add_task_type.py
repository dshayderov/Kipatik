"""add_task_type

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-13 12:00:00.000000

Тип задачи: bug | feature | null.

На карточке задачи тип показывался заглушкой — чётный id значил «Баг»,
нечётный «Фича». Поле в базе не было нигде, поэтому подпись ничего
не сообщала: у задачи «Разбор даты» с id 12 стоял «Баг» только потому,
что 12 чётное.

Теперь тип выбирает человек при создании задачи и может изменить.
Значения хранятся строкой, а не enum: перечень короткий, он может
расшириться, и добавление нового типа не должно требовать миграции
типа данных — достаточно поправить список в интерфейсе.

Существующим задачам тип не проставляется: он не был известен, и
угадывать его задним числом значило бы выдумать данные. Пустое
значение показывается как «без типа».
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('task_type', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'task_type')