"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Отклонённая привязка: отказ должен быть помнящимся, обратимым и не
мешать модели предлагать то же самое снова.

Проверяется, что:
  * отклонение не удаляет связь, а помечает её;
  * модель не предлагает отклонённую пару заново;
  * отклонённый коммит виден в выборе объектов;
  * ручная привязка превращает отклонение в подтверждение;
  * отказ можно вернуть к рассмотрению;
  * отклонённое не попадает ни в карточку, ни в прогресс.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_rejected_link.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import warnings

warnings.filterwarnings("ignore")

import asyncio
import logging

logging.disable(logging.INFO)

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
import app.git.models  # noqa: F401
from app.tasks.progress import get_task_progress
from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.git.models import Commit, CommitFile, GitProviderType, GitRepository, TaskGitLink
from app.main import app
from app.users.models import User

PROJECT = 14
PROBE_URL = "https://example.invalid/probe/reject"
PROBE_SHA = "aaaa1111"
PROBE_TITLE = "Зонд отклонения"

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

repo_id = None
commit_id = None
task_ids = None


async def setup():
    """Репозиторий-зонд с одним коммитом и предложением к двум задачам."""
    global repo_id, commit_id, task_ids

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM tasks WHERE title LIKE :t"),
                           {"t": PROBE_TITLE + "%"})
        await conn.execute(text("DELETE FROM git_repositories WHERE url = :u"),
                           {"u": PROBE_URL})

    async with sm() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id FROM tasks WHERE project_id = :p ORDER BY id LIMIT 2"
                ),
                {"p": PROJECT},
            )
        ).scalars().all()
        task_ids = list(rows)

        repo = GitRepository(
            project_id=PROJECT, url=PROBE_URL, repo_name="probe/reject",
            provider=GitProviderType.GITLAB, default_branch="master",
            access_token="t", connected_by_id=4, is_active=False,
        )
        s.add(repo)
        await s.commit()
        await s.refresh(repo)
        repo_id = repo.id

        commit = Commit(
            repository_id=repo.id, sha=PROBE_SHA,
            message="feat(export): то самое изменение",
            author="probe",
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
        )
        s.add(commit)
        await s.commit()
        await s.refresh(commit)
        commit_id = commit.id

        s.add(CommitFile(commit_id=commit.id, path="src/export.py",
                         status="modified", additions=3, deletions=1, patch="+a\n+b\n-c"))
        await s.commit()

    return repo_id, commit_id, task_ids


async def teardown():
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM task_git_links WHERE target_id IN "
                "(SELECT id FROM git_commits WHERE repository_id = :r)"
            ),
            {"r": repo_id},
        )
        await conn.execute(
            text(
                "DELETE FROM task_commits WHERE commit_id IN "
                "(SELECT id FROM git_commits WHERE repository_id = :r)"
            ),
            {"r": repo_id},
        )
        await conn.execute(
            text("DELETE FROM commit_files WHERE commit_id IN "
                 "(SELECT id FROM git_commits WHERE repository_id = :r)"),
            {"r": repo_id},
        )
        await conn.execute(
            text("DELETE FROM git_commits WHERE repository_id = :r"), {"r": repo_id}
        )
        await conn.execute(
            text("DELETE FROM git_repositories WHERE id = :i"), {"i": repo_id}
        )
        await conn.execute(
            text("DELETE FROM tasks WHERE title LIKE :t"), {"t": PROBE_TITLE + "%"}
        )


def link_state(link_id):
    async def _run():
        async with sm() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT id, status, source, reason FROM task_git_links "
                        "WHERE id = :i"
                    ),
                    {"i": link_id},
                )
            ).mappings().first()
            return dict(row) if row else None

    return asyncio.run(_run())


client = TestClient(app)

