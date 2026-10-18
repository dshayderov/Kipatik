import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api/client';
import {
  Loader2,
  Brain,
  Tag,
  Gauge,
  Power,
  RefreshCw,
  Info,
  AlertTriangle,
  HardDrive,
  Cpu,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface AIModel {
  key: string;
  title_key: string;
  purpose_key: string;
  kind: 'neural' | 'rules';
  enabled: boolean;
  env_default: boolean;
  overridden: boolean;
  depends_on: string[];
  artifact: string | null;
  artifact_exists: boolean;
  artifact_size_mb: number;
  blocked_by: string[];
  loaded: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

const ICONS: Record<string, React.ReactNode> = {
  encoder: <Brain className="text-purple-600" size={20} />,
  type_classifier: <Tag className="text-blue-600" size={20} />,
  progress_estimator: <Gauge className="text-green-600" size={20} />,
};

export default function NeuralModelsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const { data: models, isLoading, error } = useQuery<AIModel[]>({
    queryKey: ['admin', 'models'],
    queryFn: async () => {
      const { data } = await api.get('/admin/models');
      return data;
    },
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['admin', 'models'] });

  const toggleMutation = useMutation({
    mutationFn: async ({ key, enabled }: { key: string; enabled: boolean }) => {
      setBusyKey(key);
      return api.patch(`/admin/models/${key}`, { enabled });
    },
    onSuccess: invalidate,
    onSettled: () => setBusyKey(null),
  });

  const unloadMutation = useMutation({
    mutationFn: async (key: string) => {
      setBusyKey(key);
      return api.post(`/admin/models/${key}/unload`);
    },
    onSuccess: invalidate,
    onSettled: () => setBusyKey(null),
  });

  const reloadMutation = useMutation({
    mutationFn: async () => {
      setBusyKey('__reload__');
      return api.post('/admin/models/reload');
    },
    onSuccess: invalidate,
    onSettled: () => setBusyKey(null),
  });

  const anyLoaded = models?.some((m) => m.loaded) ?? false;
  const totalMb = models?.reduce((s, m) => s + (m.artifact_size_mb || 0), 0) ?? 0;

  return (
    <div className="p-8 max-w-6xl mx-auto w-full space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#1f2328]">
            {t('admin.models_management')}
          </h1>
          <p className="text-sm text-[#636c76]">{t('admin.models_subtitle')}</p>
        </div>
        <button
          onClick={() => reloadMutation.mutate()}
          disabled={reloadMutation.isPending}
          title={t('admin.models.reload_hint')}
          className="flex items-center gap-2 bg-[#1f2328] text-white px-4 py-2 rounded-md font-semibold text-sm hover:bg-[#333] shadow-sm transition-colors disabled:opacity-50"
        >
          {reloadMutation.isPending ? (
            <Loader2 className="animate-spin" size={16} />
          ) : (
            <RefreshCw size={16} />
          )}
          {t('admin.models.reload')}
        </button>
      </div>

      {/* Что сейчас занимает память */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryCard
          icon={<HardDrive size={16} />}
          label={t('admin.models.total_size')}
          value={`${totalMb.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} МБ`}
        />
        <SummaryCard
          icon={<Cpu size={16} />}
          label={t('admin.models.loaded_now')}
          value={t('admin.models.count_models', {
            loaded: models?.filter((m) => m.loaded).length ?? 0,
            total: models?.length ?? 0,
          })}
        />
        <SummaryCard
          icon={<Power size={16} />}
          label={t('admin.models.enabled_now')}
          value={t('admin.models.count_models', {
            loaded: models?.filter((m) => m.enabled).length ?? 0,
            total: models?.length ?? 0,
          })}
        />
      </div>

      {(toggleMutation.error || reloadMutation.error) && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2 text-sm text-red-800">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          <span>
            {(toggleMutation.error as any)?.response?.data?.detail ||
              (reloadMutation.error as any)?.response?.data?.detail ||
              t('admin.models.action_failed')}
          </span>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-blue-500" size={32} />
        </div>
      ) : error ? (
        <div className="p-6 bg-red-50 border border-red-200 rounded-lg text-red-800">
          {t('admin.models.load_failed')}
        </div>
      ) : (
        <div className="space-y-4">
          {models?.map((m) => {
            const busy = busyKey === m.key;
            const canUnload = m.kind === 'neural' && m.artifact_exists;
            const blocked = m.blocked_by.length > 0;
            return (
              <div
                key={m.key}
                className={`bg-white border rounded-lg p-5 shadow-sm ${
                  m.enabled ? 'border-[#d0d7de]' : 'border-[#d0d7de] bg-[#f6f8fa]'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="p-2 bg-gray-50 rounded-lg shrink-0">
                      {ICONS[m.key] ?? <Brain size={20} />}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-bold text-[#1f2328]">
                          {t(`admin.models.items.${m.title_key}.title`)}
                        </h3>
                        <KindBadge kind={m.kind} t={t} />
                        {m.loaded && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200 font-semibold">
                            {t('admin.models.badge_loaded')}
                          </span>
                        )}
                        {m.overridden && (
                          <span
                            title={t('admin.models.overridden_hint')}
                            className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-semibold"
                          >
                            {t('admin.models.badge_overridden')}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-[#636c76] mt-1">
                        {t(`admin.models.items.${m.purpose_key}`)}
                      </p>

                      <div className="flex items-center gap-4 mt-2 text-[11px] text-[#636c76] flex-wrap">
                        {m.artifact && (
                          <span className="flex items-center gap-1">
                            <HardDrive size={11} />
                            <span className="font-mono">{m.artifact}</span>
                            {m.artifact_size_mb > 0 && (
                              <span className="ml-1 font-semibold text-[#1f2328]">
                                {m.artifact_size_mb.toLocaleString('ru-RU', {
                                  maximumFractionDigits: 2,
                                })}{' '}
                                МБ
                              </span>
                            )}
                            {!m.artifact_exists && (
                              <span className="text-red-600 font-semibold">
                                {t('admin.models.artifact_missing')}
                              </span>
                            )}
                          </span>
                        )}
                        {m.depends_on.length > 0 && (
                          <span className="flex items-center gap-1">
                            <Info size={11} />
                            {t('admin.models.depends_on', {
                              name: t(`admin.models.items.${m.depends_on[0]}.title`),
                            })}
                          </span>
                        )}
                        {m.updated_by && (
                          <span>
                            {t('admin.models.changed_by', { name: m.updated_by })}
                          </span>
                        )}
                      </div>

                      {blocked && (
                        <p className="mt-2 text-[11px] text-amber-700 flex items-start gap-1">
                          <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                          {t('admin.models.blocked', {
                            name: t(`admin.models.items.${m.blocked_by[0]}.title`),
                          })}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {canUnload && (
                      <button
                        onClick={() => unloadMutation.mutate(m.key)}
                        disabled={busy || !m.loaded}
                        title={t('admin.models.unload_hint')}
                        className="px-3 py-1.5 text-xs font-semibold border border-[#d0d7de] bg-white text-[#1f2328] rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        {t('admin.models.unload')}
                      </button>
                    )}
                    <button
                      onClick={() =>
                        toggleMutation.mutate({ key: m.key, enabled: !m.enabled })
                      }
                      disabled={busy}
                      className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors disabled:opacity-50 flex items-center gap-1.5 ${
                        m.enabled
                          ? 'bg-red-600 text-white hover:bg-red-700'
                          : 'bg-[#1f883d] text-white hover:bg-[#1a7f37]'
                      }`}
                    >
                      {busy ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Power size={13} />
                      )}
                      {m.enabled ? t('admin.models.disable') : t('admin.models.enable')}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="p-4 bg-blue-50 border border-blue-100 rounded-lg flex items-start gap-3 text-sm text-blue-900">
        <Info size={16} className="shrink-0 mt-0.5" />
        <p className="leading-relaxed">{t('admin.models.note')}</p>
      </div>
    </div>
  );
}

function SummaryCard({
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

function KindBadge({ kind, t }: { kind: string; t: any }) {
  const neural = kind === 'neural';
  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded-full border font-semibold ${
        neural
          ? 'bg-purple-50 text-purple-700 border-purple-200'
          : 'bg-gray-100 text-gray-600 border-gray-300'
      }`}
    >
      {neural ? t('admin.models.kind_neural') : t('admin.models.kind_rules')}
    </span>
  );
}