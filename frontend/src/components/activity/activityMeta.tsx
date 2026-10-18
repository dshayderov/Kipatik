import React from 'react';
import {
  GitCommit,
  GitPullRequest,
  GitBranch,
  MessageSquare,
  RefreshCw,
  CheckSquare,
  Plus,
  Trash2,
  User as UserIcon,
  Flag,
  Paperclip,
  ListChecks,
  Server,
} from 'lucide-react';

/** Группа события — используется для фильтра «тип события» */
export type ActivityGroup =
  | 'created'
  | 'status'
  | 'assignee'
  | 'priority'
  | 'comments'
  | 'subtasks'
  | 'attachments'
  | 'git';

export interface ActivityUser {
  id?: number;
  full_name?: string;
  email?: string;
  avatar_url?: string;
}

/** Нормализованное событие истории (проект или задача) */
export interface ActivityItem {
  type: 'task' | 'git';
  /** Составной ключ: числовой id из БД либо `b{id}` / `c{id}` / `p{id}` для git-объектов задачи */
  id: number | string;
  created_at: string;
  // задачи
  activity_type?: string;
  description?: string;
  old_value?: string | null;
  new_value?: string | null;
  user?: ActivityUser | null;
  task_id?: number;
  // git
  event_type?: string;
  provider?: string;
  payload?: any;
}

interface ActivityMeta {
  group: ActivityGroup;
  icon: React.ReactNode;
  /** Цвет точки/левой полосы в ленте */
  dot: string;
  /** Цвет иконки в кружке */
  iconWrap: string;
  /** Подпись типа события в плашке */
  chip: string;
}

/**
 * Полные (не собираемые динамически) классы Tailwind —
 * иначе CDN-сборка не увидит классы вида `bg-${color}`.
 */
