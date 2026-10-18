"""add_task_card_git_details

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-05 10:00:00.000000

Этап 4 — блок «Разработка» в карточке задачи:
  * commit_files — изменённые файлы коммитов;
  * task_git_links — провенанс связи задачи с коммитом/веткой/PR
    (источник, уверенность, кто подтвердил), чтобы связь можно было
    отозвать и объяснить пользователю;
  * агрегаты Pull Request: ревьюеры, статус CI, +/- и число файлов.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Провенанс связей ---
    op.create_table(
        'task_git_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('link_type', sa.String(), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='regex'),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('task_id', 'link_type', 'target_id', name='uq_task_git_links_unique'),
    )
    op.create_index(op.f('ix_task_git_links_id'), 'task_git_links', ['id'], unique=False)
    op.create_index(op.f('ix_task_git_links_task_id'), 'task_git_links', ['task_id'], unique=False)
    op.create_index(op.f('ix_task_git_links_target_id'), 'task_git_links', ['target_id'], unique=False)

    # Существующие связи помечаем как найденные регуляркой — иначе
    # в интерфейсе они выглядели бы «без источника».
    op.execute("""
        INSERT INTO task_git_links (task_id, link_type, target_id, source)
        SELECT tc.task_id, 'commit', tc.commit_id, 'regex'
        FROM task_commits tc
        WHERE NOT EXISTS (
            SELECT 1 FROM task_git_links l
            WHERE l.task_id = tc.task_id
              AND l.link_type = 'commit'
              AND l.target_id = tc.commit_id
        )
    """)
    op.execute("""
        INSERT INTO task_git_links (task_id, link_type, target_id, source)
        SELECT tb.task_id, 'branch', tb.branch_id, 'branch'
        FROM task_branches tb
        WHERE NOT EXISTS (
            SELECT 1 FROM task_git_links l
            WHERE l.task_id = tb.task_id
              AND l.link_type = 'branch'
              AND l.target_id = tb.branch_id
        )
    """)
    op.execute("""
        INSERT INTO task_git_links (task_id, link_type, target_id, source)
        SELECT tp.task_id, 'pull_request', tp.pull_request_id, 'pr'
        FROM task_pull_requests tp
        WHERE NOT EXISTS (
            SELECT 1 FROM task_git_links l
            WHERE l.task_id = tp.task_id
              AND l.link_type = 'pull_request'
              AND l.target_id = tp.pull_request_id
        )
    """)

    # --- Файлы коммитов ---
    op.create_table(
        'commit_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('commit_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('previous_path', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, server_default='modified'),
        sa.Column('additions', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('deletions', sa.Integer(), nullable=True, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['commit_id'], ['git_commits.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('commit_id', 'path', name='uq_commit_files_commit_path'),
    )
    op.create_index(op.f('ix_commit_files_id'), 'commit_files', ['id'], unique=False)
    op.create_index(op.f('ix_commit_files_commit_id'), 'commit_files', ['commit_id'], unique=False)

    # --- Агрегаты Pull Request ---
    op.add_column('git_pull_requests', sa.Column('merged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('git_pull_requests', sa.Column('additions', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('git_pull_requests', sa.Column('deletions', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('git_pull_requests', sa.Column('changed_files', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('git_pull_requests', sa.Column('reviewers', sa.JSON(), nullable=True))
    op.add_column('git_pull_requests', sa.Column('ci_status', sa.String(), nullable=True))
    op.add_column('git_pull_requests', sa.Column('ci_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('git_pull_requests', 'ci_url')
    op.drop_column('git_pull_requests', 'ci_status')
    op.drop_column('git_pull_requests', 'reviewers')
    op.drop_column('git_pull_requests', 'changed_files')
    op.drop_column('git_pull_requests', 'deletions')
    op.drop_column('git_pull_requests', 'additions')
    op.drop_column('git_pull_requests', 'merged_at')

    op.drop_index(op.f('ix_commit_files_commit_id'), table_name='commit_files')
    op.drop_index(op.f('ix_commit_files_id'), table_name='commit_files')
    op.drop_table('commit_files')

    op.drop_index(op.f('ix_task_git_links_target_id'), table_name='task_git_links')
    op.drop_index(op.f('ix_task_git_links_task_id'), table_name='task_git_links')
    op.drop_index(op.f('ix_task_git_links_id'), table_name='task_git_links')
    op.drop_table('task_git_links')
