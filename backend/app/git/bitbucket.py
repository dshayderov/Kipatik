from typing import List, Dict, Optional
import httpx
from datetime import datetime
from app.git.base import GitProvider, GitCommitDTO, GitEvent, GitFileDTO
from app.git.models import PRState
from sqlalchemy import select

class BitbucketProvider(GitProvider):
    def __init__(self, access_token: str = None):
        self.access_token = access_token
        self.api_url = "https://api.bitbucket.org/2.0"

    def _get_headers(self):
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _get_repo_path(self, url: str) -> str:
        # Пример: https://bitbucket.org/workspace/repo -> workspace/repo
        parts = url.rstrip("/").split("/")
        return f"{parts[-2]}/{parts[-1]}"

    async def _get_repo_by_id(self, repository_id: int):
        from app.git.models import GitRepository
        from app.core.database import SessionLocal
        async with SessionLocal() as db:
            res = await db.execute(select(GitRepository).filter(GitRepository.id == repository_id))
            return res.scalar_one_or_none()

    async def get_commits(self, repository_id: int, branch: str = "master", limit: int = 100) -> List[GitCommitDTO]:
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return []
        
        path = self._get_repo_path(repo_obj.url)
        url = f"{self.api_url}/repositories/{path}/commits/{branch}"
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._get_headers(), params={"pagelen": limit})
            if resp.status_code != 200: return []
            
            data = resp.json()
            commits = []
            for item in data.get("values", []):
                commits.append(GitCommitDTO(
                    sha=item["hash"],
                    message=item["message"],
                    author=item["author"].get("raw", "Unknown"),
                    email=item["author"].get("email"),
                    timestamp=datetime.fromisoformat(item["date"].replace("Z", "+00:00")),
                    url=item["links"]["html"]["href"]
                ))
            return commits

    async def get_commit_files(self, repository_id: int, sha: str) -> List[GitFileDTO]:
        """Файлы коммита с правками.

        У Bitbucket правки приходят в ответе по коммиту в values[],
        но у провайдера они обрезаны — отсюда patch_truncated.
        """
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj:
            return []

        path = self._get_repo_path(repo_obj.url)
        url = f"{self.api_url}/repositories/{path}/commit/{sha}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._get_headers())
            if resp.status_code != 200:
                return []
            data = resp.json()

        files: List[GitFileDTO] = []
        for f in data.get("values", []) or []:
            patch = f.get("patch")
            files.append(
                GitFileDTO(
                    path=f.get("path", ""),
                    previous_path=f.get("old_path") if f.get("status") == "renamed" else None,
                    status=f.get("status", "modified"),
                    additions=f.get("lines_added", 0) or 0,
                    deletions=f.get("lines_removed", 0) or 0,
                    patch=patch,
                    # Bitbucket всегда обрезает выдачу
                    patch_truncated=True,
                )
            )
        return files

    async def get_branches(self, repository_id: int) -> List[str]:
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return []
        
        path = self._get_repo_path(repo_obj.url)
        url = f"{self.api_url}/repositories/{path}/refs/branches"
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._get_headers())
            if resp.status_code != 200: return []
            
            data = resp.json()
            return [item["name"] for item in data.get("values", [])]

    async def get_pull_requests(self, repository_id: int) -> List[Dict]:
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return []
        
        path = self._get_repo_path(repo_obj.url)
        url = f"{self.api_url}/repositories/{path}/pullrequests"
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._get_headers())
            if resp.status_code != 200: return []
            return resp.json().get("values", [])

    async def create_branch(self, repository_id: int, branch_name: str, base_branch: str = "master"):
        # Bitbucket требует POST на /refs/branches
        repo_obj = await self._get_repo_by_id(repository_id)
        if not repo_obj: return
        
        path = self._get_repo_path(repo_obj.url)
        url = f"{self.api_url}/repositories/{path}/refs/branches"
        
        payload = {
            "name": branch_name,
            "target": {"hash": base_branch}
        }
        
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, headers=self._get_headers())

    def parse_webhook(self, repository_id: int, payload: Dict, event_type: str) -> Optional[GitEvent]:
        # Bitbucket event types: repo:push, pullrequest:created, etc.
        if event_type == "repo:push":
            # Берем последний коммит из первой измененной ветки
            changes = payload.get("push", {}).get("changes", [])
            if not changes: return None
            
            new_data = changes[0].get("new", {})
            if not new_data or new_data.get("type") != "branch": return None
            
            target = new_data.get("target", {})
            return GitEvent(
                repository_id=repository_id,
                event_type="push",
                branch=new_data.get("name"),
                commit_sha=target.get("hash"),
                commit_message=target.get("message"),
                author=target.get("author", {}).get("raw")
            )
        return None
