"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Тип задачи: bugfix | feature | refactor | docs | test | chore | пусто.

Набор совпадает с типами коммитов, которые определяет классификатор:
это позволяет сравнивать заявленный тип задачи с тем, что модель
насчитала по её коммитам.

Раньше тип на карточке был заглушкой — чётный id значил «Баг», нечётный
«Фича» — и подпись ничего не говорила о задаче. Проверяем, что тип
доходит от запроса до базы, меняется и очищается, что принимаются все
шесть значений, а неизвестное отклоняется с 422.

Задачи-зоны удаляются сами.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\venv\Scripts\python.exe -W ignore tests\test_task_type.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import warnings

warnings.filterwarnings("ignore")

import asyncio
import json
import logging
import re
from pathlib import Path

logging.disable(logging.INFO)

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
from app.schemas.task import TASK_TYPES
from app.users.models import User

PROJECT = 14
PROBE_TITLE = "Зонд типа задачи"

# Значения вне набора. «bug» был в первой версии и мог остаться
# в данных, поэтому проверяем и его.
BAD_VALUES = ["bugg", "BUG", "задача", "bug", "", None]

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

client = TestClient(app)


async def clear_probe():
    # По LIKE, а не по точному совпадению: часть проверок создаёт
    # «Зонд типа задачи 2» и «3», и их тоже нужно убрать.
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM tasks WHERE title LIKE :t"), {"t": PROBE_TITLE + "%"}
        )


def db_type(task_id):
    async def _read():
        async with sm() as s:
            row = (
                await s.execute(
                    text("SELECT task_type FROM tasks WHERE id = :i"), {"i": task_id}
                )
            ).mappings().first()
            return row["task_type"] if row else "<нет задачи>"

    return asyncio.run(_read())


created = None

