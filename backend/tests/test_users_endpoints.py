"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Регистрация и выдача пользователей не падают с MissingGreenlet.
Связь git_accounts грузится заранее, а не лениво на сериализации.
Созданного пользователя скрипт удаляет сам.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\venv\Scripts\python.exe -W ignore tests\test_users_endpoints.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import asyncio
import logging
import warnings

warnings.filterwarnings("ignore")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.main import app
from app.users.models import User

TEST_EMAIL = "greenlet-probe@diplom-probe.ru"

# Отдельный движок: NullPool не держит соединений между вызовами,
# поэтому запросы из asyncio.run не конфликтуют с пулом приложения.
probe_engine = create_async_engine(
    settings.DATABASE_URL, poolclass=NullPool, echo=False
)

# Тот же NullPool, но под видом фабрики сессий — её подставляем в
# зависимость get_db приложения.
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

app_session = async_sessionmaker(
    bind=probe_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_db():
    """Сессия на NullPool.

    TestClient без контекстного менеджера создаёт новый event loop на
    каждый запрос, и соединения из обычного пула переиспользуются в
    другой петле — asyncpg падает. NullPool открывает соединение заново
    на каждый запрос, поэтому тест работает.

    Откатывать commit нельзя: регистрация после commit вызывает
    db.refresh(), и на несохранённом объекте это падает. Пользователь,
    которого создаёт тест, удаляется в конце явно.
    """
    async with app_session() as session:
        yield session


app.dependency_overrides[get_db] = override_db

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


async def fetch_admin():
    async with probe_engine.connect() as conn:
        r = await conn.execute(
            text("SELECT id, email, full_name, is_superuser, is_active "
                 "FROM users WHERE is_superuser IS true LIMIT 1")
        )
        row = r.mappings().first()
    if row is None:
        return None
    u = User(
        id=row["id"], email=row["email"], full_name=row["full_name"],
        is_superuser=row["is_superuser"], is_active=row["is_active"],
        hashed_password="x",
    )
    return u


async def fetch_admin_full_name(user_id):
    async with probe_engine.connect() as conn:
        r = await conn.execute(
            text("SELECT full_name FROM users WHERE id = :i"), {"i": user_id}
        )
        return r.scalar()


async def count_probes():
    async with probe_engine.connect() as conn:
        r = await conn.execute(
            text("SELECT count(*) FROM users WHERE email LIKE :p"),
            {"p": "greenlet-probe@%"},
        )
        return r.scalar()


async def restore_admin_name(user_id, name):
    async with probe_engine.connect() as conn:
        await conn.execute(
            text("UPDATE users SET full_name = :n WHERE id = :i"),
            {"n": name, "i": user_id},
        )
        await conn.commit()


async def purge_probes():
    async with probe_engine.connect() as conn:
        r = await conn.execute(
            text("SELECT id FROM users WHERE email LIKE :p"), {"p": "greenlet-probe@%"}
        )
        ids = [row[0] for row in r.fetchall()]
        if ids:
            # Каскадов на users нет намеренно — чистим зависимости руками
            await conn.execute(
                text("DELETE FROM notifications WHERE user_id = ANY(:ids)"), {"ids": ids}
            )
            await conn.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids}
            )
        await conn.commit()
        return len(ids)


admin = asyncio.run(fetch_admin())
print(f"суперпользователь: {admin.email if admin else 'НЕТ В БАЗЕ'}")
print(f"его ФИО до теста:   {admin.full_name if admin else '—'}\n")

# Убираем следы предыдущих прогонов: тест должен быть независим
stale = asyncio.run(purge_probes())
if stale:
    print(f"(убрано пользователей от прошлых прогонов: {stale})\n")

client = TestClient(app)  # без with: lifespan не выполняется

from app.api import deps  # noqa: E402

if admin is not None:
    app.dependency_overrides[deps.get_current_active_superuser] = lambda: admin

# ------------------------------------------------------------------ #
print("=== 1. Регистрация нового пользователя (падала с MissingGreenlet) ===")
r = client.post(
    "/api/v1/auth/register",
    json={"email": TEST_EMAIL, "password": "VerySecret123", "full_name": "Проба Greenlet"},
)
check("POST /auth/register вернул 200", r.status_code == 200, r.status_code)
if r.status_code == 200:
    body = r.json()
    check("в ответе есть id", "id" in body, list(body.keys()))
    check("поле git_accounts присутствует", "git_accounts" in body, body.get("git_accounts"))
    check("git_accounts — пустой список", body.get("git_accounts") == [], body.get("git_accounts"))
else:
    print(f"      тело ответа: {r.text[:400]}")

# ------------------------------------------------------------------ #
print("\n=== 2. Повторная регистрация того же email ===")
r2 = client.post(
    "/api/v1/auth/register",
    json={"email": TEST_EMAIL, "password": "VerySecret123", "full_name": "Проба 2"},
)
check("занятый email отклонён (400)", r2.status_code == 400, r2.status_code)
check("не 500", r2.status_code != 500, r2.status_code)

# ------------------------------------------------------------------ #
print("\n=== 3. Список пользователей админа (падал с 500) ===")
if admin is None:
    check("нашёлся суперпользователь", False)
else:
    r3 = client.get("/api/v1/admin/users", params={"query": ""})
    check("GET /admin/users вернул 200", r3.status_code == 200, r3.status_code)
    if r3.status_code == 200:
        users = r3.json()
        check("получен список", isinstance(users, list), type(users).__name__)
        check("список не пуст", len(users) > 0, len(users))
        check(
            "у каждого есть git_accounts",
            all("git_accounts" in u for u in users),
            [u.get("email") for u in users if "git_accounts" not in u][:3],
        )
        check(
            "git_accounts — именно списки",
            all(isinstance(u.get("git_accounts"), list) for u in users),
            [u.get("email") for u in users if not isinstance(u.get("git_accounts"), list)][:3],
        )
    else:
        print(f"      тело ответа: {r3.text[:400]}")

    r4 = client.get("/api/v1/admin/users", params={"query": "adm"})
    check("поиск по query отработал", r4.status_code == 200, r4.status_code)
    if r4.status_code == 200:
        found = r4.json()
        check("поиск что-то нашёл", len(found) > 0, len(found))
        check("в найденных тоже git_accounts", all("git_accounts" in u for u in found))

# ------------------------------------------------------------------ #
print("\n=== 4. Правка пользователя админом (тоже отдаёт UserSchema) ===")
if admin is not None:
    r5 = client.patch(
        f"/api/v1/admin/users/{admin.id}", json={"full_name": "Админ (проверка)"}
    )
    check("PATCH /admin/users/{id} вернул 200", r5.status_code == 200, r5.status_code)
    if r5.status_code == 200:
        check("в ответе есть git_accounts", "git_accounts" in r5.json(), list(r5.json().keys()))
    else:
        print(f"      тело ответа: {r5.text[:300]}")

# ------------------------------------------------------------------ #
print("\n=== 5. Уборка ===")
removed = asyncio.run(purge_probes())
check("тестовые пользователи удалены", removed > 0, f"удалено: {removed}")
left = asyncio.run(count_probes())
check("в базе не осталось следов", left == 0, left)

if admin is not None:
    # PATCH выше записал новое ФИО — возвращаем как было
    asyncio.run(restore_admin_name(admin.id, admin.full_name))
    now = asyncio.run(fetch_admin_full_name(admin.id))
    check("ФИО админа восстановлено", now == admin.full_name, now)

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")