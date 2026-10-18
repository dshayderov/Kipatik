"""Скачивание словаря и конфига кодировщика.

Зачем нужен этот скрипт
-----------------------

В чекпоинте ``commit_tracer.pt`` лежат **только веса**. Архитектуры
ни в чекпоинте, ни в коде нет: модель собирается через
``from_config``, а архитектура берётся из ``config.json`` и словарь —
из ``tokenizer.json``. Без них кодировщик не запустится, и страница
управления моделями покажет причину ``tokenizer_missing``.

В ноутбуке это происходило само собой через
``AutoModel.from_pretrained(MODEL_NAME)``, но такой вызов тянет 1.11 ГБ
весов, чтобы тут же их затёрть. Здесь скачивается только нужное:
конфиг, словарь и модель sentencepiece — около 13 МБ.

Почему папка словаря под контролем версий
-----------------------------------------

Она небольшая и нужна для работы, поэтому хранится в репозитории, а
не генерируется при развёртывании. Воспроизводимость важнее
экономии тринадцати мегабайт: без неё чистая машина не запустит
модель.

Использование
-------------

    python backend/scripts/fetch_tokenizer.py            # скачать, если нет
    python backend/scripts/fetch_tokenizer.py --force    # перекачать
    python backend/scripts/fetch_tokenizer.py --check    # только проверить

Проверка ничего не скачивает и ничего не меняет — её можно запускать
в проверках развёртывания.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request

# Имя папки с конфигом и словарём внутри app/ai/encoder/tokenizer/.
# Должно совпадать с TOKENIZER_SUBDIR в app/ai/encoder/service.py —
# иначе кодировщик будет искать папку, которой нет.
MODEL_SUBDIR = "paraphrase-multilingual-mpnet-base-v2"

BASE_URL = (
    "https://huggingface.co/sentence-transformers/"
    "paraphrase-multilingual-mpnet-base-v2/resolve/main"
)

# Обязательные файлы: без любого из них токенизатор не поднимется.
REQUIRED_FILES = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    # Модель sentencepiece нужна не всем, но transformers может
    # обратиться к ней при медленном токенизаторе.
    "sentencepiece.bpe.model",
)

# backend/scripts/fetch_tokenizer.py -> backend -> репозиторий.
# Два dirname, а не три: третий уводит на уровень выше backend,
# и словарь скачался бы в папку, которую никто не читает.
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_DIR = os.path.join(BACKEND, "app", "ai", "code_model", MODEL_SUBDIR)

TIMEOUT = 60


def human(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} МБ"
    return f"{size / 1024:.0f} КБ"


def download(url: str, dest: str) -> bool:
    tmp = dest + ".part"
    try:
        print(f"  качаю {os.path.basename(dest)} ... ", end="", flush=True)
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            data = resp.read()
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
        print(f"готово ({human(len(data))})")
        return True
    except urllib.error.HTTPError as exc:
        print(f"ошибка HTTP {exc.code}")
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    except Exception as exc:  # noqa: BLE001 — скрипт должен пережить сеть
        print(f"ошибка: {type(exc).__name__}: {exc}")
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Скачать словарь и конфиг кодировщика анализа кода."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="перекачать, даже если файлы уже на месте",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="только проверить наличие файлов, ничего не скачивая",
    )
    parser.add_argument(
        "--target", default=TARGET_DIR,
        help=f"куда складывать (по умолчанию {TARGET_DIR})",
    )
    args = parser.parse_args()

    target = args.target
    print(f"Папка назначения: {target}")
    print()

    if args.check:
        missing = [
            n for n in REQUIRED_FILES
            if not os.path.isfile(os.path.join(target, n))
        ]
        if missing:
            print(f"  НЕ ХВАТАЕТ: {', '.join(missing)}")
            print("  Скачать: python backend/scripts/fetch_tokenizer.py")
            return 1
        size = sum(
            os.path.getsize(os.path.join(target, n)) for n in REQUIRED_FILES
        )
        print(f"  все файлы на месте, {human(size)}")
        return 0

    os.makedirs(target, exist_ok=True)

    failed = []
    for name in REQUIRED_FILES:
        dest = os.path.join(target, name)
        if os.path.isfile(dest) and not args.force:
            print(f"  есть {name} ({human(os.path.getsize(dest))}), пропускаю")
            continue
        if not download(f"{BASE_URL}/{name}", dest):
            failed.append(name)

    print()
    if failed:
        print(f"Не удалось скачать: {', '.join(failed)}")
        print(f"Скачайте вручную с {BASE_URL} и положите в {target}")
        return 1

    size = sum(os.path.getsize(os.path.join(target, n)) for n in REQUIRED_FILES)
    print(f"Готово: {human(size)} в {target}")
    print()
    print("Осталось положить веса моделей — скрипт их не качает:")
    for name in (settings_names := ("commit_tracer.pt", "type_classifier.pt")):
        print(f"  {os.path.join(BACKEND, 'app', 'ai', 'code_model', name)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())