try:
    asyncio.run(clear_probe())

    # ---------------------------------------------------------- #
    print(f"=== 1. Набор совпадает с типами коммитов и с фронтендом ===")
    from app.ai.api import COMMIT_TYPES

    check("в бэкенде те же шесть типов",
          set(TASK_TYPES) == set(COMMIT_TYPES),
          f"задачи={sorted(TASK_TYPES)} коммиты={sorted(COMMIT_TYPES)}")

    # Фронтенд держит свой список в единственном месте (types/taskType.ts),
    # но список продублирован в бэкенде: без сверки они молча разойдутся,
    # и backend начнёт отклонять значение, которое выбрать нельзя.
    frontend_file = (
        Path(__file__).resolve().parent.parent.parent
        / "frontend" / "src" / "types" / "taskType.ts"
    )
    if frontend_file.exists():
        src = frontend_file.read_text(encoding="utf-8")
        found = set(re.findall(r"'([a-z]+)'", src.split("TASK_TYPE_STYLE")[0]))
        check("в фронтенде те же типы", found == set(TASK_TYPES),
              f"фронт={sorted(found)}")
    else:
        check("файл frontend/src/types/taskType.ts найден", False,
              str(frontend_file))

    # Подписи типов у задач и у коммитов должны быть одни и те же.
    # Раньше они жили в двух разделах: у задачи «Дефект», у коммита
    # «исправление», и в английском переводе вместо подписей были
    # сами ключи. Сверяем, что дубль удалён и раздел один.
    i18n_dir = frontend_file.parent.parent / "i18n"
    for name in ("ru.json", "en.json"):
        path = i18n_dir / name
        if not path.exists():
            check(f"{name} найден", False, str(path))
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        labels = data.get("task_type", {})
        dev = data.get("tasks", {}).get("dev", {})

        check(f"{name}: ключи подписей совпадают с набором типов",
              set(labels) == set(TASK_TYPES), sorted(labels))
        check(f"{name}: подписи не пустые",
              all(isinstance(v, str) and v.strip() for v in labels.values()),
              labels)
        check(f"{name}: дубль tasks.dev.commit_type удалён",
              "commit_type" not in dev, sorted(dev.get("commit_type", {})))
        check(f"{name}: нет подписи, совпадающей с ключом",
              not any(k == v for k, v in labels.items()),
              {k: v for k, v in labels.items() if k == v})

    # ---------------------------------------------------------- #
    print("\n=== 2. Все шесть типов принимаются и сохраняются ===")
    r = client.post(
        f"/api/v1/tasks/",
        json={"title": PROBE_TITLE, "project_id": PROJECT, "task_type": "bugfix"},
    )
    check("создание принято", r.status_code in (200, 201),
          f"{r.status_code} {r.text[:200]}")
    if r.status_code in (200, 201):
        created = r.json()["id"]
        check("в ответе bugfix", r.json().get("task_type") == "bugfix",
              r.json().get("task_type"))
        check("в БД bugfix", db_type(created) == "bugfix", db_type(created))

        for kind in sorted(TASK_TYPES):
            r = client.patch(f"/api/v1/tasks/{created}", json={"task_type": kind})
            ok = r.status_code == 200 and db_type(created) == kind
            check(f"PATCH на «{kind}» сохранён", ok,
                  f"{r.status_code} в БД {db_type(created)!r}")

    # ---------------------------------------------------------- #
    print("\n=== 3. Тип очищается ===")
    if created:
        r = client.patch(f"/api/v1/tasks/{created}", json={"task_type": None})
        check("PATCH принят", r.status_code == 200, r.status_code)
        check("в БД пусто", db_type(created) is None, repr(db_type(created)))

    print("\n=== 4. Без типа при создании ===")
    r = client.post(
        f"/api/v1/tasks/", json={"title": PROBE_TITLE + " 2", "project_id": PROJECT}
    )
    check("принято", r.status_code in (200, 201), r.status_code)
    if r.status_code in (200, 201):
        check("в БД пусто", db_type(r.json()["id"]) is None,
              repr(db_type(r.json()["id"])))

    # ---------------------------------------------------------- #
    print("\n=== 5. Неизвестное значение отклоняется ===")
    # Пустая строка — это «без типа», а не ошибка, её проверяем отдельно.
    for bad in [v for v in BAD_VALUES if v not in ("", None)]:
        if created:
            client.patch(f"/api/v1/tasks/{created}", json={"task_type": "bugfix"})
            r = client.patch(f"/api/v1/tasks/{created}", json={"task_type": bad})
            check(f"PATCH с {bad!r} отклонён", r.status_code == 422, f"{r.status_code}")
            check(f"  значение не изменилось на {bad!r}",
                  db_type(created) == "bugfix", repr(db_type(created)))

        r = client.post(
            f"/api/v1/tasks/",
            json={"title": PROBE_TITLE + " 3", "project_id": PROJECT, "task_type": bad},
        )
        check(f"создание с {bad!r} отклонено", r.status_code == 422, f"{r.status_code}")

    # ---------------------------------------------------------- #
    print("\n=== 6. Пустое значение — «без типа», а не ошибка ===")
    if created:
        r = client.patch(f"/api/v1/tasks/{created}", json={"task_type": "bugfix"})
        check("поставили bugfix", r.status_code == 200, r.status_code)
        r = client.patch(f"/api/v1/tasks/{created}", json={"task_type": ""})
        check("пустая строка принята", r.status_code == 200, f"{r.status_code}")
        check("в БД снова пусто", db_type(created) is None, repr(db_type(created)))

    r = client.post(
        f"/api/v1/tasks/",
        json={"title": PROBE_TITLE + " 4", "project_id": PROJECT, "task_type": ""},
    )
    check("создание с пустой строкой принято", r.status_code in (200, 201), r.status_code)
    if r.status_code in (200, 201):
        check("  и в БД пусто", db_type(r.json()["id"]) is None,
              repr(db_type(r.json()["id"])))

finally:
    client.close()
    asyncio.run(clear_probe())
    print("\n  временные записи удалены")

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")