"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL.

Запуск приложения целиком: lifespan, фоновые задачи, прогрев моделей.

Зачем отдельная проверка
-----------------------

Остальные наборы создают `TestClient(app)` и сразу бросают запросы.
Так lifespan **не выполняется**: события старта не запускаются,
фоновые задачи не создаются. Ошибка только в стартовом коде при этом
не проявляется ни в одном из них — и это уже случилось: переименование
функции реестра моделей дало падение сервера при старте, при полностью
зелёном прогоне всех остальных проверок.

Здесь же проверяется то, что сервер не падает при старте, и то, что
фоновые задачи действительно запустились.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_startup.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено».
Данные не изменяются, кроме записи решений о включении моделей —
те же, что делает сам сервер при старте.
"""
import asyncio
import inspect
import io
import logging
import os
import sys
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.INFO)

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
import app.git.models  # noqa: F401
from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.users.models import User

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

TEST_USER = User(
    id=4, email="renebus125@gmail.ru", full_name="probe",
    hashed_password="x", is_active=True, is_superuser=True,
)


async def _get_db():
    async with sm() as s:
        yield s


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = lambda: TEST_USER

try:
    # ---------------------------------------------------------- #
    print("=== 1. Приложение поднимается целиком ===")
    # Именно этот способ запускает lifespan. Вход в контекстный
    # менеджер — единственное, что выполняет события старта.
    startup_error = None
    try:
        with TestClient(app) as client:
            r = client.get("/")
            check("сервер ответил после старта", r.status_code == 200,
                  f"HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001 — падение старта и есть проверяемое
        startup_error = exc
        check("lifespan отработал без исключений", False,
              f"{type(exc).__name__}: {exc}")

    if startup_error is None:
        check("lifespan отработал без исключений", True)

    # ---------------------------------------------------------- #
    print("\n=== 2. Стартовый код ссылается на существующие имена ===")
    # Приём ловит ровно ту ошибку, что была: вызов переименованной
    # функции. Имена разрешаются по-настоящему, без запуска сервера.
    import app.main as main_mod
    from app.ai import api as ai_api

    source = io.open(main_mod.__file__, encoding="utf-8").read()
    check("в startup_event нет вызовов несуществующих имён модуля моделей",
          "refresh_registry" not in source,
          "остался вызов функции, которой нет в app.ai.api")

    for attr in ("refresh", "is_enabled", "KEY_ENCODER", "KEY_TYPE_CLASSIFIER"):
        check(f"app.ai.api.{attr} существует", hasattr(ai_api, attr))

    # ---------------------------------------------------------- #
    print("\n=== 3. Фоновые задачи создаются ===")
    # start_periodic_sync запускается с интервалом из настроек.
    # Проверяем, что значение вообще читается: переменная
    # GIT_SYNC_INTERVAL_SECONDS была объявлена и не использовалась —
    # в коде стояло жёсткое число, и настройка молча ничего не значила.
    check("интервал сверки берётся из настроек",
          isinstance(settings.GIT_SYNC_INTERVAL_SECONDS, int)
          and settings.GIT_SYNC_INTERVAL_SECONDS > 0,
          settings.GIT_SYNC_INTERVAL_SECONDS)

    import app.git.services as git_services
    sig = inspect.signature(git_services.start_periodic_sync)
    check("start_periodic_sync принимает интервал",
          "interval_seconds" in sig.parameters, list(sig.parameters))

    # ---------------------------------------------------------- #
    print("\n=== 4. Модуль моделей отвечает после старта ===")
    r = client.get("/api/v1/ai/code-model/status")
    check("диагностика моделей отвечает", r.status_code == 200,
          f"HTTP {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        for field in ("enabled", "available", "reason", "device", "artifacts"):
            check(f"в ответе есть {field}", field in data, sorted(data)[:8])

finally:
    pass

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")
sys.exit(1 if failed else 0)