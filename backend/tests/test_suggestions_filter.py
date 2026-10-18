"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Фильтр предложений по задаче: карточка задачи показывает только свои
предложения, а все предложения проекта по-прежнему доступны без фильтра.
Заодно проверяется, что задача чужого проекта не открывается по номеру.

Тест заводит собственный репозиторий-зонд и удаляет всё по его id,
поэтому чужие предложения не затрагиваются.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\venv\Scripts\python.exe -W ignore tests\test_suggestions_filter.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import warnings

warnings.filterwarnings("ignore")

import logging

logging.disable(logging.INFO)

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
import app.git.models  # noqa: F401
from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.git.models import Commit, GitProviderType, GitRepository, TaskGitLink
from app.main import app
from app.users.models import User

PROJECT = 14
PROBE_URL = "https://example.invalid/probe/filter"

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

TEST_USER = User(
    id=4, email="renebus125@gmail.ru", full_name="probe", hashed_password="x",
    is_active=True, is_superuser=True,
)


async def _get_db():
    async with sm() as s:
        yield s


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = lambda: TEST_USER

created_repo = None
task_a = None
task_b = None
foreign_task = None
client = TestClient(app)


async def find_tasks():
    """Две задачи проекта-зонда и одна задача чужого проекта."""
    global task_a, task_b, foreign_task
    async with sm() as s:
        ours = (
            await s.execute(
                text(
                    "SELECT id, title FROM tasks WHERE project_id = :p ORDER BY id LIMIT 2"
                ),
                {"p": PROJECT},
            )
        ).mappings().all()
        other = (
            await s.execute(
                text(
                    "SELECT id FROM tasks WHERE project_id != :p "
                    "ORDER BY id LIMIT 1"
                ),
                {"p": PROJECT},
            )
        ).scalar()
    if len(ours) < 2 or other is None:
        return None
    task_a, task_b = ours[0]["id"], ours[1]["id"]
    foreign_task = other
    return task_a, task_b


async def setup():
    """Репозиторий-зонд, два коммита и по предложению на каждую задачу."""
    global created_repo

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM git_repositories WHERE url = :u"), {"u": PROBE_URL}
        )

    async with sm() as s:
        repo = GitRepository(
            project_id=PROJECT,
            url=PROBE_URL,
            repo_name="probe/filter",
            provider=GitProviderType.GITHUB,
            default_branch="main",
            access_token="t",
            connected_by_id=4,
            is_active=False,  # чтобы фоновая сверка его не трогала
        )
        s.add(repo)
        await s.commit()
        await s.refresh(repo)
        created_repo = repo.id

        for sha, msg, task_id, conf in (
            ("aaaabbbb", "feat(export): выгрузка отчётов в CSV", task_a, 0.91),
            ("ccccdddd", "fix(dates): разбор даты в формате ДД.ММ.ГГГГ", task_b, 0.94),
        ):
            commit = Commit(
                repository_id=repo.id,
                sha=sha,
                message=msg,
                author="probe",
                timestamp=datetime.now(timezone.utc) - timedelta(days=1),
            )
            s.add(commit)
            await s.flush()

            s.add(
                TaskGitLink(
                    task_id=task_id,
                    link_type="commit",
                    target_id=commit.id,
                    source="model",
                    confidence=conf,
                    status="proposed",
                    reason="Предложено по смыслу изменений",
                )
            )
        await s.commit()

    return created_repo


async def teardown():
    if created_repo is None:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM task_git_links WHERE target_id IN "
                "(SELECT id FROM git_commits WHERE repository_id = :r)"
            ),
            {"r": created_repo},
        )
        await conn.execute(
            text(
                "DELETE FROM task_commits WHERE commit_id IN "
                "(SELECT id FROM git_commits WHERE repository_id = :r)"
            ),
            {"r": created_repo},
        )
        await conn.execute(
            text("DELETE FROM git_commits WHERE repository_id = :r"), {"r": created_repo}
        )
        await conn.execute(
            text("DELETE FROM git_repositories WHERE id = :i"), {"i": created_repo}
        )


def task_ids_of(payload):
    return sorted({s["task_id"] for s in payload})


try:
    found = asyncio.run(find_tasks())
    if not found:
        print("Не нашлись две задачи проекта и задача чужого проекта — тест пропущен")
        raise SystemExit(0)

    print(f"=== задачи проекта {PROJECT}: {task_a}, {task_b}; чужой проект: {foreign_task}\n")

    rid = asyncio.run(setup())
    print(f"=== подготовлено: репозиторий-зонд #{rid} ===\n")

    # ---------------------------------------------------------- #
    print("=== 1. Без фильтра отдаём предложения всего проекта ===")
    r = client.get(f"/api/v1/git/{rid}/suggestions")
    check("эндпоинт вернул 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    all_sug = r.json()
    check("видны предложения обеих задач", task_ids_of(all_sug) == sorted([task_a, task_b]),
          task_ids_of(all_sug))
    check("все предложения — из репозитория-зонда",
          all(s["commit_id"] for s in all_sug) and len(all_sug) == 2, len(all_sug))

    # ---------------------------------------------------------- #
    print(f"\n=== 2. Фильтр task_id={task_a} ===")
    r = client.get(f"/api/v1/git/{rid}/suggestions", params={"task_id": task_a})
    check("эндпоинт вернул 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    sug_a = r.json()
    check("вернулось ровно одно предложение", len(sug_a) == 1, len(sug_a))
    check("оно принадлежит запрошенной задаче",
          all(s["task_id"] == task_a for s in sug_a), task_ids_of(sug_a))
    check("уверенность сохранена", sug_a and abs(sug_a[0]["confidence"] - 0.91) < 1e-6,
          sug_a[0]["confidence"] if sug_a else None)
    check("сообщение коммита на месте",
          sug_a and "выгрузка" in sug_a[0]["commit_message"],
          sug_a[0]["commit_message"] if sug_a else None)

    # ---------------------------------------------------------- #
    print(f"\n=== 3. Фильтр task_id={task_b} ===")
    r = client.get(f"/api/v1/git/{rid}/suggestions", params={"task_id": task_b})
    sug_b = r.json()
    check("вернулось ровно одно предложение", len(sug_b) == 1, len(sug_b))
    check("оно принадлежит запрошенной задаче",
          all(s["task_id"] == task_b for s in sug_b), task_ids_of(sug_b))
    check("это другое предложение, не из первой задачи",
          not sug_a or not sug_b or sug_a[0]["link_id"] != sug_b[0]["link_id"])

    # ---------------------------------------------------------- #
    print("\n=== 4. Утечки между проектами и граничные значения ===")
    r = client.get(f"/api/v1/git/{rid}/suggestions", params={"task_id": foreign_task})
    check("чужая задача не открывает предложения",
          r.status_code == 200 and r.json() == [], f"{r.status_code} {r.json()}")

    r = client.get(f"/api/v1/git/{rid}/suggestions", params={"task_id": 99999999})
    check("несуществующая задача даёт пустой список",
          r.status_code == 200 and r.json() == [], f"{r.status_code} {r.json()}")

    r = client.get(f"/api/v1/git/{rid}/suggestions", params={"task_id": "abc"})
    check("некорректный task_id не ломает эндпоинт",
          r.status_code in (200, 422), f"{r.status_code} {r.text[:120]}")

    r = client.get("/api/v1/git/99999999/suggestions")
    check("несуществующий репозиторий даёт 404", r.status_code == 404, r.status_code)

finally:
    client.close()
    asyncio.run(teardown())
    print("\n  временные записи удалены")

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")