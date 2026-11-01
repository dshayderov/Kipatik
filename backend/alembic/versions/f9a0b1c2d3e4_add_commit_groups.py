"""add_commit_groups

Revision ID: f9a0b1c2d3e4
Revises: c1d2e3f4a5b6
Create Date: 2026-10-27 12:00:00.000000

Группировка коммитов и отношения между ними (ЛР №2).

Группы и связи хранятся отдельно от привязки коммита к задаче: одна
и та же связь «коммит → задача» может быть подтверждена, а группа
ещё оставаться предложением. Подтверждение группы и переименование
не должны менять саму привязку.

Все таблицы удаляются каскадом вместе с задачей. Коммит и задача
остаются в системе, если группа удалена.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'task_commit_groupings',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('algorithm_version', sa.String(), nullable=True),
        sa.Column('n_commits', sa.Integer(), server_default='0', nullable=False),
        sa.Column('n_groups', sa.Integer(), server_default='0', nullable=False),
        sa.Column('n_relations', sa.Integer(), server_default='0', nullable=False),
        sa.Column('model_used', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column(
            'generated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('task_id'),
    )

    op.create_table(
        'commit_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('title_source', sa.String(), server_default='template', nullable=False),
        sa.Column('title_type', sa.String(), nullable=True),
        sa.Column('title_area', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), server_default='proposed', nullable=False),
        sa.Column('position', sa.Integer(), server_default='0', nullable=False),
        sa.Column('algorithm_version', sa.String(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'task_id', 'position', name='uq_commit_groups_task_position'
        ),
    )
    op.create_index(
        op.f('ix_commit_groups_id'), 'commit_groups', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_commit_groups_task_id'), 'commit_groups', ['task_id'], unique=False
    )

    op.create_table(
        'commit_group_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('commit_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(
            ['commit_id'], ['git_commits.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['group_id'], ['commit_groups.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'task_id', 'commit_id', name='uq_commit_group_members_task_commit'
        ),
        sa.UniqueConstraint(
            'group_id', 'commit_id', name='uq_commit_group_members_group_commit'
        ),
    )
    op.create_index(
        op.f('ix_commit_group_members_id'),
        'commit_group_members',
        ['id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_commit_group_members_task_id'),
        'commit_group_members',
        ['task_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_commit_group_members_group_id'),
        'commit_group_members',
        ['group_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_commit_group_members_commit_id'),
        'commit_group_members',
        ['commit_id'],
        unique=False,
    )

    op.create_table(
        'commit_relations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('source_commit_id', sa.Integer(), nullable=False),
        sa.Column('target_commit_id', sa.Integer(), nullable=False),
        sa.Column('relation_type', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), server_default='0', nullable=False),
        sa.Column('direction', sa.String(), server_default='unknown', nullable=False),
        sa.Column('rule', sa.String(), nullable=True),
        sa.Column('type_source', sa.String(), server_default='heuristic', nullable=False),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), server_default='proposed', nullable=False),
        sa.Column('in_graph', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ['source_commit_id'], ['git_commits.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['target_commit_id'], ['git_commits.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'task_id',
            'source_commit_id',
            'target_commit_id',
            'relation_type',
            name='uq_commit_relations_task_pair_type',
        ),
    )
    op.create_index(
        op.f('ix_commit_relations_id'), 'commit_relations', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_commit_relations_task_id'),
        'commit_relations',
        ['task_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_commit_relations_source_commit_id'),
        'commit_relations',
        ['source_commit_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_commit_relations_target_commit_id'),
        'commit_relations',
        ['target_commit_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_commit_relations_target_commit_id'), table_name='commit_relations')
    op.drop_index(op.f('ix_commit_relations_source_commit_id'), table_name='commit_relations')
    op.drop_index(op.f('ix_commit_relations_task_id'), table_name='commit_relations')
    op.drop_index(op.f('ix_commit_relations_id'), table_name='commit_relations')
    op.drop_table('commit_relations')

    op.drop_index(op.f('ix_commit_group_members_commit_id'), table_name='commit_group_members')
    op.drop_index(op.f('ix_commit_group_members_group_id'), table_name='commit_group_members')
    op.drop_index(op.f('ix_commit_group_members_task_id'), table_name='commit_group_members')
    op.drop_index(op.f('ix_commit_group_members_id'), table_name='commit_group_members')
    op.drop_table('commit_group_members')

    op.drop_index(op.f('ix_commit_groups_task_id'), table_name='commit_groups')
    op.drop_index(op.f('ix_commit_groups_id'), table_name='commit_groups')
    op.drop_table('commit_groups')

    op.drop_table('task_commit_groupings')
