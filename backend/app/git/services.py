import asyncio
import logging
import re
from typing import List, Optional, Dict
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from app.core.config import settings
from app.core.database import SessionLocal
from app.projects.models import Project
from app.tasks.models import Task
from app.tasks.services import TaskStatusService
from app.git.models import (
    GitRepository, Commit, Branch, PullRequest,
    GitProviderType, PRState, UnlinkedGitEvent, GitEventLog,
    CommitFile, TaskGitLink,
)
from app.git.factory import get_git_provider
from app.git.base import GitEvent, GitCommitDTO
from app.git.http_client import GitAPIError

logger = logging.getLogger(__name__)

class TaskLinkingService:
    @staticmethod
    async def extract_task_ids(text: str) -> List[int]:
        """Извлекает ID задач из текста (сообщения коммитов, названия веток)"""
        if not text:
            return []
        # Паттерны: #123, TASK-123, feature/42-something, fix/123, 123-description
        patterns = [
            r'(?:#|TASK-|task-|feature/|fix/|bug/)(\d+)', # С префиксом
            r'(?:^|/)(\d+)(?:-|$)' # В начале или после слеша (42-auth)
        ]
        task_ids = set()
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                task_ids.add(int(m))
        return list(task_ids)

    @staticmethod
    async def resolve_author_user(
        db: AsyncSession,
        author_raw: str | None,
        author_email: str | None = None,
        repository_id: int | None = None,
    ) -> int | None:
        """Сопоставляет автора коммита с пользователем системы.

        Делегирует AuthorMappingService, где собран порядок проб:
        явное (в том числе ручное) правило -> email -> логин провайдера.
        """
        from app.git.author_mapping import AuthorMappingService

        user_id, _source = await AuthorMappingService.resolve(
            db, repository_id, author_raw, author_email
        )
        return user_id

    @staticmethod
    async def save_commit_files(db: AsyncSession, commit: Commit, files: List) -> int:
        """Сохраняет список изменённых файлов коммита.

        Повторный вызов не создаёт дублей: уникальный индекс (commit_id, path).
        """
        if not files:
            return 0

        # Коммит должен быть сохранён: без id файлы некуда привязать.
        # Раньше здесь был бы NOT NULL на commit_id из глубины стека.
        if commit is None or not getattr(commit, "id", None):
            return 0

        existing = {
            f.path
            for f in (
                await db.execute(
                    select(CommitFile).where(CommitFile.commit_id == commit.id)
                )
            ).scalars().all()
        }

        added = 0
        for f in files:
            path = getattr(f, "path", None) or (f.get("path") if isinstance(f, dict) else None)
            if not path or path in existing:
                continue
            if isinstance(f, dict):
                db.add(
                    CommitFile(
                        commit_id=commit.id,
                        path=path,
                        previous_path=f.get("previous_path"),
                        status=f.get("status", "modified"),
                        additions=f.get("additions", 0),
                        deletions=f.get("deletions", 0),
                    )
                )
            else:
                db.add(
                    CommitFile(
                        commit_id=commit.id,
                        path=path,
                        previous_path=getattr(f, "previous_path", None),
                        status=getattr(f, "status", "modified"),
                        additions=getattr(f, "additions", 0) or 0,
                        deletions=getattr(f, "deletions", 0) or 0,
                    )
                )
            added += 1

        if added:
            await db.flush()
        return added

    @staticmethod
    async def record_link(
        db: AsyncSession,
        task_id: int,
        link_type: str,
        target_id: int,
        source: str = "regex",
        confidence: float | None = None,
        created_by_id: int | None = None,
    ) -> None:
        """Фиксирует провенанс связи задачи с объектом Git.

        Раньше связь была «голая» Many-to-Many, поэтому было нельзя понять,
        откуда она взялась, и нельзя было отозвать одну, не удаляя общую строку.
        """
        existing = (
            await db.execute(
                select(TaskGitLink).where(
                    TaskGitLink.task_id == task_id,
                    TaskGitLink.link_type == link_type,
                    TaskGitLink.target_id == target_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            # Отклонённое предложение, к которому человек вернулся
            # вручную, снова становится подтверждённой связью: строка
            # одна и та же (уникальный индекс не дал бы создать вторую),
            # и без смены статуса коммит остался бы невидимым.
            if existing.status == "rejected":
                existing.status = "confirmed"
                existing.source = source
                existing.created_by_id = created_by_id
                existing.reason = "Привязано вручную"
            # Решение человека не должно затираться последующей автоматикой.
            # Признак того, что человек связь трогал, — заполненный
            # created_by_id, а не строка source: у подтверждённой связи,
            # найденной моделью, source остаётся "model" и защищать его
            # по строке нельзя — иначе регулярка переписала бы провенанс.
            human_touched = existing.created_by_id is not None or existing.source == "manual"
            if not human_touched:
                existing.source = source
            if created_by_id is not None and existing.created_by_id is None:
                existing.created_by_id = created_by_id
            # Уверенность модели не обнуляется, если новое значение не передано:
            # ручное подтверждение дополняет связь, а не затирает оценку.
            if confidence is not None:
                existing.confidence = confidence
            return

        db.add(
            TaskGitLink(
                task_id=task_id,
                link_type=link_type,
                target_id=target_id,
                source=source,
                confidence=confidence,
                created_by_id=created_by_id,
            )
        )

    @staticmethod
    async def upsert_commit(
        db: AsyncSession, repo: GitRepository, commit_dto: GitCommitDTO
    ) -> Commit:
        """Сохраняет коммит, даже если на него никто не ссылался.

        Раньше link_commit_to_tasks возвращался сразу, если в сообщении
        не было номера задачи, и коммит просто терялся. Из-за этого не
        работала ни привязка по смыслу (модели нечего анализировать), ни
        выбор «Перепривязать» в карточке задачи: там тоже нужен список
        коммитов проекта, а в базе их не было.
        """
        author_user_id = await TaskLinkingService.resolve_author_user(
            db, commit_dto.author, commit_dto.email, repo.id
        )

        result = await db.execute(
            select(Commit).filter(
                Commit.sha == commit_dto.sha, Commit.repository_id == repo.id
            )
        )
        commit = result.scalar_one_or_none()

        if not commit:
            commit = Commit(
                repository_id=repo.id,
                sha=commit_dto.sha,
                message=commit_dto.message,
                author=commit_dto.author,
                author_email=commit_dto.email,
                author_id=author_user_id,
                timestamp=commit_dto.timestamp,
                meta_data={"url": commit_dto.url},
            )
            db.add(commit)
            await db.flush()  # Получаем ID
        else:
            if author_user_id and not commit.author_id:
                commit.author_id = author_user_id
            # Email мог прийти позже — например, после повторной сверки
            if commit_dto.email and not commit.author_email:
                commit.author_email = commit_dto.email

        if commit_dto.files:
            await TaskLinkingService.save_commit_files(db, commit, commit_dto.files)

        return commit

    @staticmethod
    async def link_commit_to_tasks(db: AsyncSession, repo: GitRepository, commit_dto: GitCommitDTO) -> List[int]:
        """Связывает коммит с задачами на основе его сообщения.

        Порядок: сначала регулярки, и только если они ничего не нашли —
        модель трассировки. Регулярки точны и бесплатны, модель дороже
        и может ошибиться, поэтому она не должна перебивать найденное
        ими и не должна заменять их вообще.
        """
        task_ids = await TaskLinkingService.extract_task_ids(commit_dto.message)

        commit = await TaskLinkingService.upsert_commit(db, repo, commit_dto)

        # Коммит сохраняем всегда, даже если задачи не нашлось: без него
        # нечего ни анализировать моделью, ни показать в «Перепривязать».
        if not task_ids:
            await db.commit()
            return []

        # Проверяем принадлежность задач проекту
        linked: List[int] = []
        for task_id in task_ids:
            res = await db.execute(
                select(Task).filter(Task.id == task_id, Task.project_id == repo.project_id)
            )
            task = res.scalar_one_or_none()
            if task:
                if commit not in task.commits:
                    task.commits.append(commit)
                await TaskLinkingService.record_link(
                    db, task.id, "commit", commit.id, source="regex"
                )
                linked.append(task_id)

        await db.commit()

        # Тип коммита считаем после коммита и отдельным шагом: это
        # украшение, и его отсутствие не должно отменять привязку.
        await TaskLinkingService.classify_new_links(db, [commit.id] if linked else [])

        return linked

    @staticmethod
    async def classify_new_links(db: AsyncSession, commit_ids: List[int]) -> None:
        """Определяет тип только что привязанных коммитов.

        Отдельным шагом и после коммита: тип — украшение, и его
        отсутствие не должно отменять саму привязку.
        """
        if not commit_ids:
            return
        try:
            from app.git.commit_types import classify_linked_commits

            await classify_linked_commits(db, commit_ids, flush=False)
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось определить типы коммитов: %s", exc)

    @staticmethod
    async def link_branch_to_tasks(db: AsyncSession, repo: GitRepository, branch_name: str) -> List[int]:
        """Связывает ветку с задачами на основе её имени"""
        task_ids = await TaskLinkingService.extract_task_ids(branch_name)
        if not task_ids:
            return []

        # Ищем или создаем ветку
        result = await db.execute(select(Branch).filter(Branch.name == branch_name, Branch.repository_id == repo.id))
        branch = result.scalar_one_or_none()
        
        if not branch:
            branch = Branch(repository_id=repo.id, name=branch_name)
            db.add(branch)
            await db.flush()

        linked_task_ids = []
        for task_id in task_ids:
            res = await db.execute(select(Task).filter(Task.id == task_id, Task.project_id == repo.project_id))
            task = res.scalar_one_or_none()
            if task:
                if branch not in task.branches:
                    task.branches.append(branch)
                await TaskLinkingService.record_link(
                    db, task.id, "branch", branch.id, source="branch"
                )
                linked_task_ids.append(task_id)

        await db.commit()
        return linked_task_ids

def _normalize_ci(conclusion: str | None, status: str | None = None) -> str | None:
    """Приводит вывод CI провайдера к единому виду: success/failure/pending."""
    value = (conclusion or status or "").lower()
    if not value:
        return None
    if value in ("success", "neutral", "skipped"):
        return "success"
    if value in ("failure", "error", "timed_out", "cancelled", "action_required"):
        return "failure"
    if value in ("pending", "in_progress", "queued", "waiting", "requested"):
        return "pending"
    return None


class GitEventService:
    @staticmethod
    async def process_event(
        db: AsyncSession,
        event: GitEvent,
        signature_verified: bool = False,
        delivery_id: str | None = None,
    ):
        """Обработка Unified Git Event"""
        result = await db.execute(select(GitRepository).filter(GitRepository.id == event.repository_id))
        repo = result.scalar_one_or_none()
        if not repo:
            return {"status": "repo_not_found"}

        # Идемпотентность: провайдеры повторяют доставку при таймаутах.
        # Повтор с тем же delivery_id не должен дважды двигать задачи по доске.
        if delivery_id:
            dup = await db.execute(
                select(GitEventLog.id).where(
                    GitEventLog.repository_id == repo.id,
                    GitEventLog.delivery_id == delivery_id,
                )
            )
            if dup.scalar_one_or_none() is not None:
                logger.info(
                    "Дублирующая доставка %s для репозитория %s — пропускаем",
                    delivery_id, repo.id,
                )
                return {"status": "duplicate", "delivery_id": delivery_id}

        # 1. Логируем входящее событие
        log = GitEventLog(
            repository_id=repo.id,
            provider=repo.provider,
            event_type=event.type,
            payload=event.model_dump(),
            signature_verified=signature_verified,
            delivery_id=delivery_id,
        )
        db.add(log)
        await db.flush()

        # Для индикатора «доставка работает»: время последнего события
        repo.last_event_at = datetime.now(timezone.utc)

        linked_any = False
        all_task_ids = set()

        if event.type == "push":
            # Обработка коммитов
            for commit_dto in event.commits:
                task_ids = await TaskLinkingService.link_commit_to_tasks(db, repo, commit_dto)
                if task_ids:
                    linked_any = True
                    all_task_ids.update(task_ids)
            
            # Обработка ветки
            if event.branch:
                task_ids = await TaskLinkingService.link_branch_to_tasks(db, repo, event.branch)
                if task_ids:
                    linked_any = True
                    all_task_ids.update(task_ids)

        elif event.type == "pull_request":
            # Обработка PR
            pr_data = event.pull_request
            if pr_data:
                # Пытаемся найти задачи в заголовке или описании PR
                task_ids = await TaskLinkingService.extract_task_ids(pr_data.get("title", ""))
                task_ids.extend(await TaskLinkingService.extract_task_ids(pr_data.get("description", "") or ""))
                all_task_ids.update(task_ids)
                
                # Также ищем задачи в ветке PR
                if pr_data.get("source_branch"):
                    branch_tasks = await TaskLinkingService.extract_task_ids(pr_data.get("source_branch"))
                    all_task_ids.update(branch_tasks)

                if all_task_ids:
                    linked_any = True
                
                await GitEventService.process_pull_request(db, repo, pr_data, list(all_task_ids))

        elif event.type == "check_run":
            # Статус CI привязываем ко всем открытым PR этой ветки
            branch = event.branch
            if branch:
                prs = (
                    await db.execute(
                        select(PullRequest).where(
                            PullRequest.repository_id == repo.id,
                            PullRequest.source_branch == branch,
                        )
                    )
                ).scalars().all()
                conclusion = (event.check or {}).get("conclusion")
                status = (event.check or {}).get("status", "completed")
                prs = list(prs)
                for pr in prs:
                    pr.ci_status = _normalize_ci(conclusion, status)
                    pr.ci_url = (event.check or {}).get("url") or pr.ci_url

        elif event.type == "pull_request_review":
            # Ревьюер: отмечаем, что ответ пришёл
            reviewer = (event.review or {}).get("reviewer")
            if reviewer and event.pull_request:
                external_id = event.pull_request.get("external_id")
                if external_id is not None:
                    pr_row = (
                        await db.execute(
                            select(PullRequest).filter(
                                PullRequest.repository_id == repo.id,
                                PullRequest.external_id == external_id,
                            )
                        )
                    ).scalar_one_or_none()
                    if pr_row:
                        current = list(pr_row.reviewers or [])
                        current = [r for r in current if r.get("login") != reviewer]
                        current.append(
                            {
                                "login": reviewer,
                                "state": (event.review or {}).get("state", ""),
                            }
                        )
                        pr_row.reviewers = current

        # 2. Если ничего не привязали - сохраняем в Unlinked
        if not linked_any:
            external_id = None
            if event.type == "push" and event.commits:
                external_id = event.commits[0].sha
            elif event.type == "pull_request" and event.pull_request:
                external_id = str(event.pull_request.get("external_id"))

            unlinked = UnlinkedGitEvent(
                repository_id=repo.id,
                event_type=event.type,
                external_id=external_id,
                payload=event.model_dump()
            )
            db.add(unlinked)
        
        await db.commit()

        return {
            "status": "processed",
            "linked": bool(linked_any),
            "task_ids": sorted(all_task_ids),
        }

    @staticmethod
    async def process_pull_request(db: AsyncSession, repo: GitRepository, pr_data: Dict, task_ids: List[int]):
        """Обновление информации о PR и автоматизация статусов задач"""
        external_id = pr_data.get("external_id")
        
        result = await db.execute(
            select(PullRequest).filter(
                PullRequest.external_id == external_id, 
                PullRequest.repository_id == repo.id
            )
        )
        pr = result.scalar_one_or_none()
        
        state_map = {
            "open": PRState.OPEN,
            "closed": PRState.CLOSED,
            "merged": PRState.MERGED
        }
        
        new_state = state_map.get(pr_data.get("state"), PRState.OPEN)
        is_merged = pr_data.get("merged", False)
        if is_merged:
            new_state = PRState.MERGED

        if not pr:
            pr = PullRequest(
                repository_id=repo.id,
                external_id=external_id,
                title=pr_data.get("title"),
                state=new_state,
                url=pr_data.get("url"),
                source_branch=pr_data.get("source_branch"),
                target_branch=pr_data.get("target_branch"),
            )
            db.add(pr)
            # Нужен id для записи провенанса связи (task_git_links).
            # Без flush pr.id остаётся None и вставка падает по NOT NULL.
            await db.flush()
        else:
            pr.state = new_state
            if pr_data.get("title"):
                pr.title = pr_data["title"]

        # Данные для блока «Разработка» в карточке задачи.
        # Заполняются только если пришли, чтобы не затирать старые значения
        # событиями, которые этих полей не содержат.
        for field in ("url", "source_branch", "target_branch"):
            if pr_data.get(field):
                setattr(pr, field, pr_data[field])

        for field in ("additions", "deletions", "changed_files"):
            if pr_data.get(field) is not None:
                setattr(pr, field, pr_data[field] or 0)

        if pr_data.get("reviewers") is not None:
            pr.reviewers = pr_data["reviewers"]
        if pr_data.get("ci_status"):
            pr.ci_status = pr_data["ci_status"]
        if pr_data.get("ci_url"):
            pr.ci_url = pr_data["ci_url"]
        if pr_data.get("merged_at"):
            pr.merged_at = pr_data["merged_at"]
        
        # Автоматизация статусов задач
        if task_ids:
            for task_id in task_ids:
                await TaskLinkingService.record_link(
                    db, task_id, "pull_request", pr.id, source="pr"
                )
                if is_merged:
                    # PR Merged -> Задачи в Done
                    await TaskStatusService.move_task_to_status(db, task_id, "DONE")
                elif new_state == PRState.OPEN:
                    # PR Opened -> Задачи в Review
                    await TaskStatusService.move_task_to_status(db, task_id, "REVIEW")
        
        await db.commit()

class SyncService:
    """Периодическая сверка состояния репозиториев через API.

    Нужна потому, что вебхуки теряются: провайдеры не гарантируют доставку,
    а при таймаутах повторяют её конечное число раз.
    """

    @staticmethod
    async def sync_all_repositories():
        """Синхронизация всех подключенных репозиториев"""
        async with SessionLocal() as db:
            result = await db.execute(
                select(GitRepository).where(GitRepository.is_active.is_(True))
            )
            repositories = result.scalars().all()
            logger.info("Сверка запущена для %d репозиториев", len(repositories))

            for repo in repositories:
                try:
                    await SyncService.sync_repository(db, repo)
                except Exception:
                    # Ошибка одного репозитория не должна ронять весь цикл
                    logger.exception("Сбой синхронизации репозитория %s", repo.id)
                    await db.rollback()

    @staticmethod
    async def sync_repository(db: AsyncSession, repo: GitRepository) -> dict:
        """Синхронизация одного репозитория.

        Ошибки больше не глотаются: они попадают в last_sync_status /
        last_sync_error, поэтому индикатор состояния показывает правду.
        """
        if not repo.is_active:
            return {"status": "skipped", "reason": "inactive"}

        try:
            # Токен мог истечь: у OAuth-провайдеров он живёт считаные часы
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

            provider = get_git_provider(
                repo.provider, token=token, api_url=repo.api_url
            )

            # Коммиты
            #
            # Ветку обязательно передаём явно: дефолты в провайдерах
            # расходятся (main у GitLab и Gitea, master у Bitbucket),
            # и запрос уходил в несуществующую ветку. GitLab на такой
            # запрос отвечает 404, get_commits молча возвращает [],
            # и синхронизация рапортовала status=ok при нуле коммитов.
            branch = (repo.default_branch or "").strip()

            # Ветки запрашиваем ДО коммитов: они нужны, чтобы проверить,
            # что default_branch вообще существует. GitLab на несуществующую
            # ветку отвечает 200 с пустым списком, а не 404, поэтому
            # по одному ответу get_commits расхождение не видно.
            branches = await provider.get_branches(repo.id)

            if branch and branches and branch not in branches:
                # Раньше это молча давало status=ok при нуле коммитов.
                # Теперь попадает в last_sync_error и видно в интерфейсе.
                available = ", ".join(sorted(branches)[:5])
                raise GitAPIError(
                    f"Ветка по умолчанию «{branch}» не найдена в репозитории. "
                    f"Доступные ветки: {available}. "
                    f"Исправьте default_branch у репозитория."
                )

            if not branch and branches:
                # Ветка в базе не задана, а ветки в репозитории есть:
                # берём первую и запоминаем, чтобы не гадать каждый раз.
                branch = sorted(branches)[0]
                repo.default_branch = branch
                logger.info(
                    "Репозиторий %s: ветка по умолчанию не задана, беру «%s»",
                    repo.id, branch,
                )

            commits = await provider.get_commits(
                repo.id, branch=branch, limit=settings.GIT_SYNC_PAGE_SIZE
            )
            linked = 0
            for commit_dto in commits:
                linked += len(
                    await TaskLinkingService.link_commit_to_tasks(db, repo, commit_dto)
                )

            for branch_name in branches:
                await TaskLinkingService.link_branch_to_tasks(db, repo, branch_name)

            # Pull Requests: раньше был помечен TODO и не подтягивался,
            # из-за чего потерянный вебхук о merge необратимо ломал статус задачи
            prs = await provider.get_pull_requests(repo.id)
            for pr_data in prs:
                await GitEventService.process_pull_request(db, repo, pr_data, [])

            repo.last_sync_status = "ok"
            repo.last_sync_error = None
            repo.last_sync_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Репозиторий %s: коммитов %d, веток %d, PR %d, привязок %d",
                repo.id, len(commits), len(branches), len(prs), linked,
            )

            # Тяжёлая часть — в фон.
            #
            # Раньше трассировка шла прямо здесь, и её пришлось выключить
            # флагом: модель на CPU даёт сотни миллисекунд на коммит, и
            # кнопка «Синхронизировать» висела бы минутами. Но выключать
            # функцию — не решение: пользователь видел пустой интерфейс и
            # думал, что связывание не работает. Теперь доработка идёт
            # отдельной задачей, а её прогресс виден в интерфейсе.
            enrichment = schedule_enrichment(repo.id)

            return {
                "status": "ok",
                "commits": len(commits),
                "branches": len(branches),
                "pull_requests": len(prs),
                "linked": linked,
                # Что именно запущено дальше: пользователь должен понимать,
                # что сейчас будет, а не гадать.
                "enrichment": enrichment,
            }

        except Exception as exc:
            repo.last_sync_status = "error"
            repo.last_sync_error = f"{type(exc).__name__}: {exc}"[:500]
            repo.last_sync_at = datetime.now(timezone.utc)
            try:
                await db.commit()
            except Exception:
                await db.rollback()
            logger.warning(
                "Ошибка синхронизации репозитория %s (%s): %s",
                repo.id, type(exc).__name__, exc,
            )
            return {"status": "error", "error": str(exc)}


# Сколько ручной запрос синхронизации готов ждать фоновую доработку.
#
# Потолок нужен по двум причинам. Первая — терпение: пользователь не должен
# смотреть на крутящийся индикатор минутами. Вторая — защита: запрос держит
# соединение с БД, и при большом репозитории ждать разбора всех коммитов
# бессмысленно. Не дождавшись, отдаём прогресс и разрешаем интерфейсу
# показать «идёт разбор», а результат подтянется позже.
ENRICHMENT_WAIT_SECONDS = 90.0


# Репозитории, для которых доработка уже идёт. Нужен, чтобы периодическая
# сверка (раз в 5 минут) не плодила параллельные прогоны модели: два
# одновременных разбора одного репозитория делят и так негустой CPU.
_enrichment_running: set[int] = set()


def schedule_enrichment(repo_id: int) -> dict:
    """Запускает фоновое дооболнение репозитория.

    Возвращает описание того, что произойдёт, — это уходит в ответ
    синхронизации, чтобы интерфейс мог показать «идёт разбор», а не пустоту.

    Задача намеренно fire-and-forget: пользователь нажал кнопку и ждёт
    загрузки коммитов, а не минуты ожидания модели. Что он увидит дальше
    (предложения, типы, правки) — отслеживается по enrichment_status.
    """
    steps: list[str] = []
    if settings.GIT_FETCH_PATCHES:
        steps.append("patches")
    if settings.CODE_MODEL_ENABLED and settings.GIT_TRACE_ON_SYNC:
        steps.append("trace")

    if not steps:
        return {
            "started": False,
            "reason": "disabled",
            "steps": [],
            "hint": "GIT_FETCH_PATCHES и GIT_TRACE_ON_SYNC выключены",
        }

    if repo_id in _enrichment_running:
        return {
            "started": False,
            "reason": "already_running",
            "steps": steps,
            "hint": "Обработка уже идёт",
        }

    try:
        asyncio.create_task(_enrich_repository(repo_id))
        return {"started": True, "reason": None, "steps": steps, "hint": None}
    except RuntimeError:
        # Нет работающего event loop — доработка не запустится, но
        # синхронизация уже прошла и это не повод её считать проваленной.
        logger.warning(
            "Не удалось запланировать доработку репозитория %s: нет event loop",
            repo_id,
        )
        return {
            "started": False,
            "reason": "no_event_loop",
            "steps": steps,
            "hint": "Фоновая обработка требует запущенного приложения",
        }


async def _enrich_repository(repo_id: int) -> None:
    """Тяжёлая часть: правки, трассировка, типы. Работает в фоне.

    Идёт по шагам, а не «всё сразу», по двум причинам:

      * правки — отдельный запрос к API провайдера на коммит, поэтому
        их порция ограничена и между запросами пауза (GIT_PATCH_BACKFILL_DELAY),
        чтобы не упереться в rate limit;
      * трассировка ходит в модель, а модель на CPU медленная — её тоже
        ограничиваем за один проход.

    Прогресс пишется в БД, поэтому интерфейс видит его без опроса задач.
    """
    _enrichment_running.add(repo_id)
    try:
        async with SessionLocal() as db:
            repo = (
                await db.execute(select(GitRepository).where(GitRepository.id == repo_id))
            ).scalar_one_or_none()
            if repo is None:
                return

            steps_done: list[str] = []
            repo.enrichment_status = "running"
            repo.enrichment_error = None
            repo.enrichment_done = 0
            repo.enrichment_at = datetime.now(timezone.utc)
            await db.commit()

            try:
                # Шаг 1: тексты изменений. Модель без них видит только
                # имена файлов — это резко ухудшает трассировку.
                if settings.GIT_FETCH_PATCHES:
                    from app.git.patches import backfill_commit_patches

                    repo.enrichment_total = settings.GIT_PATCH_BACKFILL_LIMIT
                    await db.commit()

                    stats = await backfill_commit_patches(
                        db, repo, limit=settings.GIT_PATCH_BACKFILL_LIMIT
                    )
                    # filled, а не examined: «просмотрено» может включать
                    # уже заполненные, и прогресс-бар прыгал бы назад.
                    repo.enrichment_done = int(stats.get("filled", 0))
                    await db.commit()
                    steps_done.append("patches")
                    logger.info(
                        "Репозиторий %s: правки %s", repo_id, stats
                    )

                # Шаг 2: трассировка по смыслу. Только непривязанные
                # коммиты — уже привязанные регулярками повторно не трогаем.
                if settings.CODE_MODEL_ENABLED and settings.GIT_TRACE_ON_SYNC:
                    from app.git.tracing import suggest_for_unlinked_commits

                    repo.enrichment_total = settings.GIT_TRACE_SYNC_LIMIT
                    await db.commit()

                    trace_stats = await suggest_for_unlinked_commits(
                        db, repo, settings.GIT_TRACE_SYNC_LIMIT
                    )
                    repo.enrichment_done = int(trace_stats.get("examined", 0))
                    steps_done.append("trace")
                    logger.info(
                        "Репозиторий %s: трассировка %s", repo_id, trace_stats
                    )

                # Шаг 3: типы. Нужны только привязанным коммитам — непривязанные
                # в карточке задачи не видны, и тратить на них модель
                # незачем. Дозаполняем те, у кого тип не посчитался
                # в момент привязки (модель тогда ещё не прогревалась).
                if settings.CODE_MODEL_ENABLED:
                    from app.git.commit_types import backfill_commit_types

                    type_stats = await backfill_commit_types(
                        db, repo_id=repo_id, limit=settings.GIT_TRACE_SYNC_LIMIT
                    )
                    steps_done.append("types")
                    logger.info(
                        "Репозиторий %s: типы %s", repo_id, type_stats
                    )

                repo.enrichment_status = "done"
                repo.enrichment_at = datetime.now(timezone.utc)
                await db.commit()

            except Exception as exc:  # noqa: BLE001 — фон не должен ронять сервис
                await db.rollback()
                logger.exception(
                    "Ошибка дооболнения репозитория %s на шаге %s",
                    repo_id, steps_done or ["patches"],
                )
                # Пишем ошибку отдельной сессией: текущая может быть
                # в непригодном состоянии после сбоя.
                async with SessionLocal() as err_db:
                    target = (
                        await err_db.execute(
                            select(GitRepository).where(GitRepository.id == repo_id)
                        )
                    ).scalar_one_or_none()
                    if target is not None:
                        target.enrichment_status = "error"
                        target.enrichment_error = f"{type(exc).__name__}: {exc}"[:500]
                        target.enrichment_at = datetime.now(timezone.utc)
                        await err_db.commit()
    finally:
        _enrichment_running.discard(repo_id)


async def start_periodic_storage_purge(interval_seconds: int | None = None):
    """Периодическая очистка корзины и осиротевших файлов.

    Раньше за это отвечали задачи Celery, но расписание beat не было
    задано вовсе, задачи не регистрировались и ниоткуда не вызывались:
    то есть корзина не очищалась никогда. Цикл на asyncio сделан так
    же, как периодическая сверка Git, — этот механизм в проекте
    рабочий.
    """
    from app.storage import purge as purge_mod
    from app.storage import settings as storage_settings

    logger.info("Периодическая очистка корзины запущена")

    while True:
        try:
            await asyncio.sleep(interval_seconds or 3600)
            # Настройки перечитываются каждый проход: срок хранения и
            # период может поменять администратор, и ждать перезапуска
            # он не должен.
            async with SessionLocal() as db:
                await storage_settings.refresh(db)
                if not storage_settings.auto_purge_enabled():
                    logger.debug("Автоочистка выключена, проход пропущен")
                    continue

                result = await purge_mod.cleanup_orphans(db)
                if result["removed"]:
                    logger.info("Убрано неприкреплённых файлов: %s", result["removed"])

                result = await purge_mod.purge_trash(db)
                if result["removed"]:
                    logger.info(
                        "Очищено корзины: %s записей, %s байт",
                        result["removed"], result["freed_bytes"],
                    )
        except asyncio.CancelledError:
            logger.info("Периодическая очистка корзины остановлена")
            raise
        except Exception:
            logger.exception("Необработанная ошибка цикла очистки корзины")
            await asyncio.sleep(60)


async def start_periodic_sync(interval_seconds: int | None = None):
    """Фоновая синхронизация (reconcile) с настраиваемым интервалом."""
    if not settings.GIT_SYNC_ENABLED:
        logger.info("Периодическая синхронизация отключена (GIT_SYNC_ENABLED=false)")
        return

    interval = interval_seconds or settings.GIT_SYNC_INTERVAL_SECONDS
    while True:
        try:
            await SyncService.sync_all_repositories()
        except asyncio.CancelledError:
            logger.info("Фоновая синхронизация остановлена")
            raise
        except Exception:
            logger.exception("Необработанная ошибка цикла синхронизации")
        await asyncio.sleep(interval)
