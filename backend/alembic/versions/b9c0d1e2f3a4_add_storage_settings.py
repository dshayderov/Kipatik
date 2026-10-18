"""add_storage_settings

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-10-15 16:00:00.000000

Настройки хранения файлов: лимиты вложений и правила корзины.

Лимиты были константами в коде — 25 МБ на файл и фиксированный
список расширений, — поэтому изменить их можно было только правкой
исходников. Срок хранения корзины тоже был зашит в задачу Celery
(семь дней), которая вдобавок никогда не запускалась: расписание
beat не было задано, задачи не регистрировались и никем не
вызывались. Теперь всё это настраивается администратором.

storage_limit_bytes в projects становится nullable: прежнее
значение по умолчанию 500 МБ было зашито в модели, и изменение
админом не действовало бы на новые проекты. Теперь лимит хранится
в настройках, а в проекте null означает «взять общий».
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9c0d1e2f3a4'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'storage_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('max_file_size_mb', sa.Integer(), nullable=False, server_default='25'),
        sa.Column(
            'allowed_extensions',
            sa.String(),
            nullable=False,
            server_default='.png,.jpg,.jpeg,.gif,.pdf,.doc,.docx,.txt,.zip,.log',
        ),
        sa.Column(
            'default_project_limit_mb', sa.Integer(), nullable=False, server_default='500'
        ),
        sa.Column(
            'trash_retention_days', sa.Integer(), nullable=False, server_default='7'
        ),
        sa.Column(
            'auto_purge_enabled', sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            'purge_interval_hours', sa.Integer(), nullable=False, server_default='6'
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['updated_by_id'], ['users.id'], ondelete='SET NULL'
        ),
    )

    op.alter_column(
        'projects', 'storage_limit_bytes', existing_type=sa.BigInteger(), nullable=True
    )

    # Строка со значениями по умолчанию: без неё приложение работало бы
    # на дефолтах из кода, и в панели было бы нечего показывать.
    op.execute(
        "INSERT INTO storage_settings (id) VALUES (1)"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE projects SET storage_limit_bytes = 524288000 "
        "WHERE storage_limit_bytes IS NULL"
    )
    op.alter_column(
        'projects',
        'storage_limit_bytes',
        existing_type=sa.BigInteger(),
        nullable=False,
        server_default='524288000',
    )
    op.drop_table('storage_settings')