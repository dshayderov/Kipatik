import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api/client';
import {
  Loader2,
  HardDrive,
  Trash2,
  Clock,
  ShieldCheck,
  Save,
  FileWarning,
  Info,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface StorageSettings {
  max_file_size_mb: number;
  allowed_extensions: string;
  default_project_limit_mb: number;
  trash_retention_days: number;
  auto_purge_enabled: boolean;
  purge_interval_hours: number;
}

interface ProjectUsage {
  id: number;
  name: string;
  used_bytes: number;
  limit_bytes: number;
  own_limit: boolean;
  usage_percent: number;
}

interface StorageStats {
  active: { count: number; bytes: number };
  trash: { count: number; bytes: number };
  orphan: { count: number; bytes: number };
  total_bytes: number;
  projects: ProjectUsage[];
  trash_expired: number;
}

interface StorageResponse {
  settings: StorageSettings;
  limits: Record<string, [number, number]>;
  stats: StorageStats;
}

const fmt = (bytes: number) =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(
    (bytes || 0) / 1024 / 1024
  ) + ' МБ';

export default function StoragePage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<StorageSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmEmpty, setConfirmEmpty] = useState(false);

  const { data, isLoading } = useQuery<StorageResponse>({
    queryKey: ['admin', 'storage'],
    queryFn: async () => {
      const { data: d } = await api.get('/admin/storage');
      return d;
    },
  });

  useEffect(() => {
    if (data?.settings && !dirty) setForm(data.settings);
  }, [data, dirty]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['admin', 'storage'] });

  const saveMutation = useMutation({
    mutationFn: async (values: StorageSettings) => api.patch('/admin/storage', values),
    onSuccess: (res) => {
      setDirty(false);
      queryClient.setQueryData(['admin', 'storage'], res);
    },
  });

  const limitMutation = useMutation({
    mutationFn: async ({ id, limit_mb }: { id: number; limit_mb: number | null }) =>
      api.patch(`/admin/storage/projects/${id}/limit`, { limit_mb }),
    onSuccess: invalidate,
  });

  const purgeMutation = useMutation({
    mutationFn: async (which: 'purge' | 'purge/expired') => api.post(`/admin/storage/${which}`),
    onSuccess: () => {
      setConfirmEmpty(false);
      invalidate();
    },
  });

  const set = <K extends keyof StorageSettings>(key: K, value: StorageSettings[K]) => {
    setForm((f) => (f ? { ...f, [key]: value } : f));
    setDirty(true);
  };

  const bounds = data?.limits ?? {};

  return (
    <div className="p-8 max-w-6xl mx-auto w-full space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#1f2328]">
            {t('admin.storage_management')}
          </h1>
          <p className="text-sm text-[#636c76]">{t('admin.storage_subtitle')}</p>
        </div>
        {form && (
          <button
            onClick={() => saveMutation.mutate(form)}
            disabled={!dirty || saveMutation.isPending}
            className="flex items-center gap-2 bg-[#1f883d] text-white px-4 py-2 rounded-md font-semibold text-sm hover:bg-[#1a7f37] shadow-sm transition-colors disabled:opacity-50"
          >
            {saveMutation.isPending ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              <Save size={16} />
            )}
            {t('admin.storage.save')}
          </button>
        )}
      </div>

      {saveMutation.error && (
        <ErrorBox
          detail={(saveMutation.error as any)?.response?.data?.detail}
          fallback={t('admin.storage.save_failed')}
        />
      )}

      {isLoading || !form || !data ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-blue-500" size={32} />
        </div>
      ) : (
        <>
          {/* Что сейчас лежит на диске */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <StatCard
              icon={<HardDrive size={16} />}
              label={t('admin.storage.total')}
              value={fmt(data.stats.total_bytes)}
            />
            <StatCard
              icon={<ShieldCheck size={16} />}
              label={t('admin.storage.active')}
              value={`${data.stats.active.count} · ${fmt(data.stats.active.bytes)}`}
            />
            <StatCard
              icon={<Trash2 size={16} />}
              label={t('admin.storage.trash')}
              value={`${data.stats.trash.count} · ${fmt(data.stats.trash.bytes)}`}
            />
            <StatCard
              icon={<FileWarning size={16} />}
              label={t('admin.storage.orphan')}
              value={`${data.stats.orphan.count} · ${fmt(data.stats.orphan.bytes)}`}
            />
          </div>

          {/* Лимиты вложений */}
          <Card title={t('admin.storage.limits_title')} icon={<ShieldCheck size={16} />}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <NumberField
                id="max_file_size_mb"
                label={t('admin.storage.max_file_size')}
                hint={t('admin.storage.max_file_size_hint')}
                value={form.max_file_size_mb}
                min={bounds.max_file_size_mb?.[0]}
                max={bounds.max_file_size_mb?.[1]}
                suffix={t('admin.storage.mb')}
                onChange={(v) => set('max_file_size_mb', v)}
              />
              <NumberField
                id="default_project_limit_mb"
                label={t('admin.storage.default_project_limit')}
                hint={t('admin.storage.default_project_limit_hint')}
                value={form.default_project_limit_mb}
                min={bounds.default_project_limit_mb?.[0]}
                max={bounds.default_project_limit_mb?.[1]}
                suffix={t('admin.storage.mb')}
                onChange={(v) => set('default_project_limit_mb', v)}
              />
            </div>

            <div className="mt-4 space-y-1">
              <label
                htmlFor="allowed_extensions"
                className="block text-xs font-bold text-[#636c76] uppercase tracking-wider"
              >
                {t('admin.storage.extensions')}
              </label>
              <input
                id="allowed_extensions"
                value={form.allowed_extensions}
                onChange={(e) => set('allowed_extensions', e.target.value)}
                className="w-full bg-white border border-[#d0d7de] rounded-md px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-blue-500"
              />
              <p className="text-[11px] text-[#636c76]">
                {t('admin.storage.extensions_hint')}
              </p>
            </div>
          </Card>

          {/* Корзина */}
          <Card title={t('admin.storage.trash_title')} icon={<Trash2 size={16} />}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <NumberField
                id="trash_retention_days"
                label={t('admin.storage.retention')}
                hint={t('admin.storage.retention_hint')}
                value={form.trash_retention_days}
                min={bounds.trash_retention_days?.[0]}
                max={bounds.trash_retention_days?.[1]}
                suffix={t('admin.storage.days')}
                onChange={(v) => set('trash_retention_days', v)}
              />
              <NumberField
                id="purge_interval_hours"
                label={t('admin.storage.interval')}
                hint={t('admin.storage.interval_hint')}
                value={form.purge_interval_hours}
                min={bounds.purge_interval_hours?.[0]}
                max={bounds.purge_interval_hours?.[1]}
                suffix={t('admin.storage.hours')}
                onChange={(v) => set('purge_interval_hours', v)}
                disabled={!form.auto_purge_enabled}
              />
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={form.auto_purge_enabled}
                    onChange={(e) => set('auto_purge_enabled', e.target.checked)}
                    className="w-4 h-4 accent-[#1f883d] cursor-pointer"
                  />
                  <span className="text-sm font-semibold text-[#1f2328]">
                    {t('admin.storage.auto_purge')}
                  </span>
                </label>
              </div>
            </div>

            <p className="mt-3 text-[11px] text-[#636c76] flex items-start gap-1.5">
              <Clock size={12} className="shrink-0 mt-0.5" />
              {t('admin.storage.retention_explain', {
                days: form.trash_retention_days,
                expired: data.stats.trash_expired,
              })}
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-3 pt-4 border-t border-[#f0f2f4]">
              <button
                onClick={() => purgeMutation.mutate('purge/expired')}
                disabled={purgeMutation.isPending || data.stats.trash_expired === 0}
                className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold border border-[#d0d7de] bg-white text-[#1f2328] rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {purgeMutation.isPending ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <RotateCcw size={13} />
                )}
                {t('admin.storage.purge_expired')}
              </button>

              {!confirmEmpty ? (
                <button
                  onClick={() => setConfirmEmpty(true)}
                  disabled={data.stats.trash.count === 0}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  <Trash2 size={13} />
                  {t('admin.storage.empty_trash')}
                </button>
              ) : (
                <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-md px-3 py-1.5">
                  <span className="text-xs font-semibold text-red-800">
                    {t('admin.storage.empty_confirm', {
                      count: data.stats.trash.count,
                    })}
                  </span>
                  <button
                    onClick={() => purgeMutation.mutate('purge')}
                    className="px-2 py-1 text-xs font-bold bg-red-600 text-white rounded hover:bg-red-700"
                  >
                    {t('admin.storage.yes_delete')}
                  </button>
                  <button
                    onClick={() => setConfirmEmpty(false)}
                    className="px-2 py-1 text-xs font-bold bg-white border border-red-300 text-red-700 rounded hover:bg-red-100"
                  >
                    {t('admin.storage.cancel')}
                  </button>
                </div>
              )}
            </div>
          </Card>

          {/* Проекты */}
          <Card title={t('admin.storage.projects_title')} icon={<HardDrive size={16} />}>
            <div className="space-y-3">
              {data.stats.projects.map((p) => (
                <ProjectRow
                  key={p.id}
                  project={p}
                  busy={limitMutation.isPending}
                  t={t}
                  onSet={(mb) => limitMutation.mutate({ id: p.id, limit_mb: mb })}
                  onReset={() => limitMutation.mutate({ id: p.id, limit_mb: null })}
                />
              ))}
            </div>
          </Card>

          <div className="p-4 bg-blue-50 border border-blue-100 rounded-lg flex items-start gap-3 text-sm text-blue-900">
            <Info size={16} className="shrink-0 mt-0.5" />
            <p className="leading-relaxed">{t('admin.storage.note')}</p>
          </div>
        </>
      )}
    </div>
  );
}

