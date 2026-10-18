import type { TaskType } from './taskType';

export type { TaskType };

export interface User {
  id: number;
  email: string;
  full_name?: string;
  avatar_url?: string;
  language?: string;
  role?: string;
  is_active?: boolean;
  is_superuser?: boolean;
  can_create_projects?: boolean;
  github_token?: string;
  gitlab_token?: string;
  bitbucket_token?: string;
  gitea_token?: string;
  github_username?: string;
  /** Привязанные Git-аккаунты, приходят вместе с /users/me */
  git_accounts?: GitAccount[];
}

export interface GitAccount {
  id: number;
  provider: string;
  username?: string;
  created_at: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

/** Кастомное SQL-правило, сохранённое в проекте */
export interface CustomSqlRule {
  id: number;
  query: string;
}

export interface GitRepository {
  id: number;
  url: string;
  repo_name?: string;
  api_url?: string;
  default_branch?: string;
  path_filter?: string;
  provider: 'github' | 'gitlab' | 'bitbucket' | 'gitea' | 'gitlab_custom';
  webhook_secret?: string;
  webhook_id?: string;
  is_active?: boolean;
  last_sync_at?: string;
  last_sync_status?: 'pending' | 'ok' | 'error' | 'skipped';
  last_sync_error?: string;
  last_event_at?: string;
  // Фоновое дооболнение после синхронизации: правки и разбор моделью.
  // Идёт отдельно от last_sync_status, потому что загрузка коммитов
  // заканчивается быстро, а разбор — заметно позже.
  enrichment_status?: 'pending' | 'running' | 'done' | 'error';
  enrichment_total?: number;
  enrichment_done?: number;
  enrichment_error?: string;
  enrichment_at?: string;
}

export interface UnlinkedGitEvent {
  id: number;
  event_type: string;
  external_id?: string;
  payload: any;
  created_at: string;
  status: 'pending' | 'linked' | 'ignored';
}

/** Вид фона страницы проекта: none — белый, default — базовый из
 *  поставки, custom — загруженный руководителем. */
export type ProjectBackground = 'none' | 'default' | 'custom';

export interface Project {
  id: number;
  name: string;
  description?: string;
  git_url?: string;
  /** Задаётся у всех проектов; отсутствует только у очень старых записей */
  background?: ProjectBackground;
  /** Адрес загруженного файла. Есть только при background === 'custom' */
  background_url?: string | null;
  owner_id: number;
  user_role?: string;
  members?: User[];
  repositories?: GitRepository[];
  storage_used_bytes: number;
  storage_limit_bytes: number;
  rules?: {
    required_fields: string[];
    auto_assign_on_move: boolean;
    column_role_locks: Record<string, string[]>;
    start_date_logic: 'created_at' | 'manual_pm' | 'manual_assignee';
    custom_sql_rules?: CustomSqlRule[];
  };
}

export interface TaskCreate {
  title: string;
  description?: string;
  priority: number;
  project_id: number;
  column_id?: number;
  assignee_id?: number;
  start_date?: string;
  due_date?: string;
  dependency_ids?: number[];
  subtasks?: { title: string; is_completed: boolean }[];
}

export interface TaskUpdate {
  title?: string;
  description?: string;
  priority?: number;
  column_id?: number;
  assignee_id?: number;
  start_date?: string;
  due_date?: string;
  dependency_ids?: number[];
}

export interface Column {
  id: number;
  board_id: number;
  name: string;
  state_category: 'TODO' | 'IN_PROGRESS' | 'DONE';
  position: number;
  color?: string;
}

export interface Board {
  id: number;
  project_id: number;
  columns: Column[];
}

export interface Notification {
  id: number;
  title: string;
  message: string;
  type: 'info' | 'project_invite' | 'task_assigned' | 'task_updated' | 'pr_review_requested';
  is_read: boolean;
  created_at: string;
  project_id?: number;
  task_id?: number;
  invite_id?: number;
}

export interface ProjectInvite {
  id: number;
  project_id: number;
  user_id: number;
  inviter_id: number;
  role: string;
  status: 'pending' | 'accepted' | 'declined';
  created_at: string;
}

export interface SubTask {
  id: number;
  title: string;
  is_completed: boolean;
  task_id: number;
}

export interface CommentReaction {
  id: number;
  user_id: number;
  emoji: string;
}

export interface Attachment {
  id: string; // UUID
  filename: string;
  path: string;
  size_bytes: number;
  mime_type?: string;
  uploaded_by: number;
  project_id: number;
  task_id: number;
  comment_id?: number;
  status: 'orphan' | 'active' | 'deleted';
  created_at: string;
  deleted_at?: string;
}

export interface TaskComment {
  id: number;
  content: string;
  created_at: string;
  updated_at?: string;
  task_id: number;
  user_id: number;
  parent_id?: number;
  author?: User;
  reactions?: CommentReaction[];
  attachments?: Attachment[];
}

export interface Task {
  id: number;
  title: string;
  description?: string;
  priority: number;
  /** Тип задачи: выбирает человек при создании. Пусто — «без типа». */
  task_type?: TaskType | null;
  start_date?: string;
  due_date?: string;
  project_id: number;
  column_id: number;
  assignee_id?: number;
  parent_id?: number;
  created_at: string;
  updated_at?: string;
  subtasks: SubTask[];
  comments: TaskComment[];
  activities?: any[];
  branches?: any[];
  commits?: any[];
  pull_requests?: any[];
  /** ID задач, от которых зависит текущая */
  dependencies?: number[];
}
