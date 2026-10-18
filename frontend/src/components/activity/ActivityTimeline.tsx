import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, RefreshCw, GitBranch, User as UserIcon, ArrowRight, Tag, Filter } from 'lucide-react';
import {
  ActivityItem,
  ActivityGroup,
  getActivityMeta,
  getActivityKey,
  getActivityAuthor,
  groupByDay,
} from './activityMeta';

interface ActivityTimelineProps {
  items: ActivityItem[];
  isLoading?: boolean;
  isFetching?: boolean;
  onRefresh?: () => void;
  /** Показывать фильтры (участник / тип / только Git) */
  showFilters?: boolean;
  /** Клик по ссылке на задачу */
  onTaskClick?: (taskId: number) => void;
  /** Показывать ссылку «Задача #id» */
  showTaskLink?: boolean;
  /** Пустое состояние */
  emptyText?: string;
  /** Заголовок блока (опционально) */
  title?: string;
  className?: string;
}

const GROUPS: ActivityGroup[] = [
  'created',
  'status',
  'assignee',
  'priority',
  'comments',
  'subtasks',
  'attachments',
  'git',
];

const PRIORITY_BY_VALUE: Record<string, string> = {
  '1': 'tasks.low',
  '2': 'tasks.medium',
  '3': 'tasks.high',
};

