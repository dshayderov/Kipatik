"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Объём изменений и честность прогресса:

  * additions/deletions считаются по тексту правки, когда провайдер
    их не прислал. GitLab в ответе на /diff отдаёт только diff, из-за
    чего объёмная составляющая всегда была нулевой, а прогресс
    упирался в 50%;
  * ремонт уже сохранённых правок не ходит к провайдеру;
  * неподтверждённые предложения в прогресс не попадают.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\venv\Scripts\python.exe -W ignore tests\test_progress_volume.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

import warnings

warnings.filterwarnings("ignore")

import logging

logging.disable(logging.INFO)

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
import app.git.models  # noqa: F401
from app.ai.code_model.progress_estimator import calculate_progress_detailed
from app.tasks.progress import _shrunk_expected, get_task_progress
from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.git.models import Commit, CommitFile, GitProviderType, GitRepository, TaskGitLink
from app.git.patches import count_changed_lines, repair_change_counts
from app.main import app
from app.tasks.models import Task
from app.users.models import User

PROJECT = 14
PROBE_URL = "https://example.invalid/probe/volume"
# Своя задача-зонд: у задач проекта уже есть связи, и проверять на них
# нельзя — иначе результат зависит от того, что нажали до нас.
PROBE_TITLE = "Зонд проверки объёма src/probe.py"

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


# --------------------------------------------------------------- #
# 1. Формула прогресса и калибровка объёма
# --------------------------------------------------------------- #
def pct(lines, expected=200, mentioned=("export.py",), subtasks=None):
    """Прогресс по той же функции, что работает в приложении."""
    diff = "\n".join(["+"] * lines) if lines else ""
    return calculate_progress_detailed(
        task={
            "files_mentioned": list(mentioned),
            "files_touched": ["src/export.py"] if lines else [],
            "expected_volume": expected,
        },
        commits_diffs=[diff] if diff else [],
        subtasks=subtasks,
    )


