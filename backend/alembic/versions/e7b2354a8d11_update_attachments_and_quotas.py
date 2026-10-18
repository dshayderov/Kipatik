"""update_attachments_and_quotas

Revision ID: e7b2354a8d11
Revises: 83874d98c064
Create Date: 2026-03-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7b2354a8d11"
down_revision: Union[str, Sequence[str], None] = "83874d98c064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add quota fields to projects
    op.add_column("projects", sa.Column("storage_used_bytes", sa.BigInteger(), nullable=True, server_default="0"))
    op.add_column("projects", sa.Column("storage_limit_bytes", sa.BigInteger(), nullable=True, server_default="524288000"))
    
    # 2. Drop old task_attachments and create new attachments table
    op.drop_table("task_attachments")
    
    op.create_table("attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("comment_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="orphan"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["comment_id"], ["task_comments.id"], ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id")
    )


def downgrade() -> None:
    op.drop_table("attachments")
    op.create_table("task_attachments",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("file_path", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("content_type", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("size", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("task_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("comment_id", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("uploader_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["comment_id"], ["task_comments.id"], name="task_attachments_comment_id_fkey"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="task_attachments_task_id_fkey"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], name="task_attachments_uploader_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="task_attachments_pkey")
    )
    op.drop_column("projects", "storage_limit_bytes")
    op.drop_column("projects", "storage_used_bytes")
