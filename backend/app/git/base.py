from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

class GitFileDTO(BaseModel):
    """Файл, изменённый в коммите."""
    path: str
    previous_path: Optional[str] = None
    # added | modified | removed | renamed
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
    # Текст изменений по этому файлу (patch в терминах GitHub API).
    # Нужен моделям анализа кода: без него на вход подаётся только список
    # имён файлов, а модель училась на тексте правок.
    patch: Optional[str] = None
    # Правка не получена (большой файл, бинарник, провайдер не отдал).
    # Отличаем от пустой строки: пустая — это «изменений нет».
    patch_truncated: bool = False


class GitCommitDTO(BaseModel):
    sha: str
    message: str
    author: str
    # Email автора. Без него сопоставление с пользователем системы почти
    # не работает: в вебхуках провайдеры присылают только имя.
    email: Optional[str] = None
    timestamp: datetime
    url: Optional[str] = None
    files: List[GitFileDTO] = []
    # Сводка по коммиту (может прийти из PR)
    additions: int = 0
    deletions: int = 0


class GitEvent(BaseModel):
    type: Literal[
        "push",
        "pull_request",
        "branch_created",
        "branch_deleted",
        # CI и ревью — нужны для блока «Разработка» в карточке задачи
        "check_run",
        "status",
        "pull_request_review",
    ]
    repository_id: int
    branch: Optional[str] = None
    commits: List[GitCommitDTO] = []
    pull_request: Optional[Dict] = None
    sender: Optional[str] = None
    # Данные событий CI / ревью
    check: Optional[Dict] = None
    review: Optional[Dict] = None

class GitProvider(ABC):
    @abstractmethod
    async def get_commits(self, repository_id: int, branch: str = "main", limit: int = 10) -> List[GitCommitDTO]:
        """Получить список коммитов"""
        pass

    @abstractmethod
    async def get_branches(self, repository_id: int) -> List[str]:
        """Получить список веток"""
        pass

    @abstractmethod
    async def get_pull_requests(self, repository_id: int) -> List[Dict]:
        """Получить список PR/MR"""
        pass
        
    @abstractmethod
    async def create_branch(self, repository_id: int, branch_name: str, base_branch: str = "main"):
        """Создать ветку через API"""
        pass

    # ------------------------------------------------------------------ #
    # Тексты изменений
    # ------------------------------------------------------------------ #
    async def get_commit_files(self, repository_id: int, sha: str) -> List[GitFileDTO]:
        """Файлы коммита вместе с текстом правок.

        Отдельный запрос по каждому коммиту: списком коммитов ни один
        провайдер правки не отдаёт. По умолчанию не поддерживается —
        провайдер переопределяет метод там, где API это умеет.
        """
        return []

    @abstractmethod
    def parse_webhook(self, repository_id: int, payload: Dict, event_type: str) -> Optional[GitEvent]:
        """Преобразовать Payload вебхука в Unified GitEvent"""
        pass

    # ------------------------------------------------------------------ #
    # Регистрация вебхуков (необязательные для провайдера)
    # ------------------------------------------------------------------ #
    async def validate_token(self) -> Dict:
        """Проверяет, что токен рабочий. По умолчанию — не поддерживается."""
        return {"ok": False, "supported": False}

    async def register_webhook(
        self,
        repository_id: int,
        callback_url: str,
        secret: str,
        events: Optional[List[str]] = None,
    ) -> Dict:
        """Создаёт вебхук на стороне провайдера.

        Возвращает {"id": ..., "url": ..., "events": [...]} либо
        {"supported": False}, если провайдер этого не умеет.
        """
        return {"supported": False}

    async def list_webhooks(self, repository_id: int) -> List[Dict]:
        """Список зарегистрированных вебхуков."""
        return []

    async def delete_webhook(self, repository_id: int, webhook_id: str) -> bool:
        """Удаляет вебхук. Возвращает True при успехе."""
        return False
