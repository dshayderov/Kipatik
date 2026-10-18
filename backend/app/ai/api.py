"""Единая точка работы с моделями анализа кода.

Что здесь лежит
---------------

1. Реестр моделей: что есть на диске, что включено, где лежат
   артефакты.
2. Модель трассировки — подбирает задачу для коммита по смыслу
   изменений (лабораторная работа №1).
3. Модель типов коммитов — bugfix, feature, refactor, docs, test,
   chore (лабораторная работа №3). Работает поверх эмбеддингов
   кодировщика, поэтому порядок загрузки обязателен.
4. HTTP-маршруты: анализ задачи, оценка прогресса и диагностика
   моделей для проверки развёртывания.

Артефакты лежат рядом, в папке code_model/:

    code_model/commit_tracer.pt                     веса трассировки
    code_model/type_classifier.pt                   веса типов
    code_model/progress_estimator.py                модуль правил
    code_model/paraphrase-multilingual-mpnet-base-v2/  конфиг и словарь

В файлах весов лежат только веса. Архитектура и словарь берутся из
папки с моделью mpnet: без неё кодировщик не запустится.

Загрузка ленивая: импорт этого модуля не тянет за собой torch и не
читает гигабайтный файл. Выключенная модель вообще не поднимается.
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.models.ai_settings import AIModelSetting
from app.tasks.models import Task
from app.tasks.nlp_service import nlp_engine
from app.core.database import get_db
from app.tasks.progress import get_task_progress
from app.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Реестр моделей
# ---------------------------------------------------------------------------


logger = logging.getLogger(__name__)

KEY_ENCODER = "encoder"
KEY_TYPE_CLASSIFIER = "type_classifier"
KEY_PROGRESS = "progress_estimator"

MODEL_KEYS = (KEY_ENCODER, KEY_TYPE_CLASSIFIER, KEY_PROGRESS)

# Описание для интерфейса. Ключи i18n хранятся отдельно, здесь —
# только то, что знает сервер: артефакт, размер и потребитель.
MODEL_SPECS: Dict[str, dict] = {
    KEY_ENCODER: {
        "title_key": "encoder",
        "artifact_setting": "CODE_MODEL_TRACER_FILE",
        "kind": "neural",
        "loads_into_memory": True,
        "depends_on": [],
        "purpose_key": "encoder_purpose",
        # Классификатор типов работает поверх эмбеддингов кодировщика,
        # поэтому выключение кодировщика выключает и его.
        "blocks": [KEY_TYPE_CLASSIFIER],
    },
    KEY_TYPE_CLASSIFIER: {
        "title_key": "type_classifier",
        "artifact_setting": "CODE_MODEL_CLASSIFIER_FILE",
        "kind": "neural",
        # Занимает память и выгружается отдельно от кодировщика:
        # она маленькая, и держать её ради одного мегабайта незачем.
        "loads_into_memory": True,
        "depends_on": [KEY_ENCODER],
        "purpose_key": "type_classifier_purpose",
        "blocks": [],
    },
    KEY_PROGRESS: {
        "title_key": "progress_estimator",
        "artifact_setting": None,
        "kind": "rules",
        "loads_into_memory": False,
        "depends_on": [],
        "purpose_key": "progress_estimator_purpose",
        "blocks": [],
    },
}

# Переопределения из базы: ключ → включено. Пусто, пока база не
# прочитана, тогда действуют значения окружения.
_overrides: Dict[str, bool] = {}


def _env_default(key: str) -> bool:
    """Значение из окружения — то, что действует до первого решения админа."""
    if key == KEY_ENCODER:
        return bool(settings.CODE_MODEL_ENABLED)
    if key == KEY_TYPE_CLASSIFIER:
        return bool(settings.CODE_MODEL_ENABLED and settings.CODE_MODEL_CLASSIFY)
    if key == KEY_PROGRESS:
        return bool(settings.PROGRESS_ENABLED)
    return True


def is_enabled(key: str) -> bool:
    """Включена ли модель. Синхронная: зовётся из горячего пути."""
    if key in _overrides:
        return _overrides[key]
    return _env_default(key)


def overrides() -> Dict[str, bool]:
    """Текущие переопределения — копия, чтобы вызывающий не мутил словарь."""
    return dict(_overrides)


# Имя папки с конфигом и словарём кодировщика. Должно совпадать
# с именем, под которым словарь кладёт scripts/fetch_tokenizer.py.
TOKENIZER_SUBDIR = "paraphrase-multilingual-mpnet-base-v2"


def model_root() -> Path:
    """Корень, в котором лежат папки моделей.

    Пустой CODE_MODEL_DIR означает «искать рядом с кодом». Раньше здесь
    стоял относительный путь, который разрешался от рабочей папки
    процесса: запуск сервера не из папки backend находил артефакты и
    молча работал без моделей.
    """
    configured = (settings.CODE_MODEL_DIR or "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent


# Имя папки с артефактами. Обе модели живут в ней рядом: веса
# кодировщика, веса типов, модуль правил и папка со словарём.
ARTIFACT_DIR = "code_model"


def code_model_dir() -> Path:
    """Папка с артефактами: app/ai/code_model рядом с кодом."""
    return model_root() / ARTIFACT_DIR


def tokenizer_dir() -> Path:
    """Папка с конфигом и словарём кодировщика.

    Словарь принадлежит кодировщику, но лежит в общей папке: он нужен
    обоим моделям, потому что классификатор считает поверх
    эмбеддингов кодировщика.
    """
    return code_model_dir() / TOKENIZER_SUBDIR


def artifact_path(key: str) -> Optional[Path]:
    """Путь к файлу весов модели, если у неё есть файл."""
    setting = MODEL_SPECS.get(key, {}).get("artifact_setting")
    if not setting:
        return None
    return code_model_dir() / getattr(settings, setting)


def artifact_size_mb(key: str) -> float:
    """Размер артефакта на диске в мегабайтах; 0, если файла нет."""
    path = artifact_path(key)
    if not path or not path.exists():
        return 0.0
    return round(path.stat().st_size / 1024 / 1024, 2)


async def refresh(db: AsyncSession) -> None:
    """Перечитывает переопределения из базы.

    Ошибку не поднимает: приложение обязано работать и при недоступной
    базе настроек — тогда действуют значения окружения.
    """


    try:
        rows = (
            await db.execute(select(AIModelSetting))
        ).scalars().all()
        _overrides.clear()
        for row in rows:
            _overrides[row.key] = bool(row.enabled)
    except Exception as exc:  # noqa: BLE001 — деградация вместо падения
        logger.warning("Не удалось прочитать настройки моделей: %s", exc)
        _overrides.clear()


async def set_enabled(db: AsyncSession, key: str, enabled: bool, user_id: int) -> bool:
    """Записывает решение администратора и сразу обновляет кеш."""


    if key not in MODEL_KEYS:
        raise KeyError(key)

    row = (
        await db.execute(select(AIModelSetting).where(AIModelSetting.key == key))
    ).scalar_one_or_none()

    if row is None:
        row = AIModelSetting(key=key, enabled=enabled, updated_by_id=user_id)
        db.add(row)
    else:
        row.enabled = enabled
        row.updated_by_id = user_id

    await db.commit()

    # Кеш обновляем из только что записанного значения: повторное
    # чтение базы здесь было бы лишним запросом ради одной строки.
    _overrides[key] = bool(enabled)
    return bool(enabled)


def describe(key: str) -> dict:
    """Полное описание модели для интерфейса."""
    spec = MODEL_SPECS.get(key)
    if not spec:
        return {}

    path = artifact_path(key)
    blockers = [
        b for b in spec.get("blocks", [])
        if not is_enabled(b) and key in MODEL_SPECS[b].get("depends_on", [])
    ]

    return {
        "key": key,
        "title_key": spec["title_key"],
        "purpose_key": spec["purpose_key"],
        "kind": spec["kind"],
        "enabled": is_enabled(key),
        "env_default": _env_default(key),
        "overridden": key in _overrides,
        "depends_on": spec.get("depends_on", []),
        "artifact": str(path) if path else None,
        "artifact_exists": bool(path and path.exists()),
        "artifact_size_mb": artifact_size_mb(key),
        "blocked_by": blockers,
    }


def all_descriptions() -> List[dict]:
    return [describe(k) for k in MODEL_KEYS]


# ---------------------------------------------------------------------------
# Модель трассировки (лабораторная работа №1)
# ---------------------------------------------------------------------------


logger = logging.getLogger(__name__)

TOKENIZER_FILES = (
    "tokenizer.json",
    "sentencepiece.bpe.model",
    "tokenizer_config.json",
    "special_tokens_map.json",
)

# Вклад семантики и пересечения файлов в общую оценку (ноутбук №1).
W_SEMANTIC = 0.85
W_FILES = 0.15


class ModelUnavailable(Exception):
    """Артефакты модели отсутствуют или не читаются."""


# Путь к артефактам считает реестр: он же показывает их
# администратору. Обёртка с именем weights_path() тут была бы
# ловушкой: она есть у обеих моделей, и одна перекрыла бы другую —
# кодировщик молча прочитал бы файл классификатора.


# --------------------------------------------------------------------- #
# Текстовое представление коммита (совпадает с обучением)
# --------------------------------------------------------------------- #
def extract_files_from_diff(diff_text: str) -> List[str]:
    return re.findall(r"^File: (.+)$", diff_text or "", re.MULTILINE)


def build_commit_representation(
    diff_text: str, commit_message: str, max_files: int = 10
) -> str:
    """Структурированный текст коммита.

    Порядок блоков («Files», «Message», «Changes») и их имена — часть
    формата обучения. Перестановка или переименование блоков испортит
    качество незаметно.
    """
    files = extract_files_from_diff(diff_text)[:max_files]
    files_block = "Files: " + ", ".join(files) if files else "Files: unknown"
    code_lines = [l for l in (diff_text or "").split("\n") if not l.startswith("File:")]
    code_block = "\n".join(code_lines[:40])
    return f"{files_block}\nMessage: {commit_message}\nChanges:\n{code_block}"


def file_overlap_score(commit_files: Sequence[str], task_text: str) -> float:
    """Доля файлов коммита, чьи имена упомянуты в тексте задачи."""
    if not commit_files:
        return 0.0
    task_lower = (task_text or "").lower()
    mentioned = sum(1 for f in commit_files if f.split("/")[-1].lower() in task_lower)
    return mentioned / len(commit_files)


def combined_score(semantic_sim: float, file_overlap: float) -> float:
    return W_SEMANTIC * semantic_sim + W_FILES * file_overlap


# --------------------------------------------------------------------- #
# Сервис
# --------------------------------------------------------------------- #
class EncoderService:
    """Потокобезопасная ленивая загрузка кодировщика и подбор задачи."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._encoder = None
        self._tokenizer = None
        self._torch = None
        self._error: Optional[str] = None
        self._device = "cpu"
        self._dim: Optional[int] = None

    # ---------------- состояние ----------------
    def artifacts(self) -> Dict:
        base = tokenizer_dir()
        missing = [n for n in TOKENIZER_FILES if not (base / n).exists()]
        weights = artifact_path(KEY_ENCODER)
        return {
            "tokenizer_dir": str(base),
            "tokenizer_ready": not missing,
            "tokenizer_missing": missing,
            "tracer": str(weights),
            "tracer_ready": weights.exists(),
        }

    def status(self) -> Dict:
        art = self.artifacts()
        enabled = is_enabled(KEY_ENCODER)

        reason = None
        if not enabled:
            reason = "disabled"
        elif not art["tokenizer_ready"]:
            reason = "tokenizer_missing"
        elif not art["tracer_ready"]:
            reason = "tracer_missing"

        return {
            "enabled": enabled,
            # Доступность кодировщика не зависит от классификатора типов:
            # те модели можно держать выключенной и при этом трассировать.
            "available": enabled and art["tokenizer_ready"] and art["tracer_ready"],
            "reason": reason,
            "loaded": self._loaded,
            "loaded_flag": self._encoder is not None,
            "device": self._device,
            "error": self._error,
            "trace_threshold": settings.CODE_MODEL_TRACE_THRESHOLD,
            "artifacts": art,
        }

    def device(self) -> str:
        return self._device

    def embedding_dim(self) -> Optional[int]:
        """Размер эмбеддинга, измеренный пробой при загрузке.

        Берётся из прогона, а не из config: обёртка модели не является
        transformers-моделью и поля `config` у неё нет, а проба заодно
        показывает настоящий размер, который вернёт `encode`.
        """
        return self._dim

    # ---------------- загрузка ----------------
    def _build_encoder(self, config):
        """Архитектура из локального config.json, без скачивания весов."""
        # Импорт внутри функции: без него сам модуль оставался бы дешёвым
        # и не тянул torch при первом обращении.
        import torch.nn as nn
        from transformers import AutoModel

        class MultilingualSimilarity(nn.Module):
            def __init__(self, cfg):
                super().__init__()
                self.encoder = AutoModel.from_config(cfg)
                self.dropout = nn.Dropout(0.2)

            def encode(self, input_ids, attention_mask):
                out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
                return self.dropout(out.last_hidden_state[:, 0, :])

            def forward(self, anchor_ids, anchor_mask, positive_ids, positive_mask,
                        negative_ids, negative_mask):
                return (self.encode(anchor_ids, anchor_mask),
                        self.encode(positive_ids, positive_mask),
                        self.encode(negative_ids, negative_mask))

        return MultilingualSimilarity(config)

    def load(self) -> bool:
        """Загружает артефакты. Повторный вызов ничего не делает."""
        if self._loaded:
            return True

        with self._lock:
            if self._loaded:
                return True

            if not is_enabled(KEY_ENCODER):
                self._error = "disabled"
                return False

            st = self.status()
            if not st["available"]:
                self._error = st["reason"]
                logger.info("Кодировщик недоступен: %s", st["reason"])
                return False

            tokenizer_path = tokenizer_dir()
            tracer_path = artifact_path(KEY_ENCODER)

            try:
                import torch
                from transformers import AutoConfig, AutoTokenizer

                requested = settings.CODE_MODEL_DEVICE
                if requested == "auto":
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                else:
                    device = requested
                if device.startswith("cuda") and not torch.cuda.is_available():
                    logger.warning("CUDA недоступна, переключаюсь на CPU")
                    device = "cpu"

                tokenizer = AutoTokenizer.from_pretrained(
                    str(tokenizer_path), local_files_only=True
                )
                config = AutoConfig.from_pretrained(
                    str(tokenizer_path), local_files_only=True
                )

                encoder = self._build_encoder(config)
                # Веса читаются отображением файла в память, а параметры
                # модели ссылаются прямо на них вместо копирования.
                #
                # Раньше было torch.load + load_state_dict, и последний
                # копирует: в момент копирования в памяти живут и модель,
                # и весь state_dict. Замер показал 2680 МБ против 1615 МБ
                # при той же скорости — треть памяти уходила на копию,
                # которая тут же выбрасывалась.
                #
                # mmap требует torch 2.1+, поэтому при отсутствии поддержки
                # остаётся прежний путь: хуже по памяти, но работает.
                load_kwargs = {"map_location": "cpu", "weights_only": True}
                try:
                    state = torch.load(str(tracer_path), mmap=True, **load_kwargs)
                    use_assign = True
                except (TypeError, RuntimeError, ValueError):
                    state = torch.load(str(tracer_path), **load_kwargs)
                    use_assign = False

                try:
                    encoder.load_state_dict(state, assign=use_assign)
                finally:
                    del state

                encoder.eval()
                encoder.to(device)

                with torch.no_grad():
                    probe = self._embed(tokenizer, torch, device, ["проверка"], encoder)

            except Exception as exc:  # noqa: BLE001 — деградация вместо падения
                self._error = f"{type(exc).__name__}: {exc}"
                logger.exception("Ошибка загрузки кодировщика")
                return False

            self._torch = torch
            self._tokenizer = tokenizer
            self._encoder = encoder
            self._device = device
            self._dim = int(probe.shape[-1])
            self._error = None
            self._loaded = True

            logger.info(
                "Кодировщик загружен на %s (эмбеддинг %d)",
                device, self._dim,
            )
            return True

    def unload(self) -> None:
        """Выгружает кодировщик — для освобождения памяти.

        Повторная загрузка в том же процессе после выгрузки ненадёжна:
        аллокатор torch удерживает освобождённый блок весов, и второе
        чтение файла может упасть по памяти. В рабочем сценарии это не
        мешает — модель грузится один раз и живёт до остановки.
        """
        import gc

        with self._lock:
            self._encoder = None
            self._tokenizer = None
            self._torch = None
            self._loaded = False
            self._device = "cpu"
            self._error = None
            self._dim = None
            gc.collect()

    # ---------------- вывод ----------------
    def _embed(self, tokenizer, torch, device: str, texts: Sequence[str], encoder):
        inputs = tokenizer(
            list(texts),
            max_length=256,
            truncation=True,
            padding="max_length",
            return_tensors="pt",
        ).to(device)
        with torch.inference_mode():
            return encoder.encode(inputs["input_ids"], inputs["attention_mask"])

    def embed(self, texts: Sequence[str]):
        """Векторы для списка текстов. Требует загруженного кодировщика."""
        if not self._loaded and not self.load():
            raise ModelUnavailable(self._error or "unavailable")
        return self._embed(
            self._tokenizer, self._torch, self._device, texts, self._encoder
        )

    # ---------------- трассировка ----------------
    def link_commit_to_task(
        self,
        commit_repr: str,
        commit_files: Sequence[str],
        candidates: Sequence[Dict],
        threshold: Optional[float] = None,
    ) -> Dict:
        """Подбирает задачу для коммита.

        candidates — список словарей с ключами `id` и `description`.
        Возвращает лучшего кандидата и полный отсортированный список
        оценок. Если порог не взят, `task_id` равен None: решение
        остаётся за человеком, а не за моделью.
        """
        threshold = (
            settings.CODE_MODEL_TRACE_THRESHOLD if threshold is None else threshold
        )
        if not candidates:
            return {
                "task_id": None,
                "confidence": 0.0,
                "threshold": threshold,
                "all_scores": [],
                "reason": "no_candidates",
            }

        commit_emb = self.embed([commit_repr])
        task_texts = [c.get("description") or "" for c in candidates]
        task_embs = self.embed(task_texts)

        torch = self._torch
        # commit_emb — (1, 768), task_embs — (N, 768). Косинус считается
        # по последней оси, поэтому результат уже имеет длину N.
        sims = torch.nn.functional.cosine_similarity(commit_emb, task_embs)
        sims = sims.reshape(-1).tolist()

        scores = []
        for candidate, sim in zip(candidates, sims):
            overlap = file_overlap_score(commit_files, candidate.get("description") or "")
            scores.append(
                {
                    "task_id": candidate.get("id"),
                    "score": round(combined_score(float(sim), overlap), 4),
                    "semantic": round(float(sim), 4),
                    "file_overlap": round(overlap, 4),
                }
            )

        scores.sort(key=lambda s: s["score"], reverse=True)
        best = scores[0]
        return {
            "task_id": best["task_id"] if best["score"] >= threshold else None,
            "confidence": best["score"],
            "semantic": best["semantic"],
            "file_overlap": best["file_overlap"],
            "threshold": threshold,
            "all_scores": scores[:10],
        }


