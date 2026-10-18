"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL.

Поиск пользователей для приглашения в проект.

Раньше эндпоинт падал в 500, как только поиск хоть кого-то находил:
схема ответа читает у пользователя git_accounts, а связь не была
подгружена, и обращение к ней уходило вне greenlet. На пустом запросе
список пуст и сериализации нет, поэтому поломка не проявлялась —
окно приглашений просто показывало пустоту, а ошибка уходила в консоль.

Проверяется, что:
  * пустой запрос даёт пустой список, а не ошибку;
  * поиск по имени и по почте находит пользователей;
  * в ответе заполнены вложенные git_accounts — именно их не хватало;
  * поиск отбрасывает неактивных пользователей;
  * список ролей и список участников проекта отвечают.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_user_search.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено».
Данные не изменяются — все запросы только на чтение.
"""

import warnings

warnings.filterwarnings("ignore")

import logging

logging.disable(logging.INFO)

from datetime import datetime, timezone

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

PROJECT = 14
ME = 4

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

TEST_USER = User(
    id=ME, email="renebus125@gmail.ru", full_name="probe", hashed_password="x",
    is_active=True, is_superuser=True,
)


async def _get_db():
    async with sm() as s:
        yield s


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = lambda: TEST_USER
client = TestClient(app)


def search(q):
    """Поиск пользователей. Исключение возвращается как код.

    Без этого TestClient на сломанном эндпоинте поднимает ошибку наружу,
    и проверка обрывается на середине — падение видно, но непонятно,
    что именно сломалось. Так поломка превращается в обычный провал с
    указанием на конкретную проверку.
    """
    try:
        r = client.get("/api/v1/users/", params={"query": q})
        return r.status_code, (r.json() if r.status_code == 200 else None), r.text
    except Exception as exc:  # noqa: BLE001 - нам важно лишь зафиксировать факт
        return None, None, f"{type(exc).__name__}: {exc}"


def db_count(sql, params=None):
    async def _run():
        async with sm() as s:
            return (await s.execute(text(sql), params or {})).scalar()

    return __import__("asyncio").run(_run())


try:
    # ---------------------------------------------------------- #
    print("=== 1. Сколько всего активных пользователей ===")
    total_active = db_count("SELECT count(*) FROM users WHERE is_active")
    print(f"  активных пользователей в системе: {total_active}")

    # ---------------------------------------------------------- #
    print("\n=== 2. Пустой запрос ===")
    code, data, text_ = search("")
    check("пустой запрос отвечает 200", code == 200, code)
    check("список пуст", data == [], data)

    # ---------------------------------------------------------- #
    print("\n=== 3. Поиск, который что-то находит ===")
    # Берём реальную почту из базы, чтобы запрос гарантированно дал
    # непустой результат: проверка не должна зависеть от того, что в
    # системе случайно окажется.
    email = db_count(
        "SELECT email FROM users WHERE is_active AND id <> :me ORDER BY id LIMIT 1",
        {"me": ME},
    )
    if not email:
        print("  НЕТ активных пользователей кроме текущего — проверка неполна")
    else:
        local = email.split("@")[0]
        print(f"  ищем по: local={local!r}, email={email!r}")

        code, data, text_ = search(local)
        check("поиск отвечает 200", code == 200, f"{code} {text_[:160]}")
        check("нашёл кого-то", bool(data), f"{len(data) if data else 0}")

        code, data, text_ = search(email)
        check("поиск по полной почте отвечает 200", code == 200, f"{code} {text_[:160]}")
        check("нашёл по полной почте", bool(data), f"{len(data) if data else 0}")

        if data:
            first = data[0]
            check("в ответе есть почта", bool(first.get("email")), first.get("email"))
            # Именно это поле роняло эндпоинт: без подгруженной связи
            # чтение уходило вне greenlet.
            check("вложенные git_accounts заполнены (не null)",
                  "git_accounts" in first and first["git_accounts"] is not None,
                  first.get("git_accounts", "ПОЛЯ НЕТ"))

    # ---------------------------------------------------------- #
    print("\n=== 4. Неактивные пользователи не показываются ===")
    code, data, text_ = search("@")
    if code == 200 and data:
        active_ids = {u["id"] for u in data if u.get("is_active")}
        shown_ids = {u["id"] for u in data}
        check("в выдаче только активные", active_ids == shown_ids,
              f"неактивных среди показанных: {sorted(shown_ids - active_ids)}")
    else:
        check("широкий поиск отвечает", False, f"{code} {text_[:120]}")

    # ---------------------------------------------------------- #
    print("\n=== 5. Смежные запросы окна участников ===")
    r = client.get("/api/v1/projects/roles")
    check("список ролей отвечает", r.status_code == 200, r.status_code)
    check("роли пришли", bool(r.json()) if r.status_code == 200 else False,
          len(r.json()) if r.status_code == 200 else "")

    r = client.get(f"/api/v1/projects/{PROJECT}/members")
    check("участники проекта отвечают", r.status_code == 200, r.status_code)

    r = client.get(f"/api/v1/projects/{PROJECT}/invites")
    check("приглашения проекта отвечают", r.status_code == 200, r.status_code)

finally:
    client.close()

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")