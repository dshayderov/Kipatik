import asyncio
import os
import json
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from jose import JWTError

from app.api.v1.api import api_router
from app.core.config import settings
from app.ai import api as ai_api
from app.core.ws_manager import manager
from app.core.security import jwt, get_password_hash
from app.core.database import SessionLocal
from app.git.services import start_periodic_storage_purge, start_periodic_sync
from app.users.models import User
from app.schemas.auth import TokenPayload
import app.models 

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend for project management with Git integration and AI analytics",
    version="0.1.0"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройка статических файлов
if not os.path.exists("uploads"):
    os.makedirs("uploads")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


def _resolve_docs_dir():
    """Где лежат руководства.

    Файлы docs/ в репозитории одни и те же: их читают и Git, и страница
    справки внутри приложения. Держать вторую копию в сборке фронтенда
    значит получить два расходящихся документа, поэтому текст отдаётся
    бэкендом прямо из репозитория.

    Путь переопределяется настройкой DOCS_DIR — в контейнере папка
    копируется в /app/docs, а в разработке берётся корень репозитория.
    """
    override = (settings.DOCS_DIR or "").strip()
    if override:
        return override

    here = os.path.dirname(os.path.abspath(__file__))            # backend/app
    for candidate in (
        os.path.join(here, "docs"),                               # контейнер
        os.path.join(os.path.dirname(here), "docs"),              # backend/docs
        os.path.join(os.path.dirname(os.path.dirname(here)), "docs"),  # docs/ в корне
    ):
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(os.path.dirname(os.path.dirname(here)), "docs")


# Руководство администратора описывает секреты и переменные окружения,
# поэтому отдавать его наружу по умолчанию нельзя. Включается
# настройкой SERVE_DOCS: в разработке она включена, в контейнере
# решение принимает администратор.
if settings.SERVE_DOCS:
    _docs_dir = _resolve_docs_dir()
    if os.path.isdir(_docs_dir):
        # Адрес /docs занят встроенной документацией API, поэтому
        # руководства лежат под /manuals. Иначе страница справки
        # Swagger отдавала бы 404 на каждый файл, а поменять порядок
        # регистрации маршрутов здесь нельзя: он задаётся при создании
        # приложения, до подключения монтирований.
        app.mount("/manuals", StaticFiles(directory=_docs_dir), name="manuals")
    else:
        logging.getLogger("kipatik").warning(
            "SERVE_DOCS включён, но папка с руководствами не найдена: %s", _docs_dir
        )

# ПОДКЛЮЧЕНИЕ API РОУТОВ
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.on_event("startup")
async def startup_event():
    # 1. Создаем дефолтного пользователя, если его нет
    async with SessionLocal() as db:
        result = await db.execute(select(User).filter(User.id == 1))
        if not result.scalar_one_or_none():
            default_user = User(
                id=1,
                email="admin@example.com",
                hashed_password=get_password_hash("admin"),
                full_name="Default Admin",
                is_superuser=True,
                can_create_projects=True
            )
            db.add(default_user)
            await db.commit()
            print("Default user created.")

    # 2. Запуск фоновой синхронизации.
    #
    # Интервал берётся из настроек. Раньше здесь стояло число 300:
    # настройка GIT_SYNC_INTERVAL_SECONDS была объявлена, описана в
    # руководстве администратора и при этом ни на что не влияла —
    # её значение просто игнорировалось. Проверку включения повторять
    # не нужно: функция сама смотрит GIT_SYNC_ENABLED и пишет в лог,
    # когда синхронизация выключена.
    asyncio.create_task(start_periodic_sync(settings.GIT_SYNC_INTERVAL_SECONDS))

    # 2a. Автоочистка корзины и неприкреплённых файлов.
    # Раньше это висело на задачах Celery без расписания, то есть не
    # выполнялось никогда.
    async with SessionLocal() as db:
        from app.storage import settings as storage_settings

        await storage_settings.refresh(db)
        interval = storage_settings.purge_interval_hours() * 3600

    if storage_settings.auto_purge_enabled():
        asyncio.create_task(
            start_periodic_storage_purge(interval)
        )

    # 3. Прогрев модели анализа кода.
    #
    # Сначала читаются решения администратора из базы: включение модели
    # задаётся ими, а не только флагами окружения. Дальше прогревается
    # то, что реально включено.
    #
    # Чтение чекпоинта занимает секунды. Если ждать этого в первом же
    # запросе, вебхук привязки коммита успел бы истечь. Поэтому грузим
    # отдельной задачей и не блокируем запуск.
    async with SessionLocal() as db:
        from app.ai import api as ai_api

        await ai_api.refresh(db)

    if (
        settings.CODE_MODEL_ENABLED
        and settings.CODE_MODEL_CLASSIFY
        and ai_api.is_enabled(ai_api.KEY_ENCODER)
    ):
        asyncio.create_task(warmup_code_model())


async def warmup_code_model() -> None:
    """Прогревает модели анализа кода вне запросов.

    Кодировщик и классификатор грузятся по отдельности: классификатор
    считает поверх эмбеддингов кодировщика, поэтому при выключенном
    классификаторе поднимается только кодировщик. Это же позволяет
    держать типы выключенными, не теряя трассировку.
    """
    from app.ai.api import type_classifier, encoder

    try:
        started = time.monotonic()
        ok = await asyncio.to_thread(encoder.load)
        if not ok:
            print(
                "Кодировщик анализа кода не загружен:",
                encoder.status().get("reason") or encoder.status().get("error"),
            )
            return

        print(
            f"Кодировщик анализа кода готов за {time.monotonic() - started:.1f} с "
            f"(устройство: {encoder.status()['device']})"
        )

        if not ai_api.is_enabled(ai_api.KEY_TYPE_CLASSIFIER):
            return

        started = time.monotonic()
        types_ok = await asyncio.to_thread(type_classifier.load)
        if types_ok:
            print(
                f"Классификатор типов готов за {time.monotonic() - started:.1f} с"
            )
        else:
            print(
                "Классификатор типов не загружен:",
                type_classifier.status().get("reason")
                or type_classifier.status().get("error"),
            )
    except Exception as exc:  # noqa: BLE001 — прогрев не должен ронять запуск
        print("Не удалось прогреть модели анализа кода:", exc)

@app.get("/")
async def root():
    return {"message": f"{settings.PROJECT_NAME} API is running"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    if token is None:
        # Check if token is in subprotocol or query string (FastAPI handles token: str from query automatically)
        pass
    
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        user_id = int(token_data.sub)
    except (JWTError, Exception) as e:
        print(f"WS Auth Error: {e}")
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception:
        manager.disconnect(websocket, user_id)
