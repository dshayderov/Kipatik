import re
from typing import List, Dict, Optional
from datetime import datetime, timezone

from app.git.base import GitProvider, GitEvent, GitCommitDTO, GitFileDTO
from app.git.http_client import GitHTTPClient, GitAPIError


def _parse_utc(value: str) -> datetime:
    """Разбирает ISO-время провайдера и приводит к aware-datetime."""
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class GitHubProvider(GitProvider):
    def __init__(self, token: str = None):
        self.token = token
        self.api_url = "https://api.github.com"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-PM-System",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.client = GitHTTPClient(self.api_url, headers)

    def _parse_repo_url(self, url: str) -> Optional[tuple]:
        """Извлекает owner и repo из URL типа https://github.com/owner/repo"""
        match = re.search(r"github\.com/([^/]+)/([^/.]+)", url or "")
        if match:
            return match.group(1), match.group(2)
        return None

    async def _repo_ref(self, repository_id: int) -> Optional[tuple]:
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj:
            return None
        return self._parse_repo_url(repo_obj.url)

    async def _get_repo_by_id(self, repository_id: int):
        from app.core.database import SessionLocal
        from app.git.models import GitRepository
        from sqlalchemy import select

        async with SessionLocal() as db:
            res = await db.execute(
                select(GitRepository).filter(GitRepository.id == repository_id)
            )
            return res.scalar_one_or_none()

    async def get_commits(
        self, repository_id: int, branch: str = "main", limit: int = 100
    ) -> List[GitCommitDTO]:
        ref = await self._repo_ref(repository_id)
        if not ref:
            return []
        owner, repo = ref

        raw = await self.client.get_paginated(
            f"/repos/{owner}/{repo}/commits",
            params={"sha": branch},
        )

        commits: List[GitCommitDTO] = []
        for item in raw[:limit]:
            commit = item.get("commit") or {}
            author = commit.get("author") or {}
            # В web API поле author у коммита может быть null (удалённый аккаунт)
            name = author.get("name") or (item.get("author") or {}).get("login") or "unknown"
            commits.append(
                GitCommitDTO(
                    sha=item.get("sha", ""),
                    message=commit.get("message", ""),
                    author=name,
                    email=author.get("email") or (item.get("author") or {}).get("email"),
                    timestamp=_parse_utc(author.get("date")),
                    url=item.get("html_url"),
                )
            )
        return commits

    async def get_commit_files(self, repository_id: int, sha: str) -> List[GitFileDTO]:
        """Файлы коммита с текстом правок.

        Отдельный запрос на каждый коммит: список коммитов GitHub правки
        не содержит. Именно поэтому дозаполнение ограничено по числу
        коммитов — это запрос в один и тот же лимит API.
        """
        ref = await self._repo_ref(repository_id)
        if not ref:
            return []
        owner, repo = ref

        item = await self.client.get(f"/repos/{owner}/{repo}/commits/{sha}")
        if not isinstance(item, dict):
            return []
        return self._files_from_commit_api(item)

    async def get_pull_requests(self, repository_id: int) -> List[Dict]:
        ref = await self._repo_ref(repository_id)
        if not ref:
            return []
        owner, repo = ref

        raw = await self.client.get_paginated(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc"},
        )

        results: List[Dict] = []
        for pr in raw:
            merged_at = pr.get("merged_at")
            results.append(
                {
                    "external_id": pr.get("number"),
                    "title": pr.get("title"),
                    # У закрытого PR, который смержили, вебхук приходит с open
                    "state": "merged" if merged_at else pr.get("state"),
                    "url": pr.get("html_url"),
                    "source_branch": (pr.get("head") or {}).get("ref"),
                    "target_branch": (pr.get("base") or {}).get("ref"),
                    "merged": merged_at is not None,
                    "updated_at": pr.get("updated_at"),
                    "merged_at": merged_at,
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "changed_files": pr.get("changed_files", 0),
                    "reviewers": self._reviewers_from_pr(pr),
                    "ci_status": await self._ci_status_for_head(
                        owner, repo, (pr.get("head") or {}).get("sha")
                    ),
                }
            )
        return results

    @staticmethod
    def _reviewers_from_pr(pr: Dict) -> List[Dict]:
        """Приведённые к одному виду запрошенные ревьюеры PR."""
        reviewers = []
        for r in pr.get("requested_reviewers") or []:
            if r.get("login"):
                reviewers.append({"login": r["login"], "state": "requested"})
        return reviewers

    async def _ci_status_for_head(
        self, owner: str, repo: str, head_sha: Optional[str]
    ) -> Optional[str]:
        """Сводит commit status и check-runs в один статус.

        Возвращает success | failure | pending | None (CI не настроен).
        """
        if not head_sha:
            return None

        states = []
        try:
            combined = await self.client.get_json(
                f"/repos/{owner}/{repo}/commits/{head_sha}/status"
            )
            states.append(combined.get("state"))
        except GitAPIError:
            pass

        try:
            checks = await self.client.get_json(
                f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs"
            )
            for run in checks.get("check_runs", []) or []:
                raw = run.get("conclusion") or run.get("status")
                states.append(
                    {"completed": "success", "in_progress": "pending"}.get(raw, raw)
                )
        except GitAPIError:
            pass

        states = [x for x in states if x]
        if not states:
            return None
        if any(x in ("failure", "error", "timed_out", "cancelled") for x in states):
            return "failure"
        if any(x in ("pending", "in_progress", "queued") for x in states):
            return "pending"
        if all(x == "success" for x in states):
            return "success"
        return None

    async def get_branches(self, repository_id: int) -> List[str]:
        ref = await self._repo_ref(repository_id)
        if not ref:
            return []
        owner, repo = ref

        raw = await self.client.get_paginated(f"/repos/{owner}/{repo}/branches")
        return [b["name"] for b in raw if b.get("name")]

    async def create_branch(
        self, repository_id: int, branch_name: str, base_branch: str = "main"
    ):
        ref = await self._repo_ref(repository_id)
        if not ref:
            raise GitAPIError("Не удалось определить репозиторий по URL")
        owner, repo = ref

        base = await self.client.get_json(f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}")
        sha = ((base or {}).get("object") or {}).get("sha")
        if not sha:
            raise GitAPIError(f"Ветка {base_branch} не найдена")

        # Повторное создание той же ветки не должно считаться ошибкой
        try:
            await self.client.post_json(
                f"/repos/{owner}/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            )
        except GitAPIError as exc:
            if "already exists" in str(exc).lower():
                return
            raise

    # ------------------------------------------------------------------ #
    # Проверка токена и регистрация вебхуков
    # ------------------------------------------------------------------ #
    async def validate_token(self) -> Dict:
        try:
            me = await self.client.get_json("/user")
            return {"ok": True, "supported": True, "username": me.get("login")}
        except GitAPIError as exc:
            return {"ok": False, "supported": True, "error": str(exc)}

    async def register_webhook(
        self,
        repository_id: int,
        callback_url: str,
        secret: str,
        events: List[str] | None = None,
    ) -> Dict:
        ref = await self._repo_ref(repository_id)
        if not ref:
            return {"supported": True, "error": "Не удалось разобрать URL репозитория"}
        owner, repo = ref

        wanted = events or ["push", "pull_request"]

        # Не плодим дубликаты: ищем уже существующий вебхук на наш URL
        existing = await self.client.get_paginated(f"/repos/{owner}/{repo}/hooks")
        for hook in existing:
            cfg = (hook.get("config") or {}).get("url")
            if cfg == callback_url:
                return {
                    "id": str(hook.get("id")),
                    "url": callback_url,
                    "events": hook.get("events", []),
                    "already_exists": True,
                }

        created = await self.client.post_json(
            f"/repos/{owner}/{repo}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": wanted,
                "config": {
                    "url": callback_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
        )
        return {
            "id": str(created.get("id")),
            "url": callback_url,
            "events": created.get("events", wanted),
        }

    async def list_webhooks(self, repository_id: int) -> List[Dict]:
        ref = await self._repo_ref(repository_id)
        if not ref:
            return []
        owner, repo = ref
        hooks = await self.client.get_paginated(f"/repos/{owner}/{repo}/hooks")
        return [
            {
                "id": str(h.get("id")),
                "url": (h.get("config") or {}).get("url"),
                "events": h.get("events", []),
                "active": h.get("active", True),
            }
            for h in hooks
        ]

    async def delete_webhook(self, repository_id: int, webhook_id: str) -> bool:
        ref = await self._repo_ref(repository_id)
        if not ref:
            return False
        owner, repo = ref
        await self.client.request("DELETE", f"/repos/{owner}/{repo}/hooks/{webhook_id}")
        return True

    @staticmethod
    def _files_from_push(payload: Dict, commit_sha: str) -> List[GitFileDTO]:
        """Извлекает изменённые файлы из push-события GitHub.

        GitHub присылает списки added/modified/removed прямо в вебхуке,
        поэтому дополнительные запросы к API не нужны.
        """
        files: List[GitFileDTO] = []
        for entry in payload.get("commits", []) or []:
            if entry.get("id") != commit_sha:
                continue
            for path in entry.get("added", []) or []:
                files.append(GitFileDTO(path=path, status="added"))
            for path in entry.get("modified", []) or []:
                files.append(GitFileDTO(path=path, status="modified"))
            for path in entry.get("removed", []) or []:
                files.append(GitFileDTO(path=path, status="removed"))
            break
        return files

    @staticmethod
    def _files_from_commit_api(item: Dict) -> List[GitFileDTO]:
        """Файлы из ответа /repos/{o}/{r}/commits/{sha}."""
        files: List[GitFileDTO] = []
        for f in item.get("files", []) or []:
            files.append(
                GitFileDTO(
                    path=f.get("filename", ""),
                    previous_path=f.get("previous_filename"),
                    status=f.get("status", "modified"),
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    patch=f.get("patch"),
                    # GitHub не отдаёт patch для бинарников и очень
                    # больших файлов — ключ просто отсутствует
                    patch_truncated="patch" not in f,
                )
            )
        return files

    def parse_webhook(
        self, repository_id: int, payload: Dict, event_type: str
    ) -> Optional[GitEvent]:
        if event_type == "ping":
            return None

        if event_type == "push":
            commits = []
            for c in payload.get("commits", []) or []:
                author = c.get("author") or {}
                sha = c.get("id", "")
                commits.append(
                    GitCommitDTO(
                        sha=sha,
                        message=c.get("message", ""),
                        author=author.get("name")
                        or author.get("username")
                        or "unknown",
                        email=author.get("email"),
                        timestamp=_parse_utc(c.get("timestamp")),
                        url=c.get("url"),
                        files=self._files_from_push(payload, sha),
                    )
                )
            return GitEvent(
                type="push",
                repository_id=repository_id,
                branch=(payload.get("ref") or "").split("/")[-1],
                commits=commits,
                sender=(payload.get("sender") or {}).get("login"),
            )

        if event_type in ("check_run", "check_suite", "status"):
            run = payload.get("check_run") or {}
            status_obj = payload.get("commit") or {}
            overall = run.get("conclusion") or status_obj.get("state")

            head_branch = (run.get("check_suite") or {}).get("head_branch")
            if not head_branch:
                head_branch = (status_obj.get("ref") or "").split("/")[-1] or None

            return GitEvent(
                type="check_run",
                repository_id=repository_id,
                branch=head_branch,
                sender=(payload.get("sender") or {}).get("login"),
                check={
                    "external_id": str(run.get("id") or payload.get("id") or ""),
                    "name": run.get("name") or status_obj.get("context"),
                    "status": run.get("status") or "completed",
                    "conclusion": overall,
                    "url": run.get("html_url") or status_obj.get("target_url"),
                },
            )

        if event_type == "pull_request_review":
            review = payload.get("review") or {}
            pr = payload.get("pull_request") or {}
            return GitEvent(
                type="pull_request_review",
                repository_id=repository_id,
                branch=(pr.get("head") or {}).get("ref"),
                sender=(payload.get("sender") or {}).get("login"),
                pull_request={
                    "external_id": pr.get("number"),
                    "title": pr.get("title"),
                    "state": "merged" if pr.get("merged_at") else pr.get("state", "open"),
                    "url": pr.get("html_url"),
                },
                review={
                    "reviewer": (payload.get("sender") or {}).get("login"),
                    "state": (review.get("state") or "").lower(),
                },
            )

        if event_type == "pull_request":
            pr = payload.get("pull_request")
            if not pr:
                return None
            action = payload.get("action")
            merged = pr.get("merged") is True
            state = "merged" if merged else pr.get("state", "open")
            if action == "closed" and pr.get("merged_at"):
                state = "merged"
            return GitEvent(
                type="pull_request",
                repository_id=repository_id,
                branch=(pr.get("head") or {}).get("ref"),
                pull_request={
                    "external_id": pr.get("number"),
                    "title": pr.get("title"),
                    "state": state,
                    "url": pr.get("html_url"),
                    "action": action,
                    "merged_at": pr.get("merged_at"),
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "changed_files": pr.get("changed_files", 0),
                    "reviewers": self._reviewers_from_pr(pr),
                },
                sender=(payload.get("sender") or {}).get("login"),
            )

        return None
