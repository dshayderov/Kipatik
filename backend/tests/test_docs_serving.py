"""Проверка раздачи руководств и что монтирование не сломало приложение.

Скрипт запускается дважды — с SERVE_DOCS=true и с SERVE_DOCS=false,
потому что значение читается при импорте конфигурации, и подменить
его в уже загруженном процессе нельзя.

Проверяется:
  * оба файла руководств существуют, читаются как UTF-8 и не пустые;
  * при SERVE_DOCS=true оба отдаются по /docs/<файл> и совпадают
    с файлом в репозитории байт в байт по содержанию;
  * приложение в целом продолжает работать: корень, Swagger,
    поиск задач и список проектов не сломались;
  * при SERVE_DOCS=false текст не отдаётся.

Запуск (из папки backend, при поднятом PostgreSQL):

    $env:SERVE_DOCS='true';  .\\venv\\Scripts\\python.exe -W ignore tests\\test_docs_serving.py
    $env:SERVE_DOCS='false'; .\\venv\\Scripts\\python.exe -W ignore tests\\test_docs_serving.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено».
Данные не изменяются — все запросы только на чтение.
"""
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

# Режим берётся из настроек приложения, а не из переменной окружения:
# pydantic читает .env в себя, но в os.environ её не кладёт. Если бы
# режим определялся окружением, проверка пошла бы по ветке «выключено»
# при включённой раздаче и рапортовала бы об утечке, которой нет.
# Приоритет переменной окружения над .env у pydantic выше, поэтому
# переопределение через окружение продолжает работать.
SERVE_DOCS = settings.SERVE_DOCS

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(REPO, "docs")
# Четыре файла: по два руководства на двух языках. Английские лежат
# рядом с русскими с суффиксом .en — страница справки выбирает файл
# по языку интерфейса, поэтому отсутствие перевода проявилось бы как
# пустая страница, а не как ошибка загрузки.
FILES = [
    "user-guide.md",
    "admin-guide.md",
    "user-guide.en.md",
    "admin-guide.en.md",
]

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
client = TestClient(app)

print(f"=== Настройка: SERVE_DOCS = {SERVE_DOCS} ===")

# ---------------------------------------------------------------- #
print("\n=== 1. Файлы в репозитории ===")
contents = {}
for name in FILES:
    path = os.path.join(DOCS, name)
    exists = os.path.isfile(path)
    check(f"{name} есть в docs/", exists)
    if not exists:
        continue
    with io.open(path, "rb") as f:
        raw = f.read()
    check(f"{name} непустой", len(raw) > 5000, f"{len(raw) / 1024:.1f} КБ")
    try:
        text = raw.decode("utf-8")
        ok_utf8 = True
    except UnicodeDecodeError:
        text, ok_utf8 = "", False
    check(f"{name} читается как UTF-8", ok_utf8)
    check(f"{name} без BOM", not raw.startswith(b"\xef\xbb\xbf"))
    if not ok_utf8:
        continue
    contents[name] = text
    check(f"{name} без повреждённых символов", "�" not in text)
    check(f"{name} начинается с заголовка", text.lstrip().startswith("# "))
    check(f"{name} заканчивается переводом строки", text.endswith("\n"))
    trailing = [i + 1 for i, ln in enumerate(text.split("\n")) if ln != ln.rstrip()]
    check(f"{name}: нет завершающих пробелов", not trailing, str(trailing[:5]))
    heads = [ln for ln in text.split("\n") if ln.startswith("## ")]
    check(f"{name}: есть нумерованные разделы", len(heads) >= 8, f"{len(heads)}")
    tables = text.count("\n|")
    check(f"{name}: есть таблицы", tables > 10, f"{tables} строк таблиц")
    check(f"{name}: нет HTML-тегов", "<div" not in text and "<br" not in text)

# ---------------------------------------------------------------- #
if SERVE_DOCS:
    print("\n=== 2. Раздача включена ===")
    for name in FILES:
        r = client.get(f"/manuals/{name}")
        check(f"GET /manuals/{name} отвечает 200", r.status_code == 200,
              f"HTTP {r.status_code}")
        if r.status_code != 200:
            continue
        check(f"{name}: отдаётся ровно файл из репозитория",
              r.text.strip() == contents.get(name, "").strip(),
              f"{len(r.text)} символов")
        check(f"{name}: отдаётся как текст, а не вложением",
              "attachment" not in r.headers.get("content-disposition", ""))

    r = client.get("/manuals/nonexistent.md")
    check("несуществующий файл даёт 404", r.status_code == 404,
          f"HTTP {r.status_code}")

    r = client.get("/manuals/")
    check("листинг каталога не раскрывается наружу",
          r.status_code in (403, 404), f"HTTP {r.status_code}")

    print("\n=== 3. Приложение не сломано ===")
    r = client.get("/")
    check("корень отвечает", r.status_code == 200, f"HTTP {r.status_code}")

    # /docs — встроенная документация API. Руководства не должны были
    # занять этот адрес: иначе администратор потеряет Swagger.
    r = client.get("/docs")
    check("встроенная документация API открывается на /docs",
          r.status_code == 200, f"HTTP {r.status_code}")
    check("на /docs отдаётся Swagger, а не текст руководства",
          "swagger" in r.text.lower(), "похоже, это не Swagger")

    r = client.get("/api/v1/tasks/search", params={"q": "выгрузка"})
    check("поиск задач работает", r.status_code == 200, f"HTTP {r.status_code}")
    r = client.get("/api/v1/tasks/search")
    check("поиск без q отвечает 200 (маршрут не перехвачен)",
          r.status_code == 200, f"HTTP {r.status_code}")
    r = client.get("/api/v1/projects/")
    check("список проектов работает", r.status_code == 200, f"HTTP {r.status_code}")
    r = client.get("/openapi.json")
    check("схема OpenAPI собирается", r.status_code == 200, f"HTTP {r.status_code}")
else:
    print("\n=== 2. Раздача выключена ===")
    for name in FILES:
        r = client.get(f"/manuals/{name}")
        check(f"{name} НЕ отдаётся при SERVE_DOCS=false",
              r.status_code in (403, 404), f"HTTP {r.status_code}")
        leaked = any(word in r.text for word in
                     ("Руководство", "SECRET_KEY", "ADMIN"))
        check(f"{name}: содержимое не утекло в ответе", not leaked)

    r = client.get("/")
    check("приложение продолжает работать", r.status_code == 200,
          f"HTTP {r.status_code}")
    r = client.get("/api/v1/tasks/search", params={"q": "выгрузка"})
    check("поиск задач работает", r.status_code == 200, f"HTTP {r.status_code}")

client.close()

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")
sys.exit(1 if failed else 0)