encoder = EncoderService()


# ---------------------------------------------------------------------------
# Модель типов коммитов (лабораторная работа №3)
# ---------------------------------------------------------------------------


logger = logging.getLogger(__name__)

# Порядок классов задан в ноутбуке №3 и зашит в веса головы.
COMMIT_TYPES = ["bugfix", "feature", "refactor", "docs", "test", "chore"]





def validate_classifier_state(state_dict: Dict) -> tuple:
    """Проверяет чекпоинт головы и возвращает (вход, число классов).

    Вынесено отдельно от сборки модели, чтобы проверку можно было
    прогнать без установленного torch.

    Размеры берутся из самих ключей, а не задаются константой:
        classifier.0.weight — (скрытый, вход)  = (256, 768)
        classifier.3.weight — (классы, скрытый) = (6, 256)
    Число классов живёт во втором слое. Раньше здесь читался первый, и
    проверка рапортовала о «256 классах».

    Если чекпоинт переобучали с дополнительными структурными признаками
    (задача №3 из «исправлений»), вход перестаёт быть 768-мерным. Такое
    должно проходить здесь и падать позже, на сверке с кодировщиком,
    с понятным сообщением — а не с молчаливой ошибкой формы.
    """
    first = state_dict.get("classifier.0.weight")
    if first is None:
        raise ModelUnavailable(
            "В чекпоинте классификатора нет слоя classifier.0.weight — "
            "структура файла не совпадает с ожидаемой"
        )

    last_key = "classifier.3.weight"
    last = state_dict.get(last_key)
    if last is None:
        # Ищем последний Linear в последовательности, а не по имени:
        # при переобучении число скрытых слоёв может измениться
        candidates = sorted(
            (k for k in state_dict if k.endswith(".weight")
             and k.startswith("classifier.")),
            key=lambda k: int(k.split(".")[1]),
        )
        if not candidates:
            raise ModelUnavailable(
                "В чекпоинте классификатора нет ни одного слоя classifier"
            )
        last_key = candidates[-1]
        last = state_dict[last_key]

    in_features = int(first.shape[1])
    num_classes = int(last.shape[0])

    if num_classes != len(COMMIT_TYPES):
        raise ModelUnavailable(
            f"Классификатор обучен на {num_classes} классах, "
            f"а список типов содержит {len(COMMIT_TYPES)}. "
            "Нужно переобучение или правка COMMIT_TYPES."
        )

    return in_features, num_classes


