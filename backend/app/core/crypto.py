"""Шифрование секретов при хранении (токены Git-провайдеров).

Раньше PAT / OAuth-токены лежали в базе открытым текстом, что делало утечку
БД равносильной утечке всех доступов к репозиториям.

Здесь используется Fernet (AES-128-CBC + HMAC) из пакета `cryptography`,
который уже приходит в составе `python-jose[cryptography]`.

Схема обратной совместимости:
  * зашифрованное значение помечается префиксом ``enc:v1:``;
  * если префикса нет — значение считается legacy-открытым текстом и
    возвращается как есть, поэтому уже сохранённые токены продолжают работать;
  * ключ берётся из ``TOKEN_ENCRYPTION_KEY``, а если он не задан —
    детерминированно выводится из ``SECRET_KEY`` (тогда шифрование включено
    всегда, но менять SECRET_KEY нельзя — иначе токены перестанут читаться).
"""
from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

logger = logging.getLogger(__name__)

ENCRYPTION_PREFIX = "enc:v1:"

_fernet = None


def _build_fernet():
    """Строит Fernet из настроек. Ключ 32 байта в urlsafe-base64."""
    key_material = (
        getattr(settings, "TOKEN_ENCRYPTION_KEY", "") or ""
    ).strip() or settings.SECRET_KEY

    # Приводим любую строку к корректному 32-байтовому ключу
    digest = hashlib.sha256(key_material.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet():
    global _fernet
    if _fernet is None:
        try:
            from cryptography.fernet import Fernet

            _fernet = Fernet(_build_fernet())
        except Exception as exc:  # pragma: no cover - защитный путь
            logger.error("Не удалось инициализировать шифрование токенов: %s", exc)
            return None
    return _fernet


def encrypt_value(plaintext: Optional[str]) -> Optional[str]:
    """Шифрует значение. Уже зашифрованное и пустое возвращает как есть."""
    if plaintext is None or plaintext == "":
        return plaintext
    if isinstance(plaintext, str) and plaintext.startswith(ENCRYPTION_PREFIX):
        return plaintext

    fernet = get_fernet()
    if fernet is None:
        # Не ломаем работу системы, если шифрование недоступно,
        # но обязательно фиксируем это в логах.
        logger.error("Токен сохранён без шифрования: Fernet недоступен")
        return plaintext

    token = fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTION_PREFIX}{token}"


def decrypt_value(stored: Optional[str]) -> Optional[str]:
    """Расшифровывает значение. Legacy-открытый текст возвращает как есть."""
    if stored is None or stored == "":
        return stored
    if not isinstance(stored, str) or not stored.startswith(ENCRYPTION_PREFIX):
        return stored

    fernet = get_fernet()
    if fernet is None:
        logger.error("Не удалось расшифровать токен: Fernet недоступен")
        return None

    raw = stored[len(ENCRYPTION_PREFIX):]
    try:
        return fernet.decrypt(raw.encode("utf-8")).decode("utf-8")
    except Exception:
        # Токен зашифрован другим ключом — вернуть его «как есть» нельзя,
        # иначе провайдер получит мусор вместо токена.
        logger.error("Не удалось расшифровать токен (неверный ключ?) — значение отброшено")
        return None


class EncryptedString(TypeDecorator):
    """Строка, которая хранится в БД зашифрованной.

    В Python-коде атрибут всегда содержит открытый текст — вся бизнес-логика
    (передача токена провайдеру и т.п.) работает как раньше, а шифрование и
    расшифровка происходят только на границе с базой данных.

    Реализовано через TypeDecorator, а не через ORM-события: событие `set`
    шифровало бы значение прямо в объекте, и тогда чтение атрибута возвращало
    бы шифротекст вместо токена.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        # В БД остаётся обычный VARCHAR — схема не меняется
        return dialect.type_descriptor(String())

    def process_bind_param(self, value, dialect):
        """Python -> БД: шифруем."""
        if value is None:
            return None
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        """БД -> Python: расшифровываем (legacy-значения — как есть)."""
        if value is None:
            return None
        return decrypt_value(value)
