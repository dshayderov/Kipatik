import httpx
from typing import List, Dict, Optional
from datetime import datetime
import re
from app.git.base import GitProvider, GitEvent, GitCommitDTO, GitFileDTO

class GiteaProvider(GitProvider):
    def __init__(self, token: str = None, api_url: str = None):
        """
        api_url: Полный путь к API (например, https://gitea.example.com/api/v1)
        """
        self.token = token
        self.api_url = api_url
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "AI-PM-System"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def _parse_repo_url(self, url: str) -> Optional[tuple]:
        """Извлекает owner и repo из URL"""
        # Убираем протокол и домен, оставляем owner/repo
        # https://gitea.com/owner/repo.git -> owner, repo
        path = url.split("//")[-1].split("/", 1)[-1]
        if path.endswith(".git"):
            path = path[:-4]
        
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None

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
        
        # Используем api_url из БД если он там есть
        api_url = repo_obj.api_url or self.api_url
        if not api_url: return []

        parsed = self._parse_repo_url(repo_obj.url)
        if not parsed: return []
        owner, repo = parsed

        async with httpx.AsyncClient(headers=self.headers) as client:
            url = f"{api_url}/repos/{owner}/{repo}/commits"
            params = {"sha": branch, "limit": limit}
            
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return []
            
            data = response.json()
            commits = []
            for item in data:
                commits.append(GitCommitDTO(
                    sha=item["sha"],
                    message=item["commit"]["message"],
                    author=item["commit"]["author"]["name"],
                    email=item["commit"]["author"].get("email"),
                    timestamp=datetime.fromisoformat(item["commit"]["author"]["date"].replace("Z", "+00:00")),
                    url=item["html_url"]
                ))
            return commits

    async def get_pull_requests(self, repository_id: int) -> List[Dict]:
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return []
        
        api_url = repo_obj.api_url or self.api_url
        if not api_url: return []

        parsed = self._parse_repo_url(repo_obj.url)
        if not parsed: return []
        owner, repo = parsed

        async with httpx.AsyncClient(headers=self.headers) as client:
            url = f"{api_url}/repos/{owner}/{repo}/pulls"
            params = {"state": "all", "limit": 50}
            
            response = await client.get(url, params=params)
            if response.status_code != 200: return []
            
            data = response.json()
            results = []
            for pr in data:
                state = "open"
                if pr["merged"]: state = "merged"
                elif pr["state"] == "closed": state = "closed"

                results.append({
                    "external_id": pr["number"],
                    "title": pr["title"],
                    "state": state,
                    "url": pr["html_url"],
                    "source_branch": pr["head"]["ref"],
                    "target_branch": pr["base"]["ref"],
                    "merged": pr["merged"]
                })
            return results
        
    async def get_commit_files(self, repository_id: int, sha: str) -> List[GitFileDTO]:
        """Файлы коммита с правками.

        У Gitea правки приходят в ответе по коммиту в поле files.
        """
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj:
            return []

        api_url = repo_obj.api_url or self.api_url
        parsed = self._parse_repo_url(repo_obj.url)
        if not api_url or not parsed:
            return []
        owner, repo = parsed

        async with httpx.AsyncClient(headers=self.headers) as client:
            resp = await client.get(f"{api_url}/repos/{owner}/{repo}/git/commits/{sha}")
            if resp.status_code != 200:
                return []
            data = resp.json()

        files: List[GitFileDTO] = []
        for f in data.get("files", []) or []:
            diff = f.get("diff")
            status = "modified"
            if f.get("status") in ("added", "removed", "modified", "renamed"):
                status = f["status"]
            files.append(
                GitFileDTO(
                    path=f.get("filename", ""),
                    status=status,
                    additions=f.get("additions", 0) or 0,
                    deletions=f.get("deletions", 0) or 0,
                    patch=diff,
                    patch_truncated=diff is None,
                )
            )
        return files

    async def get_branches(self, repository_id: int) -> List[str]:
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return []
        
        api_url = repo_obj.api_url or self.api_url
        if not api_url: return []

        parsed = self._parse_repo_url(repo_obj.url)
        if not parsed: return []
        owner, repo = parsed

        async with httpx.AsyncClient(headers=self.headers) as client:
            url = f"{api_url}/repos/{owner}/{repo}/branches"
            response = await client.get(url)
            if response.status_code != 200: return []
            
            return [b["name"] for b in response.json()]

    async def create_branch(self, repository_id: int, branch_name: str, base_branch: str = "main"):
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return
        
        api_url = repo_obj.api_url or self.api_url
        if not api_url: return

        parsed = self._parse_repo_url(repo_obj.url)
        if not parsed: return
        owner, repo = parsed

        async with httpx.AsyncClient(headers=self.headers) as client:
            # Gitea API для веток может отличаться, но обычно поддерживает POST /branches
            url = f"{api_url}/repos/{owner}/{repo}/branches"
            payload = {
                "new_branch_name": branch_name,
                "old_branch_name": base_branch
            }
            await client.post(url, json=payload)

    def parse_webhook(self, repository_id: int, payload: Dict, event_type: str) -> Optional[GitEvent]:
        # Gitea вебхуки очень похожи на GitHub
        if event_type == "push":
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
            
            return GitEvent(
                type="push",
                repository_id=repository_id,
                branch=payload.get("ref", "").split("/")[-1],
                commits=commits,
                sender=payload.get("sender", {}).get("login")
            )
        
        elif event_type == "pull_request":
            action = payload.get("action")
            pr = payload.get("pull_request")
            
            return GitEvent(
                type="pull_request",
                repository_id=repository_id,
                branch=pr.get("head", {}).get("ref"),
                pull_request={
                    "external_id": pr.get("number"),
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "url": pr.get("html_url"),
                    "action": action
                },
                sender=payload.get("sender", {}).get("login")
            )
            
        return None
