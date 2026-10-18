"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL.

Фон страницы проекта: общий для всех участников, переключается тем же
правом project:edit, что и название.

Проверяется, что:
  * новый проект без фона;
  * базовый фон включается обычным обновлением;
  * вид "custom" через обновление поставить нельзя — иначе был бы
    битый фон без картинки;
  * загрузка файла включает свой фон и кладёт файл на диск;
  * некартинка и пустой файл отвергаются;
  * повторная загрузка убирает прежний файл, а не копит их;
  * снятие фона удаляет файл;
  * уход на базовый тоже удаляет пользовательский файл.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_project_background.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено».
Временный проект создаётся и удаляется сам.
"""

import warnings

warnings.filterwarnings("ignore")

import asyncio
import io
import logging
import os
import struct
import zlib

logging.disable(logging.INFO)

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
import app.git.models  # noqa: F401
from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.projects.models import Project, ProjectMember
from app.users.models import User

PROBE_NAME = "Зонд фона"
USER_ID = 4

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


def make_png(width=8, height=8, rgb=(200, 220, 255)) -> bytes:
    """Настоящий PNG нужного размера — сервер смотрит сигнатуру."""
    raw = b""
    for _ in range(height):
        raw += b"\x00" + bytes(rgb) * width

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


# Тот же белый прямоугольник, но в обёртке JPEG: подпись файла другая,
# и прежний .png при загрузке должен исчезнуть.
JPEG_STUB = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 40 + b"\xff\xd9"

engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

TEST_USER = User(
    id=USER_ID, email="probe@example.invalid", full_name="probe",
    hashed_password="x", is_active=True, is_superuser=True,
)


async def _get_db():
    async with sm() as s:
        yield s


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = lambda: TEST_USER
client = TestClient(app)

probe_id = None


async def setup() -> int:
    global probe_id
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM projects WHERE name = :n"), {"n": PROBE_NAME})
        await conn.execute(
            text("DELETE FROM task_git_links WHERE task_id NOT IN (SELECT id FROM tasks)")
        )

    async with sm() as s:
        project = Project(name=PROBE_NAME, owner_id=USER_ID, description="временный")
        s.add(project)
        await s.commit()
        await s.refresh(project)
        probe_id = project.id

        # Строка участия обязательна: список проектов ищет по ней, и без
        # неё временного проекта там просто не видно. Руководитель —
        # именно та роль, которой положено менять фон.
        s.add(ProjectMember(project_id=probe_id, user_id=USER_ID, role="project_manager"))
        await s.commit()
    return probe_id


def background_files(project_id: int):
    directory = os.path.join("uploads", "projects", str(project_id))
    if not os.path.isdir(directory):
        return []
    return sorted(n for n in os.listdir(directory) if n.startswith("background."))


async def teardown():
    if probe_id is None:
        return
    directory = os.path.join("uploads", "projects", str(probe_id))
    async with engine.begin() as conn:
        # Участие снимаем явно: проект удаляется прямым SQL, а каскад на
        # уровне базы у project_members не объявлен.
        await conn.execute(
            text("DELETE FROM project_members WHERE project_id = :i"), {"i": probe_id}
        )
        await conn.execute(text("DELETE FROM projects WHERE id = :i"), {"i": probe_id})
    # Каталог проекта на диске остаётся только с тем, что положила
    # проверка; удаляем целиком.
    if os.path.isdir(directory) and not os.listdir(directory):
        os.rmdir(directory)


try:
    pid = asyncio.run(setup())
    print(f"=== временный проект #{pid} ===\n")

    # ---------------------------------------------------------- #
    print("=== 1. Новый проект без фона ===")
    r = client.get("/api/v1/projects/", params={"skip": 0, "limit": 200})
    check("список проектов отвечает", r.status_code == 200, r.status_code)
    found = [p for p in (r.json() or []) if p["id"] == pid]
    check("проект виден в списке", bool(found))
    if found:
        check("фон пустой", found[0]["background"] == "none", found[0]["background"])
        check("адреса фона нет", not found[0]["background_url"], found[0]["background_url"])

    # ---------------------------------------------------------- #
    print("\n=== 2. Базовый фон включается обычным обновлением ===")
    r = client.patch(f"/api/v1/projects/{pid}", json={"background": "default"})
    check("обновление принято", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        check("вид default", r.json()["background"] == "default", r.json()["background"])
        check("адрес остался пустым",
              not r.json()["background_url"], r.json()["background_url"])

    r = client.patch(f"/api/v1/projects/{pid}", json={"background": "none"})
    check("снятие фона принято", r.status_code == 200, r.status_code)
    if r.status_code == 200:
        check("вид none", r.json()["background"] == "none", r.json()["background"])

    # ---------------------------------------------------------- #
    print("\n=== 3. Вид custom через обновление поставить нельзя ===")
    r = client.patch(f"/api/v1/projects/{pid}", json={"background": "custom"})
    check("отвергнуто 422", r.status_code == 422, f"{r.status_code} {r.text[:140]}")
    r = client.patch(f"/api/v1/projects/{pid}", json={"background": "мусор"})
    check("чужое значение отвергнуто", r.status_code == 422, r.status_code)

    # ---------------------------------------------------------- #
    print("\n=== 4. Загрузка включает свой фон ===")
    r = client.post(
        f"/api/v1/projects/{pid}/background",
        files={"file": ("background.png", make_png(), "image/png")},
    )
    check("загрузка принята", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    body = r.json() if r.status_code == 200 else {}
    check("вид custom", body.get("background") == "custom", body.get("background"))
    url = body.get("background_url") or ""
    check("адрес указывает на файл проекта",
          url.startswith(f"/uploads/projects/{pid}/background"), url)
    check("в адресе есть метка времени для сброса кэша",
          "?v=" in url, url)
    check("файл лежит на диске",
          background_files(pid) == ["background.png"], background_files(pid))

    on_disk = os.path.join("uploads", "projects", str(pid), "background.png")
    with open(on_disk, "rb") as f:
        written = f.read()
    check("на диске действительно картинка",
          written.startswith(b"\x89PNG"), written[:8])

    # ---------------------------------------------------------- #
    print("\n=== 5. Некартинка и пустой файл отвергаются ===")
    r = client.post(
        f"/api/v1/projects/{pid}/background",
        files={"file": ("background.png", "это не картинка".encode("utf-8"), "image/png")},
    )
    check("текст отвергнут", r.status_code == 400, f"{r.status_code} {r.text[:140]}")
    check("прежний фон не пострадал",
          background_files(pid) == ["background.png"], background_files(pid))

    r = client.post(
        f"/api/v1/projects/{pid}/background",
        files={"file": ("empty.png", b"", "image/png")},
    )
    check("пустой файл отвергнут", r.status_code == 400, f"{r.status_code} {r.text[:140]}")

    # ---------------------------------------------------------- #
    print("\n=== 6. Повторная загрузка убирает прежний файл ===")
    r = client.post(
        f"/api/v1/projects/{pid}/background",
        files={"file": ("background.jpg", JPEG_STUB, "image/jpeg")},
    )
    check("загрузка JPEG принята", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    files = background_files(pid)
    check("остался ровно один файл", files == ["background.jpg"], files)
    check("прежний png удалён", not os.path.exists(on_disk))
    check("адрес ведёт на jpg",
          ".jpg" in (r.json().get("background_url") or ""),
          r.json().get("background_url"))

    # ---------------------------------------------------------- #
    print("\n=== 7. Уход на базовый фон удаляет пользовательский ===")
    r = client.patch(f"/api/v1/projects/{pid}", json={"background": "default"})
    check("обновление принято", r.status_code == 200, r.status_code)
    if r.status_code == 200:
        check("вид default", r.json()["background"] == "default", r.json()["background"])
        check("адрес очищен", not r.json()["background_url"], r.json()["background_url"])
    check("файл с диска убран", background_files(pid) == [], background_files(pid))

    # ---------------------------------------------------------- #
    print("\n=== 8. Явное снятие фона ===")
    client.post(
        f"/api/v1/projects/{pid}/background",
        files={"file": ("background.png", make_png(), "image/png")},
    )
    check("фон снова свой", background_files(pid) == ["background.png"], background_files(pid))

    r = client.delete(f"/api/v1/projects/{pid}/background")
    check("снятие принято", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        check("вид none", r.json()["background"] == "none", r.json()["background"])
        check("адрес пуст", not r.json()["background_url"], r.json()["background_url"])
    check("файл удалён", background_files(pid) == [], background_files(pid))

    # Повторное снятие не должно падать: фон уже и так пуст.
    r = client.delete(f"/api/v1/projects/{pid}/background")
    check("повторное снятие не ошибка", r.status_code == 200, r.status_code)

    # ---------------------------------------------------------- #
    print("\n=== 9. Свойства проекта не пострадали ===")
    r = client.patch(f"/api/v1/projects/{pid}", json={"name": PROBE_NAME, "description": "проверка"})
    check("название и описание сохранены",
          r.status_code == 200 and r.json()["name"] == PROBE_NAME
          and r.json()["description"] == "проверка",
          r.status_code)

finally:
    client.close()
    asyncio.run(teardown())
    print("\n  временный проект удалён")

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")