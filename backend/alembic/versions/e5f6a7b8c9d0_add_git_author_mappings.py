from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Email автора коммита — основной ключ сопоставления с пользователем.
    # Раньше он не сохранялся вовсе, поэтому автоматическое сопоставление
    # почти никогда не срабатывало.
    op.add_column('git_commits', sa.Column('author_email', sa.String(), nullable=True))
    op.create_index(op.f('ix_git_commits_author_email'), 'git_commits', ['author_email'], unique=False)

    op.create_table(
        'git_author_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=True),
        sa.Column('author_key', sa.String(), nullable=False),
        sa.Column('author_name', sa.String(), nullable=True),
        sa.Column('author_email', sa.String(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='manual'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['repository_id'], ['git_repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('repository_id', 'author_key', name='uq_git_author_mappings_repo_key'),
    )
    op.create_index(op.f('ix_git_author_mappings_id'), 'git_author_mappings', ['id'], unique=False)
    op.create_index(op.f('ix_git_author_mappings_author_key'), 'git_author_mappings', ['author_key'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_git_author_mappings_author_key'), table_name='git_author_mappings')
    op.drop_index(op.f('ix_git_author_mappings_id'), table_name='git_author_mappings')
    op.drop_table('git_author_mappings')

    op.drop_index(op.f('ix_git_commits_author_email'), table_name='git_commits')
    op.drop_column('git_commits', 'author_email')
