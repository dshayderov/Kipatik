"""add_enrichment_status

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-12 17:10:00.000000

Статус фонового дооболнения репозитория.

Сверка (last_sync_*) только забирает коммиты и отвечает за секунды.
Дальше идёт тяжёлая часть: тексты изменений — отдельный запрос к API
провайдера на каждый коммит — и трассировка моделью. Она уходит в фон,
чтобы не держать пользователя у кнопки «Синхронизировать».

Но без статуса фоновая работа выглядит как «ничего не произошло»:
интерфейс не может отличить «разбираем» от «зависло». Поэтому статус
отдельный от last_sync_status — загрузка успешна и разбор модели закончен
это разные события.

Прогресс хранится парами done/total, чтобы интерфейс мог показать
«3/10», а не просто крутиться без объяснений.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "git_repositories",
        sa.Column("enrichment_status", sa.String(), nullable=True),
    )
    op.add_column(
        "git_repositories",
        sa.Column("enrichment_total", sa.Integer(), nullable=True),
    )
    op.add_column(
        "git_repositories",
        sa.Column("enrichment_done", sa.Integer(), nullable=True),
    )
    op.add_column(
        "git_repositories",
        sa.Column("enrichment_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "git_repositories",
        sa.Column("enrichment_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Существующие строки не обрабатывались: отмечаем как «готово»,
    # чтобы интерфейс не показывал незаконченную работу.
    op.execute(
        """
        UPDATE git_repositories
           SET enrichment_status = 'pending',
               enrichment_total = 0,
               enrichment_done = 0
         WHERE enrichment_status IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("git_repositories", "enrichment_at")
    op.drop_column("git_repositories", "enrichment_error")
    op.drop_column("git_repositories", "enrichment_done")
    op.drop_column("git_repositories", "enrichment_total")
    op.drop_column("git_repositories", "enrichment_status")