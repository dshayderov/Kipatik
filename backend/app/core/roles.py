from enum import Enum
from typing import Dict, List, Set

class ProjectRole(str, Enum):
    PROJECT_MANAGER = "project_manager"
    MANAGER = "manager"
    DEVELOPER = "developer"
    TESTER = "tester"
    OBSERVER = "observer"

# Права доступа (Permissions)
class Permission(str, Enum):
    # ПРОЕКТ
    PROJECT_DELETE = "project:delete"
    PROJECT_EDIT = "project:edit"
    PROJECT_VIEW = "project:view"
    PROJECT_INVITE = "project:invite"
    PROJECT_REMOVE_MEMBER = "project:remove_member"
    PROJECT_MANAGE_ROLES = "project:manage_roles"
    PROJECT_CONNECT_REPO = "project:connect_repo"
    PROJECT_MANAGE_COLUMNS = "project:manage_columns"
    PROJECT_MANAGE_LABELS = "project:manage_labels"
    PROJECT_VIEW_SETTINGS = "project:view_settings"
    PROJECT_MANAGE_RULES = "project:manage_rules"
    
    # ДОСКА
    BOARD_VIEW = "board:view"
    BOARD_MANAGE_COLUMNS = "board:manage_columns"
    BOARD_MOVE_TASK = "board:move_task"
    
    # ЗАДАЧА
    TASK_CREATE = "task:create"
    TASK_VIEW = "task:view"
    TASK_EDIT = "task:edit"
    TASK_DELETE = "task:delete"
    TASK_ASSIGN_SELF = "task:assign_self"
    TASK_ASSIGN_OTHER = "task:assign_other"
    TASK_MANAGE_PRIORITY = "task:manage_priority"
    TASK_MANAGE_DEADLINE = "task:manage_deadline"
    TASK_MANAGE_LABELS = "task:manage_labels"
    TASK_MANAGE_SUBTASKS = "task:manage_subtasks"
    TASK_CLOSE_REOPEN = "task:close_reopen"
    TASK_GIT_LINK = "task:git_link"
    TASK_AI_APPROVE = "task:ai_approve"
    
    # КОММЕНТАРИИ
    COMMENT_CREATE = "comment:create"
    COMMENT_EDIT_OWN = "comment:edit_own"
    COMMENT_DELETE_ANY = "comment:delete_any"
    
    # PR / CODE REVIEW
    PR_VIEW = "pr:view"
    PR_COMMENT = "pr:comment"
    PR_APPROVE = "pr:approve"
    PR_MERGE = "pr:merge"

# Матрица ролей и прав
ROLE_PERMISSIONS: Dict[ProjectRole, Set[Permission]] = {
    ProjectRole.PROJECT_MANAGER: set(Permission), # Все права
    
    ProjectRole.MANAGER: {
        Permission.PROJECT_EDIT,
        Permission.PROJECT_VIEW,
        Permission.PROJECT_INVITE,
        Permission.PROJECT_REMOVE_MEMBER,
        Permission.PROJECT_MANAGE_ROLES,
        Permission.PROJECT_CONNECT_REPO,
        Permission.PROJECT_MANAGE_COLUMNS,
        Permission.PROJECT_MANAGE_LABELS,
        Permission.PROJECT_VIEW_SETTINGS,
        Permission.BOARD_VIEW,
        Permission.BOARD_MANAGE_COLUMNS,
        Permission.BOARD_MOVE_TASK,
        Permission.TASK_CREATE,
        Permission.TASK_VIEW,
        Permission.TASK_EDIT,
        Permission.TASK_DELETE,
        Permission.TASK_ASSIGN_SELF,
        Permission.TASK_ASSIGN_OTHER,
        Permission.TASK_MANAGE_PRIORITY,
        Permission.TASK_MANAGE_DEADLINE,
        Permission.TASK_MANAGE_LABELS,
        Permission.TASK_MANAGE_SUBTASKS,
        Permission.TASK_CLOSE_REOPEN,
        Permission.TASK_GIT_LINK,
        Permission.TASK_AI_APPROVE,
        Permission.COMMENT_CREATE,
        Permission.COMMENT_EDIT_OWN,
        Permission.COMMENT_DELETE_ANY,
        Permission.PR_VIEW,
        Permission.PR_COMMENT,
        Permission.PR_APPROVE,
        Permission.PR_MERGE,
    },
    
    ProjectRole.DEVELOPER: {
        Permission.PROJECT_VIEW,
        Permission.PROJECT_MANAGE_LABELS, # С ограничениями (не удалять системные)
        Permission.BOARD_VIEW,
        Permission.BOARD_MOVE_TASK,
        Permission.TASK_CREATE,
        Permission.TASK_VIEW,
        Permission.TASK_EDIT, # Свои или где исполнитель
        Permission.TASK_ASSIGN_SELF,
        Permission.TASK_ASSIGN_OTHER,
        Permission.TASK_MANAGE_PRIORITY,
        Permission.TASK_MANAGE_DEADLINE,
        Permission.TASK_MANAGE_LABELS,
        Permission.TASK_MANAGE_SUBTASKS,
        Permission.TASK_CLOSE_REOPEN,
        Permission.TASK_GIT_LINK,
        Permission.TASK_AI_APPROVE,
        Permission.COMMENT_CREATE,
        Permission.COMMENT_EDIT_OWN,
        Permission.PR_VIEW,
        Permission.PR_COMMENT,
        Permission.PR_APPROVE,
        Permission.PR_MERGE, # Если разрешено в настройках
    },
    
    ProjectRole.TESTER: {
        Permission.PROJECT_VIEW,
        Permission.BOARD_VIEW,
        Permission.BOARD_MOVE_TASK,
        Permission.TASK_CREATE,
        Permission.TASK_VIEW,
        Permission.TASK_ASSIGN_SELF,
        Permission.TASK_MANAGE_LABELS,
        Permission.TASK_MANAGE_SUBTASKS,
        Permission.TASK_CLOSE_REOPEN,
        Permission.TASK_GIT_LINK,
        Permission.TASK_AI_APPROVE,
        Permission.COMMENT_CREATE,
        Permission.COMMENT_EDIT_OWN,
        Permission.PR_VIEW,
        Permission.PR_COMMENT,
        Permission.PR_APPROVE,
    },
    
    ProjectRole.OBSERVER: {
        Permission.PROJECT_VIEW,
        Permission.BOARD_VIEW,
        Permission.TASK_VIEW,
        Permission.PR_VIEW,
    }
}
