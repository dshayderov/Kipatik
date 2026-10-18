from fastapi import APIRouter
from app.projects.api import router as projects_router
from app.boards.api import router as boards_router
from app.tasks.api import router as tasks_router
from app.git.api import router as git_router
from app.ai.api import router as ai_router

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.admin import router as admin_router
from app.notifications.api import router as notifications_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])

# Управление нейросетевыми моделями живёт рядом с остальной админкой,
# но отдельным роутером: он отвечает за состояние процесса, а не за
# пользователей и проекты.
from app.api.v1.endpoints.admin_models import router as admin_models_router

api_router.include_router(
    admin_models_router, prefix="/admin", tags=["admin-models"]
)

# Управление хранилищем: лимиты вложений, корзина и её автоочистка.
from app.api.v1.endpoints.admin_storage import router as admin_storage_router

api_router.include_router(
    admin_storage_router, prefix="/admin", tags=["admin-storage"]
)
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(projects_router, prefix="/projects", tags=["projects"])
api_router.include_router(boards_router, prefix="/boards", tags=["boards"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(git_router, prefix="/git", tags=["git"])
api_router.include_router(ai_router, prefix="/ai", tags=["ai"])
