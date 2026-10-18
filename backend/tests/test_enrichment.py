"""ПРЕДУПРЕЖДЕНИЕ: проверка работает по НАСТОЯЩЕЙ базе PostgreSQL
и по НАСТОЯЩИМ данным — не запускать на боевой установке.

Фоновое дооболнение после синхронизации: правки подтягиваются,
модель предлагает привязки, статус доходит до done.
Ходит в GitLab по токену пользователя, у которого есть доступ
к тестовому репозиторию.

Запуск (из папки backend, при поднятом PostgreSQL):

    .\venv\Scripts\python.exe -W ignore tests\test_enrichment.py

Скрипт самодостаточен: печатает отчёт и итог вида «N/N проверок пройдено»,
pytest не нужен.
"""

"""Проверяет фоновую доработку целиком на настоящем GitLab.

Гоняет сверку, затем ждёт фоновой задачи и смотрит результат:
  * enrichment_status дошёл до done
  * у коммитов появились правки (commit_files.patch)
  * появились предложения привязок со статусом proposed

Репозиторий создаётся во временной строке, а в конце возвращается то,
что было до прогона. Раньше он просто удалялся, и после тестов у
проекта не оставалось подключения — приходилось подключать заново,
а вместе с ним терялись коммиты и предложения модели.

Это единственный тест, который ходит в GitLab по настоящему URL:
тестовый репозиторий нужен настоящий, иначе нечего синхронизировать.
"""
import asyncio
import logging
import sys
import time
import warnings

warnings.filterwarnings("ignore")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

from sqlalchemy import select, text

import app.models  # noqa: F401
import app.git.models  # noqa: F401
from app.core.database import SessionLocal
from app.git.models import GitAccount, GitProviderType, GitRepository
from app.git.services import _enrichment_running, SyncService

# Движок создан с echo=True (режим разработки), поэтому setLevel на
# логгере не помогает — echo ставит свой обработчик. Отключаем INFO
# глобально: иначе вывод теста тонет в SQL.
logging.disable(logging.INFO)

URL = "https://gitlab.com/renebus125/test_project"
PROJECT = 14

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"  {'OK ' if cond else 'FAIL'}  {name}{(' — ' + str(extra)) if extra else ''}")


async def drop_repository(s) -> None:
    """Удаляет репозиторий по URL вместе со связями задач.

    task_git_links.target_id — обычный Integer без внешнего ключа, поэтому
    удаление репозитории само по себе оставляет связи на несуществующие
    коммиты. Приложение чистит их в delete_project_repository, а тест идёт
    напрямую через SQL и обязан повторять то же: иначе после каждого
    прогона в базе копится мусор, который попадает в прогресс задач.

    ВАЖНО: связи удаляются по-настоящему, поэтому перед прогоном их
    нужно снять копию — см. snapshot_links / restore_links. Раньше тест
    стирал подтверждённые связи пользователя, и после каждого прогона
    приходилось подтверждать всё заново.
    """
    await s.execute(
        text(
            "DELETE FROM task_git_links WHERE link_type = 'commit' "
            "AND target_id IN ("
            "  SELECT id FROM git_commits WHERE repository_id IN "
            "  (SELECT id FROM git_repositories WHERE url = :u))"
        ),
        {"u": URL},
    )
    await s.execute(
        text(
            "DELETE FROM task_commits WHERE commit_id IN ("
            "  SELECT id FROM git_commits WHERE repository_id IN "
            "  (SELECT id FROM git_repositories WHERE url = :u))"
        ),
        {"u": URL},
    )
    await s.execute(text("DELETE FROM git_repositories WHERE url = :u"), {"u": URL})


async def snapshot_links(s) -> dict:
    """Снимает связи и ассоциативную таблицу репозитория перед прогоном.

    Идентификаторы коммитов при пересоздании репозитория меняются, поэтому
    снимок хранит sha: по нему связи восстанавливаются на новых коммитах.
    """
    commits = (
        await s.execute(
            text(
                "SELECT gc.id, gc.sha FROM git_commits gc "
                "WHERE gc.repository_id IN "
                "(SELECT id FROM git_repositories WHERE url = :u)"
            ),
            {"u": URL},
        )
    ).mappings().all()

    old_to_sha = {r["id"]: r["sha"] for r in commits}

    if not old_to_sha:
        return {"commits": {}, "links": [], "task_commits": []}

    ids = list(old_to_sha.keys())

    links = (
        await s.execute(
            text(
                "SELECT task_id, target_id, source, confidence, status, reason, "
                "created_by_id FROM task_git_links "
                "WHERE link_type = 'commit' AND target_id = ANY(:ids)"
            ),
            {"ids": ids},
        )
    ).mappings().all()

    m2m = (
        await s.execute(
            text(
                "SELECT task_id, commit_id FROM task_commits "
                "WHERE commit_id = ANY(:ids)"
            ),
            {"ids": ids},
        )
    ).mappings().all()

    return {
        "commits": old_to_sha,
        "links": [dict(r) for r in links],
        "task_commits": [dict(r) for r in m2m],
    }


