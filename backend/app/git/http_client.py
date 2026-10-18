"""HTTP-клиент для Git-провайдеров с учётом лимитов API.

Что закрывает:
  * постраничную загрузку (раньше тянули только первую страницу с `per_page`);
  * повторы при 429/5xx с экспоненциальной задержкой и джиттером;
  * уважение заголовка ``Retry-After``;
  * «вторичные» лимиты GitHub (HTTP 403 с текстом про rate limit);
  * корректные таймауты вместо бесконечного ожидания.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Признаки исчерпания лимита в теле ответа (GitHub, GitLab)
_RATE_LIMIT_HINTS = (
    "rate limit",
    "api rate limit exceeded",
    "secondary rate",
    "too many requests",
    "abuse detection",
    "quota exceeded",
)


class GitAPIError(Exception):
    """Ошибка обращения к API провайдера."""

    def __init__(self, message: str, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class GitAuthError(GitAPIError):
    """Токен недействителен или недостаточен прав."""


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    # Число секунд
    try:
        return float(value)
    except ValueError:
        pass
    # HTTP-дата — берём разницу с текущим моментом
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone

        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        delta = (target - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, min(delta, 300.0))
    except Exception:
        return None


def _looks_like_rate_limit(status_code: int, text: str) -> bool:
    if status_code == 429:
        return True
    lowered = (text or "").lower()
    return status_code == 403 and any(hint in lowered for hint in _RATE_LIMIT_HINTS)


class GitHTTPClient:
    """Асинхронный клиент одного провайдера."""

    def __init__(
        self,
        base_url: str,
        headers: Dict[str, str] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout if timeout is not None else settings.GIT_HTTP_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else settings.GIT_HTTP_MAX_RETRIES

    # ------------------------------------------------------------------ #
    # Базовый запрос с повторами
    # ------------------------------------------------------------------ #
    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        attempts = self.max_retries + 1
        last_error: GitAPIError | None = None

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    headers=self.headers, timeout=self.timeout, follow_redirects=True
                ) as client:
                    response = await client.request(method, url, **kwargs)

                if response.status_code < 400:
                    return response

                text = response.text
                if response.status_code in (401, 403) and not _looks_like_rate_limit(
                    response.status_code, text
                ):
                    raise GitAuthError(
                        f"Провайдер отклонил авторизацию ({response.status_code}): {text[:200]}",
                        status_code=response.status_code,
                    )

                if _looks_like_rate_limit(response.status_code, text):
                    last_error = GitAPIError(
                        f"Лимит API провайдера исчерпан ({response.status_code})",
                        status_code=response.status_code,
                        retryable=True,
                    )
                    if attempt < attempts - 1:
                        delay = _parse_retry_after(response.headers.get("Retry-After"))
                        if delay is None:
                            delay = self._backoff(attempt)
                        logger.warning(
                            "Git API: лимит запросов, повтор через %.1fс (%s)", delay, url
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise last_error

                if response.status_code >= 500:
                    last_error = GitAPIError(
                        f"Временная ошибка провайдера ({response.status_code})",
                        status_code=response.status_code,
                        retryable=True,
                    )
                    if attempt < attempts - 1:
                        delay = self._backoff(attempt)
                        logger.warning(
                            "Git API: %s, повтор через %.1fс", response.status_code, delay
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise last_error

                raise GitAPIError(
                    f"Ошибка API провайдера ({response.status_code}): {text[:200]}",
                    status_code=response.status_code,
                )

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = GitAPIError(f"Сеть недоступна: {exc}", retryable=True)
                if attempt < attempts - 1:
                    delay = self._backoff(attempt)
                    logger.warning("Git API: сеть недоступна (%s), повтор через %.1fс", exc, delay)
                    await asyncio.sleep(delay)
                    continue
                raise last_error

        raise last_error or GitAPIError("Неизвестная ошибка обращения к API")

    @staticmethod
    def _backoff(attempt: int) -> float:
        """Экспоненциальная задержка с джиттером: ~1с, 2с, 4с."""
        base = min(2 ** attempt, 16)
        return base + random.uniform(0, 0.5)

    # ------------------------------------------------------------------ #
    # Постраничная загрузка
    # ------------------------------------------------------------------ #
    async def get_paginated(
        self,
        path: str,
        params: Dict[str, Any] | None = None,
        page_param: str = "page",
        per_page_param: str = "per_page",
        page_size: int | None = None,
        max_pages: int | None = None,
        item_key: Optional[str] = None,
    ) -> List[Any]:
        """Собирает элементы всех страниц. Работает и со списками, и со словарями.

        ``item_key`` — ключ внутри объекта-ответа со списком
        (например ``"values"`` у GitLab).
        """
        page_size = page_size or settings.GIT_SYNC_PAGE_SIZE
        max_pages = max_pages or settings.GIT_SYNC_MAX_PAGES

        collected: List[Any] = []
        page = 1

        while page <= max_pages:
            query = dict(params or {})
            query[page_param] = page
            query[per_page_param] = page_size

            response = await self.request("GET", path, params=query)
            data = response.json()

            if item_key:
                items = data.get(item_key) or []
            elif isinstance(data, list):
                items = data
            else:
                items = data.get("items") or data.get("values") or []

            if not items:
                break

            collected.extend(items)

            if len(items) < page_size:
                break
            page += 1

        return collected

    async def get_json(self, path: str, **kwargs: Any) -> Any:
        return (await self.request("GET", path, **kwargs)).json()

    async def post_json(self, path: str, **kwargs: Any) -> Any:
        return (await self.request("POST", path, **kwargs)).json()


def parse_gitlab_project_path(url: str, api_url: str | None = None) -> str | None:
    """Извлекает ``group/subgroup/project`` из URL GitLab."""
    if not url:
        return None
    match = re.search(r"gitlab[^/]*/(.+?)(?:\.git)?/?$", url.strip())
    if not match:
        return None
    return match.group(1)