export const ACTIVITY_META: Record<string, ActivityMeta> = {
  task_created: {
    group: 'created',
    icon: <Plus size={16} />,
    dot: 'bg-green-500',
    iconWrap: 'bg-green-100 text-green-600 border-green-200',
    chip: 'bg-green-50 text-green-700 border-green-200',
  },
  status_change: {
    group: 'status',
    icon: <RefreshCw size={16} />,
    dot: 'bg-amber-500',
    iconWrap: 'bg-amber-100 text-amber-600 border-amber-200',
    chip: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  assignee_change: {
    group: 'assignee',
    icon: <UserIcon size={16} />,
    dot: 'bg-blue-500',
    iconWrap: 'bg-blue-100 text-blue-600 border-blue-200',
    chip: 'bg-blue-50 text-blue-700 border-blue-200',
  },
  priority_change: {
    group: 'priority',
    icon: <Flag size={16} />,
    dot: 'bg-red-500',
    iconWrap: 'bg-red-100 text-red-600 border-red-200',
    chip: 'bg-red-50 text-red-700 border-red-200',
  },
  comment_added: {
    group: 'comments',
    icon: <MessageSquare size={16} />,
    dot: 'bg-purple-500',
    iconWrap: 'bg-purple-100 text-purple-600 border-purple-200',
    chip: 'bg-purple-50 text-purple-700 border-purple-200',
  },
  subtask_added: {
    group: 'subtasks',
    icon: <ListChecks size={16} />,
    dot: 'bg-cyan-500',
    iconWrap: 'bg-cyan-100 text-cyan-600 border-cyan-200',
    chip: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  },
  subtask_status: {
    group: 'subtasks',
    icon: <CheckSquare size={16} />,
    dot: 'bg-teal-500',
    iconWrap: 'bg-teal-100 text-teal-600 border-teal-200',
    chip: 'bg-teal-50 text-teal-700 border-teal-200',
  },
  subtask_deleted: {
    group: 'subtasks',
    icon: <Trash2 size={16} />,
    dot: 'bg-slate-400',
    iconWrap: 'bg-slate-100 text-slate-600 border-slate-200',
    chip: 'bg-slate-50 text-slate-700 border-slate-200',
  },
  attachment_added: {
    group: 'attachments',
    icon: <Paperclip size={16} />,
    dot: 'bg-orange-500',
    iconWrap: 'bg-orange-100 text-orange-600 border-orange-200',
    chip: 'bg-orange-50 text-orange-700 border-orange-200',
  },
  attachment_deleted: {
    group: 'attachments',
    icon: <Trash2 size={16} />,
    dot: 'bg-slate-400',
    iconWrap: 'bg-slate-100 text-slate-600 border-slate-200',
    chip: 'bg-slate-50 text-slate-700 border-slate-200',
  },
  // Git
  push: {
    group: 'git',
    icon: <GitCommit size={16} />,
    dot: 'bg-indigo-500',
    iconWrap: 'bg-indigo-100 text-indigo-600 border-indigo-200',
    chip: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  },
  pull_request: {
    group: 'git',
    icon: <GitPullRequest size={16} />,
    dot: 'bg-purple-600',
    iconWrap: 'bg-purple-100 text-purple-700 border-purple-200',
    chip: 'bg-purple-50 text-purple-700 border-purple-200',
  },
  branch_created: {
    group: 'git',
    icon: <GitBranch size={16} />,
    dot: 'bg-emerald-500',
    iconWrap: 'bg-emerald-100 text-emerald-600 border-emerald-200',
    chip: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  branch_deleted: {
    group: 'git',
    icon: <GitBranch size={16} />,
    dot: 'bg-slate-400',
    iconWrap: 'bg-slate-100 text-slate-600 border-slate-200',
    chip: 'bg-slate-50 text-slate-700 border-slate-200',
  },
};

export const DEFAULT_META: ActivityMeta = {
  group: 'status',
  icon: <Server size={16} />,
  dot: 'bg-gray-400',
  iconWrap: 'bg-gray-100 text-gray-500 border-gray-200',
  chip: 'bg-gray-50 text-gray-600 border-gray-200',
};

export function getActivityMeta(item: ActivityItem): ActivityMeta {
  const key = item.type === 'git' ? item.event_type || '' : item.activity_type || '';
  return ACTIVITY_META[key] ?? DEFAULT_META;
}

/** Ключ события для локализации */
export function getActivityKey(item: ActivityItem): string {
  return item.type === 'git' ? item.event_type || 'unknown' : item.activity_type || 'unknown';
}

/** Участник события: пользователь задачи либо автор коммита / отправитель webhook */
export function getActivityAuthor(item: ActivityItem): string | null {
  if (item.type === 'git') {
    // Автор приходит в двух видах: строкой из payload провайдера
    // («Имя <почта>») и объектом {name} из истории задачи. Раньше здесь
    // ждали только строку, и на объекте .exec()/.trim() падали с
    // TypeError — вкладка «История» показывала белый экран.
    const asText = (value: unknown): string | null => {
      if (typeof value === 'string') return value;
      if (value && typeof value === 'object') {
        const obj = value as Record<string, unknown>;
        const name = obj.name ?? obj.username ?? obj.email;
        if (typeof name === 'string' && name.trim()) return name.trim();
      }
      return null;
    };

    // «Имя <почта>» приводим к почте одинаково для sender и для автора
    // коммита: иначе в списке участников один и тот же человек
    // выглядел бы двумя разными строками.
    const stripEmail = (value: string) => {
      const match = /<(.*)>/.exec(value);
      return (match ? match[1] : value).trim();
    };

    const sender = asText(item.payload?.sender);
    if (sender) return stripEmail(sender);

    const author = asText(item.payload?.commits?.[0]?.author);
    if (author) return stripEmail(author);

    return null;
  }
  if (item.user) return item.user.full_name || item.user.email || null;
  return null;
}

/** Группировка по календарному дню (локальная таймзона пользователя) */
export interface DayGroup {
  key: string;
  items: ActivityItem[];
}

export function groupByDay(items: ActivityItem[]): DayGroup[] {
  const groups = new Map<string, ActivityItem[]>();
  for (const item of items) {
    const d = new Date(item.created_at);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    const bucket = groups.get(key);
    if (bucket) bucket.push(item);
    else groups.set(key, [item]);
  }
  // Порядок групп задаётся порядком отсортированных элементов
  return Array.from(groups.entries()).map(([key, groupItems]) => ({ key, items: groupItems }));
}
