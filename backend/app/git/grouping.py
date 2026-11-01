"""Группировка коммитов задачи и отношения между ними (ЛР №2).

Модуль переносит логику версии 3 ноутбука в приложение без pandas,
networkx и sklearn: в рабочем образе этих библиотек нет. Поэтому
агломеративное дробление больших групп и максимальное остовное дерево
реализованы небольшими функциями на чистом Python. Это тот же алгоритм
по смыслу, а не «похожая эвристика»:

* кандидаты — все пары коммитов с комплексной близостью выше порога;
* группа — связная компонента рёбер с уверенностью выше порога группы;
* большие компоненты дробятся average-linkage до MAX_GROUP;
* для графа группы выбирается максимальное остовное дерево, полный
  список рёбер остаётся в базе для аудита.

Группа — это предложение. Она не считается подтверждённой, пока человек
не нажал «Подтвердить». Название строится шаблоном (доминирующий тип +
область), а не генеративной моделью, и может быть переименовано.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.git.models import (
    Commit,
    CommitFile,
    CommitGroup,
    CommitGroupMember,
    CommitRelation,
    TaskCommitGrouping,
    TaskGitLink,
)

logger = logging.getLogger(__name__)

ALGORITHM_VERSION = "lr2-v3-app-1"

RELATION_TYPES = ("related", "extends", "fixes", "tests")

TYPE_TITLE = {
    "feature": "Реализация",
    "bugfix": "Исправление",
    "test": "Тесты",
    "docs": "Документация",
    "refactor": "Рефакторинг",
    "chore": "Сопровождение",
}
_TITLE_ORDER = ["feature", "bugfix", "refactor", "test", "docs", "chore"]

_NOISE_NAMES = {
    "cargo.lock",
    "package-lock.json",
    "yarn.lock",
    "go.sum",
    "composer.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
}
_NOISE_PARTS = {
    "coverage",
    "node_modules",
    "venv",
    ".venv",
    "build",
    "target",
    "vendor",
    "__pycache__",
    ".next",
    "dist",
}

_TYPE_PREFIX = {
    "fix": "bugfix",
    "bugfix": "bugfix",
    "hotfix": "bugfix",
    "feat": "feature",
    "feature": "feature",
    "refactor": "refactor",
    "doc": "docs",
    "docs": "docs",
    "documentation": "docs",
    "test": "test",
    "tests": "test",
    "testing": "test",
    "chore": "chore",
    "build": "chore",
    "ci": "chore",
    "style": "chore",
    "perf": "chore",
    "revert": "chore",
}
_PREFIX_RE = re.compile(r"^\s*([a-zA-Z]+)\s*(?:\([^)]*\))?\s*:\s*")
_MERGE_RE = re.compile(r"^\s*merge\s+(pull request|branch|remote-tracking)", re.IGNORECASE)
_DEP_RE = re.compile(r"\bbump\w*\b|\bup-?grade\b|\bdown-?grade\b", re.IGNORECASE)
_NARROW = [
    ("bugfix", r"\bfix(es|ed|ing)?\b|\bbugs?\b|\bresolv\w+\b"),
    ("refactor", r"\brefactor\w*\b|\bclean[\s-]?up\b|\brename\b|\bextract\b"),
    ("docs", r"\bdocs?\b|\breadme\b|\bchangelog\b|\btypos?\b"),
    ("test", r"\btests?\b|\btesting\b|\bspecs?\b"),
]
_WIDE = [
    ("bugfix", r"\bbug\w*\b"),
    ("feature", r"\bfeat\w*\b|\badd(ed|ing|s)?\b|\bimplement\w*\b|\bsupport\b"),
]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


@dataclass
class GroupFeatures:
    """Признаки коммитов одной задачи."""

    ids: List[int]
    uids: List[str]
    msgs: List[str]
    types: List[str]
    files: List[Set[str]]
    dates: List[Optional[datetime]]
    emb_repr: List[List[float]]
    emb_msg: List[List[float]]
    type_sources: List[str]
    min_rule_aff: float = 0.55

    W_SEM = 0.55
    W_MSG = 0.15
    W_FILES = 0.30

    RULES = {
        ("feature", "test"): "tests",
        ("bugfix", "test"): "tests",
        ("refactor", "test"): "tests",
        ("feature", "bugfix"): "fixes",
        ("refactor", "bugfix"): "fixes",
        ("bugfix", "bugfix"): "fixes",
        ("feature", "feature"): "extends",
        ("feature", "refactor"): "extends",
        ("refactor", "feature"): "extends",
        ("refactor", "refactor"): "extends",
    }

    def __post_init__(self) -> None:
        lengths = {
            len(self.ids),
            len(self.uids),
            len(self.msgs),
            len(self.types),
            len(self.files),
            len(self.dates),
            len(self.emb_repr),
            len(self.emb_msg),
            len(self.type_sources),
        }
        if len(lengths) != 1:
            raise ValueError("Все признаки GroupFeatures должны быть одной длины")

    def affinity(
        self,
        i: int,
        j: int,
        use_sem: bool = True,
        use_msg: bool = True,
        use_files: bool = True,
    ) -> float:
        score, weight = 0.0, 0.0
        if use_sem:
            score += self.W_SEM * _dot(self.emb_repr[i], self.emb_repr[j])
            weight += self.W_SEM
        if use_msg:
            score += self.W_MSG * _dot(self.emb_msg[i], self.emb_msg[j])
            weight += self.W_MSG
        if use_files:
            inter = len(self.files[i] & self.files[j])
            union = len(self.files[i] | self.files[j])
            score += self.W_FILES * (inter / union if union else 0.0)
            weight += self.W_FILES
        return score / weight if weight else 0.0

    def relation(self, i: int, j: int, direction: str = "known") -> Tuple[str, Dict, List[str]]:
        sem = _dot(self.emb_repr[i], self.emb_repr[j])
        msg = _dot(self.emb_msg[i], self.emb_msg[j])
        inter = len(self.files[i] & self.files[j])
        union = len(self.files[i] | self.files[j])
        file_overlap = inter / union if union else 0.0
        ti, tj = self.types[i], self.types[j]
        aff = self.affinity(i, j)
        matched = self.RULES.get((ti, tj))

        evidence = [
            f"семантика диффов {sem:.2f}",
            f"сходство сообщений {msg:.2f}",
        ]
        if inter:
            evidence.append(f"общие файлы {inter} шт.")
        if matched and aff < self.min_rule_aff:
            evidence.append(
                f"близость {aff:.2f} < {self.min_rule_aff:.2f}: правило не применено"
            )
            matched = None
        if matched in ("fixes", "tests") and direction != "known":
            evidence.append("направление неизвестно: тип не уточняется")
            matched = None
        if matched:
            evidence.append(f"типы {ti}→{tj}")
        if self.type_sources[i] != "lr3" or self.type_sources[j] != "lr3":
            evidence.append("тип(ы) из эвристики")

        relation = matched or "related"
        features = {
            "sem": round(sem, 3),
            "msg": round(msg, 3),
            "files": round(file_overlap, 3),
            "rule": matched or "",
        }
        return relation, features, evidence


def _short_uid(uid: str) -> str:
    s = str(uid)
    if "@" in s:
        s = s.split("@", 1)[1]
    return s[:8]


def _type_penalty(type_source: str) -> float:
    return {"lr3": 1.0, "mixed": 0.95, "heuristic": 0.88}.get(type_source, 0.85)


def commit_subject(message: str) -> str:
    for line in str(message or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def auto_label_type(message: str) -> str:
    """Эвристика типа по теме коммита, как в ЛР №3."""
    subject = commit_subject(message)
    low = subject.lower()
    if _MERGE_RE.match(subject):
        return "chore"
    match = _PREFIX_RE.match(low)
    if match and match.group(1) in _TYPE_PREFIX:
        return _TYPE_PREFIX[match.group(1)]
    for kind, pattern in _NARROW:
        if re.search(pattern, low):
            return kind
    if _DEP_RE.search(low):
        return "chore"
    for kind, pattern in _WIDE:
        if re.search(pattern, low):
            return kind
    return "chore"


def is_merge_or_dependency(message: str) -> bool:
    subject = commit_subject(message)
    return bool(_MERGE_RE.match(subject) or _DEP_RE.search(subject))


def _clean_files(files: Iterable[str]) -> List[str]:
    out: List[str] = []
    for value in files:
        path = str(value).replace("\\", "/").strip("/")
        low = path.lower()
        if not path:
            continue
        if os.path.basename(low) in _NOISE_NAMES:
            continue
        if any(part in _NOISE_PARTS for part in low.split("/")):
            continue
        if low.endswith((".min.js", ".min.css", ".map")):
            continue
        out.append(path)
    return out


def _common_area(paths: Iterable[str]) -> str:
    """Общий каталог файлов или самый частый каталог второго уровня."""
    parts = [PurePosixPath(path).parts for path in paths if path]
    dirs = ["/".join(part[:-1]) for part in parts if len(part) > 1]
    if not dirs:
        return ""
    split = [d.split("/") for d in dirs]
    common: List[str] = []
    for values in zip(*split):
        if len(set(values)) != 1:
            break
        common.append(values[0])
    if common:
        area = "/".join(common)
        return area if len(area) <= 40 else "…" + area[-39:]
    top = Counter("/".join(parts[:2]) for parts in split if len(parts) >= 2)
    return top.most_common(1)[0][0] if top else ""


def _group_area(F: GroupFeatures, members: Sequence[int]) -> str:
    files: List[str] = []
    for index in members:
        files.extend(_clean_files(F.files[index]))
    if files:
        area = _common_area(files)
        if area:
            return area
    center = (
        max(members, key=lambda i: sum(F.affinity(i, j) for j in members if j != i))
        if len(members) > 1
        else members[0]
    )
    lines = (F.msgs[center] or "").strip().splitlines()
    return lines[0][:40] if lines else "без области"


def group_title_parts(F: GroupFeatures, members: Sequence[int]) -> Tuple[str, str]:
    """Возвращает (доминирующий тип, область). Название собирает API/UI."""
    types = Counter(F.types[i] for i in members)
    if not types:
        return "chore", "без области"
    dominant = sorted(
        types,
        key=lambda kind: (
            -types[kind],
            _TITLE_ORDER.index(kind) if kind in _TITLE_ORDER else 99,
        ),
    )[0]
    return dominant, _group_area(F, members)


def group_title(F: GroupFeatures, members: Sequence[int]) -> str:
    dominant, area = group_title_parts(F, members)
    return f"{TYPE_TITLE.get(dominant, dominant)} — {area}"


def group_description(F: GroupFeatures, members: Sequence[int]) -> str:
    type_word = {
        "feature": "реализация",
        "bugfix": "исправление",
        "test": "тесты",
        "docs": "документация",
        "refactor": "рефакторинг",
        "chore": "обслуживание",
    }
    types = Counter(F.types[i] for i in members)
    center = (
        max(members, key=lambda i: sum(F.affinity(i, j) for j in members if j != i))
        if len(members) > 1
        else members[0]
    )
    center_text = f"центр — «{F.msgs[center][:60]}»"
    files: Set[str] = set()
    for index in members:
        files.update(_clean_files(F.files[index])[:3])
    composition = " + ".join(
        f"{count}× {type_word.get(kind, kind)}" for kind, count in types.most_common()
    )
    files_text = ", файлы: " + ", ".join(sorted(files)[:4]) if files else ""
    return f"{composition}; {center_text}{files_text}"


def build_edges(
    F: GroupFeatures, indexes: Sequence[int], threshold: float
) -> List[Dict]:
    order = sorted(
        indexes,
        key=lambda i: (F.dates[i] is None, F.dates[i] or datetime.min.replace(tzinfo=timezone.utc)),
    )
    edges: List[Dict] = []
    for a in range(len(order)):
        for b in range(a + 1, len(order)):
            i, j = order[a], order[b]
            affinity = F.affinity(i, j)
            if affinity < threshold:
                continue
            di, dj = F.dates[i], F.dates[j]
            if di is None or dj is None:
                direction = "unknown"
            else:
                direction = "known"
                if dj < di:
                    i, j = j, i
            relation, features, evidence = F.relation(i, j, direction)
            gap = None
            if direction == "known":
                gap = round((F.dates[j] - F.dates[i]).total_seconds() / 86400, 1)

            confidence = 0.75 * affinity
            confidence += 0.15 * (1.0 if relation != "related" else 0.0)
            confidence += 0.10 * (1.0 if features["files"] > 0.2 else 0.0)
            if direction == "unknown":
                confidence *= 0.9
            source_i, source_j = F.type_sources[i], F.type_sources[j]
            if source_i == "lr3" and source_j == "lr3":
                type_source = "lr3"
            elif source_i == "heuristic" and source_j == "heuristic":
                type_source = "heuristic"
            else:
                type_source = "mixed"
            confidence *= _type_penalty(type_source)
            edges.append(
                {
                    "i": i,
                    "j": j,
                    "source_uid": F.uids[i],
                    "target_uid": F.uids[j],
                    "relation": relation,
                    "direction": direction,
                    "rule": features["rule"],
                    "type_source": type_source,
                    "confidence": round(float(min(1.0, max(0.0, confidence))), 3),
                    "affinity": round(float(affinity), 3),
                    "gap_days": gap,
                    "evidence": "; ".join(evidence),
                }
            )
    return edges


def components_groups(
    F: GroupFeatures, indexes: Sequence[int], edges: Sequence[Dict], threshold: float
) -> Tuple[List[List[int]], List[int]]:
    parent = {index: index for index in indexes}

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for edge in edges:
        if edge["confidence"] < threshold:
            continue
        left, right = find(edge["i"]), find(edge["j"])
        if left != right:
            parent[left] = right

    components: Dict[int, List[int]] = {}
    for index in indexes:
        components.setdefault(find(index), []).append(index)
    groups = sorted(
        [sorted(members) for members in components.values() if len(members) >= 2],
        key=len,
        reverse=True,
    )
    grouped = {index for group in groups for index in group}
    return groups, [index for index in indexes if index not in grouped]


def _average_linkage_two(F: GroupFeatures, members: Sequence[int]) -> Optional[Tuple[List[int], List[int]]]:
    """Average-linkage до двух кластеров без sklearn.

    На каждом шаге сливаются кластеры с наибольшей средней близостью.
    Это ровно то, что делает AgglomerativeClustering(metric='precomputed',
    linkage='average', n_clusters=2), только без внешней зависимости.
    """
    clusters: List[List[int]] = [[index] for index in members]
    while len(clusters) > 2:
        best: Optional[Tuple[int, int, float]] = None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                affinity = _mean(
                    F.affinity(i, j) for i in clusters[a] for j in clusters[b]
                )
                if best is None or affinity > best[2]:
                    best = (a, b, affinity)
        if best is None:
            return None
        a, b, _ = best
        clusters[a] = clusters[a] + clusters[b]
        clusters.pop(b)
    if len(clusters) != 2:
        return None
    first, second = [sorted(cluster) for cluster in clusters]
    return first, second


def _split_two(F: GroupFeatures, members: Sequence[int]) -> Tuple[Optional[List[List[int]]], List[int]]:
    if len(members) <= 2:
        return None, []
    parts = _average_linkage_two(F, members)
    if not parts:
        return None, []
    first, second = parts
    if min(len(first), len(second)) < 2:
        big, small = sorted(parts, key=len, reverse=True)
        return [big], small
    return [first, second], []


def cap_group_sizes(
    F: GroupFeatures,
    indexes: Sequence[int],
    groups: Sequence[Sequence[int]],
    max_size: int,
) -> Tuple[List[List[int]], List[int], List[List[int]]]:
    if max_size < 2:
        raise ValueError("max_size должен быть не меньше 2")
    result: List[List[int]] = []
    oversized: List[List[int]] = []
    dropped: List[int] = []
    stack = [sorted(group) for group in groups if len(group) >= 2]
    while stack:
        group = stack.pop()
        if len(group) <= max_size:
            result.append(sorted(group))
            continue
        parts, small = _split_two(F, group)
        if not parts:
            result.append(sorted(group))
            oversized.append(sorted(group))
            continue
        dropped.extend(small)
        stack.extend(parts)
    result = sorted(result, key=lambda group: (-len(group), min(group)))
    grouped = {index for group in result for index in group}
    ungrouped = [index for index in indexes if index not in grouped]
    return result, ungrouped, oversized


def _edge_map(edges: Sequence[Dict]) -> Dict[Tuple[int, int], Dict]:
    best: Dict[Tuple[int, int], Dict] = {}
    for edge in edges:
        key = (min(edge["i"], edge["j"]), max(edge["i"], edge["j"]))
        if key not in best or edge["confidence"] > best[key]["confidence"]:
            best[key] = edge
    return best


def display_graph_edges(
    F: GroupFeatures, members: Sequence[int], edges: Sequence[Dict]
) -> List[Dict]:
    """Максимальное остовное дерево группы (не более n−1 рёбер)."""
    member_set = set(members)
    candidates = [
        edge
        for edge in edges
        if edge["i"] in member_set and edge["j"] in member_set
    ]
    if len(member_set) < 2 or not candidates:
        return []

    parent = {index: index for index in member_set}

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    tree: List[Dict] = []
    for edge in sorted(
        _edge_map(candidates).values(),
        key=lambda item: (-item["confidence"], item["i"], item["j"]),
    ):
        left, right = find(edge["i"]), find(edge["j"])
        if left == right:
            continue
        parent[left] = right
        tree.append(edge)
    return sorted(tree, key=lambda item: (-item["confidence"], item["i"], item["j"]))


def _lexical_embeddings(texts: Sequence[str]) -> List[List[float]]:
    """Резервные векторы, если нейросеть недоступна.

    Это не замена модели и не «тихая подмена»: в ответе API есть
    model_used='lexical'. Но группировка остаётся рабочей, а не падает
    вместе с torch.
    """
    tokenized = [re.findall(r"[\w./-]+", text.lower()) for text in texts]
    document_frequency: Counter = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))
    total = max(1, len(tokenized))
    vocabulary = {token: index for index, token in enumerate(sorted(document_frequency))}
    if not vocabulary:
        return [[0.0] * 8 for _ in texts]
    vectors: List[List[float]] = []
    for tokens in tokenized:
        counts = Counter(tokens)
        vector = [0.0] * len(vocabulary)
        for token, count in counts.items():
            tf = 1.0 + math.log(count)
            idf = math.log((1.0 + total) / (1.0 + document_frequency[token])) + 1.0
            vector[vocabulary[token]] = tf * idf
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        vectors.append([value / norm for value in vector])
    return vectors


async def _embed_texts(texts: Sequence[str]) -> Tuple[List[List[float]], str]:
    if not texts:
        return [], "lexical"
    if settings.CODE_MODEL_ENABLED:
        try:
            from app.ai.api import encoder

            def run() -> List[List[float]]:
                tensor = encoder.embed(list(texts))
                return tensor.float().cpu().tolist()

            # Инференс на CPU занимает секунды и не должен блокировать
            # цикл событий: иначе на время группировки встают все
            # остальные запросы.
            return await asyncio.to_thread(run), "encoder"
        except Exception as exc:  # noqa: BLE001 — деградация вместо падения
            logger.warning("Эмбеддинги для группировки недоступны: %s", exc)
    return _lexical_embeddings(texts), "lexical"


def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _load_commit_rows(db: AsyncSession, task_id: int):
    links = (
        await db.execute(
            select(TaskGitLink).where(
                TaskGitLink.task_id == task_id,
                TaskGitLink.link_type == "commit",
                TaskGitLink.status.notin_(("proposed", "rejected")),
            )
        )
    ).scalars().all()
    commit_ids = [link.target_id for link in links]
    if not commit_ids:
        return [], {}
    commits = (
        await db.execute(select(Commit).where(Commit.id.in_(commit_ids)))
    ).scalars().all()
    files: Dict[int, List[CommitFile]] = {}
    for row in (
        await db.execute(select(CommitFile).where(CommitFile.commit_id.in_(commit_ids)))
    ).scalars().all():
        files.setdefault(row.commit_id, []).append(row)
    commits.sort(
        key=lambda c: (
            c.timestamp is None,
            _as_aware(c.timestamp) or datetime.min.replace(tzinfo=timezone.utc),
            c.id,
        )
    )
    return commits, files


async def build_task_features(db: AsyncSession, task_id: int) -> Tuple[GroupFeatures, str]:
    """Собирает признаки и эмбеддинги подтверждённых коммитов задачи."""
    from app.ai.api import build_commit_representation
    from app.git.patches import build_commit_diff

    commits, files_by_commit = await _load_commit_rows(db, task_id)
    ids: List[int] = []
    uids: List[str] = []
    messages: List[str] = []
    types: List[str] = []
    type_sources: List[str] = []
    file_sets: List[Set[str]] = []
    dates: List[Optional[datetime]] = []
    representations: List[str] = []

    for commit in commits:
        files = files_by_commit.get(commit.id, [])
        message = commit.message or ""
        # Merge-коммиты и обновления зависимостей не содержат работы
        # разработчика; в ноутбуке №2 они исключаются из группировки.
        # В карточке они остаются как «вне групп».
        if is_merge_or_dependency(message):
            continue
        kind = commit.commit_type or auto_label_type(message)
        ids.append(commit.id)
        uids.append(commit.sha)
        messages.append(message)
        types.append(kind)
        type_sources.append("lr3" if commit.commit_type else "heuristic")
        file_sets.append({row.path for row in files if row.path})
        dates.append(_as_aware(commit.timestamp))
        representations.append(
            build_commit_representation(build_commit_diff(files), message)
        )

    if not ids:
        return (
            GroupFeatures(
                ids=[], uids=[], msgs=[], types=[], files=[], dates=[],
                emb_repr=[], emb_msg=[], type_sources=[],
            ),
            "lexical",
        )

    combined, model_used = await _embed_texts(representations + messages)
    count = len(ids)
    return (
        GroupFeatures(
            ids=ids,
            uids=uids,
            msgs=messages,
            types=types,
            files=file_sets,
            dates=dates,
            emb_repr=combined[:count],
            emb_msg=combined[count : count * 2],
            type_sources=type_sources,
            min_rule_aff=settings.GIT_COMMIT_GROUP_MIN_RULE_AFFINITY,
        ),
        model_used,
    )


async def _clear_group_data(db: AsyncSession, task_id: int) -> None:
    """Удаляет группы и связи, но оставляет строку состояния.

    Строку состояния нельзя удалять bulk-запросом, если она уже
    загружена в сессию: объект останется в identity map, и повторная
    вставка того же task_id упадёт с конфликтом ключа.
    """
    await db.execute(delete(CommitRelation).where(CommitRelation.task_id == task_id))
    await db.execute(
        delete(CommitGroupMember).where(CommitGroupMember.task_id == task_id)
    )
    await db.execute(delete(CommitGroup).where(CommitGroup.task_id == task_id))


async def _delete_grouping_data(db: AsyncSession, task_id: int) -> None:
    await _clear_group_data(db, task_id)
    await db.execute(
        delete(TaskCommitGrouping).where(TaskCommitGrouping.task_id == task_id)
    )


async def invalidate_task_grouping(db: AsyncSession, task_id: int) -> None:
    """Сбрасывает кэш группировки после изменения состава коммитов."""
    await _delete_grouping_data(db, task_id)


async def invalidate_task_groupings(db: AsyncSession, task_ids: Iterable[int]) -> None:
    ids = list({int(task_id) for task_id in task_ids})
    if not ids:
        return
    await db.execute(delete(CommitRelation).where(CommitRelation.task_id.in_(ids)))
    await db.execute(
        delete(CommitGroupMember).where(CommitGroupMember.task_id.in_(ids))
    )
    await db.execute(delete(CommitGroup).where(CommitGroup.task_id.in_(ids)))
    await db.execute(
        delete(TaskCommitGrouping).where(TaskCommitGrouping.task_id.in_(ids))
    )


async def _persist_groups(
    db: AsyncSession,
    task_id: int,
    F: GroupFeatures,
    groups: Sequence[Sequence[int]],
    edges: Sequence[Dict],
    model_used: str,
    n_commits: Optional[int] = None,
) -> None:
    await _clear_group_data(db, task_id)

    graph_pairs: Set[Tuple[int, int]] = set()
    for position, members in enumerate(groups):
        internal = [
            edge
            for edge in edges
            if edge["i"] in set(members) and edge["j"] in set(members)
        ]
        graph = display_graph_edges(F, members, edges)
        graph_pairs.update(
            (min(edge["i"], edge["j"]), max(edge["i"], edge["j"]))
            for edge in graph
        )
        confidence = (
            round(_mean(edge["confidence"] for edge in internal), 3)
            if internal
            else None
        )
        title_type, title_area = group_title_parts(F, members)
        group = CommitGroup(
            task_id=task_id,
            title=group_title(F, members),
            title_source="template",
            title_type=title_type,
            title_area=title_area,
            description=group_description(F, members),
            rationale=(
                f"внутренние связи: {len(internal)} рёбер, "
                f"средняя уверенность {confidence:.2f}; "
                f"ограничение размера ≤ {settings.GIT_COMMIT_GROUP_MAX_SIZE}"
                if len(members) > 1
                else "единственный коммит"
            ),
            confidence=confidence,
            status="proposed",
            position=position,
            algorithm_version=ALGORITHM_VERSION,
        )
        db.add(group)
        await db.flush()
        for member_position, index in enumerate(sorted(members)):
            db.add(
                CommitGroupMember(
                    task_id=task_id,
                    group_id=group.id,
                    commit_id=F.ids[index],
                    position=member_position,
                )
            )

    for edge in edges:
        db.add(
            CommitRelation(
                task_id=task_id,
                source_commit_id=F.ids[edge["i"]],
                target_commit_id=F.ids[edge["j"]],
                relation_type=edge["relation"],
                confidence=edge["confidence"],
                direction=edge["direction"],
                rule=edge["rule"] or None,
                type_source=edge["type_source"],
                evidence=edge["evidence"],
                status="proposed",
                in_graph=(min(edge["i"], edge["j"]), max(edge["i"], edge["j"]))
                in graph_pairs,
            )
        )

    state = await db.get(TaskCommitGrouping, task_id)
    if state is None:
        state = TaskCommitGrouping(task_id=task_id)
        db.add(state)
    state.status = "done"
    state.algorithm_version = ALGORITHM_VERSION
    state.n_commits = n_commits if n_commits is not None else len(F.ids)
    state.n_groups = len(groups)
    state.n_relations = len(edges)
    state.model_used = model_used
    state.error = None
    state.generated_at = datetime.now(timezone.utc)


async def ensure_task_groups(
    db: AsyncSession, task_id: int, force: bool = False
) -> None:
    """Строит группы, если их ещё нет, и сохраняет их как предложения."""
    if not settings.GIT_COMMIT_GROUPING_ENABLED:
        return

    state = await db.get(TaskCommitGrouping, task_id)
    if state is not None and not force and state.status not in ("error", "empty"):
        return

    commits, _ = await _load_commit_rows(db, task_id)
    if len(commits) < 2:
        if force:
            # Чистим старые группы, но не саму строку состояния:
            # bulk-delete не обновляет identity map, и повторный get()
            # вернул бы уже удалённый объект из кеша сессии.
            await db.execute(
                delete(CommitRelation).where(CommitRelation.task_id == task_id)
            )
            await db.execute(
                delete(CommitGroupMember).where(CommitGroupMember.task_id == task_id)
            )
            await db.execute(
                delete(CommitGroup).where(CommitGroup.task_id == task_id)
            )
        if state is None:
            state = TaskCommitGrouping(
                task_id=task_id,
                algorithm_version=ALGORITHM_VERSION,
            )
            db.add(state)
        state.status = "empty"
        state.n_commits = len(commits)
        state.n_groups = 0
        state.n_relations = 0
        state.error = None
        await db.commit()
        return

    try:
        F, model_used = await build_task_features(db, task_id)
        edges = build_edges(
            F, list(range(len(F.ids))),
            settings.GIT_COMMIT_GROUP_CANDIDATE_THRESHOLD,
        )
        raw_groups, _ = components_groups(
            F, list(range(len(F.ids))), edges,
            settings.GIT_COMMIT_GROUP_THRESHOLD,
        )
        groups, _, _ = cap_group_sizes(
            F, list(range(len(F.ids))), raw_groups,
            settings.GIT_COMMIT_GROUP_MAX_SIZE,
        )
        await _persist_groups(
            db, task_id, F, groups, edges, model_used, n_commits=len(commits)
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — ошибка сохраняется для UI
        await db.rollback()
        logger.exception("Не удалось построить группы задачи %s", task_id)
        row = await db.get(TaskCommitGrouping, task_id)
        if row is None:
            row = TaskCommitGrouping(task_id=task_id)
            db.add(row)
        row.status = "error"
        row.algorithm_version = ALGORITHM_VERSION
        row.n_commits = len(commits)
        row.n_groups = 0
        row.n_relations = 0
        row.error = f"{type(exc).__name__}: {exc}"[:500]
        await db.commit()


async def _commit_info(db: AsyncSession, commit_ids: Sequence[int]) -> Dict[int, Dict]:
    if not commit_ids:
        return {}
    commits = (
        await db.execute(select(Commit).where(Commit.id.in_(commit_ids)))
    ).scalars().all()
    return {
        commit.id: {
            "id": commit.id,
            "sha": commit.sha,
            "message": commit.message or "",
            "commit_type": commit.commit_type,
            "timestamp": commit.timestamp.isoformat() if commit.timestamp else None,
        }
        for commit in commits
    }


def _relation_out(relation: CommitRelation, commits: Dict[int, Dict]) -> Dict:
    source = commits.get(relation.source_commit_id, {})
    target = commits.get(relation.target_commit_id, {})
    return {
        "id": relation.id,
        "source_commit_id": relation.source_commit_id,
        "target_commit_id": relation.target_commit_id,
        "source_sha": source.get("sha"),
        "target_sha": target.get("sha"),
        "source_short": (
            f"{str(source.get('sha', ''))[:8]}:{source.get('commit_type') or '—'}"
        ),
        "target_short": (
            f"{str(target.get('sha', ''))[:8]}:{target.get('commit_type') or '—'}"
        ),
        "relation_type": relation.relation_type,
        "confidence": relation.confidence,
        "direction": relation.direction,
        "rule": relation.rule,
        "type_source": relation.type_source,
        "evidence": relation.evidence,
        "status": relation.status,
        "in_graph": relation.in_graph,
    }


async def serialize_task_groups(db: AsyncSession, task_id: int) -> Dict:
    state = await db.get(TaskCommitGrouping, task_id)
    groups = (
        await db.execute(
            select(CommitGroup)
            .where(CommitGroup.task_id == task_id)
            .order_by(CommitGroup.position, CommitGroup.id)
        )
    ).scalars().all()

    all_commits, _ = await _load_commit_rows(db, task_id)
    commit_ids = [commit.id for commit in all_commits]
    commits = await _commit_info(db, commit_ids)

    members = (
        await db.execute(
            select(CommitGroupMember)
            .where(CommitGroupMember.task_id == task_id)
            .order_by(CommitGroupMember.position)
        )
    ).scalars().all()
    by_group: Dict[int, List[CommitGroupMember]] = {}
    for member in members:
        by_group.setdefault(member.group_id, []).append(member)

    relations = (
        await db.execute(
            select(CommitRelation)
            .where(CommitRelation.task_id == task_id)
            .order_by(CommitRelation.confidence.desc())
        )
    ).scalars().all()

    group_out = []
    grouped_ids: Set[int] = set()
    for group in groups:
        group_members = by_group.get(group.id, [])
        member_ids = {member.commit_id for member in group_members}
        grouped_ids.update(member_ids)
        internal = [
            relation
            for relation in relations
            if relation.source_commit_id in member_ids
            and relation.target_commit_id in member_ids
        ]
        graph = [relation for relation in internal if relation.in_graph]
        if not graph and len(member_ids) > 1:
            # На случай старых/неполных данных: граф не должен исчезнуть.
            graph = internal[: max(0, len(member_ids) - 1)]
        group_out.append(
            {
                "id": group.id,
                "title": group.title,
                "title_source": group.title_source,
                "title_type": group.title_type,
                "title_area": group.title_area,
                "description": group.description,
                "rationale": group.rationale,
                "confidence": group.confidence,
                "status": group.status,
                "position": group.position,
                "size": len(member_ids),
                "commits": [
                    commits.get(member.commit_id, {"id": member.commit_id})
                    for member in group_members
                ],
                "relations": [_relation_out(relation, commits) for relation in internal],
                "graph_relations": [_relation_out(relation, commits) for relation in graph],
            }
        )

    ungrouped = [
        commit
        for commit in (commits[commit_id] for commit_id in commit_ids)
        if commit["id"] not in grouped_ids
    ]

    reason = None
    available = False
    if not settings.GIT_COMMIT_GROUPING_ENABLED:
        reason = "disabled"
    elif state is None:
        reason = "not_analyzed"
    elif state.status == "error":
        reason = state.error or "analysis_error"
    elif state.status == "empty":
        reason = "not_enough_commits"
    elif state.status != "done":
        reason = state.status
    else:
        available = True

    return {
        "task_id": task_id,
        "available": available,
        "reason": reason,
        "model_used": state.model_used if state else None,
        "algorithm_version": state.algorithm_version if state else ALGORITHM_VERSION,
        "generated_at": (
            state.generated_at.isoformat() if state and state.generated_at else None
        ),
        "groups": group_out,
        "ungrouped": ungrouped,
        "summary": {
            "commits": len(commit_ids),
            "grouped": len(grouped_ids),
            "ungrouped": len(ungrouped),
            "groups": len(group_out),
            "relations": len(relations),
        },
    }


async def _refresh_relation_statuses(db: AsyncSession, task_id: int) -> None:
    """Согласовать статусы связей с подтверждёнными группами.

    Связь подтверждается не сама по себе, а вместе с группой, внутри
    которой она находится. Если состав или статус группы изменился,
    старые отметки могли остаться на связях с коммитами, которые уже
    выведены из группы. Поэтому статус пересчитывается от текущего
    состава подтверждённых групп, а не правится точечно.
    """
    groups = (
        await db.execute(select(CommitGroup).where(CommitGroup.task_id == task_id))
    ).scalars().all()
    confirmed_ids = {group.id for group in groups if group.status == "confirmed"}
    if confirmed_ids:
        members = (
            await db.execute(
                select(CommitGroupMember).where(
                    CommitGroupMember.group_id.in_(confirmed_ids)
                )
            )
        ).scalars().all()
    else:
        members = []
    by_group: Dict[int, List[int]] = {}
    for member in members:
        by_group.setdefault(member.group_id, []).append(member.commit_id)

    confirmed_pairs: Set[Tuple[int, int]] = set()
    for commit_ids in by_group.values():
        for left_index, left in enumerate(commit_ids):
            for right in commit_ids[left_index + 1 :]:
                confirmed_pairs.add((min(left, right), max(left, right)))

    relations = (
        await db.execute(
            select(CommitRelation).where(CommitRelation.task_id == task_id)
        )
    ).scalars().all()
    for relation in relations:
        pair = (
            min(relation.source_commit_id, relation.target_commit_id),
            max(relation.source_commit_id, relation.target_commit_id),
        )
        relation.status = "confirmed" if pair in confirmed_pairs else "proposed"


async def update_group(
    db: AsyncSession,
    group_id: int,
    *,
    title: Optional[str] = None,
    status: Optional[str] = None,
    commit_ids: Optional[Sequence[int]] = None,
    user_id: Optional[int] = None,
) -> CommitGroup:
    """Переименование, подтверждение и редактирование состава группы."""
    group = await db.get(CommitGroup, group_id)
    if group is None:
        raise LookupError("group_not_found")

    if title is not None:
        value = title.strip()
        if value:
            group.title = value[:255]
            group.title_source = "manual"
        else:
            group.title_source = "template"
            group.title = (
                f"{TYPE_TITLE.get(group.title_type, group.title_type or 'Группа')} — "
                f"{group.title_area or 'без области'}"
            )

    if commit_ids is not None:
        selected = sorted({int(value) for value in commit_ids})
        if len(selected) < 2:
            raise ValueError("group_too_small")

        linked_ids = set(
            (
                await db.execute(
                    select(TaskGitLink.target_id).where(
                        TaskGitLink.task_id == group.task_id,
                        TaskGitLink.link_type == "commit",
                        TaskGitLink.status.notin_(("proposed", "rejected")),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not set(selected).issubset(linked_ids):
            raise ValueError("commit_not_linked")

        other_members = (
            await db.execute(
                select(CommitGroupMember).where(
                    CommitGroupMember.task_id == group.task_id,
                    CommitGroupMember.commit_id.in_(selected),
                    CommitGroupMember.group_id != group_id,
                )
            )
        ).scalars().all()
        if other_members:
            raise ValueError("commit_in_other_group")

        current = (
            await db.execute(
                select(CommitGroupMember).where(
                    CommitGroupMember.group_id == group_id
                )
            )
        ).scalars().all()
        current_by_commit = {member.commit_id: member for member in current}
        for member in current:
            if member.commit_id not in selected:
                await db.delete(member)
        for position, commit_id in enumerate(selected):
            if commit_id in current_by_commit:
                current_by_commit[commit_id].position = position
            else:
                db.add(
                    CommitGroupMember(
                        task_id=group.task_id,
                        group_id=group_id,
                        commit_id=commit_id,
                        position=position,
                    )
                )

        commits = (
            await db.execute(select(Commit).where(Commit.id.in_(selected)))
        ).scalars().all()
        type_counter = Counter(
            commit.commit_type or auto_label_type(commit.message or "")
            for commit in commits
        )
        if type_counter:
            group.title_type = sorted(
                type_counter,
                key=lambda kind: (
                    -type_counter[kind],
                    _TITLE_ORDER.index(kind) if kind in _TITLE_ORDER else 99,
                ),
            )[0]
        files = (
            await db.execute(
                select(CommitFile).where(CommitFile.commit_id.in_(selected))
            )
        ).scalars().all()
        area = _common_area([row.path for row in files if row.path])
        if area:
            group.title_area = area
        if group.title_source == "template":
            group.title = (
                f"{TYPE_TITLE.get(group.title_type, group.title_type or 'Группа')} — "
                f"{group.title_area or 'без области'}"
            )

        internal = (
            await db.execute(
                select(CommitRelation).where(
                    CommitRelation.task_id == group.task_id,
                    CommitRelation.source_commit_id.in_(selected),
                    CommitRelation.target_commit_id.in_(selected),
                )
            )
        ).scalars().all()
        if internal:
            group.confidence = round(_mean(item.confidence for item in internal), 3)
        else:
            group.confidence = None

    if status is not None:
        if status not in ("proposed", "confirmed"):
            raise ValueError("bad_status")
        group.status = status
        group.created_by_id = user_id if status == "confirmed" else None

    await db.flush()
    await _refresh_relation_statuses(db, group.task_id)
    await db.commit()
    await db.refresh(group)
    return group
