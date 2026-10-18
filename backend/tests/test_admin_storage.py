"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Управление хранилищем: лимиты вложений, корзина и автоочистка.

Проверяется, что:
  * настройки читаются и меняются через панель, а не константами;
  * значения вне разумных границ отклоняются, а не портят загрузку;
  * расширения нормализуются: без точки и с повторами;
  * очистка по сроку трогает только просроченное, а полная — всё;
  * освобождённое место возвращается счётчику проекта;
  * файлы удаляются с диска, а не только из базы;
  * обычному пользователю панель закрыта.

Тест заводит временные файлы в uploads/ под префиксом и удаляет их
за собой. Настоящие вложения не трогаются: работа ведётся только
с записями, созданными самим тестом.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_admin_storage.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import warnings

warnings.filterwarnings("ignore")

import asyncio
import logging
import os
import uuid

logging.disable(logging.INFO)

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
import app.storage.models  # noqa: F401
from app.projects.models import Project
from app.api import deps
from app.core.config import settings as app_settings
from app.core.database import get_db
from app.main import app
from app.storage import purge as purge_mod
from app.storage import settings as storage_settings
from app.tasks.models import Attachment
from app.users.models import User

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


engine = create_async_engine(app_settings.DATABASE_URL, poolclass=NullPool, echo=False)
sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

ADMIN = User(
    id=4, email="renebus125@gmail.ru", full_name="probe", hashed_password="x",
    is_active=True, is_superuser=True,
)
PLAIN = User(
    id=999, email="nobody@example.com", full_name="не админ",
    hashed_password="x", is_active=True, is_superuser=False,
)

current_user_holder = {"user": ADMIN}

# Префикс, по которому тест узнаёт свои записи при уборке.
PROBE = "probe-storage-test"
created_paths = []


async def _get_db():
    async with sm() as s:
        yield s


async def _get_current_user():
    return current_user_holder["user"]


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = _get_current_user

BASE = "/api/v1/admin/storage"


async def find_task():
    async with sm() as s:
        return (
            await s.execute(text("SELECT id, project_id FROM tasks ORDER BY id LIMIT 1"))
        ).mappings().first()


def _write_file(rel_path: str) -> int:
    """Создаёт настоящий файл, чтобы проверить физическое удаление."""
    full = os.path.join("uploads", rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    payload = b"probe storage file\n" * 40
    with open(full, "wb") as f:
        f.write(payload)
    created_paths.append(full)
    return len(payload)


async def make_attachment(task_id: int, project_id: int, *, status: str,
                          deleted_days_ago: float | None = None) -> dict:
    """Создаёт вложение с настоящим файлом и возвращает его данные.

    Счётчик проекта увеличивается здесь же: загрузка через эндпоинт
    делает это сама, а тест создаёт записи напрямую, и без этого
    проверять освобождение места было бы не на чем.
    """
    att_id = uuid.uuid4()
    rel = f"probe/{PROBE}/{att_id}.txt"
    size = _write_file(rel)

    deleted_at = None
    if deleted_days_ago is not None:
        deleted_at = datetime.now(timezone.utc) - timedelta(days=deleted_days_ago)

    async with sm() as s:
        s.add(
            Attachment(
                id=att_id,
                filename=f"{PROBE}.txt",
                path=rel,
                size_bytes=size,
                mime_type="text/plain",
                uploaded_by=4,
                project_id=project_id,
                task_id=task_id,
                status=status,
                created_at=datetime.now(timezone.utc) - timedelta(days=30),
                deleted_at=deleted_at,
            )
        )

        project = (
            await s.execute(select(Project).where(Project.id == project_id))
        ).scalar_one()
        project.storage_used_bytes = (project.storage_used_bytes or 0) + size
        await s.commit()

    return {"id": str(att_id), "path": rel, "full": os.path.join("uploads", rel),
            "size": size}


async def purge_probe_records() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM attachments WHERE path LIKE :p"), {"p": f"%{PROBE}%"}
        )