function ProjectRow({
  project,
  busy,
  t,
  onSet,
  onReset,
}: {
  project: ProjectUsage;
  busy: boolean;
  t: any;
  onSet: (mb: number) => void;
  onReset: () => void;
}) {
  const [value, setValue] = useState<string>('');
  const pct = Math.min(100, project.usage_percent || 0);
  const over = pct >= 90;

  return (
    <div className="border border-[#d0d7de] rounded-lg p-3">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-sm text-[#1f2328] truncate">
            {project.name}
          </span>
          {!project.own_limit && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-300 font-semibold shrink-0">
              {t('admin.storage.shared_limit')}
            </span>
          )}
        </div>
        <span
          className={`text-xs font-semibold tabular-nums shrink-0 ${
            over ? 'text-red-600' : 'text-[#636c76]'
          }`}
        >
          {fmt(project.used_bytes)} / {fmt(project.limit_bytes)}
        </span>
      </div>

      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            over ? 'bg-red-500' : pct > 60 ? 'bg-amber-500' : 'bg-green-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex items-center gap-2 mt-2">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={String(Math.round(project.limit_bytes / 1024 / 1024))}
          className="w-28 bg-white border border-[#d0d7de] rounded px-2 py-1 text-xs font-mono outline-none focus:ring-1 focus:ring-blue-500"
        />
        <span className="text-[11px] text-[#636c76]">{t('admin.storage.mb')}</span>
        <button
          onClick={() => onSet(Number(value))}
          disabled={busy || !value || Number.isNaN(Number(value))}
          className="px-2 py-1 text-xs font-semibold bg-[#1f2328] text-white rounded hover:bg-[#333] disabled:opacity-40"
        >
          {t('admin.storage.set')}
        </button>
        <button
          onClick={onReset}
          disabled={busy || !project.own_limit}
          className="px-2 py-1 text-xs font-semibold border border-[#d0d7de] bg-white text-[#1f2328] rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {t('admin.storage.reset_limit')}
        </button>
      </div>
    </div>
  );
}

