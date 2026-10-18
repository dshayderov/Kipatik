/** Панель фильтра задач.
 *
 *  Раньше на этом месте стояла плашка «Фильтр», оформленная как span:
 *  нажать её было нельзя, и она ничего не делала. Теперь это кнопка с
 *  выпадающей панелью.
 *
 *  Фильтрация идёт на уже загруженном списке задач проекта, поэтому
 *  запросов не добавляет и работает мгновенно: задачи всех проектов
 *  пользователя отдельно грузить не нужно.
 *
 *  Сами проверки лежат в src/taskFilters.ts — здесь только интерфейс.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Filter, X } from 'lucide-react';
import { TASK_TYPES, TASK_TYPE_STYLE, TaskType } from '../types/taskType';
import {
  EMPTY_FILTERS,
  PRIORITIES,
  TaskFilters,
  countActiveFilters,
} from '../taskFilters';

interface MemberOption {
  id: number;
  email?: string;
  full_name?: string;
}

interface Props {
  filters: TaskFilters;
  onChange: (next: TaskFilters) => void;
  members: MemberOption[];
  /** Из них сколько задач сейчас на доске — показывается внизу панели. */
  shown: number;
  total: number;
}

export default function TaskFilterButton({
  filters,
  onChange,
  members,
  shown,
  total,
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = countActiveFilters(filters);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const toggle = <K extends 'assignees' | 'priorities' | 'types'>(
    key: K,
    value: TaskFilters[K][number],
  ) => {
    const list = filters[key] as unknown[];
    const next = list.includes(value)
      ? list.filter((v) => v !== value)
      : [...list, value];
    onChange({ ...filters, [key]: next } as TaskFilters);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        title={t('tasks.filter_title')}
        className={`px-2 py-1 border rounded-md text-xs font-medium flex items-center gap-1 transition ${
          active > 0
            ? 'bg-blue-50 border-blue-300 text-[#0969da]'
            : 'bg-[#f6f8fa] border-[#d0d7de] text-[#636c76] hover:bg-[#ebf0f4]'
        }`}
      >
        <Filter size={12} />
        {t('common.filter')}
        {active > 0 && (
          <span className="bg-[#0969da] text-white rounded-full px-1.5 text-[9px] font-bold">
            {active}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 mt-1 w-72 bg-white border border-[#d0d7de] rounded-lg shadow-lg p-3 z-40 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#1f2328]">
              {t('tasks.filter_title')}
            </span>
            {active > 0 && (
              <button
                onClick={() => onChange(EMPTY_FILTERS)}
                className="text-[10px] text-[#0969da] hover:underline flex items-center gap-1"
              >
                <X size={10} /> {t('tasks.filter_reset')}
              </button>
            )}
          </div>

          <div>
            <div className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider mb-1">
              {t('tasks.filter_assignee')}
            </div>
            <div className="space-y-0.5 max-h-32 overflow-y-auto">
              <label className="flex items-center gap-2 text-xs cursor-pointer hover:bg-[#f6f8fa] px-1 py-0.5 rounded">
                <input
                  type="checkbox"
                  checked={filters.assignees.length === 0}
                  onChange={() => onChange({ ...filters, assignees: [] })}
                />
                <span className="text-[#636c76]">{t('tasks.filter_any')}</span>
              </label>
              {members.map((m) => (
                <label
                  key={m.id}
                  className="flex items-center gap-2 text-xs cursor-pointer hover:bg-[#f6f8fa] px-1 py-0.5 rounded"
                >
                  <input
                    type="checkbox"
                    checked={filters.assignees.includes(m.id)}
                    onChange={() => toggle('assignees', m.id)}
                  />
                  <span className="truncate text-[#1f2328]">
                    {m.full_name || m.email}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider mb-1">
              {t('tasks.filter_priority')}
            </div>
            <div className="flex gap-3">
              {PRIORITIES.map((p) => (
                <label key={p.value} className="flex items-center gap-1 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filters.priorities.includes(p.value)}
                    onChange={() => toggle('priorities', p.value)}
                  />
                  {t(p.labelKey)}
                </label>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider mb-1">
              {t('tasks.filter_type')}
            </div>
            <div className="flex flex-wrap gap-1">
              {TASK_TYPES.map((ty) => {
                const on = filters.types.includes(ty);
                return (
                  <button
                    key={ty}
                    onClick={() => toggle('types', ty)}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${
                      on
                        ? TASK_TYPE_STYLE[ty].badge
                        : 'bg-white border-[#d0d7de] text-[#636c76] hover:bg-[#f6f8fa]'
                    }`}
                  >
                    {on && <Check size={9} />}
                    {/* Короткое название типа живёт в task_type.*.
                        tasks.type_hint — длинные пояснения для подсказок,
                        в кнопке фильтра они неуместны. */}
                    {t(`task_type.${ty}`)}
                  </button>
                );
              })}
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input
              type="checkbox"
              checked={filters.overdue}
              onChange={(e) => onChange({ ...filters, overdue: e.target.checked })}
            />
            <span className="text-[#cf222e] font-bold">
              {t('tasks.filter_overdue')}
            </span>
          </label>

          <div className="pt-2 border-t border-[#d0d7de] text-[10px] text-[#636c76]">
            {t('tasks.filter_shown', { shown, total })}
          </div>
        </div>
      )}
    </div>
  );
}