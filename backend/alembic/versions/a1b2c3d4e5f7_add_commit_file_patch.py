"""add_commit_file_patch

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-10-10 12:00:00.000000

Этап 3 — тексты изменений для моделей анализа кода.

Модели из лабораторных работ обучались на представлении коммита, где
кроме списка файлов есть текст правок:

    Files: src/auth/oauth.py
    Message: Fix token validation
    Changes:
    +def validate_token(t): ...

Без блока Changes модель получает только имя файла и работает заметно
хуже. В базе текстов правок не было: commit_files хранил путь, статус
и счётчики строк.

Добавляем:
  * commit_files.patch       — текст правок, обрезанный до
    GIT_MAX_PATCH_CHARS;
  * commit_files.patch_truncated — правка не сохранена целиком.

Большой объём текста ожидаем: поле вынесено в отдельную колонку, чтобы
выборки commit_files для списка файлов в интерфейсе не тащили его с собой.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "commit_files",
        sa.Column("patch", sa.Text(), nullable=True),
    )
    op.add_column(
        "commit_files",
        sa.Column("patch_truncated", sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("commit_files", "patch_truncated")
    op.drop_column("commit_files", "patch")