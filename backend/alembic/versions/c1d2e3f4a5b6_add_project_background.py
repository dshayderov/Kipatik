"""add_project_background

Revision ID: c1d2e3f4a5b6
Revises: b9c0d1e2f3a4
Create Date: 2026-10-15 18:30:00.000000

Фон проекта: общий для всех участников, переключается во вкладке
«общее» настроек проекта.

Два поля, а не одно:
  * background     — вид: none (без фона), default (базовый из source),
                     custom (загруженный пользователем);
  * background_url — адрес загруженного файла.

Разделение сделано намеренно. Если бы адрес лежал в одном поле со
значением вида, то строка вида «custom» без файла дала бы битый фон, и
появился бы ещё и вопрос, кто отвечает за её починку. Здесь адресом
владеет исключительно загрузка, а видом — обычное обновление проекта.

По умолчанию у всех проектов none: внешний вид не должен меняться у
пользователей без их участия.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column(
            'background',
            sa.String(),
            nullable=False,
            server_default='none',
        ),
    )
    op.add_column(
        'projects',
        sa.Column('background_url', sa.String(), nullable=True),
    )


def downgrade() -> None:
    # Файл остаётся на диске — он не в базе и удалять его откатом
    # схемы нельзя: откат затрагивает структуру, а не содержимое
    # хранилища. Страница проекта при отсутствии фона просто не
    # покажет его, а при следующей загрузке файл будет перезаписан.
    op.drop_column('projects', 'background_url')
    op.drop_column('projects', 'background')