class TypeClassifierService:
    """Ленивая загрузка головы классификатора и определение типа."""

    def __init__(self, encoder) -> None:
        self._encoder = encoder
        self._lock = threading.Lock()
        self._loaded = False
        self._classifier = None
        self._torch = None
        self._in_features: Optional[int] = None
        self._device = "cpu"
        self._error: Optional[str] = None

    # ---------------- состояние ----------------
    def artifacts(self) -> Dict:
        weights = artifact_path(KEY_TYPE_CLASSIFIER)
        return {
            "classifier": str(weights),
            "classifier_ready": weights.exists(),
        }

    def status(self) -> Dict:
        art = self.artifacts()
        enabled = is_enabled(KEY_TYPE_CLASSIFIER)
        encoder_on = is_enabled(KEY_ENCODER)

        reason = None
        if not enabled:
            reason = "disabled"
        elif not encoder_on:
            # Классификатор работает поверх кодировщика: включать его
            # при выключенном кодировщике бессмысленно, и сервер такое
            # отклоняет.
            reason = "encoder_disabled"
        elif not art["classifier_ready"]:
            reason = "classifier_missing"

        return {
            "enabled": enabled,
            "available": enabled and encoder_on and art["classifier_ready"],
            "reason": reason,
            "loaded": self._loaded,
            "loaded_flag": self._classifier is not None,
            "device": self._device,
            "error": self._error,
            "in_features": self._in_features,
            "commit_types": COMMIT_TYPES,
            "artifacts": art,
        }

    # ---------------- загрузка ----------------
    def _build_classifier(self, torch, state_dict: Dict):
        import torch.nn as nn

        in_features, num_classes = validate_classifier_state(state_dict)

        class CommitTypeClassifier(nn.Module):
            def __init__(self, embedding_dim, classes):
                super().__init__()
                self.classifier = nn.Sequential(
                    nn.Linear(embedding_dim, 256),
                    nn.ReLU(),
                    nn.Dropout(0.2),
                    nn.Linear(256, classes),
                )

            def forward(self, embedding):
                return self.classifier(embedding)

        model = CommitTypeClassifier(in_features, num_classes)
        model.load_state_dict(state_dict)
        return model, in_features

    def load(self) -> bool:
        """Загружает голову. Повторный вызов ничего не делает.

        Кодировщик при этом поднимается, если ещё не поднят: без него
        голову не на чем считать.
        """
        if self._loaded:
            return True

        with self._lock:
            if self._loaded:
                return True

            st = self.status()
            if not st["available"]:
                self._error = st["reason"]
                logger.info("Классификатор типов недоступен: %s", st["reason"])
                return False

            if not self._encoder.load():
                self._error = self._encoder.status().get("reason") or "encoder_failed"
                return False

            head_path = artifact_path(KEY_TYPE_CLASSIFIER)
            device = self._encoder.device()

            try:
                import torch

                head_state = torch.load(
                    str(head_path), map_location="cpu", weights_only=True
                )
                classifier, in_features = self._build_classifier(torch, head_state)
                classifier.eval()
                classifier.to(device)

                expected = self._encoder.embedding_dim()
                if expected is not None and expected != in_features:
                    raise ModelUnavailable(
                        f"Кодировщик даёт {expected}-мерный вектор, "
                        f"а классификатор ждёт {in_features}. Чекпоинты несовместимы."
                    )
            except ModelUnavailable as exc:
                self._error = str(exc)
                logger.warning("Классификатор типов не загружен: %s", exc)
                return False
            except Exception as exc:  # noqa: BLE001 — деградация вместо падения
                self._error = f"{type(exc).__name__}: {exc}"
                logger.exception("Ошибка загрузки классификатора типов")
                return False

            self._torch = torch
            self._classifier = classifier
            self._in_features = in_features
            self._device = device
            self._error = None
            self._loaded = True

            logger.info(
                "Классификатор типов загружен на %s (вход %d)",
                device, in_features,
            )
            return True

    def unload(self) -> None:
        """Выгружает голову. Кодировщик при этом остаётся в памяти:
        он нужен трассировке, и весит несопоставимо больше."""
        import gc

        with self._lock:
            self._classifier = None
            self._torch = None
            self._loaded = False
            self._in_features = None
            self._device = "cpu"
            self._error = None
            gc.collect()

    # ---------------- вывод ----------------
    def classify_commit(self, commit_repr: str) -> Dict:
        """Определяет тип коммита и уверенность."""
        # Голова могла не загрузиться — администратор выключил
        # классификатор типов. Проверка до обращения к кодировщику:
        # иначе выключенная модель всё равно подняла бы кодировщик
        # на гигабайт памяти.
        if not is_enabled(KEY_TYPE_CLASSIFIER):
            return {"commit_type": None, "confidence": 0.0, "reason": "disabled"}
        if self._classifier is None:
            if not self.load():
                return {
                    "commit_type": None,
                    "confidence": 0.0,
                    "reason": self._error or "unavailable",
                }
            if self._classifier is None:
                return {"commit_type": None, "confidence": 0.0, "reason": "disabled"}

        emb = self._encoder.embed([commit_repr])
        torch = self._torch
        with torch.inference_mode():
            probs = torch.softmax(self._classifier(emb), dim=1).squeeze()
        values = probs.tolist()
        best = int(max(range(len(values)), key=lambda i: values[i]))
        return {
            "commit_type": COMMIT_TYPES[best],
            "confidence": round(float(values[best]), 4),
            "all_scores": {t: round(float(v), 4) for t, v in zip(COMMIT_TYPES, values)},
        }


