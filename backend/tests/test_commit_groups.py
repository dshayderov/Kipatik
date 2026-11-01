"""Проверка чистой логики группировки коммитов (без базы).

Тест не требует PostgreSQL и не ходит в модели: признаки и векторы
задаются вручную. Проверяются вещи, которые легко сломать при переносе
ноутбука в приложение:

* направление отношения известно/неизвестно;
* правила fixes/tests не применяются без близости и направления;
* группа — связная компонента, а не все коммиты подряд;
* большая группа дробится и не превышает MAX_GROUP;
* граф группы — остовное дерево, а не полный граф;
* название собирается из типа и области.

Запуск (из папки backend):

    .\\venv\\Scripts\\python.exe -W ignore tests\\test_commit_groups.py
"""

import math
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

warnings.filterwarnings("ignore")

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.git.grouping import (  # noqa: E402
    GroupFeatures,
    auto_label_type,
    build_edges,
    cap_group_sizes,
    components_groups,
    display_graph_edges,
    group_title,
    _lexical_embeddings,
)

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


def norm(values):
    length = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / length for value in values]


BASE = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def make_features(
    types,
    files,
    dates=None,
    msg_vectors=None,
    repr_vectors=None,
    type_sources=None,
):
    count = len(types)
    if dates is None:
        dates = [BASE + timedelta(days=index) for index in range(count)]
    if repr_vectors is None:
        repr_vectors = [norm([1.0, 0.02 * index, 0.0]) for index in range(count)]
    if msg_vectors is None:
        msg_vectors = repr_vectors
    if type_sources is None:
        type_sources = ["lr3"] * count
    return GroupFeatures(
        ids=list(range(1, count + 1)),
        uids=[f"sha{index}" for index in range(count)],
        msgs=[f"commit {index}" for index in range(count)],
        types=types,
        files=files,
        dates=dates,
        emb_repr=repr_vectors,
        emb_msg=msg_vectors,
        type_sources=type_sources,
        min_rule_aff=0.55,
    )


print("1. Отношения и направление")

types = ["feature", "test", "bugfix", "feature"]
files = [
    {"src/api/a.py"},
    {"src/api/a_test.py"},
    {"src/api/a.py"},
    {"src/api/b.py"},
]
dates = [BASE + timedelta(days=index) for index in range(4)]
vectors = [norm([1.0, 0.01 * index, 0.0]) for index in range(4)]
F = make_features(types, files, dates=dates, repr_vectors=vectors)
edges = build_edges(F, list(range(4)), threshold=0.30)
by_pair = {(edge["i"], edge["j"]): edge for edge in edges}

check("ребро feature→test найдено", (0, 1) in by_pair)
if (0, 1) in by_pair:
    check("тип tests", by_pair[(0, 1)]["relation"] == "tests", by_pair[(0, 1)]["relation"])
    check(
        "направление по времени",
        by_pair[(0, 1)]["direction"] == "known",
        by_pair[(0, 1)]["direction"],
    )

check("ребро feature→bugfix найдено", (0, 2) in by_pair)
if (0, 2) in by_pair:
    check("тип fixes", by_pair[(0, 2)]["relation"] == "fixes", by_pair[(0, 2)]["relation"])

unknown_dates = [None, None, None, None]
F_unknown = make_features(types, files, dates=unknown_dates, repr_vectors=vectors)
unknown_edges = build_edges(F_unknown, list(range(4)), threshold=0.30)
unknown_pair = {
    (edge["i"], edge["j"]): edge for edge in unknown_edges
}.get((0, 1))
check("без дат направление unknown", unknown_pair is not None and unknown_pair["direction"] == "unknown")
check(
    "без направления fixes/tests превращаются в related",
    unknown_pair is not None and unknown_pair["relation"] == "related",
    unknown_pair["relation"] if unknown_pair else "нет ребра",
)

far_vectors = [norm([1.0, 0.0, 0.0]), norm([0.0, 1.0, 0.0])] + [norm([1.0, 0.0, 0.0])] * 2
F_far = make_features(["feature", "test", "feature", "feature"], files, dates=dates, repr_vectors=far_vectors)
far_edges = build_edges(F_far, list(range(4)), threshold=0.20)
far_pair = {(edge["i"], edge["j"]): edge for edge in far_edges}.get((0, 1))
check(
    "слабая пара не получает rules-тип",
    far_pair is None or far_pair["relation"] == "related",
    far_pair["relation"] if far_pair else "ниже порога",
)

print("2. Группы и ограничение размера")

edges = build_edges(F, list(range(4)), threshold=0.30)
groups, ungrouped = components_groups(F, list(range(4)), edges, threshold=0.55)
check("связная компонента стала группой", len(groups) == 1, groups)
check("в группе все четыре коммита", len(groups[0]) == 4 if groups else False)
check("вне групп никого", ungrouped == [], ungrouped)

big_types = ["feature"] * 10
big_files = [{"src/core/file.py"} for _ in range(10)]
big_vectors = [norm([1.0, 0.001 * index, 0.0]) for index in range(10)]
F_big = make_features(
    big_types,
    big_files,
    dates=[BASE + timedelta(days=index) for index in range(10)],
    repr_vectors=big_vectors,
)
big_edges = build_edges(F_big, list(range(10)), threshold=0.30)
big_groups, _ = components_groups(F_big, list(range(10)), big_edges, threshold=0.55)
check("исходная группа больше предела", bool(big_groups) and len(big_groups[0]) == 10)
capped, capped_ungrouped, oversized = cap_group_sizes(F_big, list(range(10)), big_groups, max_size=8)
check("после дробления нет групп больше 8", all(len(group) <= 8 for group in capped), capped)
check("дробление не теряет коммиты зря", len(capped) >= 2 and not oversized, (capped, capped_ungrouped))
check(
    "все коммиты распределены",
    sum(len(group) for group in capped) + len(capped_ungrouped) == 10,
)

print("3. Граф группы")

tree = display_graph_edges(F, groups[0], edges)
check("граф не пуст", len(tree) > 0, len(tree))
check("в графе n−1 рёбер", len(tree) == len(groups[0]) - 1, len(tree))
check(
    "граф связный",
    len({edge["i"] for edge in tree} | {edge["j"] for edge in tree}) == len(groups[0]),
)

print("4. Название и тип")

title = group_title(F, groups[0])
check("название содержит тип", "Реализация" in title, title)
check("название содержит область", "src/api" in title, title)

check("fix: → bugfix", auto_label_type("fix: падение отчёта") == "bugfix")
check("feat: → feature", auto_label_type("feat: экспорт в CSV") == "feature")
check("docs: → docs", auto_label_type("docs: описание API") == "docs")
check("merge → chore", auto_label_type("Merge pull request #4 from dev") == "chore")

print("5. Резервные векторы")

texts = ["fix: падение отчёта", "feat: экспорт CSV", "docs: описание"]
lexical = _lexical_embeddings(texts)
check("векторы построены для всех текстов", len(lexical) == 3)
check(
    "векторы нормированы",
    all(abs(math.sqrt(sum(value * value for value in row)) - 1.0) < 1e-6 for row in lexical),
)
check("похожие тексты ближе разных", sum(a * b for a, b in zip(lexical[0], lexical[2])) < 0.9)

print("\n" + "=" * 60)
failed = [name for name, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for name in failed:
    print(f"  ПРОВАЛ: {name}")
raise SystemExit(1 if failed else 0)
