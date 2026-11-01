"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL.
Создаёт временные задачи с префиксом «Зонд групп» и удаляет их в конце.
Не запускать на боевой установке без согласия владельца данных.

Проверяет связку API → БД для групп коммитов:

* группы строятся при первом обращении и сохраняются;
* в ответе есть коммиты, отношения и остовное дерево для графа;
* группу можно переименовать и подтвердить;
* состав можно изменить, но нельзя оставить меньше двух коммитов;
* пересборка сбрасывает ручное название и возвращает шаблон.

Эмбеддинги подменяются фиксированными векторами: сам кодировщик уже
проверен отдельно, а здесь важны SQL, права и сериализация. Без
подмены тест зависел бы от весов и занимал десятки секунд.

Запуск (из папки backend, при поднятом PostgreSQL и применённых
миграциях):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_commit_groups_api.py
"""

import asyncio
import logging
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
logging.disable(logging.INFO)

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
import app.git.models  # noqa: F401
import app.git.grouping as grouping
from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.git.models import (
    Commit,
    CommitFile,
    GitProviderType,
    GitRepository,
    TaskGitLink,
    task_commits,
)
from app.main import app
from app.users.models import User

PROJECT = 14
TITLE_PREFIX = "Зонд групп"

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

TEST_USER = User(
    id=4,
    email="renebus125@gmail.ru",
    full_name="probe",
    hashed_password="x",
    is_active=True,
    is_superuser=True,
)


async def _get_db():
    async with sm() as s:
        yield s


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = lambda: TEST_USER
client = TestClient(app)


async def clear_probe() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM tasks WHERE title LIKE :title"),
            {"title": TITLE_PREFIX + "%"},
        )


async def setup_probe() -> tuple[int, list[int]]:
    async with sm() as session:
        repo = GitRepository(
            project_id=PROJECT,
            url="https://example.invalid/probe/groups",
            repo_name="probe/groups",
            provider=GitProviderType.GITHUB,
            default_branch="main",
            access_token="t",
            connected_by_id=TEST_USER.id,
            is_active=False,
        )
        session.add(repo)
        await session.commit()
        await session.refresh(repo)

        now = datetime.now(timezone.utc)
        definitions = [
            ("feat(api): добавить выгрузку", "feature", "src/api/export.py", now - timedelta(days=4)),
            ("feat(api): расширить выгрузку", "feature", "src/api/export.py", now - timedelta(days=3)),
            ("test(api): проверить выгрузку", "test", "tests/test_export.py", now - timedelta(days=2)),
            ("fix(api): падение выгрузки", "bugfix", "src/api/export.py", now - timedelta(days=1)),
        ]
        commits = []
        for index, (message, kind, path, timestamp) in enumerate(definitions):
            commit = Commit(
                repository_id=repo.id,
                sha=f"grp{index:05d}",
                message=message,
                author="probe",
                timestamp=timestamp,
                commit_type=kind,
                commit_type_confidence=0.9,
            )
            session.add(commit)
            await session.flush()
            session.add(
                CommitFile(
                    commit_id=commit.id,
                    path=path,
                    status="modified",
                    additions=10,
                    deletions=2,
                    patch="+def probe():\n+    return True",
                )
            )
            commits.append(commit)
        await session.commit()
        for commit in commits:
            await session.refresh(commit)
        return repo.id, [commit.id for commit in commits]


async def link_commits(task_id: int, commit_ids: list[int]) -> None:
    async with sm() as session:
        for commit_id in commit_ids:
            session.add(
                TaskGitLink(
                    task_id=task_id,
                    link_type="commit",
                    target_id=commit_id,
                    source="manual",
                    status="confirmed",
                    created_by_id=TEST_USER.id,
                )
            )
            await session.execute(
                task_commits.insert().values(task_id=task_id, commit_id=commit_id)
            )
        await session.commit()


async def cleanup_repo(repo_id: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM git_repositories WHERE id = :id"), {"id": repo_id}
        )


async def relation_map(task_id: int) -> dict[tuple[int, int], str]:
    async with sm() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT source_commit_id, target_commit_id, status "
                    "FROM commit_relations WHERE task_id = :id"
                ),
                {"id": task_id},
            )
        ).all()
        return {
            (
                min(row.source_commit_id, row.target_commit_id),
                max(row.source_commit_id, row.target_commit_id),
            ): row.status
            for row in rows
        }


async def fake_embeddings(texts):
    """Все тексты близки: цель теста — БД и API, а не качество модели."""
    return ([[1.0, 0.0, 0.0] for _ in texts], "encoder")


def find_group(payload, group_id=None):
    for group in payload.get("groups", []):
        if group_id is None or group["id"] == group_id:
            return group
    return None


created_repo = None
try:
    asyncio.run(clear_probe())
    original_embeddings = grouping._embed_texts
    grouping._embed_texts = fake_embeddings

    print("=== 1. Подготовка задачи и коммитов ===")
    response = client.post(
        "/api/v1/tasks/",
        json={"title": TITLE_PREFIX + " API", "project_id": PROJECT},
    )
    check("задача создана", response.status_code in (200, 201), response.text[:200])
    if response.status_code not in (200, 201):
        raise SystemExit(1)
    task_id = response.json()["id"]

    created_repo, commit_ids = asyncio.run(setup_probe())
    asyncio.run(link_commits(task_id, commit_ids))
    check("подготовлено четыре коммита", len(commit_ids) == 4, commit_ids)

    print("=== 2. Первое обращение строит и сохраняет группы ===")
    response = client.get(f"/api/v1/git/task/{task_id}/groups")
    check("GET групп отвечает 200", response.status_code == 200, response.text[:300])
    payload = response.json() if response.status_code == 200 else {}
    check("группировка доступна", payload.get("available") is True, payload.get("reason"))
    check("создана одна группа", len(payload.get("groups", [])) == 1, payload.get("summary"))
    group = find_group(payload)
    check("в группе четыре коммита", group is not None and group["size"] == 4, group and group["size"])
    if group is None:
        raise SystemExit(1)
    check(
        "граф — три ребра",
        group is not None and len(group["graph_relations"]) == 3,
        group and len(group["graph_relations"]),
    )
    relation_types = {relation["relation_type"] for relation in (group or {}).get("relations", [])}
    check("есть отношения fixes и tests", {"fixes", "tests"} <= relation_types, sorted(relation_types))
    check("название шаблонное", group is not None and group["title_source"] == "template")

    print("=== 3. Переименование и подтверждение ===")
    response = client.patch(
        f"/api/v1/git/task/{task_id}/groups/{group['id']}",
        json={"title": "Выгрузка отчётов", "status": "confirmed"},
    )
    check("PATCH отвечает 200", response.status_code == 200, response.text[:300])
    payload = response.json() if response.status_code == 200 else {}
    group = find_group(payload, group["id"])
    check("название сохранено", group is not None and group["title"] == "Выгрузка отчётов")
    check("название ручное", group is not None and group["title_source"] == "manual")
    check("группа подтверждена", group is not None and group["status"] == "confirmed")
    check(
        "внутренние связи подтверждены",
        all(relation["status"] == "confirmed" for relation in (group or {}).get("relations", [])),
    )

    print("=== 4. Состав группы ===")
    response = client.patch(
        f"/api/v1/git/task/{task_id}/groups/{group['id']}",
        json={"commit_ids": commit_ids[:2]},
    )
    check("сокращение состава отвечает 200", response.status_code == 200, response.text[:300])
    payload = response.json() if response.status_code == 200 else {}
    group = find_group(payload, group["id"])
    check("в группе два коммита", group is not None and group["size"] == 2, group and group["size"])
    check("ручное название не затёрто", group is not None and group["title"] == "Выгрузка отчётов")
    check("оставшиеся коммиты вне групп", payload.get("summary", {}).get("ungrouped") == 2)
    statuses = asyncio.run(relation_map(task_id))
    kept_pair = tuple(sorted(commit_ids[:2]))
    check(
        "связь внутри подтверждённой группы подтверждена",
        statuses.get(kept_pair) == "confirmed",
        statuses.get(kept_pair),
    )
    check(
        "связи с выведенными коммитами снова предложены",
        all(
            status == "proposed"
            for pair, status in statuses.items()
            if pair != kept_pair
        ),
        statuses,
    )

    response = client.patch(
        f"/api/v1/git/task/{task_id}/groups/{group['id']}",
        json={"commit_ids": commit_ids[:1]},
    )
    check("группа из одного коммита отклоняется", response.status_code == 400, response.status_code)
    check(
        "код ошибки group_too_small",
        response.status_code == 400 and response.json().get("detail") == "group_too_small",
        response.text[:200],
    )

    print("=== 5. Пересборка сбрасывает ручные правки ===")
    response = client.post(
        f"/api/v1/git/task/{task_id}/groups/analyze", json={"force": True}
    )
    check("пересборка отвечает 200", response.status_code == 200, response.text[:300])
    payload = response.json() if response.status_code == 200 else {}
    group = find_group(payload)
    check("снова одна группа из четырёх", group is not None and group["size"] == 4, group and group["size"])
    check("название снова шаблонное", group is not None and group["title_source"] == "template")
    check("подтверждение сброшено", group is not None and group["status"] == "proposed")

    print("=== 6. Чтение не пересобирает подтверждённое ===")
    response = client.patch(
        f"/api/v1/git/task/{task_id}/groups/{group['id']}",
        json={"status": "confirmed"},
    )
    check("подтверждение перед чтением", response.status_code == 200, response.text[:200])
    response = client.get(f"/api/v1/git/task/{task_id}/groups", params={"ensure": False})
    payload = response.json() if response.status_code == 200 else {}
    group = find_group(payload)
    check("ensure=false не строит заново", group is not None and group["status"] == "confirmed")

finally:
    grouping._embed_texts = original_embeddings if "original_embeddings" in globals() else grouping._embed_texts
    client.close()
    asyncio.run(clear_probe())
    if created_repo is not None:
        asyncio.run(cleanup_repo(created_repo))
    print("\n  Временные задачи удалены")

print("\n" + "=" * 60)
failed = [name for name, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for name in failed:
    print(f"  ПРОВАЛ: {name}")
raise SystemExit(1 if failed else 0)