function NumberField({
  id,
  label,
  hint,
  value,
  min,
  max,
  suffix,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  value: number;
  min?: number;
  max?: number;
  suffix: string;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);

  const parsed = Number(text);
  const invalid =
    text.trim() === '' ||
    Number.isNaN(parsed) ||
    (min !== undefined && parsed < min) ||
    (max !== undefined && parsed > max);

  return (
    <div>
      <label
        htmlFor={id}
        className="block text-xs font-bold text-[#636c76] uppercase tracking-wider"
      >
        {label}
      </label>
      <div className="flex items-center gap-2 mt-1">
        <input
          id={id}
          type="number"
          value={text}
          min={min}
          max={max}
          disabled={disabled}
          onChange={(e) => {
            setText(e.target.value);
            const n = Number(e.target.value);
            if (!Number.isNaN(n)) onChange(n);
          }}
          className={`w-28 bg-white border rounded px-2 py-1.5 text-sm font-mono outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400 ${
            invalid ? 'border-red-400' : 'border-[#d0d7de]'
          }`}
        />
        <span className="text-xs text-[#636c76]">{suffix}</span>
        {(min !== undefined || max !== undefined) && (
          <span className="text-[10px] text-[#8b949e] ml-auto">
            {min}…{max}
          </span>
        )}
      </div>
      <p className="text-[11px] text-[#636c76] mt-0.5">{hint}</p>
    </div>
  );
}

function Card({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white border border-[#d0d7de] rounded-lg p-5 shadow-sm">
      <h2 className="flex items-center gap-2 font-bold text-[#1f2328] mb-4">
        <span className="text-[#636c76]">{icon}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="bg-white border border-[#d0d7de] rounded-lg p-4 flex items-center gap-3 shadow-sm">
      <div className="p-2 bg-gray-50 rounded-lg text-[#636c76] shrink-0">{icon}</div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider truncate">
          {label}
        </p>
        <p className="text-sm font-bold text-[#1f2328] truncate">{value}</p>
      </div>
    </div>
  );
}

function ErrorBox({ detail, fallback }: { detail?: string; fallback: string }) {
  return (
    <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2 text-sm text-red-800">
      <AlertTriangle size={16} className="shrink-0 mt-0.5" />
      <span>{detail || fallback}</span>
    </div>
  );
}