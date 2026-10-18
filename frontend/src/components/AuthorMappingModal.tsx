import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  X,
  Loader2,
  Users,
  UserCheck,
  UserX,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Search,
  Globe,
  ChevronDown,
  Info,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';

interface Props {
  repositoryId: number;
  repositoryName: string;
  onClose: () => void;
  onUpdated: () => void;
}

interface AuthorEntry {
  author_key: string;
  author_name?: string;
  author_email?: string;
  commits: number;
  user_id?: number;
  user_name?: string;
  source?: string;
}

interface Report {
  repository_id: number;
  authors: AuthorEntry[];
  stats: {
    total_commits: number;
    attributed_commits: number;
    distinct_authors: number;
    unmatched_authors: number;
    auto_matched_authors: number;
  };
}

interface Candidate {
  id: number;
  full_name?: string;
  email: string;
  avatar_url?: string;
}

type Filter = 'all' | 'unmatched' | 'matched';

export default function AuthorMappingModal({ repositoryId, repositoryName, onClose, onUpdated }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [searchQ, setSearchQ] = useState('');
  const [openPicker, setOpenPicker] = useState<string | null>(null);

  const { data: report, isLoading, refetch, isFetching } = useQuery<Report>({
    queryKey: ['git-authors', repositoryId],
    queryFn: async () => {
      const { data } = await api.get(`/git/${repositoryId}/authors`);
      return data;
    },
  });

  // Кандидаты подгружаются только при открытии списка
  const { data: candidates } = useQuery<Candidate[]>({
    queryKey: ['git-author-candidates', searchQ],
    queryFn: async () => {
      const { data } = await api.get(`/git/${repositoryId}/authors/candidates`, {
        params: { q: searchQ },
      });
      return data;
    },
    enabled: openPicker !== null,
  });

  const mapMutation = useMutation({
    mutationFn: async (payload: { author_key: string; user_id: number }) => {
      const { data } = await api.post(`/git/${repositoryId}/authors/map`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['git-authors', repositoryId] });
      onUpdated();
      setOpenPicker(null);
    },
  });

  const rematchMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(`/git/${repositoryId}/authors/rematch`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['git-authors', repositoryId] });
      onUpdated();
    },
  });

  const visible = useMemo(() => {
    let list = report?.authors || [];
    if (filter === 'unmatched') list = list.filter((a) => !a.user_id);
    if (filter === 'matched') list = list.filter((a) => !!a.user_id);
    return list;
  }, [report, filter]);

  const stats = report?.stats;
  const percent = stats?.total_commits
    ? Math.round(((stats.attributed_commits || 0) / stats.total_commits) * 100)
    : 0;

  const isAuto = (a: AuthorEntry) => a.source === 'auto_email' || a.source === 'auto_username';
  const isStored = (a: AuthorEntry) => a.source === 'stored';

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
      <div className="bg-white rounded-lg w-full max-w-3xl max-h-[90vh] shadow-2xl border border-[#d0d7de] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-[#1f2328]">{t('projects.git.authors.title')}</h2>
            <p className="text-xs text-[#636c76]">{repositoryName}</p>
          </div>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 rounded-md hover:bg-gray-200 transition">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {isLoading ? (
            <div className="p-12 text-center">
              <Loader2 className="animate-spin mx-auto text-blue-500" size={28} />
            </div>
          ) : (
            <>
              {/* Статистика */}
              <div className="p-4 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#636c76] uppercase tracking-wider">
                    {t('projects.git.authors.attribution')}
                  </span>
                  <span className="text-sm font-bold text-[#1f2328]">
                    {stats?.attributed_commits || 0} / {stats?.total_commits || 0}
                    <span className="ml-2 text-[#636c76]">({percent}%)</span>
                  </span>
                </div>
                <div className="h-2 bg-[#d0d7de] rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all ${percent === 100 ? 'bg-green-500' : 'bg-amber-500'}`}
                    style={{ width: `${percent}%` }}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <StatBox value={stats?.distinct_authors ?? 0} label={t('projects.git.authors.authors')} />
                  <StatBox
                    value={stats?.unmatched_authors ?? 0}
                    label={t('projects.git.authors.unmatched')}
                    tone={(stats?.unmatched_authors ?? 0) > 0 ? 'warn' : 'ok'}
                  />
                  <StatBox value={stats?.auto_matched_authors ?? 0} label={t('projects.git.authors.auto')} />
                </div>
                <p className="text-[11px] text-[#636c76] flex items-start gap-1">
                  <Info size={12} className="shrink-0 mt-0.5" />
                  {t('projects.git.authors.explain')}
                </p>
              </div>

              {stats && stats.unmatched_authors > 0 && (
                <div className="p-3 rounded-lg bg-[#fff8c5] border border-[#d4a72c4d] flex items-start gap-3">
                  <AlertTriangle size={18} className="text-[#9a6700] shrink-0" />
                  <p className="text-xs text-[#735c0f]">{t('projects.git.authors.warn')}</p>
                </div>
              )}

              {/* Фильтры */}
              <div className="flex flex-wrap items-center gap-2">
                {([
                  ['all', t('projects.git.authors.filter_all')],
                  ['unmatched', t('projects.git.authors.filter_unmatched')],
                  ['matched', t('projects.git.authors.filter_matched')],
                ] as [Filter, string][]).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setFilter(key)}
                    className={`px-3 py-1.5 rounded-md text-xs font-bold transition ${
                      filter === key
                        ? 'bg-[#1f2328] text-white'
                        : 'bg-white border border-[#d0d7de] text-[#636c76] hover:bg-[#f6f8fa]'
                    }`}
                  >
                    {label}
                  </button>
                ))}

                <div className="relative flex-1 min-w-[180px]">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#636c76]" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') setSearchQ(search); }}
                    placeholder={t('projects.git.authors.search')}
                    className="w-full pl-8 pr-3 py-1.5 bg-white border border-[#d0d7de] rounded-md text-xs outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                <button
                  onClick={() => rematchMutation.mutate()}
                  disabled={rematchMutation.isPending}
                  className="px-3 py-1.5 rounded-md text-xs font-bold bg-white border border-[#d0d7de] text-[#636c76] hover:bg-[#f6f8fa] transition disabled:opacity-50 flex items-center gap-1.5"
                >
                  {rematchMutation.isPending ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <RefreshCw size={12} />
                  )}
                  {t('projects.git.authors.rematch')}
                </button>

                <button
                  onClick={() => refetch()}
                  className="p-1.5 hover:bg-gray-100 rounded-md text-[#636c76] transition"
                >
                  <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
                </button>
              </div>

              {/* Список */}
              <div className="space-y-2">
                {visible.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-[#d0d7de] rounded-lg">
                    <Users size={36} className="mx-auto text-[#d0d7de] mb-3 opacity-30" />
                    <p className="text-sm text-[#636c76]">{t('projects.git.authors.empty')}</p>
                  </div>
                ) : (
                  visible.map((a) => (
                    <div
                      key={a.author_key}
                      className={`p-3 border rounded-lg transition ${
                        a.user_id ? 'border-[#d0d7de] bg-white' : 'border-amber-200 bg-amber-50/40'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-[#f6f8fa] border border-[#d0d7de] flex items-center justify-center shrink-0">
                          {a.user_id ? (
                            <UserCheck size={15} className="text-green-600" />
                          ) : (
                            <UserX size={15} className="text-amber-600" />
                          )}
                        </div>

                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-bold text-[#1f2328] truncate">
                            {a.author_name || a.author_key}
                          </p>
                          <p className="text-[10px] text-[#636c76] font-mono truncate">{a.author_key}</p>
                        </div>

                        <span className="text-[10px] font-bold text-[#636c76] bg-[#f6f8fa] border border-[#d0d7de] px-2 py-0.5 rounded-full shrink-0">
                          {a.commits} {t('projects.git.authors.commits')}
                        </span>

                        <div className="w-44 shrink-0 text-right">
                          {a.user_name ? (
                            <div className="flex items-center justify-end gap-1.5">
                              <span className="text-xs font-bold text-[#1f2328] truncate">{a.user_name}</span>
                              {isAuto(a) && (
                                <span className="text-[9px] font-bold text-blue-600 bg-blue-50 border border-blue-100 px-1 py-0.5 rounded">
                                  {t('projects.git.authors.auto_badge')}
                                </span>
                              )}
                              {isStored(a) && (
                                <span className="text-[9px] font-bold text-gray-600 bg-gray-50 border border-gray-200 px-1 py-0.5 rounded">
                                  {t('projects.git.authors.saved')}
                                </span>
                              )}
                            </div>
                          ) : (
                            <button
                              onClick={() => setOpenPicker(openPicker === a.author_key ? null : a.author_key)}
                              className="px-2.5 py-1 rounded-md text-[11px] font-bold bg-[#0969da] text-white hover:bg-[#0861c5] transition flex items-center gap-1 ml-auto"
                            >
                              {t('projects.git.authors.map')}
                              <ChevronDown size={12} />
                            </button>
                          )}
                        </div>
                      </div>

                      {openPicker === a.author_key && (
                        <div className="mt-3 pt-3 border-t border-[#d0d7de]">
                          <div className="flex gap-2 mb-2">
                            <input
                              defaultValue=""
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') setSearchQ((e.target as HTMLInputElement).value);
                              }}
                              placeholder={t('projects.git.authors.search_user')}
                              className="flex-1 px-2 py-1.5 bg-white border border-[#d0d7de] rounded text-xs outline-none focus:ring-1 focus:ring-blue-500"
                            />
                            <button
                              onClick={() => setSearchQ('')}
                              className="px-2 py-1.5 bg-white border border-[#d0d7de] rounded text-[#636c76] hover:bg-[#f6f8fa] text-xs font-bold"
                            >
                              {t('projects.git.authors.reset_search')}
                            </button>
                          </div>

                          <div className="max-h-48 overflow-y-auto border border-[#d0d7de] rounded-md divide-y divide-[#f0f2f4]">
                            {(candidates || []).length === 0 ? (
                              <p className="p-3 text-center text-xs text-[#636c76]">
                                {t('projects.git.authors.no_candidates')}
                              </p>
                            ) : (
                              (candidates || []).map((u) => (
                                <button
                                  key={u.id}
                                  onClick={() => mapMutation.mutate({ author_key: a.author_key, user_id: u.id })}
                                  disabled={mapMutation.isPending}
                                  className="w-full flex items-center gap-2 p-2 hover:bg-[#f6f8fa] transition text-left disabled:opacity-50"
                                >
                                  <div className="w-6 h-6 rounded-full bg-gray-200 overflow-hidden shrink-0">
                                    {u.avatar_url ? (
                                      <img src={u.avatar_url} alt="" className="w-full h-full object-cover" />
                                    ) : (
                                      <div className="w-full h-full flex items-center justify-center text-[9px] font-bold text-gray-600">
                                        {(u.full_name || u.email)?.[0]?.toUpperCase()}
                                      </div>
                                    )}
                                  </div>
                                  <div className="min-w-0">
                                    <p className="text-xs font-bold text-[#1f2328] truncate">
                                      {u.full_name || u.email}
                                    </p>
                                    <p className="text-[10px] text-[#636c76] truncate">{u.email}</p>
                                  </div>
                                </button>
                              ))
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function StatBox({ value, label, tone }: { value: number; label: string; tone?: 'ok' | 'warn' }) {
  return (
    <div className="bg-white border border-[#d0d7de] rounded-md py-2">
      <p
        className={`text-lg font-bold ${
          tone === 'warn' ? 'text-amber-600' : tone === 'ok' ? 'text-green-600' : 'text-[#1f2328]'
        }`}
      >
        {value}
      </p>
      <p className="text-[10px] text-[#636c76]">{label}</p>
    </div>
  );
}
