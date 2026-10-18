"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Управление нейросетевыми моделями администратором.

Проверяется, что:
  * решение администратора действует поверх флага окружения и
    переживает перечитывание кеша;
  * классификатор типов нельзя включить при выключенном кодировщике;
  * неизвестный ключ отклоняется;
  * выключенный классификатор не поднимает кодировщик — иначе
    отключение не освободило бы память;
  * настройки чистятся за собой.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_admin_models.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import warnings

warnings.filterwarnings("ignore")

import asyncio
import logging

logging.disable(logging.INFO)

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models.ai_settings  # noqa: F401
import app.models  # noqa: F401
from app.ai import api as registry
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

ADMIN = User(
    id=4, email="renebus125@gmail.ru", full_name="probe", hashed_password="x",
    is_active=True, is_superuser=True,
)
PLAIN = User(
    id=999, email="nobody@example.com", full_name="не админ",
    hashed_password="x", is_active=True, is_superuser=False,
)

current_user_holder = {"user": ADMIN}


async def _get_db():
    async with sm() as s:
        yield s


async def _get_current_user():
    return current_user_holder["user"]


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = _get_current_user

BASE = "/api/v1/admin/models"


async def clear_settings():
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM ai_model_settings"))
    registry._overrides.clear()


def refresh():
    async def _run():
        async with sm() as s:
            await registry.refresh(s)

    asyncio.run(_run())


def count_settings() -> int:
    async def _run():
        async with sm() as s:
            return (
                await s.execute(text("SELECT count(*) FROM ai_model_settings"))
            ).scalar()

    return asyncio.run(_run())


client = TestClient(app)

try:
    asyncio.run(clear_settings())

    # ---------------------------------------------------------- #
    print("=== 1. Список моделей ===")
    r = client.get(BASE)
    check("доступен администратору", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    rows = r.json() if r.status_code == 200 else []
    check("три модели", len(rows) == 3, [x["key"] for x in rows])

    by_key = {x["key"]: x for x in rows}
    check("есть кодировщик", registry.KEY_ENCODER in by_key, sorted(by_key))
    check("есть классификатор типов", registry.KEY_TYPE_CLASSIFIER in by_key)
    check("есть оценка объёма", registry.KEY_PROGRESS in by_key)

    enc = by_key.get(registry.KEY_ENCODER, {})
    check("у кодировщика указан файл", enc.get("artifact_exists") is True)
    check("размер кодировщика больше гигабайта",
          (enc.get("artifact_size_mb") or 0) > 1000, enc.get("artifact_size_mb"))
    check("классификатор работает поверх кодировщика",
          by_key.get(registry.KEY_TYPE_CLASSIFIER, {}).get("depends_on")
          == [registry.KEY_ENCODER],
          by_key.get(registry.KEY_TYPE_CLASSIFIER, {}).get("depends_on"))
    check("оценка объёма помечена как правила, а не нейросеть",
          by_key.get(registry.KEY_PROGRESS, {}).get("kind") == "rules",
          by_key.get(registry.KEY_PROGRESS, {}).get("kind"))
    check("нет переопределения — действует окружение",
          all(x.get("overridden") is False for x in rows))

    # ---------------------------------------------------------- #
    print("\n=== 2. Переключение действует поверх окружения ===")
    r = client.patch(f"{BASE}/{registry.KEY_TYPE_CLASSIFIER}", json={"enabled": False})
    check("выключение принято", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    check("в ответе выключено", r.json().get("enabled") is False, r.json().get("enabled"))
    check("помечено как переопределённое", r.json().get("overridden") is True)
    check("среда и переопределение разошлись",
          r.json().get("env_default") is True and r.json().get("enabled") is False,
          (r.json().get("env_default"), r.json().get("enabled")))

    check("в базе появилась строка",
          count_settings() == 1, count_settings())

    refresh()
    check("кеш обновлён после перечитывания",
          registry.is_enabled(registry.KEY_TYPE_CLASSIFIER) is False)
    check("кодировщик не тронут",
          registry.is_enabled(registry.KEY_ENCODER) is True)

    # ---------------------------------------------------------- #
    print("\n=== 3. Зависимость: классификатор без кодировщика ===")
    client.patch(f"{BASE}/{registry.KEY_ENCODER}", json={"enabled": False})
    refresh()
    r = client.patch(f"{BASE}/{registry.KEY_TYPE_CLASSIFIER}", json={"enabled": True})
    check("включение классификатора отклонено", r.status_code == 400,
          f"{r.status_code} {r.text[:160]}")
    check("кодировщик остался выключенным",
          registry.is_enabled(registry.KEY_ENCODER) is False)

    # ---------------------------------------------------------- #
    print("\n=== 4. Неизвестный ключ ===")
    r = client.patch(f"{BASE}/nope", json={"enabled": False})
    check("PATCH отклонён", r.status_code == 404, r.status_code)

    # ---------------------------------------------------------- #
    print("\n=== 5. Выключенный классификатор не тянет кодировщик ===")
    asyncio.run(clear_settings())
    refresh()
    client.patch(f"{BASE}/{registry.KEY_TYPE_CLASSIFIER}", json={"enabled": False})

    from app.ai.api import encoder, type_classifier

    encoder.unload()
    type_classifier.unload()
    result = type_classifier.classify_commit("feat: проверка")
    check("классификация вернула пустой тип",
          result.get("commit_type") is None, result)
    check("указана причина «выключено»", result.get("reason") == "disabled", result)
    check("кодировщик не загрузился",
          encoder.status()["loaded_flag"] is False,
          encoder.status()["loaded_flag"])

    # ---------------------------------------------------------- #
    print("\n=== 6. Права: обычный пользователь не администратор ===")
    current_user_holder["user"] = PLAIN
    r = client.get(BASE)
    check("список закрыт для не-суперюзера", r.status_code == 403, r.status_code)
    r = client.patch(f"{BASE}/{registry.KEY_ENCODER}", json={"enabled": False})
    check("переключение закрыто", r.status_code == 403, r.status_code)
    r = client.post(f"{BASE}/{registry.KEY_ENCODER}/unload")
    check("выгрузка закрыта", r.status_code == 403, r.status_code)
    current_user_holder["user"] = ADMIN

    # ---------------------------------------------------------- #
    print("\n=== 7. Сброс к настройкам окружения ===")
    r = client.patch(f"{BASE}/{registry.KEY_TYPE_CLASSIFIER}", json={"enabled": True})
    check("включение принято", r.status_code == 200, r.status_code)
    check("совпало с окружением", r.json().get("enabled") is True, r.json().get("enabled"))
    check("помечено как переопределённое", r.json().get("overridden") is True)
    refresh()
    check("кеш синхронизирован",
          registry.is_enabled(registry.KEY_TYPE_CLASSIFIER) is True)

finally:
    client.close()
    asyncio.run(clear_settings())
    refresh()
    print("\n  настройки моделей удалены")

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")
