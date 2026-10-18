"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Подтверждение и отклонение предложения модели: связь сохраняется,
тип коммита считается сразу, а не при следующей синхронизации.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\venv\Scripts\python.exe -W ignore tests\test_suggestion_confirm.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import warnings

warnings.filterwarnings("ignore")

import logging
logging.disable(logging.INFO)

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
TASK_ID = 11  # «Выгрузка отчётов в CSV»

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
created_commit_id = None
created_link_id = None
client = TestClient(app)

import asyncio


async def setup():
    """Готовит репозиторий, коммит и предложение в БД."""
    global created_repo, created_commit_id, created_link_id

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM task_git_links WHERE task_id = :t"), {"t": TASK_ID}
        )
        await conn.execute(
            text(
                "DELETE FROM git_commits WHERE repository_id IN "
                "(SELECT id FROM git_repositories WHERE project_id = :p) AND sha = :s"
            ),
            {"p": PROJECT, "s": "deadbeef"},
        )
        await conn.execute(
            text("DELETE FROM git_repositories WHERE project_id = :p AND url = :u"),
            {"p": PROJECT, "u": "https://example.invalid/probe/sugg"},
        )

    async with sm() as s:
        repo = GitRepository(
            project_id=PROJECT,
            url="https://example.invalid/probe/sugg",
            repo_name="probe/sugg",
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

        commit = Commit(
            repository_id=repo.id,
            sha="deadbeef",
            message="feat(export): выгрузка отчётов в CSV",
            author="probe",
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
        )
        s.add(commit)
        await s.commit()
        await s.refresh(commit)
        created_commit_id = commit.id

        link = TaskGitLink(
            task_id=TASK_ID,
            link_type="commit",
            target_id=commit.id,
            source="model",
            confidence=0.71,
            status="proposed",
            reason="Предложено по смыслу изменений (уверенность 0.71)",
        )
        s.add(link)
        await s.commit()
        await s.refresh(link)
        created_link_id = link.id

    return created_repo, created_commit_id, created_link_id


async def read_state(link_id):
    async with sm() as s:
        row = (
            await s.execute(
                text(
                    "SELECT l.status, l.source, l.created_by_id AS created_by, "
                    "gc.commit_type, gc.commit_type_confidence, "
                    "(SELECT count(*) FROM task_commits tc "
                    " WHERE tc.task_id = l.task_id AND tc.commit_id = l.target_id) AS in_m2m "
                    "FROM task_git_links l JOIN git_commits gc ON gc.id = l.target_id "
                    "WHERE l.id = :i"
                ),
                {"i": link_id},
            )
        ).mappings().first()
        return dict(row) if row else {}


async def teardown():
    async with engine.begin() as conn:
        # Подчищаем всё, что создал тест, по репозиторию — так нельзя
        # случайно задеть чужие связи.
        await conn.execute(
            text(
                "DELETE FROM task_git_links WHERE target_id IN "
                "(SELECT id FROM git_commits WHERE repository_id = :r)"
            ),
            {"r": created_repo},
        )
        await conn.execute(
            text("DELETE FROM task_commits WHERE commit_id IN "
                 "(SELECT id FROM git_commits WHERE repository_id = :r)"),
            {"r": created_repo},
        )
        await conn.execute(
            text("DELETE FROM git_commits WHERE repository_id = :r"), {"r": created_repo}
        )
        await conn.execute(
            text("DELETE FROM git_repositories WHERE id = :i"), {"i": created_repo}
        )


try:
    rid, cid, lid = asyncio.run(setup())
    print(f"=== подготовлено: репозиторий #{rid}, коммит #{cid}, предложение #{lid} ===\n")

    before = asyncio.run(read_state(lid))
    print(f"  до подтверждения: {before}")
    check("предложение в статусе proposed", before.get("status") == "proposed", before.get("status"))
    check("типа ещё нет", before.get("commit_type") is None, before.get("commit_type"))

    # ---------------------------------------------------------- #
    print("\n=== 1. Подтверждение предложения ===")
    r = client.post(f"/api/v1/git/suggestions/{lid}/confirm")
    check("эндпоинт вернул 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

    after = asyncio.run(read_state(lid))
    print(f"  после: {after}")
    check("статус confirmed", after.get("status") == "confirmed", after.get("status"))
    # Источник не перетирается: он отвечает на вопрос «как связь найдена»,
    # а status — «подтвердил ли человек». Раньше здесь стояло "manual",
    # и после подтверждения бейдж «модель» исчезал навсегда.
    check("источник остался model", after.get("source") == "model", after.get("source"))
    check("признак подтверждения есть (created_by)",
          after.get("created_by") is not None, after.get("created_by"))
    check(
        "тип посчитан сразу, без ожидания синхронизации",
        after.get("commit_type") is not None,
        after.get("commit_type"),
    )
    check("уверенность типа записана", after.get("commit_type_confidence") is not None,
          after.get("commit_type_confidence"))
    check("связь есть в task_commits", (after.get("in_m2m") or 0) >= 1, after.get("in_m2m"))

    # ---------------------------------------------------------- #
    print("\n=== 2. Отклонение предложения ===")
    lid2 = None
    cid2 = None

    async def make_second():
        # Отдельный коммит: на один (task, link_type, target_id) стоит
        # уникальный индекс, второе предложение так не создать.
        global lid2, cid2
        async with sm() as s:
            commit2 = Commit(
                repository_id=rid, sha="feedface",
                message="fix(dates): разбор даты в формате ДД.ММ.ГГГГ",
                author="probe",
                timestamp=datetime.now(timezone.utc) - timedelta(days=1),
            )
            s.add(commit2)
            await s.commit()
            await s.refresh(commit2)
            cid2 = commit2.id

            link = TaskGitLink(
                task_id=TASK_ID, link_type="commit", target_id=cid2,
                source="model", confidence=0.44, status="proposed",
                reason="Предложено по смыслу изменений (уверенность 0.44)",
            )
            s.add(link)
            await s.flush()
            await s.execute(
                text("INSERT INTO task_commits (task_id, commit_id) VALUES (:t, :c)"),
                {"t": TASK_ID, "c": cid2},
            )
            await s.commit()
            await s.refresh(link)
            lid2 = link.id
        return lid2

    asyncio.run(make_second())
    r = client.post(f"/api/v1/git/suggestions/{lid2}/reject")
    check("отклонение вернуло 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

    async def after_reject():
        async with sm() as s:
            link = (
                await s.execute(
                    text("SELECT count(*) FROM task_git_links WHERE id = :i"), {"i": lid2}
                )
            ).scalar()
            m2m = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM task_commits "
                        "WHERE task_id = :t AND commit_id = :c"
                    ),
                    {"t": TASK_ID, "c": cid2},
                )
            ).scalar()
            return link, m2m

    n_link, n_m2m = asyncio.run(after_reject())
    # Отклонение больше не удаляет строку: она помечается rejected, чтобы
    # модель не предлагала тот же коммит заново и чтобы отказ можно было
    # пересмотреть. Подробнее — в test_rejected_link.py.
    check("предложение помечено отклонённым, а не удалено", n_link == 1, n_link)
    check("связь из task_commits убрана", n_m2m == 0, n_m2m)

    async def rejected_status():
        async with sm() as s:
            return (
                await s.execute(
                    text("SELECT status FROM task_git_links WHERE id = :i"),
                    {"i": lid2},
                )
            ).scalar()

    check("статус rejected", asyncio.run(rejected_status()) == "rejected",
          asyncio.run(rejected_status()))

finally:
    client.close()
    asyncio.run(teardown())
    print("\n  временные записи удалены")

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")