type_classifier = TypeClassifierService(encoder)


# ---------------------------------------------------------------------------
# Маршруты
# ---------------------------------------------------------------------------

# --------------------------------------------------------------------- #
# Маршруты
# --------------------------------------------------------------------- #
class TaskAnalysisRequest(BaseModel):
    title: str
    description: Optional[str] = None


class TaskAnalysisResponse(BaseModel):
    suggested_category: str
    suggested_priority: int
    subtasks: List[str]


@router.post("/analyze-task", response_model=TaskAnalysisResponse)
async def analyze_task_endpoint(request: TaskAnalysisRequest):
    """Разбор текста задачи перед созданием.

    Это разбор по ключевым словам, а не нейросеть: он предлагает
    приоритет и примерный разбор на подзадачи, а решение остаётся за
    человеком.
    """
    return await nlp_engine.analyze_task(request.title, request.description)


# --------------------------------------------------------------------- #
# Оценка прогресса задачи (лабораторная работа №2)
# --------------------------------------------------------------------- #
class ProgressComponents(BaseModel):
    structural: float
    volume: float
    semantic: float
    # Прицельность: 1.0 — работа шла по названным в задаче файлах,
    # 0.5 — ни одного. Множитель объёма, а не самостоятельный балл.
    targeting: float = 1.0
    # Объём, помноженный на прицельность, — то, из чего считается
    # прогресс при отсутствии подзадач.
    completion: float = 0.0


