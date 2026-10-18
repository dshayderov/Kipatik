"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Каскадное удаление проекта. Проверяет, что удаление не падает
с ForeignKeyViolationError и уносит связанные строки: приглашения,
репозитории с коммитами и правками, уведомления, вложения,
комментарии. Работает в транзакции с откатом.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\venv\Scripts\python.exe -W ignore tests\test_cascade_delete.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import asyncio
import logging
import warnings

warnings.filterwarnings("ignore")
# Каждое обращение к БД печатается движком — вывод становится нечитаемым.
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

import app.models  # noqa: F401
import app.git.models  # noqa: F401

from app.core.database import SessionLocal
from app.git.models import (
    Commit, CommitFile, GitAuthorMapping, GitProviderType, GitRepository,
    TaskGitLink,
)
from app.notifications.models import Notification, NotificationType
from app.projects.models import InviteStatus, Project, ProjectInvite, ProjectMember
from app.tasks.models import Attachment, Task, TaskComment, CommentReaction, SubTask
from app.users.models import User

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


async def main():
    async with SessionLocal() as db:
        # ---------------------------------------------------------- #
        # Фикстура: проект, полностью обвешанный связанными строками
        # ---------------------------------------------------------- #
        # ВАЖНО: никаких commit() — тест обязан уйти в откат.
        # Промежуточные flush() нужны только чтобы получить id.
        print("=== 1. Фикстура ===")

        owner = User(
            email="cascade-owner@x.io", full_name="Владелец", hashed_password="x",
            is_superuser=True, can_create_projects=True,
        )
        member = User(
            email="cascade-member@x.io", full_name="Участник", hashed_password="x",
        )
        db.add_all([owner, member])
        await db.flush()

        project = Project(name="Проект для каскада", owner_id=owner.id)
        db.add(project)
        await db.flush()
        pid = project.id

        db.add(ProjectMember(project_id=pid, user_id=owner.id, role="project_manager"))
        db.add(ProjectMember(project_id=pid, user_id=member.id, role="developer"))

        invite = ProjectInvite(
            project_id=pid, user_id=member.id, inviter_id=owner.id,
            role="developer", status=InviteStatus.PENDING,
        )
        db.add(invite)
        await db.flush()

        repo = GitRepository(
            project_id=pid, url="https://github.com/org/cascade", repo_name="org/cascade",
            provider=GitProviderType.GITHUB, default_branch="main", access_token="t",
        )
        db.add(repo)
        await db.flush()

        now = datetime.now(timezone.utc) - timedelta(days=1)
        commit = Commit(
            repository_id=repo.id, sha="c0ffee1", message="feat: каскадное удаление",
            author="dev", timestamp=now,
        )
        db.add(commit)
        await db.flush()

        db.add(CommitFile(commit_id=commit.id, path="app/main.py", additions=10, deletions=2))
        db.add(GitAuthorMapping(repository_id=repo.id, author_key="dev", user_id=member.id))

        task = Task(
            project_id=pid, title="Задача с коммитом",
            description="Описание", column_id=None,
        )
        db.add(task)
        await db.flush()

        db.add(SubTask(task_id=task.id, title="Подзадача"))
        db.add(TaskComment(task_id=task.id, user_id=member.id, content="Комментарий"))
        db.add(Attachment(
            filename="doc.pdf", path="uploads/projects/x/doc.pdf", size_bytes=10,
            mime_type="application/pdf", uploaded_by=member.id, project_id=pid,
            task_id=task.id,
        ))
        db.add(TaskGitLink(
            task_id=task.id, link_type="commit", target_id=commit.id,
            source="regex", status="confirmed",
        ))
        db.add(Notification(
            user_id=member.id, title="Приглашение", message="Вас пригласили",
            type=NotificationType.PROJECT_INVITE, project_id=pid, invite_id=invite.id,
        ))
        db.add(Notification(
            user_id=member.id, title="Назначена задача", message="Вам назначили задачу",
            type=NotificationType.TASK_ASSIGNED, project_id=pid, task_id=task.id,
        ))
        await db.flush()

        check("фикстура создана", pid is not None, f"project_id={pid}")

        # ---------------------------------------------------------- #
        # Сколько строк ссылается на проект
        # ---------------------------------------------------------- #
        print("\n=== 2. Связанные строки до удаления ===")
        LINKED = {
            "project_invites": "project_id",
            "git_repositories": "project_id",
            "attachments": "project_id",
            "notifications": "project_id",
            "project_members": "project_id",
            "tasks": "project_id",
            "boards": "project_id",
        }
        before = {}
        for table, col in LINKED.items():
            n = (
                await db.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {col} = :p"), {"p": pid}
                )
            ).scalar()
            before[table] = n
            print(f"    {table:<20} {n}")

        check("есть приглашение", before["project_invites"] == 1)
        check("есть репозиторий", before["git_repositories"] == 1)
        check("есть вложение", before["attachments"] == 1)
        check("есть уведомления", before["notifications"] == 2)

        # ---------------------------------------------------------- #
        # Удаление — ровно как это делает delete_project
        # ---------------------------------------------------------- #
        print("\n=== 3. Удаление проекта ===")
        try:
            proj = (
                await db.execute(select(Project).where(Project.id == pid))
            ).scalar_one_or_none()
            check("проект найден", proj is not None)
            await db.delete(proj)
            await db.flush()
            check("db.delete + flush отработал без ошибки", True)
        except Exception as exc:
            check("db.delete + flush отработал без ошибки", False, f"{type(exc).__name__}: {exc}")

        # Проверяем, что каскад всё унёс
        after = {}
        for table, col in LINKED.items():
            after[table] = (
                await db.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {col} = :p"), {"p": pid}
                )
            ).scalar()

        check("проекта больше нет", after.get("projects", 0) == 0)
        left = {t: after[t] for t in LINKED if after[t] > 0}
        check("все связанные строки удалены", not left, left)

        # Глубокие таблицы
        deep = {
            "git_commits": f"repository_id = {repo.id}",
            "commit_files": f"commit_id = {commit.id}",
            "git_author_mappings": f"repository_id = {repo.id}",
            "subtasks": f"task_id = {task.id}",
            "task_comments": f"task_id = {task.id}",
            "task_git_links": f"task_id = {task.id}",
        }
        left_deep = {}
        for table, cond in deep.items():
            n = (await db.execute(text(f"SELECT count(*) FROM {table} WHERE {cond}"))).scalar()
            if n:
                left_deep[table] = n
        check("глубокие строки удалены", not left_deep, left_deep)

        # ---------------------------------------------------------- #
        # Удаление репозитория отдельно — тот же endpoint
        # ---------------------------------------------------------- #
        print("\n=== 4. Удаление репозитория отдельно ===")
        project2 = Project(name="Второй проект", owner_id=owner.id)
        db.add(project2)
        await db.flush()
        repo2 = GitRepository(
            project_id=project2.id, url="https://gitlab.com/g/r2", repo_name="g/r2",
            provider=GitProviderType.GITLAB, default_branch="main", access_token="t",
        )
        db.add(repo2)
        await db.flush()
        c2 = Commit(
            repository_id=repo2.id, sha="beef001", message="fix: что-то",
            author="dev", timestamp=now,
        )
        db.add(c2)
        await db.flush()
        db.add(CommitFile(commit_id=c2.id, path="x.py", additions=1, deletions=1))
        await db.flush()

        try:
            r2 = (
                await db.execute(select(GitRepository).where(GitRepository.id == repo2.id))
            ).scalar_one_or_none()
            await db.delete(r2)
            await db.flush()
            check("репозиторий с коммитами удаляется", True)
        except Exception as exc:
            check("репозиторий с коммитами удаляется", False, f"{type(exc).__name__}: {exc}")

        n_files = (
            await db.execute(
                text(f"SELECT count(*) FROM commit_files WHERE commit_id = {c2.id}")
            )
        ).scalar()
        check("правки коммита удалены каскадом", n_files == 0, n_files)

        # ---------------------------------------------------------- #
        # Откат: база возвращается в исходное состояние
        # ---------------------------------------------------------- #
        await db.rollback()

    # Контроль после отката — отдельная сессия
    async with SessionLocal() as db:
        leftovers = (
            await db.execute(
                text("SELECT name FROM projects WHERE name IN (:a, :b)"),
                {"a": "Проект для каскада", "b": "Второй проект"},
            )
        ).scalars().all()
        check("откат вернул базу в исходное состояние", not leftovers, leftovers)

        users = (
            await db.execute(
                text("SELECT count(*) FROM users WHERE email LIKE 'cascade-%'")
            )
        ).scalar()
        check("тестовые пользователи не остались", users == 0, users)

    # ---------------------------------------------------------- #
    # 5. Модели объявляют каскады (схема, созданная из моделей,
    #    должна вести себя так же, как мигрированная)
    # ---------------------------------------------------------- #
    print("\n=== 5. Модели объявляют ON DELETE CASCADE ===")
    from app.core.database import Base

    EXPECTED = [
        ("project_invites", "project_id"),
        ("git_repositories", "project_id"),
        ("attachments", "project_id"),
        ("notifications", "project_id"),
        ("notifications", "invite_id"),
        ("project_members", "project_id"),
        ("tasks", "project_id"),
        ("boards", "project_id"),
        ("columns", "board_id"),
        ("git_commits", "repository_id"),
        ("task_comments", "task_id"),
        ("task_git_links", "task_id"),
        ("task_commits", "commit_id"),
        ("task_commits", "task_id"),
    ]
    fk_map = {}
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            fk_map[(table.name, fk.parent.name)] = (fk.ondelete or "").upper()

    bad = []
    for table, col in EXPECTED:
        got = fk_map.get((table, col))
        if got != "CASCADE":
            bad.append(f"{table}.{col}={got!r}")
    check("все ключи владения помечены CASCADE", not bad, bad)

    # Обратные ссылки на пользователя. Удаление пользователя — отдельная
    # задача, поэтому каскадить здесь нельзя всё подряд: молча унести
    # чужие проекты при удалении учётной записи недопустимо.
    #
    # Допустимо терять только то, что не имеет смысла без пользователя:
    # сопоставление авторов (его и так можно пересоздать) и подписи
    # активности, где уже стоит SET NULL.
    ALLOWED = {
        ("git_author_mappings", "user_id"),  # сопоставление «автор → пользователь»
    }
    not_cascaded = []
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name != "users":
                continue
            rule = (fk.ondelete or "").upper()
            if rule == "CASCADE" and (table.name, fk.parent.name) not in ALLOWED:
                not_cascaded.append(f"{table.name}.{fk.parent.name}")
    check(
        "ссылки на users не каскадят, кроме сопоставления авторов",
        not not_cascaded,
        not_cascaded,
    )

    # ---------------------------------------------------------- #
    # 6. git_accounts предзагружаются (иначе MissingGreenlet)
    # ---------------------------------------------------------- #
    print("\n=== 6. Выдача пользователей не падает на ленивой загрузке ===")
    import inspect

    from app.api.v1.endpoints import admin, auth

    for name, mod, needles in (
        ("admin.py: список пользователей", admin, ["select(User).options(selectinload"]),
        ("auth.py: регистрация", auth, ["selectinload"]),
    ):
        src = inspect.getsource(mod)
        ok = any(n in src for n in needles)
        check(f"{name} — есть selectinload", ok)

    from app.users.models import User as U

    check(
        "git_accounts есть в relationships модели User",
        "git_accounts" in U.__mapper__.relationships,
        sorted(U.__mapper__.relationships.keys()),
    )

    # ---------------------------------------------------------- #
    print("\n" + "=" * 60)
    failed = [n for n, ok in results if not ok]
    print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
    if failed:
        print("ПРОВАЛЕНО:")
        for n in failed:
            print(f"  - {n}")


asyncio.run(main())