try:
    rid, cid, tasks = asyncio.run(setup())
    if not tasks or len(tasks) < 2:
        print("Нужны две задачи в проекте — тест пропущен")
        raise SystemExit(0)
    print(f"=== репозиторий #{rid}, коммит #{cid}, задачи {tasks} ===\n")

    # Предлагаем коммит к первой задаче так, как это делает модель.
    from app.git.tracing import propose_link as _propose

    async def make_proposal():
        async with sm() as s:
            commit = (await s.execute(select(Commit).where(Commit.id == cid))).scalar_one()
            link = await _propose(s, commit, tasks[0], 0.91)
            await s.commit()
            return link.id

    link_id = asyncio.run(make_proposal())
    print(f"  предложение #{link_id} создано моделью\n")

    # ---------------------------------------------------------- #
    print("=== 1. Отклонение помечает связь, а не удаляет ===")
    r = client.post(f"/api/v1/git/suggestions/{link_id}/reject")
    check("отклонение принято", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

    state = link_state(link_id)
    check("связь осталась в базе", state is not None, state)
    check("статус rejected", (state or {}).get("status") == "rejected",
          (state or {}).get("status"))
    check("причина записана",
          "тклонено" in str((state or {}).get("reason") or ""),
          (state or {}).get("reason"))

    # ---------------------------------------------------------- #
    print("\n=== 2. Модель не предлагает отклонённое заново ===")
    before = link_state(link_id)["id"]

    async def propose_again():
        async with sm() as s:
            commit = (await s.execute(select(Commit).where(Commit.id == cid))).scalar_one()
            link = await _propose(s, commit, tasks[0], 0.99)
            await s.commit()
            return link.id

    again = asyncio.run(propose_again())
    check("возвращена та же строка, а не новая", again == before, (again, before))
    check("статус остался rejected", link_state(link_id)["status"] == "rejected")
    check("источник не переписан",
          (link_state(link_id) or {}).get("source") == "model",
          (link_state(link_id) or {}).get("source"))

    # ---------------------------------------------------------- #
    print("\n=== 3. Отклонённый коммит виден в выборе объектов ===")
    r = client.get(f"/api/v1/git/task/{tasks[0]}/unlinked-candidates")
    check("эндпоинт отвечает", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    ids = [c["id"] for c in r.json().get("commits", [])]
    check("коммит есть среди кандидатов", cid in ids, ids[:8])

    # ---------------------------------------------------------- #
    print("\n=== 4. Ручная привязка возвращает коммит в работу ===")
    r = client.post(
        f"/api/v1/git/task/{tasks[0]}/links",
        json={"link_type": "commit", "target_id": cid},
    )
    check("привязка принята", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    state = link_state(link_id)
    check("статус снова confirmed", state["status"] == "confirmed", state["status"])
    check("источник manual", state["source"] == "manual", state["source"])

    async def in_m2m():
        async with sm() as s:
            return (
                await s.execute(
                    text(
                        "SELECT count(*) FROM task_commits "
                        "WHERE task_id = :t AND commit_id = :c"
                    ),
                    {"t": tasks[0], "c": cid},
                )
            ).scalar()

    check("коммит появился в task_commits", asyncio.run(in_m2m()) == 1,
          asyncio.run(in_m2m()))

    # ---------------------------------------------------------- #
    print("\n=== 5. Возврат отказа к рассмотрению ===")
    # Снова отклоняем, чтобы проверить restore.
    r = client.post(f"/api/v1/git/suggestions/{link_id}/reject")
    check("отклонение принято", r.status_code == 200, r.status_code)
    check("статус rejected", link_state(link_id)["status"] == "rejected")

    r = client.post(f"/api/v1/git/suggestions/{link_id}/restore")
    check("возврат выполнен", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    check("статус proposed", link_state(link_id)["status"] == "proposed",
          link_state(link_id)["status"])

    r = client.post(f"/api/v1/git/suggestions/{link_id}/restore")
    check("повторный возврат отклонён — 400", r.status_code == 400, r.status_code)

    # ---------------------------------------------------------- #
    print("\n=== 6. Отклонённое не попадает в карточку и в прогресс ===")
    client.post(f"/api/v1/git/suggestions/{link_id}/reject")

    r = client.get(f"/api/v1/git/task/{tasks[0]}/card")
    check("карточка отвечает", r.status_code == 200, r.status_code)
    card = r.json() if r.status_code == 200 else {}
    commit_ids_in_card = [c["id"] for c in card.get("commits", [])]
    check("в коммитах карточки его нет", cid not in commit_ids_in_card,
          commit_ids_in_card)
    rejected = card.get("rejected", [])
    check("в отдельном списке он есть", any(x["target_id"] == cid for x in rejected),
          rejected)

    async def progress_of(task_id):
        async with sm() as s:
            row = (
                await s.execute(
                    text("SELECT id, title, description, project_id FROM tasks WHERE id = :i"),
                    {"i": task_id},
                )
            ).mappings().first()
            fake = SimpleNamespace(
                id=row["id"], title=row["title"], description=row["description"],
                project_id=row["project_id"],
            )
            return await get_task_progress(s, fake)

    p = asyncio.run(progress_of(tasks[0]))
    check("в прогрессе коммитов не учтено", p["inputs"]["commits"] == 0,
          p["inputs"]["commits"])

    # ---------------------------------------------------------- #
    print("\n=== 7. Цикл скрыть → вернуть не теряет единицу в счётчике ===")
    #
    # Число на вкладке «Разработка» берётся из task_commits. Строку туда
    # добавляет propose_link вместе с предложением, а отклонение её
    # удаляет. Раньше возврат отказа статус не восстанавливал, и после
    # цикла счётчик оставался на единицу меньше навсегда: предложение
    # было на месте, а цифра утверждала обратное.
    async def badge(task_id):
        async with sm() as s:
            return (
                await s.execute(
                    text("SELECT count(*) FROM task_commits WHERE task_id = :t"),
                    {"t": task_id},
                )
            ).scalar()

    # Связь после раздела 6 осталась отклонённой, а на отклонённой
    # propose_link ничего не вставляет — поэтому цикл начинается с
    # возврата, и отсчёт ведётся уже от полного состояния.
    r = client.post(f"/api/v1/git/suggestions/{link_id}/restore")
    check("исходное состояние восстановлено", r.status_code == 200, r.status_code)

    before = asyncio.run(badge(tasks[0]))

    r = client.post(f"/api/v1/git/suggestions/{link_id}/reject")
    check("«Скрыть» принят", r.status_code == 200, r.status_code)
    after_hide = asyncio.run(badge(tasks[0]))
    check("после скрытия счётчик уменьшился",
          after_hide == before - 1, (before, after_hide))

    r = client.post(f"/api/v1/git/suggestions/{link_id}/restore")
    check("«Вернуть» принят", r.status_code == 200, r.status_code)
    after_restore = asyncio.run(badge(tasks[0]))
    check("после возврата счётчик восстановился — единица не потеряна",
          after_restore == before, (before, after_restore))

finally:
    client.close()
    asyncio.run(teardown())
    print("\n  временные записи удалены")

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")