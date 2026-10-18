import asyncio
from typing import Dict
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.git.factory import get_git_provider
from app.git.models import GitRepository
from sqlalchemy import select


@celery_app.task(name="process_git_webhook")
def process_git_webhook(
    repository_id: int,
    payload: Dict,
    event_type: str,
    signature_verified: bool = False,
    delivery_id: str | None = None,
):
    """Фоновая задача для обработки вебхука"""
    # Поскольку Celery работает синхронно, а сервисы асинхронные,
    # запускаем event loop вручную. Создаём новый цикл явно:
    # asyncio.get_event_loop() в worker-процессе на части версий Python
    # бросает RuntimeError («There is no current event loop»).
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _process_git_event(
                repository_id, payload, event_type, signature_verified, delivery_id
            )
        )
    finally:
        loop.close()


async def _process_git_event(
    repository_id: int,
    payload: Dict,
    event_type: str,
    signature_verified: bool = False,
    delivery_id: str | None = None,
):
    async with SessionLocal() as db:
        # 1. Получаем репозиторий
        result = await db.execute(select(GitRepository).filter(GitRepository.id == repository_id))
        repo = result.scalar_one_or_none()
        if not repo:
            return {"error": "Repository not found"}

        # 2. Получаем провайдер
        # Токен репозитория мог истечь (OAuth-токены живут считаные часы) —
        # обновляем его перед использованием.
        token = repo.access_token
        if repo.connected_by_id:
            from app.git.token_resolver import resolve_user_token

            fresh = await resolve_user_token(
                db, repo.connected_by_id, repo.provider, repo.api_url
            )
            if fresh and fresh != token:
                repo.access_token = fresh
                await db.commit()
                token = fresh
        provider = get_git_provider(repo.provider, token=token, api_url=repo.api_url)

        # 3. Парсим событие в Unified GitEvent
        event = provider.parse_webhook(repository_id, payload, event_type)
        if not event:
            return {"status": "ignored"}

        # 4. Логика привязки к задачам (Task Linking Engine)
        from app.git.services import GitEventService
        await GitEventService.process_event(
            db, event, signature_verified=signature_verified, delivery_id=delivery_id
        )

        return {"status": "success", "event_type": event.type}