class ProgressWeights(BaseModel):
    structural: float = 0.6
    completion: float = 0.4


class ProgressInputs(BaseModel):
    commits: int
    additions: int
    deletions: int
    lines_changed: int
    expected_volume: int
    expected_volume_source: str
    expected_volume_sample: int
    # Наблюдаемый перцентиль по выборке и вес, с которым он вошёл
    # в оценку (остальное — априорное значение из настроек).
    expected_volume_raw: Optional[int] = None
    expected_volume_weight: float = 0.0
    subtasks_total: int
    subtasks_done: int
    files_touched: int = 0
    files_mentioned: int = 0
    files_matched: int = 0
    # Сколько связей с коммитами отклонено и не попало в прогресс:
    # человек отклонил их, и модель тут ни при чём.
    dropped_links: int = 0


class ProgressDay(BaseModel):
    date: str
    volume_ratio: float


class ProgressResponse(BaseModel):
    available: bool
    reason: Optional[str] = None
    task_id: Optional[int] = None
    percent: float = 0.0
    confidence: str = "low"
    confidence_reasons: List[str] = []
    components: Optional[ProgressComponents] = None
    weights: Optional[ProgressWeights] = None
    inputs: Optional[ProgressInputs] = None
    last_commit_at: Optional[str] = None
    days_since_last_commit: Optional[int] = None
    history: List[ProgressDay] = []


