from typing import List, Dict, Optional
from datetime import datetime, timezone
import re
# httpx используется в get_commits, get_commit_files, get_branches,
# create_branch и register_webhook, но импорта не было: любой вызов
# к API GitLab падал с NameError. Провайдер был полностью нерабочим.
import httpx
from app.git.base import GitProvider, GitEvent, GitCommitDTO, GitFileDTO
from app.git.http_client import GitHTTPClient, GitAPIError

class GitLabProvider(GitProvider):
    def __init__(self, token: str = None, host: str = "https://gitlab.com"):
        self.token = token
        self.host = host.rstrip("/")
        self.api_url = f"{self.host}/api/v4"
        self.headers = {
            "User-Agent": "AI-PM-System"
        }
        if self.token:
            self.headers["PRIVATE-TOKEN"] = self.token
        self.client = GitHTTPClient(self.api_url, self.headers)

    def _parse_repo_url(self, url: str) -> Optional[str]:
        """
        Извлекает ID проекта или path из URL. 
        """
        # Убираем протокол
        path = url.split("//")[-1]
        # Убираем домен (первую часть до первого /)
        if "/" in path:
            path = path.split("/", 1)[-1]
        
        if path.endswith(".git"):
            path = path[:-4]
            
        # Заменяем / на %2F для использования в API
        return path.replace("/", "%2F")

    async def _get_repo_by_id(self, repository_id: int):
        from app.core.database import SessionLocal
        from app.git.models import GitRepository
        from sqlalchemy import select
        async with SessionLocal() as db:
            res = await db.execute(select(GitRepository).filter(GitRepository.id == repository_id))
            return res.scalar_one_or_none()

    async def get_commits(self, repository_id: int, branch: str = "main", limit: int = 100) -> List[GitCommitDTO]:
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return []
        
        api_url = repo_obj.api_url or self.api_url
        project_path = self._parse_repo_url(repo_obj.url)
        if not project_path: return []

        async with httpx.AsyncClient(headers=self.headers) as client:
            url = f"{api_url}/projects/{project_path}/repository/commits"
            params = {"ref_name": branch, "per_page": limit}
            
            response = await client.get(url, params=params)
            if response.status_code != 200:
                # Раньше здесь стоял print и возврат []: синхронизация
                # рапортовала status=ok при нуле коммитов, и заметить
                # потерю данных было негде. Ошибку нужно поднимать.
                #
                # Отдельно про 404: GitLab так отвечает на несуществующую
                # ветку — почти всегда default_branch в базе не совпадает
                # с веткой в репозитории.
                hint = ""
                if response.status_code == 404 and branch:
                    hint = (
                        f" (ветка «{branch}» не найдена — проверьте "
                        f"default_branch у репозитория)"
                    )
                raise GitAPIError(
                    f"GitLab API {response.status_code}{hint}: {response.text[:200]}"
                )
            
            data = response.json()
            commits = []
            for item in data:
                commits.append(GitCommitDTO(
                    sha=item["id"],
                    message=item["message"],
                    author=item["author_name"],
                    email=item.get("author_email"),
                    timestamp=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                    url=f"{repo_obj.url.rstrip('.git')}/-/commit/{item['id']}"
                ))
            return commits

    async def get_pull_requests(self, repository_id: int) -> List[Dict]:
        """В GitLab это Merge Requests"""
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return []
        
        api_url = repo_obj.api_url or self.api_url
        project_path = self._parse_repo_url(repo_obj.url)
        if not project_path: return []

        async with httpx.AsyncClient(headers=self.headers) as client:
            url = f"{api_url}/projects/{project_path}/merge_requests"
            params = {"state": "all", "per_page": 50}
            
            response = await client.get(url, params=params)
            if response.status_code != 200: return []
            
            data = response.json()
            results = []
            for mr in data:
                # Маппинг состояний GitLab на наши PRState
                state = "open"
                if mr["state"] == "merged": state = "merged"
                elif mr["state"] == "closed": state = "closed"
                
                results.append({
                    "external_id": mr["iid"],
                    "title": mr["title"],
                    "state": state,
                    "url": mr["web_url"],
                    "source_branch": mr["source_branch"],
                    "target_branch": mr["target_branch"],
                    "merged": mr["state"] == "merged"
                })
            return results
        
    async def get_commit_files(self, repository_id: int, sha: str) -> List[GitFileDTO]:
        """Файлы коммита с правками.

        У GitLab правки лежат в отдельном эндпоинте
        /repository/commits/{sha}/diff, а не в ответе по самому коммиту.
        """
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj:
            return []

        api_url = repo_obj.api_url or self.api_url
        project_path = self._parse_repo_url(repo_obj.url)
        if not project_path:
            return []

        async with httpx.AsyncClient(headers=self.headers) as client:
            resp = await client.get(
                f"{api_url}/projects/{project_path}/repository/commits/{sha}/diff"
            )
            if resp.status_code != 200:
                return []

        files: List[GitFileDTO] = []
        for f in resp.json():
            old_path = f.get("old_path")
            new_path = f.get("new_path")
            if f.get("new_file"):
                status = "added"
            elif f.get("deleted_file"):
                status = "removed"
            elif f.get("renamed_file"):
                status = "renamed"
            else:
                status = "modified"

            diff = f.get("diff")
            files.append(
                GitFileDTO(
                    path=new_path or old_path,
                    previous_path=old_path if status == "renamed" else None,
                    status=status,
                    patch=diff,
                    patch_truncated=diff is None,
                )
            )
        return files

    async def get_branches(self, repository_id: int) -> List[str]:
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return []
        
        api_url = repo_obj.api_url or self.api_url
        project_path = self._parse_repo_url(repo_obj.url)
        if not project_path: return []

        async with httpx.AsyncClient(headers=self.headers) as client:
            url = f"{api_url}/projects/{project_path}/repository/branches"
            response = await client.get(url)
            if response.status_code != 200: return []
            
            return [b["name"] for b in response.json()]

    async def create_branch(self, repository_id: int, branch_name: str, base_branch: str = "main"):
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return
        
        api_url = repo_obj.api_url or self.api_url
        project_path = self._parse_repo_url(repo_obj.url)
        if not project_path: return

        async with httpx.AsyncClient(headers=self.headers) as client:
            url = f"{api_url}/projects/{project_path}/repository/branches"
            payload = {
                "branch": branch_name,
                "ref": base_branch
            }
            await client.post(url, params=payload)

    # ------------------------------------------------------------------ #
    # Проверка токена и регистрация вебхуков
    # ------------------------------------------------------------------ #
    async def _project_path(self, repository_id: int) -> Optional[str]:
        """Закодированный путь проекта (group%2Fsubgroup%2Fproject) для API."""
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj:
            return None
        api_url = repo_obj.api_url or self.api_url
        return self._parse_path(repo_obj.url, api_url)

    @staticmethod
    def _parse_path(url: str, api_url: str) -> Optional[str]:
        """Отрезает домен (и хост для self-hosted) от URL репозитория."""
        path = url.split("//")[-1]
        if "/" in path:
            path = path.split("/", 1)[-1]
        # У self-hosted инстанса домен может отличаться от api_url
        host = api_url.split("//")[-1].split("/")[0]
        if host and path.startswith(host + "/"):
            path = path[len(host) + 1:]
        if path.endswith(".git"):
            path = path[:-4]
        return path.replace("/", "%2F") if path else None

    async def validate_token(self) -> Dict:
        try:
            me = await self.client.get_json("/user")
            return {"ok": True, "supported": True, "username": me.get("username")}
        except GitAPIError as exc:
            return {"ok": False, "supported": True, "error": str(exc)}

    async def register_webhook(
        self,
        repository_id: int,
        callback_url: str,
        secret: str,
        events: List[str] | None = None,
    ) -> Dict:
        project_path = await self._project_path(repository_id)
        if not project_path:
            return {"supported": True, "error": "Не удалось разобрать путь проекта"}

        hook_path = f"/projects/{project_path}/hooks"

        # Не плодим дубликаты
        try:
            existing = await self.client.get_paginated(hook_path)
            for hook in existing:
                if hook.get("url") == callback_url:
                    return {
                        "id": str(hook.get("id")),
                        "url": callback_url,
                        "events": events or ["push", "merge_request"],
                        "already_exists": True,
                    }
        except GitAPIError:
            # Нет прав на чтение списка хуков — пробуем просто создать
            pass

        payload: Dict = {"url": callback_url, "token": secret, "push_events": True}
        wanted = events or ["push", "merge_request"]
        if "merge_request" in wanted:
            payload["merge_requests_events"] = True
        if "issue" in wanted:
            payload["issues_events"] = True
        if "note" in wanted:
            payload["note_events"] = True
        if "pipeline" in wanted:
            payload["pipeline_events"] = True

        created = await self.client.post_json(hook_path, json=payload)
        return {
            "id": str(created.get("id")),
            "url": callback_url,
            "events": wanted,
        }

    async def list_webhooks(self, repository_id: int) -> List[Dict]:
        project_path = await self._project_path(repository_id)
        if not project_path:
            return []
        hooks = await self.client.get_paginated(f"/projects/{project_path}/hooks")
        return [{"id": str(h.get("id")), "url": h.get("url"), "active": True} for h in hooks]

    async def delete_webhook(self, repository_id: int, webhook_id: str) -> bool:
        project_path = await self._project_path(repository_id)
        if not project_path:
            return False
        await self.client.request("DELETE", f"/projects/{project_path}/hooks/{webhook_id}")
        return True

    @staticmethod
    def _files_from_diff(diff: Dict) -> List[GitFileDTO]:
        """Разбирает объект diff из вебхука GitLab в список файлов."""
        new_path = diff.get("new_path") or ""
        old_path = diff.get("old_path") or ""
        if not new_path and not old_path:
            return []

        if diff.get("new_file"):
            status = "added"
        elif diff.get("deleted_file"):
            status = "removed"
        elif diff.get("renamed_file"):
            status = "renamed"
        else:
            status = "modified"

        return [
            GitFileDTO(
                path=new_path or old_path,
                previous_path=old_path if status == "renamed" else None,
                status=status,
            )
        ]

    def parse_webhook(self, repository_id: int, payload: Dict, event_type: str) -> Optional[GitEvent]:
        # В GitLab тип события передается в заголовке X-Gitlab-Event, 
        # либо в поле object_kind самого payload
        kind = payload.get("object_kind")
        
        if kind == "push":
            commits = []
            for c in payload.get("commits", []):
                commits.append(GitCommitDTO(
                    sha=c["id"],
                    message=c["message"],
                    author=c["author"]["name"],
                    email=c["author"].get("email"),
                    timestamp=datetime.fromisoformat(c["timestamp"].replace("Z", "+00:00")),
                    url=c["url"]
                ))
            
            # ref обычно имеет вид "refs/heads/master"
            ref = payload.get("ref", "")
            branch = ref.split("/")[-1] if "/" in ref else ref

            return GitEvent(
                type="push",
                repository_id=repository_id,
                branch=branch,
                commits=commits,
                sender=payload.get("user_username")
            )
        
        elif kind == "merge_request":
            attr = payload.get("object_attributes", {})
            action = attr.get("action")
            
            # Состояния GitLab: opened, closed, merged, reopened
            state = attr.get("state")
            if state == "opened": mapped_state = "open"
            else: mapped_state = state

            return GitEvent(
                type="pull_request",
                repository_id=repository_id,
                branch=attr.get("source_branch"),
                pull_request={
                    "external_id": attr.get("iid"),
                    "title": attr.get("title"),
                    "state": mapped_state,
                    "url": attr.get("url"),
                    "action": action,
                    "merged": state == "merged"
                },
                sender=payload.get("user", {}).get("username")
            )
            
        return None