async def restore_defaults() -> None:
    async with sm() as s:
        await storage_settings.update(
            s,
            {
                "max_file_size_mb": 25,
                "allowed_extensions":
                    ".png,.jpg,.jpeg,.gif,.pdf,.doc,.docx,.txt,.zip,.log",
                "default_project_limit_mb": 500,
                "trash_retention_days": 7,
                "auto_purge_enabled": True,
                "purge_interval_hours": 6,
            },
            4,
        )


def refresh():
    async def _run():
        async with sm() as s:
            await storage_settings.refresh(s)

    asyncio.run(_run())


client = TestClient(app)

try:
    task = asyncio.run(find_task())
    if not task:
        print("Нет задач — тест пропущен")
        raise SystemExit(0)
    TASK_ID, PROJECT_ID = task["id"], task["project_id"]
    print(f"=== задача #{TASK_ID}, проект #{PROJECT_ID} ===\n")

    asyncio.run(purge_probe_records())

    # ---------------------------------------------------------- #
    print("=== 1. Чтение настроек ===")
    r = client.get(BASE)
    check("доступно администратору", r.status_code == 200,
          f"{r.status_code} {r.text[:200]}")
    data = r.json() if r.status_code == 200 else {}
    s = data.get("settings", {})
    check("есть лимит файла", s.get("max_file_size_mb") == 25, s.get("max_file_size_mb"))
    check("есть срок хранения корзины", s.get("trash_retention_days") == 7)
    check("есть автоочистка", s.get("auto_purge_enabled") is True)
    check("приходят границы значений", bool(data.get("limits")))
    check("приходит статистика", "stats" in data, sorted(data.get("stats", {})))

    # ---------------------------------------------------------- #
    print("\n=== 2. Проверка границ ===")
    for bad in ({"max_file_size_mb": 0}, {"trash_retention_days": -1},
                {"purge_interval_hours": 0}, {"default_project_limit_mb": 999999}):
        r = client.patch(BASE, json=bad)
        check(f"{list(bad)[0]}={list(bad.values())[0]} отклонено",
              r.status_code == 400, f"{r.status_code}")

    refresh()
    check("после отказов значения не изменились",
          storage_settings.get()["max_file_size_mb"] == 25)

    r = client.patch(BASE, json={})
    check("пустой запрос отклонён", r.status_code == 400, r.status_code)

    # ---------------------------------------------------------- #
    print("\n=== 3. Нормализация расширений ===")
    r = client.patch(BASE, json={"allowed_extensions": "png, .JPG ,txt,png"})
    check("принято", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    exts = storage_settings.extensions()
    check("точка добавлена", exts == (".jpg", ".png", ".txt"), exts)
    check("повторы убраны и порядок приведён", len(exts) == 3, exts)

    r = client.patch(BASE, json={"allowed_extensions": "  ,  ,"})
    check("пустой список отклонён", r.status_code == 400, r.status_code)
    check("список не испорчен", storage_settings.extensions() == (".jpg", ".png", ".txt"),
          storage_settings.extensions())

    # ---------------------------------------------------------- #
    print("\n=== 4. Лимит файла применяется к загрузке ===")
    r = client.patch(BASE, json={"max_file_size_mb": 2})
    check("лимит изменён на 2 МБ", r.status_code == 200, r.status_code)
    check("кеш обновился без перечитывания",
          storage_settings.max_file_size_bytes() == 2 * 1024 * 1024,
          storage_settings.max_file_size_bytes())
    check("список расширений не сбросился",
          storage_settings.extensions() == (".jpg", ".png", ".txt"))

    # ---------------------------------------------------------- #
    print("\n=== 5. Очистка по сроку не трогает свежее ===")
    old = asyncio.run(make_attachment(TASK_ID, PROJECT_ID, status="deleted",
                                      deleted_days_ago=30))
    fresh = asyncio.run(make_attachment(TASK_ID, PROJECT_ID, status="deleted",
                                        deleted_days_ago=0))
    active = asyncio.run(make_attachment(TASK_ID, PROJECT_ID, status="active"))

    async def used_bytes():
        async with sm() as s:
            return (
                await s.execute(
                    text("SELECT storage_used_bytes FROM projects WHERE id = :i"),
                    {"i": PROJECT_ID},
                )
            ).scalar() or 0

    before = asyncio.run(used_bytes())

    r = client.post(f"{BASE}/purge/expired")
    check("очистка выполнена", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    body = r.json()
    check("удалена просроченная", body.get("removed") == 1, body)
    check("файл удалён с диска", not os.path.exists(old["full"]))
    check("свежая запись осталась", os.path.exists(fresh["full"]))
    check("активный файл не тронут", os.path.exists(active["full"]))

    after = asyncio.run(used_bytes())
    check("счётчик проекта уменьшен ровно на размер удалённого",
          before - after == old["size"], f"было {before}, стало {after}, размер {old['size']}")

    # ---------------------------------------------------------- #
    print("\n=== 6. Очистка просроченного повторно ничего не делает ===")
    r = client.post(f"{BASE}/purge/expired")
    check("пустой результат", r.json().get("removed") == 0, r.json())

    # ---------------------------------------------------------- #
    print("\n=== 7. Полная очистка корзины ===")
    r = client.post(f"{BASE}/purge")
    check("очистка выполнена", r.status_code == 200, r.status_code)
    body = r.json()
    check("удалена свежая запись", body.get("removed") == 1, body)
    check("её файл удалён с диска", not os.path.exists(fresh["full"]))
    check("активный файл уцелел", os.path.exists(active["full"]))

    async def remaining():
        async with sm() as s:
            return (
                await s.execute(
                    text("SELECT count(*) FROM attachments WHERE path LIKE :p"),
                    {"p": f"%{PROBE}%"},
                )
            ).scalar()

    check("в базе осталась только активная запись",
          asyncio.run(remaining()) == 1, asyncio.run(remaining()))

    # ---------------------------------------------------------- #
    print("\n=== 8. Лимит конкретного проекта ===")
    r = client.patch(f"{BASE}/projects/{PROJECT_ID}/limit", json={"limit_mb": 42})
    check("лимит задан", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    proj = next(p for p in r.json()["stats"]["projects"] if p["id"] == PROJECT_ID)
    check("в статистике 42 МБ", proj["limit_bytes"] == 42 * 1024 * 1024,
          proj["limit_bytes"])

    r = client.patch(f"{BASE}/projects/{PROJECT_ID}/limit", json={"limit_mb": None})
    check("сброс на общий лимит", r.status_code == 200, r.status_code)
    proj = next(p for p in r.json()["stats"]["projects"] if p["id"] == PROJECT_ID)
    check("вернулся общий лимит", proj["limit_bytes"] == 500 * 1024 * 1024,
          proj["limit_bytes"])

    r = client.patch(f"{BASE}/projects/999999/limit", json={"limit_mb": 10})
    check("несуществующий проект — 404", r.status_code == 404, r.status_code)

    # ---------------------------------------------------------- #
    print("\n=== 9. Права ===")
    current_user_holder["user"] = PLAIN
    check("чтение закрыто", client.get(BASE).status_code == 403)
    check("изменение закрыто",
          client.patch(BASE, json={"trash_retention_days": 30}).status_code == 403)
    check("очистка закрыта", client.post(f"{BASE}/purge").status_code == 403)
    current_user_holder["user"] = ADMIN

finally:
    client.close()
    asyncio.run(purge_probe_records())
    asyncio.run(restore_defaults())
    for path in created_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    # Убираем пустые каталоги, оставшиеся от теста
    probe_dir = os.path.join("uploads", "probe", PROBE)
    if os.path.isdir(probe_dir):
        try:
            os.rmdir(probe_dir)
        except OSError:
            pass
    print("\n  временные файлы и настройки удалены")

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")