@router.get("/task/{task_id}/progress", response_model=ProgressResponse)
async def task_progress(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Оценка готовности задачи по её Git-активности.

    Считается модулем правил, поэтому работает и когда модели
    выключены. В комментарии к модели прогресса сказано, почему
    объём в строках нельзя напрямую считать трудозатратами.
    """
    from app.core.roles import Permission
    from app.tasks.api import get_member_and_check_permission

    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Права проверяются по проекту задачи, а не по самой задаче:
    # иначе участник чужого проекта увидел бы прогресс по её задачам.
    await get_member_and_check_permission(
        db, current_user.id, task.project_id, Permission.TASK_VIEW
    )

    return await get_task_progress(db, task)


# --------------------------------------------------------------------- #
# Служебные маршруты моделей: проверка развёртывания и ручной запуск
# --------------------------------------------------------------------- #
class CommitCandidate(BaseModel):
    id: int
    description: str = ""


class TraceRequest(BaseModel):
    diff_text: str = ""
    commit_message: str = ""
    files: List[str] = []
    candidates: List[CommitCandidate] = []
    threshold: Optional[float] = None


class TraceResponse(BaseModel):
    available: bool = True
    task_id: Optional[int] = None
    confidence: float = 0.0
    semantic: float = 0.0
    file_overlap: float = 0.0
    threshold: float = 0.0
    all_scores: List[Dict] = []
    reason: Optional[str] = None


class CommitTypeResponse(BaseModel):
    available: bool = True
    commit_type: Optional[str] = None
    confidence: float = 0.0
    all_scores: Dict[str, float] = {}
    reason: Optional[str] = None


class ModelStatusResponse(BaseModel):
    enabled: bool
    available: bool
    reason: Optional[str] = None
    loaded: bool
    device: str
    error: Optional[str] = None
    commit_types: List[str] = []
    trace_threshold: float = 0.0
    artifacts: Dict = {}


def _unavailable(reason: str, model_cls):
    return model_cls(available=False, reason=reason)


def combined_status() -> dict:
    """Сводное состояние обеих моделей.

    Моделей две, а смотрит на них одно окно в панели администратора
    и один диагностический маршрут. Поэтому сводка собирается здесь,
    а не размазывается по потребителям: каждая модель честно отвечает
    за своё, сводка отвечает за картину целиком.

    Ключи `encoder_loaded` и `classifier_loaded` оставлены как были:
    на них смотрит панель администратора.
    """
    enc = encoder.status()
    cls = type_classifier.status()

    # Общая причина недоступности берётся от кодировщика: пока его
    # нет, классификатор всё равно не поедет, и показывать причину
    # про его веса было бы вводить в заблуждение.
    return {
        "enabled": enc["enabled"],
        "available": enc["available"],
        "reason": enc["reason"] or cls["reason"],
        "loaded": enc["loaded"],
        "device": enc["device"],
        "error": enc["error"] or cls["error"],
        "commit_types": cls["commit_types"],
        "trace_threshold": enc["trace_threshold"],
        "encoder_loaded": enc["loaded_flag"],
        "classifier_loaded": cls["loaded_flag"],
        "type_classifier_enabled": cls["enabled"],
        "artifacts": {**enc["artifacts"], **cls["artifacts"]},
    }


@router.get("/code-model/status", response_model=ModelStatusResponse)
async def code_model_status():
    """Готовность моделей: какие файлы на месте и загружена ли модель.

    Нужен для проверки развёртывания: без него не видно, что модель
    молча не работает из-за отсутствующего словаря.
    """
    return combined_status()


@router.post("/code-model/load", response_model=ModelStatusResponse)
async def code_model_load():
    """Прогревает модели заранее.

    Первый вызов занимает несколько секунд на чтение весов, поэтому
    полезно вызвать его при старте, а не в момент первого запроса.
    Кодировщик загружается всегда, классификатор — только если он
    включён: выключенная модель не должна подниматься вместе с ним.
    """
    encoder.load()
    if type_classifier.status()["enabled"]:
        type_classifier.load()
    return combined_status()


@router.post("/code-model/trace", response_model=TraceResponse)
async def trace_commit(request: TraceRequest):
    """Подбор задачи для коммита по смыслу изменений."""
    if not encoder.load():
        return _unavailable(encoder.status()["reason"] or "unavailable", TraceResponse)

    try:
        result = encoder.link_commit_to_task(
            commit_repr=build_commit_representation(
                request.diff_text, request.commit_message),
            commit_files=request.files,
            candidates=[c.model_dump() for c in request.candidates],
            threshold=request.threshold,
        )
    except ModelUnavailable as exc:
        return _unavailable(str(exc), TraceResponse)

    return TraceResponse(**result)


@router.post("/code-model/commit-type", response_model=CommitTypeResponse)
async def classify_commit_type(request: TraceRequest):
    """Определение типа коммита: bugfix, feature, refactor, docs, test, chore."""
    if not type_classifier.load():
        status = type_classifier.status()
        return _unavailable(
            status["reason"] or status.get("error") or "unavailable",
            CommitTypeResponse,
        )

    try:
        result = type_classifier.classify_commit(
            build_commit_representation(request.diff_text, request.commit_message)
        )
    except ModelUnavailable as exc:
        return _unavailable(str(exc), CommitTypeResponse)

    return CommitTypeResponse(**result)