def formula_checks():
    print("\n=== 2. Формула: семантика множитель, а не слагаемое ===")

    # Пол исходной формулы: одна строка кода давала 50%.
    check("одна строка не даёт 50%",
          pct(1)["progress_percent"] < 2.0,
          f"{pct(1)['progress_percent']}%")
    check("21 строка даёт около 10%",
          9.0 < pct(21)["progress_percent"] < 12.0,
          f"{pct(21)['progress_percent']}%")
    check("прогресс растёт с объёмом",
          pct(21)["progress_percent"] < pct(50)["progress_percent"] < pct(100)["progress_percent"],
          [pct(n)["progress_percent"] for n in (21, 50, 100)])
    check("достижение ожидаемого объёма даёт 100%",
          pct(200)["progress_percent"] == 100.0,
          pct(200)["progress_percent"])
    check("перебор объёма не даёт больше 100%",
          pct(400)["progress_percent"] == 100.0,
          pct(400)["progress_percent"])

    print("\n=== 3. Прицельность снижает оценку, но не обнуляет ===")
    right = pct(200)
    wrong = pct(200, mentioned=("other.py",))
    check("нужные файлы дают прицельность 1.0",
          right["targeting_component"] == 1.0, right["targeting_component"])
    check("чужие файлы дают прицельность 0.5",
          wrong["targeting_component"] == 0.5, wrong["targeting_component"])
    check("при полном объёме и чужих файлах прогресс 50%, а не 0",
          wrong["progress_percent"] == 50.0, wrong["progress_percent"])
    check("работа не по тем файлам обходится дешевле",
          wrong["progress_percent"] < right["progress_percent"])

    print("\n=== 4. Отсутствие упомянутых файлов не штрафуется ===")
    no_mentions = pct(200, mentioned=())
    check("нет упоминаний — прицельность 1.0",
          no_mentions["targeting_component"] == 1.0,
          no_mentions["targeting_component"])
    check("нет упоминаний — семантика не показана как 0",
          no_mentions["semantic_component"] == 0.0,
          no_mentions["semantic_component"])
    check("нет упоминаний — прогресс по объёму",
          no_mentions["progress_percent"] == 100.0,
          no_mentions["progress_percent"])

    print("\n=== 5. Подзадачи остаются ведущей составляющей ===")
    st0 = [{"text": "а", "done": False}, {"text": "б", "done": False}]
    st1 = [{"text": "а", "done": True}, {"text": "б", "done": False}]
    st2 = [{"text": "а", "done": True}, {"text": "б", "done": True}]
    check("0 из 2 подзадач даёт меньше, чем 1 из 2",
          pct(200, subtasks=st0)["progress_percent"] < pct(200, subtasks=st1)["progress_percent"])
    check("2 из 2 подзадач без коммитов даёт 60%",
          pct(0, subtasks=st2)["progress_percent"] == 60.0,
          pct(0, subtasks=st2)["progress_percent"])
    check("2 из 2 подзадач и полный объём даёт 100%",
          pct(200, subtasks=st2)["progress_percent"] == 100.0,
          pct(200, subtasks=st2)["progress_percent"])

    print("\n=== 6. Стягивание калибровки к априорному значению ===")
    prior = 200
    v, w = _shrunk_expected(100, 0, prior, 3)
    check("без наблюдений — чистый априор", (v, w) == (200, 0.0), (v, w))

    v1, w1 = _shrunk_expected(20, 1, prior, 3)
    check("одна задача: данным четверть веса", w1 == 0.25, w1)
    check("одна задача: оценка далека и от 20, и от 200",
          100 < v1 < 200, v1)
    check("одна задача не даёт оценку, равную единственному наблюдению",
          v1 != 20, v1)

    v3, w3 = _shrunk_expected(100, 3, prior, 3)
    check("три задачи: половина веса у данных", w3 == 0.5, w3)
    check("три задачи: ровно посередине", v3 == 150, v3)

    v100, w100 = _shrunk_expected(100, 97, prior, 3)
    check("много задач: вес данных стремится к 1", w100 > 0.95, w100)
    # При большой выборке априор почти не мешает: остаточное смещение
    # убывает как (K/n)·|наблюдение − априор|.
    check("много задач: оценка отличается от перцентиля не больше чем на 10%",
          abs(v100 - 100) <= 10, v100)

    v_big, _ = _shrunk_expected(0, 5, prior, 3)
    check("и нулевой перцентиль не даёт нулевой ожидаемый объём", v_big >= 1, v_big)


# --------------------------------------------------------------- #
# 2. Подсчёт строк по тексту правки
# --------------------------------------------------------------- #
DIFF = """@@ -1,3 +1,4 @@
 def export(rows):
-    old_line
+    new_line
+    extra_line
     tail
"""

SINGLE = "@@ -0,0 +1 @@\n+only added\n"
DELETE_ONLY = "@@ -1,2 +0,0 @@\n-gone_one\n-gone_two\n"
EMPTY = ""
HEADER_ONLY = (
    "diff --git a/x.py b/x.py\n"
    "index 111..222 100644\n"
    "--- a/x.py\n"
    "+++ b/x.py\n"
)


def counting_checks():
    print("=== 1. Подсчёт строк по тексту правки ===")

    a, d = count_changed_lines(DIFF)
    check("добавлено 2 строки", a == 2, a)
    check("удалено 1 строка", d == 1, d)

    a, d = count_changed_lines(SINGLE)
    check("только добавление", a == 1 and d == 0, f"+{a}/-{d}")

    a, d = count_changed_lines(DELETE_ONLY)
    check("только удаление", a == 0 and d == 2, f"+{a}/-{d}")

    a, d = count_changed_lines(HEADER_ONLY)
    check("заголовки файлов не считаются изменениями", a == 0 and d == 0, f"+{a}/-{d}")

    a, d = count_changed_lines(EMPTY)
    check("пустая правка даёт нули", a == 0 and d == 0, f"+{a}/-{d}")

    a, d = count_changed_lines(None)
    check("нет правки — нули, без исключения", a == 0 and d == 0, f"+{a}/-{d}")

    # Правка без завершающих переводов строк
    a, d = count_changed_lines("+one\n-two")
    check("правка без хвостового перевода строки", a == 1 and d == 1, f"+{a}/-{d}")


