"""ПРЕДУПРЕЖДЕНИЕ: проверка ходит по файлам репозитория и создаёт
временный каталог вне проекта. Базу данных не трогает.

Целостность файлов поставки: Dockerfile, docker-compose.yml, правила
игнорирования, образец настроек и качество инструкций.

Зачем это проверяется тестом, а не на глаз:

  * правила игнорирования проверяются через `git check-ignore`, то есть
    тем же механизмом и в том же порядке, что сработают при
    клонировании. Чтение текста файла ничего не доказывает: правило
    может выглядеть правильно и при этом не сработать. Так случилось
    с каталогом миграций — он был исключён, и на чистой машине
    `alembic upgrade head` не сделал бы ничего;
  * неизвестная переменная окружения роняет приложение на старте,
    поэтому в образце настроек не должно быть ничего лишнего;
  * развалившаяся таблица в инструкции делает её нечитаемой, а
    упоминание имени файла исходников вместо названия элемента
    интерфейса отправляет читателя в код.

Запуск (из папки backend):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_repo_files.py
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(BACKEND)
SANDBOX = os.path.join(tempfile.gettempdir(), "kipatik_repo_files_sandbox")

failures = []
total = 0


def check(cond, name, extra=""):
    global total
    total += 1
    print(("  OK   " if cond else "  FAIL ") + name + (f" — {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def read(rel):
    with io.open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


# ================================================================ #
# 1. Dockerfile
# ================================================================ #
print("=== 1. Dockerfile ===")
df = read("backend/Dockerfile")
check(bool(re.search(r"^ARG INSTALL_TORCH", df, re.M)) and "$INSTALL_TORCH" in df,
      "аргумент INSTALL_TORCH объявлен перед подстановкой")
check("--reload" not in df, "режим разработки не попал в образ")
check(bool(re.search(r"^USER kipatik", df, re.M)), "образ работает не от root")
check("COPY docs ./docs" in df, "руководства копируются в образ")
check("COPY backend/app ./app" in df, "код бэкенда копируется")
check("COPY backend/alembic ./alembic" in df and "alembic.ini" in df,
      "миграции и alembic.ini внутри образа")
check("HEALTHCHECK" in df and "exit 1" in df,
      "проверка живости отдаёт ненулевой код при отказе")
check("DOCS_DIR=/app/docs" in df, "путь к руководствам задан явно")
check("CODE_MODEL_DIR" in df,
      "путь к артефактам моделей в образе не зашит")
check("SERVE_DOCS=false" in df,
      "руководство администратора по умолчанию наружу не отдаётся")
check("chown -R kipatik" in df,
      "каталог загрузок принадлежит рабочему пользователю")
check("alembic upgrade" not in df.split("CMD")[-1],
      "миграции не навешаны на CMD: иначе каждый перезапуск контейнера "
      "менял бы схему")

# ================================================================ #
# 2. docker-compose.yml
# ================================================================ #
print("\n=== 2. docker-compose.yml ===")
compose_text = read("docker-compose.yml")
try:
    import yaml

    d = yaml.safe_load(compose_text)
    b = d["services"]["backend"]
    check(True, "YAML разбирается", f"сервисы: {', '.join(d['services'])}")
    check(b["build"]["context"] == ".",
          "контекст сборки — корень репозитория (иначе не попадут docs/)")
    check(b["build"]["dockerfile"] == "backend/Dockerfile",
          "путь к Dockerfile указан явно")
    check(b["depends_on"]["db"]["condition"] == "service_healthy",
          "бэкенд ждёт готовности базы, а не её запуска")
    check(any("uploads" in v for v in b["volumes"]),
          "загруженные файлы вынесены в том", str(b["volumes"]))
    check("postgres_data" in d.get("volumes", {}),
          "данные базы сохраняются между пересборками")
    check("env_file" in b, "настройки приходят из файла, а не из environment")
except ImportError:
    check(False, "PyYAML не установлен — YAML не проверен")
except Exception as exc:
    check(False, "YAML не разбирается", f"{type(exc).__name__}: {exc}")

# ================================================================ #
# 3. Правила игнорирования — через сам git
# ================================================================ #
print("\n=== 3. Правила игнорирования (git check-ignore) ===")


def build_sandbox():
    """Временный репозиторий с теми же правилами и тем же деревом путей.

    Проект под git не находится, а проверять надо именно те правила,
    которые сработают при клонировании. Собираем окружение отдельно,
    настоящий каталог не трогаем.
    """
    if os.path.isdir(SANDBOX):
        shutil.rmtree(SANDBOX)
    os.makedirs(SANDBOX)

    placeholders = [
        ".env", ".env.example",
        "backend/.env", "backend/.env.example",
        "backend/venv/Scripts/python.exe",
        "frontend/node_modules/vite/bin/vite.js",
        "backend/uploads/avatar.png",
        "forwork/1_note.ipynb",
        "backend/app/ai/code_model/commit_tracer.pt",
        "backend/app/ai/code_model/type_classifier.pt",
        "frontend/dist/index.html",
        "backend/alembic/versions/cdaf42149890_init.py",
        "backend/app/main.py", "backend/app/tasks/api.py",
        "backend/requirements.txt",
        "frontend/src/App.tsx", "frontend/package.json",
        "backend/Dockerfile", "docker-compose.yml",
        "docs/user-guide.md", "docs/admin-guide.md",
        ".gitignore", ".dockerignore", "README.md",
    ]
    # Токенизатор модели обязателен: в чекпоинте только веса.
    for name in ("tokenizer.json", "config.json", "vocab.txt",
                 "tokenizer_config.json", "special_tokens_map.json"):
        placeholders.append(
            "backend/app/ai/code_model/"
            "paraphrase-multilingual-mpnet-base-v2/" + name)

    for rel in placeholders:
        if rel in (".gitignore", ".gitattributes"):
            # Настоящие правила копируются в конце: заглушка здесь
            # затекла бы на пустой файл, и git не нашёл бы ни одного
            # правила — проверка прошла бы вхолостую.
            continue
        full = os.path.join(SANDBOX, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        io.open(full, "w", encoding="utf-8").close()

    for rule_file in (".gitignore", ".gitattributes"):
        shutil.copyfile(os.path.join(REPO, rule_file),
                        os.path.join(SANDBOX, rule_file))
        size = os.path.getsize(os.path.join(SANDBOX, rule_file))
        if size == 0:
            raise RuntimeError(
                f"{rule_file} скопирован пустым — проверять нечего")

    subprocess.run(["git", "init", "-q", SANDBOX], check=True,
                   capture_output=True)


def ignored(path):
    """Возвращает правило, которым путь игнорируется, иначе None.

    Сначала спрашиваем у git только «игнорируется или нет»: в этом
    режиме код 0 означает «да». Ключ -v для этого не годится — он
    с кодом 0 печатает и правила-отрицания, из-за чего .env.example
    под надписью !.env.example выглядел бы проигнорированным.
    """
    verdict = subprocess.run(
        ["git", "-C", SANDBOX, "check-ignore", "-q", "--no-index", path],
        capture_output=True)
    if verdict.returncode != 0:
        return None
    detail = subprocess.run(
        ["git", "-C", SANDBOX, "check-ignore", "-v", "--no-index", path],
        capture_output=True, text=True)
    line = detail.stdout.strip()
    if line.startswith("!"):
        return None
    return line or "<игнорируется>"


def attr(path, name):
    """Значение атрибута git для пути.

    Вывод `git check-attr`: `<путь>: <атрибут>: <значение>`. Разбор
    ограничен тремя частями: иначе двоеточие внутри значения съело бы
    одну из колонок и атрибут читался бы неверно.
    """
    proc = subprocess.run(
        ["git", "-C", SANDBOX, "check-attr", name, "--", path],
        capture_output=True, text=True,
    )
    for line in proc.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(": ", 2)
        if len(parts) == 3 and parts[1] == name:
            return parts[2].strip()
    return ""


try:
    build_sandbox()
    check(True, "временный репозиторий собран")
except Exception as exc:
    check(False, "временный репозиторий не собран",
          f"{type(exc).__name__}: {exc}")
else:
    for path, what in [
        (".env", "локальные настройки в корне"),
        ("backend/.env", "локальные настройки бэкенда"),
        ("backend/venv/Scripts/python.exe", "виртуальное окружение"),
        ("frontend/node_modules/vite/bin/vite.js", "зависимости фронтенда"),
        ("backend/uploads/avatar.png", "загруженные файлы"),
        ("forwork/1_note.ipynb", "материалы лабораторных работ"),
        ("frontend/dist/index.html", "сборка фронтенда"),
    ]:
        rule = ignored(path)
        check(bool(rule), f"игнорируется: {what}",
              path if rule else f"НЕ ИГНОРИРУЕТСЯ: {path}")

    for path, what in [
        ("backend/alembic/versions/cdaf42149890_init.py", "миграции Alembic"),
        ("backend/app/main.py", "код бэкенда"),
        ("backend/requirements.txt", "зависимости бэкенда"),
        ("frontend/src/App.tsx", "код фронтенда"),
        # Веса моделей лежат в репозитории: клонирование должно давать
        # готовый комплект. Исключать их больше нельзя — развёртывание
        # требовало вручную куда-то класть гигабайтный файл.
        ("backend/app/ai/code_model/commit_tracer.pt", "веса кодировщика"),
        ("backend/app/ai/code_model/type_classifier.pt",
         "веса классификатора"),
        (".gitattributes", "правила хранения весов в LFS"),
        ("backend/Dockerfile", "Dockerfile"),
        ("docker-compose.yml", "compose"),
        ("docs/user-guide.md", "руководство пользователя"),
        ("docs/admin-guide.md", "руководство администратора"),
        ("backend/.env.example", "образец настроек"),
        ("backend/scripts/fetch_tokenizer.py", "скрипт скачивания словаря"),
        ("backend/app/ai/api.py", "единый API моделей"),
        ("backend/app/ai/code_model/progress_estimator.py",
         "модуль правил прогресса"),
        (".env.example", "образец настроек в корне"),
        (".gitignore", "сам .gitignore"),
        (".dockerignore", "сам .dockerignore"),
        ("README.md", "описание проекта"),
    ]:
        rule = ignored(path)
        check(not rule, f"НЕ игнорируется: {what}", rule or path)

    for name in ("tokenizer.json", "config.json", "vocab.txt",
                 "tokenizer_config.json", "special_tokens_map.json"):
        p = ("backend/app/ai/code_model/"
             f"paraphrase-multilingual-mpnet-base-v2/{name}")
        rule = ignored(p)
        check(not rule, f"НЕ игнорируется: токенизатор/{name}", rule or p)

    # ───────────────────────────────────────────────────────────── #
    # Веса хранятся через Git LFS. Проверяется именно результат
    # правил, а не их текст: правило может выглядеть правильно и при
    # этом не сработать.
    #
    # Почему LFS обязателен: кодировщик весит около гигабайта, а у
    # GitHub жёсткий предел 100 МБ на файл. Без LFS push отклоняется,
    # а если файл однажды попал в историю обычным git, убрать его
    # оттуда нельзя.
    print("\n=== 3a. Веса хранятся через Git LFS ===")
    for rel, what in [
        ("backend/app/ai/code_model/commit_tracer.pt", "веса кодировщика"),
        ("backend/app/ai/code_model/type_classifier.pt",
         "веса классификатора"),
    ]:
        check(attr(rel, "filter") == "lfs", f"filter=lfs для {what}",
              f"получено {attr(rel, 'filter')!r}")
        check(attr(rel, "merge") == "lfs", f"merge=lfs для {what}",
              f"получено {attr(rel, 'merge')!r}")
        check(attr(rel, "text") == "auto", f"двоичный режим для {what}",
              f"получено {attr(rel, 'text')!r}")

    # Словарь в LFS отправлять нельзя: внутри файла границы подстрок
    # помечены байтами конца строки, и переписывание окончаний строк
    # портит содержимое — токенизатор начинает выдавать мусор.
    spm = ("backend/app/ai/code_model/"
           "paraphrase-multilingual-mpnet-base-v2/sentencepiece.bpe.model")
    check(attr(spm, "diff") != "lfs",
          "файл словаря не отправляется в LFS",
          f"diff={attr(spm, 'diff')!r}")
    check(attr(spm, "text") == "unset",
          "окончания строк у словаря не нормализуются",
          f"text={attr(spm, 'text')!r}")

    shutil.rmtree(SANDBOX, ignore_errors=True)

# ================================================================ #
# 4. .dockerignore
# ================================================================ #
print("\n=== 4. .dockerignore ===")
dj = read(".dockerignore")
for pat, what in (("venv/", "виртуальное окружение"),
                  ("node_modules/", "зависимости фронтенда"),
                  ("*.pt", "веса моделей"),
                  (".env", "секреты"),
                  ("forwork/", "материалы лабораторных работ"),
                  ("uploads/", "загруженные файлы")):
    check(pat in dj, f"исключены {what}")

# ================================================================ #
# 5. Образец настроек
# ================================================================ #
print("\n=== 5. backend/.env.example ===")
ex_path = os.path.join(BACKEND, ".env.example")
check(os.path.isfile(ex_path), "образец создан")
if os.path.isfile(ex_path):
    raw = open(ex_path, "rb").read()
    try:
        ex_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        ex_text = ""
        check(False, "образец читается как UTF-8")
    if ex_text:
        check(not raw.startswith(b"\xef\xbb\xbf"), "образец без BOM")

        cfg = read("backend/app/core/config.py")
        declared = set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]+)\s*:", cfg, re.M))
        compose_only = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT",
                        "POSTGRES_DB", "REDIS_PORT", "BACKEND_PORT"}

        in_example = re.findall(r"^([A-Z][A-Z0-9_]+)=", ex_text, re.M)
        unknown = sorted(set(in_example) - declared - compose_only)
        check(not unknown,
              "каждая переменная образца реально читается",
              f"не объявлены: {unknown}" if unknown else
              f"проверено {len(set(in_example))} переменных")

        assigns = dict(re.findall(r"^([A-Z][A-Z0-9_]+)=(.*)$", ex_text, re.M))
        check(assigns.get("SECRET_KEY", "").startswith("CHANGE_ME"),
              "SECRET_KEY в образце — явная заглушка",
              assigns.get("SECRET_KEY", ""))
        check(not re.search(r"^SECRET_KEY=SUPER_SECRET", ex_text, re.M),
              "рабочий дефолт SECRET_KEY не скопирован в образец")
        for name in ("TOKEN_ENCRYPTION_KEY", "GITHUB_CLIENT_ID",
                     "GITHUB_CLIENT_SECRET", "GITLAB_CLIENT_ID",
                     "GITLAB_CLIENT_SECRET", "GITEA_CLIENT_ID",
                     "GITEA_CLIENT_SECRET", "BITBUCKET_CLIENT_ID",
                     "BITBUCKET_CLIENT_SECRET"):
            check(assigns.get(name, "") == "",
                  f"{name} пуст — секрет в репозитории не хранится",
                  assigns.get(name, "<нет переменной>"))
        check("не стартует" in ex_text or "обрывает запуск" in ex_text,
              "предупреждение об неизвестных переменных есть")

# ================================================================ #
# 6. Качество инструкций
# ================================================================ #
print("\n=== 6. Инструкции ===")
for name in ("user-guide.md", "admin-guide.md",
             "user-guide.en.md", "admin-guide.en.md"):
    path = os.path.join(REPO, "docs", name)
    print(f"--- {name} ---")
    if not os.path.isfile(path):
        check(False, f"{name} существует")
        continue

    text = read(f"docs/{name}")
    lines = text.split("\n")

    depths = [len(m.group(1)) for m in re.finditer(r"^(#{1,6}) ", text, re.M)]
    check(not depths or max(depths) <= 4,
          "заголовки не глубже 4 уровня",
          f"максимум {max(depths) if depths else 0}")
    check(len(depths) > 20, "достаточно заголовков для оглавления",
          str(len(depths)))
    check(sum(1 for d in depths if d == 2) >= 8, "есть нумерованные разделы")

    fences = [ln for ln in lines if ln.strip().startswith("```")]
    check(len(fences) % 2 == 0, "блоки кода закрыты", f"{len(fences)} ограждений")

    # Таблица не должна быть разорвана строкой без вертикальной черты.
    broken = []
    for i, ln in enumerate(lines):
        if ln.count("|") < 2 or set(ln.strip()) <= set("|- :"):
            continue
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            if nxt.strip() and nxt.count("|") < 2:
                broken.append(i + 1)
    check(not broken, "таблицы не разорваны", str(broken[:6]))

    # Число колонок не должно скакать внутри одной таблицы.
    ragged, block = [], []
    for i, ln in enumerate(lines):
        if ln.count("|") >= 2:
            block.append((i + 1, ln.count("|")))
        else:
            if len(block) >= 2 and len({w for _, w in block}) > 1:
                ragged.append(block[0][0])
            block = []
    if len(block) >= 2 and len({w for _, w in block}) > 1:
        ragged.append(block[0][0])
    check(not ragged, "число колонок одинаково по всей таблице",
          str(ragged[:6]))

    src = sorted(set(re.findall(
        r"\b([A-Z][A-Za-z]+\.(?:tsx|py|ts)|[a-z_]+\.json)\b", text)))
    check(not src, "нет имён файлов исходников", str(src[:8]))

    # Служебные пометки ищем, выбросив inline-код: «TODO» в руководстве
    # пользователя — это настоящее название группы колонок доски, и оно
    # всегда заключено в кавычки кода.
    todo = []
    for ln in lines:
        if re.search(r"\b(TODO|FIXME|XXX)\b", re.sub(r"`[^`]*`", "", ln)):
            todo.append(ln.strip()[:50])
    check(not todo, "нет незаполненных заглушек", str(todo[:3]))

    check("/docs/" not in text,
          "нет устаревшего адреса раздачи (рабочий — /manuals/)")

    # Язык файла должен совпадать с его именем: английское руководство
    # без переведённого заголовка означало бы, что перевод не начат.
    is_english = name.endswith(".en.md")
    heading = next((ln for ln in lines if ln.startswith("# ")), "")
    if is_english:
        check(not re.search(r"[а-яёА-ЯЁ]{3,}", heading),
              "заголовок английского руководства переведён", heading[:60])
    else:
        check(bool(re.search(r"[а-яёА-ЯЁ]{3,}", heading)),
              "заголовок русского руководства на русском", heading[:60])

    print(f"  строк: {len(lines)}, слов: {len(text.split())}, "
          f"таблиц: {sum(1 for ln in lines if re.match(r'^\|[-: |]+\|$', ln.strip()))}")

# ================================================================ #
# 7. Кодировка поставки
# ================================================================ #
print("\n=== 7. Кодировка ===")
for rel in (".gitignore", ".dockerignore", "docker-compose.yml",
            "backend/Dockerfile", "backend/.env.example", "README.md",
            "docs/user-guide.md", "docs/admin-guide.md"):
    raw = open(os.path.join(REPO, rel), "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        check(False, f"{rel} читается как UTF-8", str(exc))
        continue
    check("�" not in text, f"{rel} без повреждённых символов")

print("\n" + "=" * 60)
print(f"ИТОГ: {total - len(failures)}/{total} проверок пройдено")
for name in failures:
    print(f"  ПРОВАЛ: {name}")
sys.exit(1 if failures else 0)