export default function ActivityTimeline({
  items,
  isLoading,
  isFetching,
  onRefresh,
  showFilters = true,
  onTaskClick,
  showTaskLink = true,
  emptyText,
  title,
  className = '',
}: ActivityTimelineProps) {
  const { t, i18n } = useTranslation();

  const [authorFilter, setAuthorFilter] = useState<string>('');
  const [groupFilter, setGroupFilter] = useState<string>('');
  const [onlyGit, setOnlyGit] = useState(false);

  // Участники для выпадающего списка
  const authors = useMemo(() => {
    const set = new Set<string>();
    items.forEach((i) => {
      const a = getActivityAuthor(i);
      if (a) set.add(a);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [items]);

  // Какие группы реально присутствуют
  const availableGroups = useMemo(() => {
    const set = new Set<ActivityGroup>();
    items.forEach((i) => set.add(getActivityMeta(i).group));
    return GROUPS.filter((g) => set.has(g));
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((item) => {
      if (onlyGit && item.type !== 'git') return false;
      if (groupFilter && getActivityMeta(item).group !== groupFilter) return false;
      if (authorFilter) {
        const author = getActivityAuthor(item);
        if (!author || !author.toLowerCase().includes(authorFilter.toLowerCase())) return false;
      }
      return true;
    });
  }, [items, onlyGit, groupFilter, authorFilter]);

  const dayGroups = useMemo(() => groupByDay(filtered), [filtered]);

  const hasFilters = authorFilter !== '' || groupFilter !== '' || onlyGit;

  const resetFilters = () => {
    setAuthorFilter('');
    setGroupFilter('');
    setOnlyGit(false);
  };

  /**
   * Локализованный текст события.
   * Строится из activity_type + old_value/new_value, а не из description,
   * который бэкенд пишет по-английски и хранит в БД.
   */
  const renderDescription = (item: ActivityItem) => {
    const key = getActivityKey(item);

    if (item.type === 'git') {
      const provider = (item.provider || '').toUpperCase();
      if (key === 'push') {
        const commits = item.payload?.commits || [];
        const count = commits.length;
        const author = commits[0]?.author?.name || t('history.system');
        return t('history.push', {
          count,
          author,
          provider,
          // eslint-disable-next-line react/no-unknown-property
          _count: t(`history.commits_${count === 1 ? 'one' : 'many'}`, { count }),
        });
      }
      if (key === 'pull_request') {
        const pr = item.payload?.pull_request || {};
        const state = pr.state || '';
        const stateLabel =
          state === 'merged' ? t('history.pr_merged')
          : state === 'closed' ? t('history.pr_closed')
          : t('history.pr_open');
        return t('history.pull_request', { state: stateLabel, title: pr.title || '' });
      }
      if (key === 'branch_created') return t('history.branch_created');
      if (key === 'branch_deleted') return t('history.branch_deleted');
      return t('history.git_event', { event: key });
    }

    const oldValue = item.old_value ?? '';
    const newValue = item.new_value ?? '';

    switch (key) {
      case 'task_created':
        return t('history.task_created');
      case 'status_change':
        return t('history.status_change', { from: oldValue || '?', to: newValue || '?' });
      case 'assignee_change':
        return t('history.assignee_change', {
          from: oldValue || t('history.unassigned'),
          to: newValue || t('history.unassigned'),
        });
      case 'priority_change': {
        const label = PRIORITY_BY_VALUE[newValue];
        const labelText = label ? t(label) : newValue;
        const oldLabel = PRIORITY_BY_VALUE[oldValue];
        const oldText = oldLabel ? t(oldLabel) : oldValue;
        return t('history.priority_change', { from: oldText || '?', to: labelText });
      }
      case 'comment_added':
        return t('history.comment_added');
      case 'subtask_added':
        return t('history.subtask_added', { title: newValue });
      case 'subtask_status':
        return t('history.subtask_status', {
          status: newValue === 'completed' ? t('history.done') : t('history.not_done'),
        });
      case 'subtask_deleted':
        return t('history.subtask_deleted');
      case 'attachment_added':
        return t('history.attachment_added', { name: newValue });
      case 'attachment_deleted':
        return t('history.attachment_deleted');
      default:
        return item.description || t('history.unknown_event');
    }
  };

  const formatDayLabel = (dayKey: string) => {
    const [y, m, d] = dayKey.split('-').map(Number);
    const date = new Date(y, m, d);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);

    const sameDay = (a: Date, b: Date) =>
      a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

    if (sameDay(date, today)) return t('history.today');
    if (sameDay(date, yesterday)) return t('history.yesterday');
    return date.toLocaleDateString(i18n.language, {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  };

  const formatTime = (iso: string) => new Date(iso).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' });

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-blue-500" size={32} />
      </div>
    );
  }

  return (
    <div className={`flex-1 flex flex-col gap-4 ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-2">
          <h2 className="text-lg font-bold text-[#1f2328]">{title}</h2>
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isFetching}
              className="p-2 hover:bg-gray-100 rounded-md transition text-[#636c76] disabled:opacity-50"
            >
              <RefreshCw size={18} className={isFetching ? 'animate-spin' : ''} />
            </button>
          )}
        </div>
      )}

      {/* Фильтры */}
      {showFilters && items.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 px-2">
          <div className="flex items-center gap-1 text-[#636c76]">
            <Filter size={14} />
            <span className="text-xs font-bold">{t('history.filters')}:</span>
          </div>

          <select
            value={authorFilter}
            onChange={(e) => setAuthorFilter(e.target.value)}
            className="text-xs font-semibold text-[#1f2328] bg-white border border-[#d0d7de] rounded-md px-2 py-1 shadow-sm outline-none focus:ring-1 focus:ring-blue-500 max-w-[180px]"
          >
            <option value="">{t('history.all_participants')}</option>
            {authors.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>

          <select
            value={groupFilter}
            onChange={(e) => setGroupFilter(e.target.value)}
            className="text-xs font-semibold text-[#1f2328] bg-white border border-[#d0d7de] rounded-md px-2 py-1 shadow-sm outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">{t('history.all_types')}</option>
            {availableGroups.map((g) => (
              <option key={g} value={g}>{t(`history.groups.${g}`)}</option>
            ))}
          </select>

          <button
            onClick={() => setOnlyGit(!onlyGit)}
            className={`flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-md border transition ${
              onlyGit
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-[#1f2328] border-[#d0d7de] hover:bg-[#f6f8fa]'
            }`}
          >
            <GitBranch size={12} />
            {t('history.only_git')}
          </button>

          {hasFilters && (
            <button
              onClick={resetFilters}
              className="text-xs font-semibold text-[#0969da] hover:underline"
            >
              {t('history.reset_filters')}
            </button>
          )}

          <span className="text-[11px] text-[#636c76] ml-auto">
            {t('history.showing', { shown: filtered.length, total: items.length })}
          </span>
        </div>
      )}

      {/* Лента по дням */}
      <div className="space-y-6">
        {dayGroups.map((group) => (
          <div key={group.key} className="space-y-3">
            <div className="sticky top-0 z-10 flex items-center gap-3">
              <span className="text-xs font-bold text-[#1f2328] bg-[#f6f8fa] border border-[#d0d7de] rounded-full px-3 py-1">
                {formatDayLabel(group.key)}
              </span>
              <span className="text-[10px] text-[#636c76] font-semibold">
                {t('history.events_count', { count: group.items.length })}
              </span>
              <div className="flex-1 h-px bg-[#d0d7de]" />
            </div>

            <div className="space-y-3">
              {group.items.map((item) => {
                const meta = getActivityMeta(item);
                const key = getActivityKey(item);
                const author = getActivityAuthor(item);

                return (
                  <div
                    key={`${item.type}-${item.id}`}
                    className="flex gap-4 p-4 bg-white border border-[#d0d7de] rounded-xl hover:shadow-md transition-all"
                  >
                    <div className={`mt-0.5 shrink-0 w-8 h-8 rounded-full border flex items-center justify-center ${meta.iconWrap}`}>
                      {meta.icon}
                    </div>

                    <div className="flex-1 space-y-2 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-sm font-semibold text-[#1f2328] leading-tight break-words">
                          {renderDescription(item)}
                        </h3>
                        <span className="text-[10px] font-medium text-[#636c76] whitespace-nowrap bg-[#f6f8fa] px-2 py-0.5 rounded-full border border-[#d0d7de] shrink-0">
                          {formatTime(item.created_at)}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border ${meta.chip}`}>
                          {t(`history.groups.${meta.group}`)}
                        </span>

                        {author && (
                          <span className="flex items-center gap-1.5 text-[11px] text-[#636c76] font-medium">
                            {item.user?.avatar_url ? (
                              <img src={item.user.avatar_url} alt="" className="w-4 h-4 rounded-full object-cover" />
                            ) : (
                              <UserIcon size={11} className="text-gray-400" />
                            )}
                            {author}
                          </span>
                        )}

                        {showTaskLink && item.task_id && (
                          <button
                            onClick={() => onTaskClick?.(item.task_id!)}
                            className="flex items-center gap-1 text-[11px] font-bold text-[#0969da] hover:underline"
                          >
                            <Tag size={11} />
                            {t('history.task_label', { id: item.task_id })}
                            <ArrowRight size={10} />
                          </button>
                        )}
                      </div>

                      {/* Коммиты внутри push-события */}
                      {item.type === 'git' && key === 'push' && item.payload?.commits?.length > 0 && (
                        <div className="space-y-1.5 mt-2">
                          {item.payload.commits.slice(0, 3).map((commit: any, idx: number) => (
                            <div
                              key={idx}
                              className="flex items-center gap-2 text-xs text-[#636c76] bg-[#f6f8fa] p-2 rounded-md border border-[#d0d7de]/50 font-mono"
                            >
                              <span className="text-indigo-600 font-bold">{commit.sha?.substring(0, 7)}</span>
                              <span className="truncate">{commit.message}</span>
                            </div>
                          ))}
                          {item.payload.commits.length > 3 && (
                            <p className="text-[10px] text-[#636c76] italic pl-2">
                              {t('history.and_more', { count: item.payload.commits.length - 3 })}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {filtered.length === 0 && (
          <div className="text-center py-16 bg-white border border-dashed border-[#d0d7de] rounded-xl">
            <RefreshCw size={40} className="mx-auto text-[#d0d7de] mb-4 opacity-30" />
            <p className="text-sm text-[#636c76]">
              {items.length === 0
                ? (emptyText || t('history.empty'))
                : t('history.nothing_found')}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