# --------------------------------------------------------------- #
# 2. Ремонт и прогресс на настоящих данных
# --------------------------------------------------------------- #
engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

TEST_USER = User(
    id=4, email="renebus125@gmail.ru", full_name="probe", hashed_password="x",
    is_active=True, is_superuser=True,
)


async def _get_db():
    async with sm() as s:
        yield s


app.dependency_overrides[get_db] = _get_db
app.dependency_overrides[deps.get_current_user] = lambda: TEST_USER

created_repo = None
probe_commit = None
task_row = None
probe_task_id = None


async def find_task():
    """Создаёт задачу-зонд, чтобы проверка не зависела от чужих связей."""
    global task_row, probe_task_id

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM tasks WHERE title = :t"), {"t": PROBE_TITLE}
        )

    async with sm() as s:
        s.add(
            Task(
                title=PROBE_TITLE,
                description="Проверка подсчёта объёма по файлу src/probe.py",
                project_id=PROJECT,
                priority=2,
            )
        )
        await s.commit()

    async with sm() as s:
        task_row = (
            await s.execute(
                text("SELECT id, title, description FROM tasks WHERE title = :t"),
                {"t": PROBE_TITLE},
            )
        ).mappings().first()
    probe_task_id = task_row["id"]
    return task_row


async def setup():
    """Репозиторий-зонд с коммитом, у которого правка есть, а счётчики нулевые."""
    global created_repo, probe_commit

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM git_repositories WHERE url = :u"), {"u": PROBE_URL}
        )

    async with sm() as s:
        repo = GitRepository(
            project_id=PROJECT, url=PROBE_URL, repo_name="probe/volume",
            provider=GitProviderType.GITLAB, default_branch="master",
            access_token="t", connected_by_id=4, is_active=False,
        )
        s.add(repo)
        await s.commit()
        await s.refresh(repo)
        created_repo = repo.id

        commit = Commit(
            repository_id=repo.id,
            sha="aabbccdd",
            message="feat(volume): проверка объёма",
            author="probe",
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
        )
        s.add(commit)
        await s.commit()
        await s.refresh(commit)
        probe_commit = commit.id

        # Правка сохранена, а числа строк — нули: ровно то состояние,
        # в котором оказывались файлы, прочитанные до GitLab.
        s.add(
            CommitFile(
                commit_id=commit.id,
                path="src/probe.py",
                status="modified",
                additions=0,
                deletions=0,
                patch=DIFF,
            )
        )
        await s.commit()

    return created_repo


async def read_counts():
    async with sm() as s:
        row = (
            await s.execute(
                text(
                    "SELECT additions, deletions FROM commit_files "
                    "WHERE commit_id = :c AND path = 'src/probe.py'"
                ),
                {"c": probe_commit},
            )
        ).mappings().first()
        return dict(row) if row else {}


async def teardown():
    if created_repo is None:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM task_git_links WHERE target_id IN "
                "(SELECT id FROM git_commits WHERE repository_id = :r)"
            ),
            {"r": created_repo},
        )
        await conn.execute(
            text(
                "DELETE FROM task_commits WHERE commit_id IN "
                "(SELECT id FROM git_commits WHERE repository_id = :r)"
            ),
            {"r": created_repo},
        )
        await conn.execute(
            text("DELETE FROM commit_files WHERE commit_id IN "
                 "(SELECT id FROM git_commits WHERE repository_id = :r)"),
            {"r": created_repo},
        )
        await conn.execute(
            text("DELETE FROM git_commits WHERE repository_id = :r"), {"r": created_repo}
        )
        await conn.execute(
            text("DELETE FROM git_repositories WHERE id = :i"), {"i": created_repo}
        )

    if probe_task_id is not None:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM tasks WHERE id = :i"), {"i": probe_task_id}
            )


async def progress_of(task_id):
    async with sm() as s:
        row = (
            await s.execute(
                text(
                    "SELECT id, title, description, project_id FROM tasks WHERE id = :i"
                ),
                {"i": task_id},
            )
        ).mappings().first()
        fake = SimpleNamespace(
            id=row["id"], title=row["title"], description=row["description"],
            project_id=row["project_id"],
        )
        return await get_task_progress(s, fake)