async def restore_links(s, snap: dict) -> tuple:
    """Возвращает связи после прогона по sha.

    Возвращает (возвращено, уже было на месте, пропало без коммита):
    разделение нужно, чтобы по отчёту было видно, что произошло.
    Раньше всё сводилось к одному числу, и «0 из 6» читалось как
    «все потеряны», хотя означало «все целы».
    """
    if not snap["commits"]:
        return 0, 0, 0

    now = (
        await s.execute(
            text(
                "SELECT id, sha FROM git_commits "
                "WHERE repository_id IN "
                "(SELECT id FROM git_repositories WHERE url = :u)"
            ),
            {"u": URL},
        )
    ).mappings().all()

    # sha → новый id. Sha уникален в пределах репозитория.
    sha_to_new: dict = {}
    for row in now:
        sha_to_new.setdefault(row["sha"], row["id"])

    restored = 0
    already = 0
    lost = 0

    for link in snap["links"]:
        sha = snap["commits"].get(link["target_id"])
        new_id = sha_to_new.get(sha) if sha else None
        if not new_id:
            # Коммита больше нет в репозитории (например, откатили
            # ветку) — восстанавливать нечего.
            lost += 1
            continue

        exists = (
            await s.execute(
                text(
                    "SELECT id FROM task_git_links WHERE task_id = :t "
                    "AND link_type = 'commit' AND target_id = :c"
                ),
                {"t": link["task_id"], "c": new_id},
            )
        ).scalar_one_or_none()
        if exists:
            already += 1
            continue

        await s.execute(
            text(
                "INSERT INTO task_git_links (task_id, link_type, target_id, "
                "source, confidence, status, reason, created_by_id) "
                "VALUES (:t, 'commit', :c, :s, :conf, :st, :r, :by)"
            ),
            {
                "t": link["task_id"],
                "c": new_id,
                "s": link["source"],
                "conf": link["confidence"],
                "st": link["status"],
                "r": link["reason"],
                "by": link["created_by_id"],
            },
        )
        restored += 1

    for row in snap["task_commits"]:
        sha = snap["commits"].get(row["commit_id"])
        new_id = sha_to_new.get(sha) if sha else None
        if not new_id:
            continue
        await s.execute(
            text(
                "INSERT INTO task_commits (task_id, commit_id) "
                "VALUES (:t, :c) ON CONFLICT DO NOTHING"
            ),
            {"t": row["task_id"], "c": new_id},
        )

    await s.commit()
    return restored, already, lost


