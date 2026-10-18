"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Ветка по умолчанию доходит от мастера подключения до базы.
Раньше поле default_branch отсутствовало в схеме запроса,
Pydantic его отбрасывал, и репозиторий уезжал в main.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\venv\Scripts\python.exe -W ignore tests\test_branch_default.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

"""Проверка фикса: default_branch из мастера доходит до базы.

Всё через один TestClient без with: каждый запрос получает свой event loop,
поэтому глобальный пул БД между ними использовать нельзя. Ветка читается
ответом GET /projects/{id}/repositories — это и есть то, что видит фронтенд.
"""
import warnings

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
import app.git.models  # noqa: F401
from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.users.models import User

PID = 14
URL = "https://gitlab.com/renebus125/test_project-e2e"
# Тест не должен трогать настоящие подключения: эндпоинт по (project_id, url)
# находит существующий репозиторий и обновляет его — с настоящим URL
# тест переписал бы чужую запись, а в конце удалил бы её.

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


# NullPool: TestClient без with создаёт новый event loop на каждый запрос
engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

TEST_USER = User(
    id=4, email="renebus125@gmail.ru", full_name="probe", hashed_password="x",
    is_active=True, is_superuser=True,  # суперюзер — иначе проверка членства режет
)


async def _get_db():
    async with sm() as s:
        yield s


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = lambda: TEST_USER

client = TestClient(app)
created = []


def branch_of(repo_id):
    """Читает ветку так, как её видит фронтенд."""
    r = client.get(f"/api/v1/projects/{PID}/repositories")
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    for repo in r.json():
        if repo["id"] == repo_id:
            return repo.get("default_branch")
    return "не найден"


def cleanup():
    """Удаляет созданные репозитории напрямую через движок теста."""
    import asyncio

    async def _rm():
        for rid in created:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM git_repositories WHERE id = :i"), {"i": rid}
                )
            print(f"  репозиторий #{rid} удалён")

    asyncio.run(_rm())


try:
    # ---------------------------------------------------------- #
    print("=== 1. Мастер присылает default_branch=master ===")
    r = client.post(
        f"/api/v1/projects/{PID}/repositories",
        json={"url": URL, "provider": "gitlab", "default_branch": "master"},
    )
    check("эндпоинт принял запрос", r.status_code in (200, 201), r.status_code)
    if r.status_code not in (200, 201):
        print(f"      {r.text[:300]}")
        raise SystemExit(1)
    rid = r.json()["id"]
    created.append(rid)
    print(f"  создан репозиторий #{rid}")
    check("в ответе ветка master", r.json().get("default_branch") == "master",
          r.json().get("default_branch"))
    check("в БД через GET тоже master", branch_of(rid) == "master", branch_of(rid))

    # ---------------------------------------------------------- #
    print("\n=== 2. Ветка main сохраняется так же ===")
    r = client.post(
        f"/api/v1/projects/{PID}/repositories",
        json={"url": URL + "-v2", "provider": "gitlab", "default_branch": "main"},
    )
    check("принят", r.status_code in (200, 201), r.status_code)
    if r.status_code in (200, 201):
        rid2 = r.json()["id"]
        created.append(rid2)
        check("в БД main", branch_of(rid2) == "main", branch_of(rid2))

    # ---------------------------------------------------------- #
    print("\n=== 3. Поле не прислали — дефолт, не пусто ===")
    r = client.post(
        f"/api/v1/projects/{PID}/repositories",
        json={"url": URL + "-v3", "provider": "gitlab"},
    )
    check("принят", r.status_code in (200, 201), r.status_code)
    if r.status_code in (200, 201):
        rid3 = r.json()["id"]
        created.append(rid3)
        b = branch_of(rid3)
        check("в БД не пусто", bool(b), repr(b))

    # ---------------------------------------------------------- #
    print("\n=== 4. PATCH меняет ветку ===")
    r = client.patch(
        f"/api/v1/projects/{PID}/repositories/{rid}",
        json={"default_branch": "develop"},
    )
    check("PATCH принят", r.status_code == 200, r.status_code)
    check("в БД develop", branch_of(rid) == "develop", branch_of(rid))

    # ---------------------------------------------------------- #
    print("\n=== 5. Повторное подключение того же URL обновляет ветку ===")
    r = client.post(
        f"/api/v1/projects/{PID}/repositories",
        json={"url": URL, "provider": "gitlab", "default_branch": "master"},
    )
    check("принят", r.status_code in (200, 201), r.status_code)
    check("тот же id, ветка обновилась",
          r.json().get("id") == rid and branch_of(rid) == "master",
          f"id={r.json().get('id')} ветка={branch_of(rid)}")

    # ---------------------------------------------------------- #
    print("\n=== 6. Повторное подключение без ветки не затирает ===")
    r = client.post(
        f"/api/v1/projects/{PID}/repositories",
        json={"url": URL, "provider": "gitlab"},
    )
    check("принят", r.status_code in (200, 201), r.status_code)
    check("ветка осталась master", branch_of(rid) == "master", branch_of(rid))

finally:
    client.close()
    print("\n=== Уборка ===")
    cleanup()

    r2 = TestClient(app)
    left = r2.get(f"/api/v1/projects/{PID}/repositories").json()
    r2.close()
    # Проверяем свои репозитории, а не «в проекте ничего не осталось»:
    # настоящее подключение пользователя имеет право остаться на месте.
    ours = [x for x in left if "test_project-e2e" in (x.get("url") or "")]
    check("тестовых репозиториев не осталось", not ours, [x["url"] for x in ours])

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")