async def repair(repo_id):
    async with sm() as s:
        return await repair_change_counts(s, repository_id=repo_id)


client = TestClient(app)

try:
    counting_checks()
    formula_checks()

    t = asyncio.run(find_task())
    if not t:
        print("Нет задач в проекте — тест пропущен")
        raise SystemExit(0)

    print(f"\n=== 7. Ремонт уже сохранённых правок (задача {t['id']}) ===")
    rid = asyncio.run(setup())
    print(f"  репозиторий-зонд #{rid}, коммит #{probe_commit}")

    before = asyncio.run(read_counts())
    check("до ремонта числа нулевые",
          (before.get("additions") or 0) == 0 and (before.get("deletions") or 0) == 0,
          before)

    fixed = asyncio.run(repair(rid))
    check("ремонт поправил файл", fixed == 1, f"поправлено {fixed}")

    after = asyncio.run(read_counts())
    check("additions посчитаны", after.get("additions") == 2, after.get("additions"))
    check("deletions посчитаны", after.get("deletions") == 1, after.get("deletions"))

    repeat = asyncio.run(repair(rid))
    check("повторный ремонт ничего не трогает", repeat == 0, f"поправлено {repeat}")

    # -------------------------------------------------------------- #
    print(f"\n=== 8. Предложения не входят в прогресс ===")
    p_before = asyncio.run(progress_of(t["id"]))
    print(f"  прогресс до привязки: {p_before['percent']}%")

    async def add_links():
        async with sm() as s:
            for sha, status, src in (
                ("1111aaaa", "confirmed", "model"),
                ("2222bbbb", "proposed", "model"),
            ):
                c = Commit(
                    repository_id=rid, sha=sha, message=f"feat: {sha}",
                    author="probe",
                    timestamp=datetime.now(timezone.utc) - timedelta(days=1),
                )
                s.add(c)
                await s.flush()
                s.add(CommitFile(
                    commit_id=c.id, path="src/probe.py", status="modified",
                    additions=2, deletions=1, patch=DIFF,
                ))
                s.add(TaskGitLink(
                    task_id=t["id"], link_type="commit", target_id=c.id,
                    source=src, confidence=0.8, status=status,
                    reason="по смыслу изменений",
                ))
            await s.commit()

    asyncio.run(add_links())
    p_after = asyncio.run(progress_of(t["id"]))
    print(f"  прогресс после 1 подтверждённой и 1 предложения: {p_after['percent']}%")

    check("неподтверждённое предложение не увеличило число коммитов",
          p_after["inputs"]["commits"] == 1, p_after["inputs"]["commits"])

    async def count_all_links():
        async with sm() as s:
            return (
                await s.execute(
                    text(
                        "SELECT count(*) FROM task_git_links "
                        "WHERE task_id = :t AND link_type = 'commit'"
                    ),
                    {"t": t["id"]},
                )
            ).scalar()

    check("в базе при этом две связи", asyncio.run(count_all_links()) == 2,
          asyncio.run(count_all_links()))

    p_one = asyncio.run(progress_of(t["id"]))
    check("строки изменений посчитаны", p_one["inputs"]["lines_changed"] == 3,
          p_one["inputs"]["lines_changed"])
    # Учитывается только подтверждённый коммит 1111aaaa (+2/-1):
    # предложение 2222bbbb и коммит из подготовки не привязаны.
    check("добавлений 2, удалений 1",
          p_one["inputs"]["additions"] == 2 and p_one["inputs"]["deletions"] == 1,
          f"+{p_one['inputs']['additions']}/-{p_one['inputs']['deletions']}")
    check("объёмная составляющая больше не нулевая",
          p_one["components"]["volume"] > 0, p_one["components"]["volume"])

finally:
    client.close()
    asyncio.run(teardown())
    print("\n  временные записи удалены")

print("\n" + "=" * 60)
failed = [n for n, ok in results if not ok]
print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
for n in failed:
    print(f"  ПРОВАЛ: {n}")