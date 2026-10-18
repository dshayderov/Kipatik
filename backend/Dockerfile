# ───────────────────────────────────────────────────────────── #
# Образ бэкенда Kipatik
# ───────────────────────────────────────────────────────────── #
# Собирается из КОРНЯ репозитория, а не из папки backend: в образ
# должны попасть ещё и руководства из docs/, иначе страница справки
# внутри приложения останется без содержимого.
#
#   docker build -f backend/Dockerfile -t kipatik-backend .
#
# Контекст сборки и список исключений — .dockerignore в корне.
#
# ───────────────────────────────────────────────────────────── #

# ── Этап 1. Зависимости ───────────────────────────────────── #
# Отдельный этап ради кэша слоёв: пока не меняются requirements.txt,
# пересобирается только этот слой, а не весь образ целиком.
FROM python:3.12-slim AS deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential и git нужны на этапе установки: часть пакетов
# собирается из исходников, а GitPython ходит в репозитории.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Объявлено именно здесь, в этапе deps: ARG не наследуется следующими
# этапами, и без объявления переменная подставится пустой строкой,
# молча убрав torch из образа.
ARG INSTALL_TORCH=false

COPY backend/requirements.txt ./

# torch сознательно не в requirements.txt: базовый образ тянут
# сорока гигабайт с вариантами CUDA, а на CPU он в разы меньше.
# Нужен только тем, кто собирается возить модели в контейнере:
#   docker build -f backend/Dockerfile --build-arg INSTALL_TORCH=true .
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_TORCH" = "true" ]; then \
         pip install --index-url https://download.pytorch.org/whl/cpu torch \
         && pip install transformers numpy; \
       fi

# ── Этап 2. Среда выполнения ──────────────────────────────── #
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Куда смотреть за руководствами. Путь задан явно, потому что
    # в контейнере структура папок другая, чем в репозитории.
    DOCS_DIR=/app/docs \
    # Руководство администратора описывает секреты и переменные
    # окружения, поэтому наружу оно не отдаётся, пока администратор
    # не включит это явно.
    SERVE_DOCS=false \
    # Артефакты моделей в образ не кладутся: кодировщик весит около
    # гигабайта. Пусто — искать рядом с кодом; задайте /app/models,
    # если подключите папку с моделями монтированием.
    CODE_MODEL_DIR=

# Разработка образ никогда не нужна: пересборка при изменении файла
# означает, что в контейнер попадёт что-то, чего не было проверено.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Код и конфигурация миграций.
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini

# Руководства. В репозитории они лежат в docs/, здесь — там, где их
# ищет приложение.
COPY docs ./docs

# Приложение пишет загруженные файлы: аватары, фоны проектов,
# вложения комментариев. Каталог создаётся от пользователя без
# прав root, иначе первый же запрос с вложением упадёт.
RUN mkdir -p /app/uploads \
    && useradd --create-home --uid 10001 kipatik \
    && chown -R kipatik:kipatik /app

USER kipatik

EXPOSE 8000

# Проверка живости. Сделана на urllib, а не на curl, чтобы не
# тянуть лишний пакет: healthcheck должен работать в том же образе,
# который и проверяет, а не в отдельном.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/docs || curl -fsS http://127.0.0.1:8000/ || exit 1

# Миграции и стар сервера разделены. Схема применяется один раз при
# развёртывании, а не при каждом перезапуске контейнера: иначе
# второй экземпляр приложения будет всерьёз менять схему чужой базы,
# и при несовпадении версий это приведёт к простоям.
#
#   docker compose exec backend alembic upgrade head
#   docker compose up -d
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]