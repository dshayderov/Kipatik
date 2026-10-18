"""add_cascade_delete_for_owned_rows

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b9
Create Date: 2026-10-11 23:40:00.000000

Удаление проекта падало с ForeignKeyViolationError.

Причина: почти все внешние ключи в схеме созданы без ON DELETE CASCADE,
то есть с правилом NO ACTION. ORM-каскад покрывал только projects ->
project_members/boards/tasks (в моделях стоит cascade="all, delete-orphan").
Всё остальное — приглашения, репозитории с коммитами, уведомления,
вложения — оставалось в базе и блокировало удаление проекта.

Первым падал project_invites: у Project нет связи с этой таблицей.
Дальше notifications.invite_id, git_repositories -> git_commits и так далее.

Что меняем: переводим в ON DELETE CASCADE только те ключи, где строка
существует исключительно ради родителя. Обратные ссылки на users не
трогаем — удаление пользователя не должно молча уносить чужие данные,
это отдельный вопрос с отдельным решением. tasks.column_id тоже не
трогаем: колонка переживает задачу.

Союзинительные таблицы (task_commits, task_branches, task_pull_requests)
каскадируют в обе стороны — это чистые пары «задача <-> артефакт git»,
без родителя они бессмысленны.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (таблица, колонка, целевая таблица, имя констрейнта)
OWNED_FOREIGN_KEYS = [
    # от projects
    ("attachments", "project_id", "projects", "attachments_project_id_fkey"),
    ("boards", "project_id", "projects", "boards_project_id_fkey"),
    ("git_repositories", "project_id", "projects", "git_repositories_project_id_fkey"),
    ("notifications", "project_id", "projects", "notifications_project_id_fkey"),
    ("project_invites", "project_id", "projects", "project_invites_project_id_fkey"),
    ("project_members", "project_id", "projects", "project_members_project_id_fkey"),
    ("tasks", "project_id", "projects", "tasks_project_id_fkey"),
    # от boards
    ("columns", "board_id", "boards", "columns_board_id_fkey"),
    # от git_repositories
    ("git_branches", "repository_id", "git_repositories", "git_branches_repository_id_fkey"),
    ("git_commits", "repository_id", "git_repositories", "git_commits_repository_id_fkey"),
    ("git_events_log", "repository_id", "git_repositories", "git_events_log_repository_id_fkey"),
    ("git_pull_requests", "repository_id", "git_repositories", "git_pull_requests_repository_id_fkey"),
    ("unlinked_git_events", "repository_id", "git_repositories", "unlinked_git_events_repository_id_fkey"),
    # от tasks
    ("attachments", "task_id", "tasks", "attachments_task_id_fkey"),
    ("notifications", "task_id", "tasks", "notifications_task_id_fkey"),
    ("subtasks", "task_id", "tasks", "subtasks_task_id_fkey"),
    ("task_branches", "task_id", "tasks", "task_branches_task_id_fkey"),
    ("task_comments", "task_id", "tasks", "task_comments_task_id_fkey"),
    ("task_commits", "task_id", "tasks", "task_commits_task_id_fkey"),
    ("task_pull_requests", "task_id", "tasks", "task_pull_requests_task_id_fkey"),
    # соединительные таблицы: каскад в обе стороны
    ("task_commits", "commit_id", "git_commits", "task_commits_commit_id_fkey"),
    ("task_branches", "branch_id", "git_branches", "task_branches_branch_id_fkey"),
    ("task_pull_requests", "pull_request_id", "git_pull_requests", "task_pull_requests_pull_request_id_fkey"),
    # от task_comments
    ("comment_reactions", "comment_id", "task_comments", "comment_reactions_comment_id_fkey"),
    ("attachments", "comment_id", "task_comments", "attachments_comment_id_fkey"),
    ("task_comments", "parent_id", "task_comments", "task_comments_parent_id_fkey"),
    # от project_invites — именно этот ключ первым блокировал удаление
    ("notifications", "invite_id", "project_invites", "notifications_invite_id_fkey"),
]


def _rewrite(table: str, column: str, target: str, constraint: str, ondelete: str | None) -> None:
    """Пересоздаёт внешний ключ с заданным правилом ON DELETE."""
    op.drop_constraint(constraint, table, type_="foreignkey")
    op.create_foreign_key(
        constraint,
        table,
        target,
        [column],
        # Первичный ключ цели во всех затрагиваемых таблицах называется id
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    """Ставим ON DELETE CASCADE на все ключи владения."""
    for table, column, target, constraint in OWNED_FOREIGN_KEYS:
        _rewrite(table, column, target, constraint, "CASCADE")


def downgrade() -> None:
    """Возвращаем NO ACTION — то есть восстанавливаем исходную схему."""
    for table, column, target, constraint in OWNED_FOREIGN_KEYS:
        _rewrite(table, column, target, constraint, None)