"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL.

Поиск задач из строки в шапке.

Раньше в шапке стояла пустая строка ввода: элемент выглядел как поиск, но
не был ни к чему привязан. Теперь запрос уходит на сервер и ищет сразу по
всем проектам, где пользователь участник, — шапка показывается на всех
страницах, в том числе там, где проект не выбран.

Проверяется, что:
  * короткий и пустой запрос дают пустой список, а не ошибку;
  * поиск по названию задачи что-то находит;
  * в ответе заполнены все поля, включая название проекта — без него
    результат нельзя показать пользователю;
  * выдача не выходит за пределы проектов, где пользователь участник;
  * limit работает и ограничен сверху;
  * маршрут /search не перехватывает /{task_id}: порядок регистрации
    важен, эндпоинт объявлен раньше маршрута с параметром пути.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_task_search.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено».
Данные не изменяются — все запросы только на чтение.
"""

import warnings

warnings.filterwarnings("ignore")

import logging

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
from app.users.models import User

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


def search(q, **params):
    """Поиск задач. Исключение возвращается как код.

    Без этого TestClient на сломанном эндпоинте поднимает ошибку наружу
    и проверка обрывается на середине. Так поломка превращается в обычный
    провал с указанием на конкретную проверку.
    """
    params["q"] = q
    try:
        r = client.get("/api/v1/tasks/search", params=params)
        return r.status_code, (r.json() if r.status_code == 200 else None), r.text
    except Exception as exc:  # noqa: BLE001 - нам важно лишь зафиксировать факт
        return None, None, f"{type(exc).__name__}: {exc}"


def db_all(sql, params=None):
    """Первый столбец каждой строки — список скаляров."""
    async def _run():
        async with sm() as s:
            return [row[0] for row in (await s.execute(text(sql), params or {})).all()]

    return __import__("asyncio").run(_run())


def db_rows(sql, params=None):
    """Все столбцы каждой строки — список кортежей."""
    async def _run():
        async with sm() as s:
            return [tuple(row) for row in (await s.execute(text(sql), params or {})).all()]

    return __import__("asyncio").run(_run())


try:
    # ---------------------------------------------------------- #
    print("=== 1. Пустой и слишком короткий запрос ===")
    for q in ("", " ", "а"):
        code, data, text_ = search(q)
        check(f"q={q!r:5} отвечает 200", code == 200, code)
        check(f"q={q!r:5} даёт пустой список", data == [], data)

    # ---------------------------------------------------------- #
    print("\n=== 2. Поиск, который что-то находит ===")
    my_projects = set(
        db_all("SELECT project_id FROM project_members WHERE user_id = :me", {"me": ME})
    )
    print(f"  проектов, где пользователь участник: {len(my_projects)}")

    # Задача берётся из проекта, где пользователь участник, и слово — из
    # её названия: проверка не должна зависеть от того, что в системе
    # случайно окажется. Заодно это же слово служит образцом для
    # проверки состава ответа и limit.
    sample = db_rows(
        "SELECT t.id, split_part(t.title, ' ', 1) FROM tasks t "
        "JOIN project_members pm ON pm.project_id = t.project_id "
        "WHERE pm.user_id = :me AND length(t.title) >= 2 ORDER BY t.id LIMIT 1",
        {"me": ME},
    )
    if not sample:
        print("  НЕТ задач в своих проектах — проверки наполнения неполны")
        sample_word = ""
        sample_task = None
    else:
        sample_task, sample_word = sample[0][0], sample[0][1].replace(".", "")
        print(f"  образец: задача {sample_task}, слово {sample_word!r}")

        code, data, text_ = search(sample_word)
        check("поиск отвечает 200", code == 200, f"{code} {text_[:160]}")
        check("нашёл хоть что-то", bool(data), f"{len(data) if data else 0}")
        check("нашлась именно задача-образец",
              bool(data) and any(h["task_id"] == sample_task for h in data),
              [h["task_id"] for h in data][:8] if data else "пусто")

    # ---------------------------------------------------------- #
    print("\n=== 3. Состав ответа ===")
    code, data, text_ = search(sample_word)
    if code == 200 and data:
        hit = data[0]
        for field in ("task_id", "title", "task_type", "priority",
                      "due_date", "project_id", "project_name"):
            check(f"поле {field} есть в ответе", field in hit, hit.get(field))
        check("название проекта не пустое", bool(hit.get("project_name")))
        check("task_id — число", isinstance(hit.get("task_id"), int))
    else:
        check("выдача получена", False, f"{code} {text_[:120]}")

    # ---------------------------------------------------------- #
    print("\n=== 4. Чужие проекты не попадают в выдачу ===")
    if code == 200 and data:
        shown = {hit["project_id"] for hit in data}
        leaked = sorted(shown - my_projects)
        check("все найденные задачи из своих проектов", not leaked,
              f"проекты без членства: {leaked}")
    else:
        check("выдача получена", False, f"{code} {text_[:120]}")

    # ---------------------------------------------------------- #
    print("\n=== 5. limit ===")
    code, data, text_ = search(sample_word, limit=1)
    check("limit=1 уважается", code == 200 and len(data) <= 1,
          len(data) if code == 200 else code)

    code, data, text_ = search(sample_word, limit=9999)
    check("limit срезан до 50", code == 200 and len(data) <= 50,
          len(data) if code == 200 else code)

    # ---------------------------------------------------------- #
    print("\n=== 6. /search не перехватывает /{task_id} ===")
    if sample_task:
        r = client.get(f"/api/v1/tasks/{sample_task}")
        check("карточка задачи открывается", r.status_code == 200,
              f"HTTP {r.status_code} {r.text[:120]}")
    else:
        print("  НЕТ задачи-образца — проверка неполна")

    r = client.get("/api/v1/tasks/not-a-number")
    check("нечисловой id даёт 422, а не 500", r.status_code == 422,
          f"HTTP {r.status_code}")

finally:
    client.close()

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")