async def main():
    # ---------------------------------------------------------- #
    print("=== 0. Подготовка ===")
    # Тест работает с настоящим URL, и раньше перед прогоном он
    # удалял репозиторий целиком — вместе с подтверждёнными связями
    # пользователя. После каждого запуска проверок приходилось
    # подтверждать всё заново.
    #
    # Теперь: если репозиторий уже подключён, он не трогается вовсе,
    # а снимается копия связей, которая возвращается в конце. Если не
    # подключён — создаётся временный и удаляется как раньше.
    snapshot = None
    link_snapshot = {"commits": {}, "links": [], "task_commits": []}
    async with SessionLocal() as s:
        row = (
            await s.execute(
                text(
                    "SELECT id, project_id, url, repo_name, provider, default_branch, "
                    "access_token, connected_by_id, is_active, path_filter "
                    "FROM git_repositories WHERE url = :u"
                ),
                {"u": URL},
            )
        ).mappings().first()
        snapshot = dict(row) if row else None

        if snapshot:
            link_snapshot = await snapshot_links(s)
            print(f"  репозиторий уже подключён: #{snapshot['id']}, "
                  f"не трогаем, связи вернём после прогона")
        else:
            print("  подключения нет — создаём временное")

    print(f"  связей снято: {len(link_snapshot['links'])}, "
          f"строк в task_commits: {len(link_snapshot['task_commits'])}")

    async with SessionLocal() as s:
        row = (
            await s.execute(
                select(GitAccount.access_token)
                .where(GitAccount.provider == "gitlab", GitAccount.user_id == 4)
            )
        ).first()
        token = getattr(row[0], "plain", None) or str(row[0])

        if snapshot:
            # Подключение уже есть — работаем с ним, а не создаём второе.
            repo = (
                await s.execute(
                    select(GitRepository).where(GitRepository.id == snapshot["id"])
                )
            ).scalar_one()
            if repo.access_token is None:
                repo.access_token = token
            rid = repo.id
            await s.commit()
            print(f"  используем подключённый репозиторий #{rid}")
        else:
            repo = GitRepository(
                project_id=PROJECT, url=URL, repo_name="renebus125/test_project",
                provider=GitProviderType.GITLAB, default_branch="master",
                access_token=token, connected_by_id=4, is_active=True,
            )
            s.add(repo)
            await s.commit()
            await s.refresh(repo)
            rid = repo.id
            print(f"  временный репозиторий #{rid}")

    try:
        # ---------------------------------------------------------- #
        print("\n=== 1. Сверка запускает фоновую доработку ===")
        async with SessionLocal() as s:
            repo = (
                await s.execute(select(GitRepository).where(GitRepository.id == rid))
            ).scalar_one()
            stats = await SyncService.sync_repository(s, repo)
            print(f"  сверка: {stats}")
            check("коммитов загружено", stats.get("commits", 0) > 0, stats.get("commits"))
            enrich = stats.get("enrichment") or {}
            check("доработка запущена", enrich.get("started") is True, enrich)
            check(
                "включены и правки, и трассировка",
                set(enrich.get("steps") or []) == {"patches", "trace"},
                enrich.get("steps"),
            )
            # Задача стартует на ближайшем await, поэтому сразу после
            # sync_repository она может ещё не попасть в список.
            # Даём event loop переключиться.
            await asyncio.sleep(0.1)
            check("репозиторий в списке активных задач", rid in _enrichment_running)

        # ---------------------------------------------------------- #
        print("\n=== 2. Ждём фоновую доработку ===")
        started = time.monotonic()
        while rid in _enrichment_running and time.monotonic() - started < 300:
            await asyncio.sleep(1.0)
            async with SessionLocal() as s:
                r = (
                    await s.execute(
                        text(
                            "SELECT enrichment_status, enrichment_done, enrichment_total "
                            "FROM git_repositories WHERE id = :i"
                        ),
                        {"i": rid},
                    )
                ).mappings().first()
                print(
                    f"    {time.monotonic() - started:5.1f} с  "
                    f"{r['enrichment_status']}  {r['enrichment_done']}/{r['enrichment_total']}"
                )
        elapsed = time.monotonic() - started
        check("доработка завершилась", rid not in _enrichment_running, f"{elapsed:.1f} с")
        check("уложилась в разумное время", elapsed < 300, f"{elapsed:.1f} с")

        # ---------------------------------------------------------- #
        print("\n=== 3. Что получилось в базе ===")
        async with SessionLocal() as s:
            r = (
                await s.execute(
                    text(
                        "SELECT enrichment_status, enrichment_error, enrichment_done "
                        "FROM git_repositories WHERE id = :i"
                    ),
                    {"i": rid},
                )
            ).mappings().one()
            print(f"  статус: {r['enrichment_status']}")
            if r["enrichment_error"]:
                print(f"  ошибка: {r['enrichment_error'][:200]}")
            check("статус done", r["enrichment_status"] == "done", r["enrichment_status"])
            check("без ошибки", not r["enrichment_error"], r["enrichment_error"])

            # Правки
            n_files = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM commit_files cf "
                        "JOIN git_commits gc ON gc.id = cf.commit_id "
                        "WHERE gc.repository_id = :i"
                    ),
                    {"i": rid},
                )
            ).scalar()
            n_patch = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM commit_files cf "
                        "JOIN git_commits gc ON gc.id = cf.commit_id "
                        "WHERE gc.repository_id = :i AND cf.patch IS NOT NULL AND cf.patch <> ''"
                    ),
                    {"i": rid},
                )
            ).scalar()
            print(f"  строк commit_files: {n_files}, из них с правкой: {n_patch}")
            check("правки подтянуты автоматически", n_patch > 0, n_patch)

            # Предложения
            rows = (
                await s.execute(
                    text(
                        "SELECT l.id, l.status, l.source, t.title, gc.message "
                        "FROM task_git_links l "
                        "JOIN git_commits gc ON gc.id = l.target_id "
                        "JOIN tasks t ON t.id = l.task_id "
                        "WHERE gc.repository_id = :i AND l.status = 'proposed'"
                    ),
                    {"i": rid},
                )
            ).mappings().all()
            print(f"\n  предложений привязки: {len(rows)}")
            for row in rows[:6]:
                title = (row["message"] or "").splitlines()[0][:46]
                print(f"    → задача «{row['title']}» ← {title} ({row['source']})")
            check("модель предложила привязки", len(rows) > 0, len(rows))

            # Типы
            typed = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM git_commits "
                        "WHERE repository_id = :i AND commit_type IS NOT NULL"
                    ),
                    {"i": rid},
                )
            ).scalar()
            print(f"\n  коммитов с типом: {typed}")
            rows = (
                await s.execute(
                    text(
                        "SELECT commit_type, count(*) FROM git_commits "
                        "WHERE repository_id = :i GROUP BY commit_type"
                    ),
                    {"i": rid},
                )
            ).all()
            print("  распределение:", rows)

    finally:
        if snapshot:
            # Подключение было до прогона и осталось на месте —
            # возвращаем только связи, которые прогон снял.
            async with SessionLocal() as s:
                restored, already, lost = await restore_links(s, link_snapshot)
                total = len(link_snapshot["links"])
                print(f"\n  связей: всего {total}, на месте уже было {already}, "
                      f"возвращено {restored}, потеряно с коммитом {lost}")
        else:
            async with SessionLocal() as s:
                await drop_repository(s)
                await s.commit()
                print("\n  временный репозиторий удалён")

    print("\n" + "=" * 60)
    failed = [n for n, ok in results if not ok]
    print(f"ИТОГ: {len(results) - len(failed)}/{len(results)} проверок пройдено")
    for n in failed:
        print(f"  ПРОВАЛ: {n}")


asyncio.run(main())
