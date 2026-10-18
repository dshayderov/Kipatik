import React, { useState } from 'react';
import {
  GitBranch,
  GitPullRequest,
  GitCommit,
  ChevronDown,
  ChevronRight,
  Plus,
  Minus,
  Loader2,
  X,
  Link2Off,
  User,
  ExternalLink,
  FileCode2,
  FilePlus2,
  FileX2,
  FilePen,
  AlertTriangle,
  Sparkles,
  Check,
  CheckCircle2,
  Clock,
  Info,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import ProgressBlock from './ProgressBlock';
import { TASK_TYPE_STYLE, type TaskType } from '../types/taskType';

interface Props {
  card: TaskDevCard;
  onChanged: () => void;
  canEdit: boolean;
  /** Нужен для загрузки предложений модели трассировки */
  repoId?: number;
}

interface CommitFile {
  path: string;
  previous_path?: string;
  status: string;
  additions: number;
  deletions: number;
}

interface TaskCommit {
  id: number;
  sha: string;
  message: string;
  author?: string;
  timestamp?: string;
  url?: string;
  additions: number;
  deletions: number;
  files: CommitFile[];
  /** Тип по модели: bugfix | feature | refactor | docs | test | chore */
  commit_type?: string;
  commit_type_confidence?: number;
  /** false — класс из тех, где классификатор не проверен */
  commit_type_reliable?: boolean;
  link_id?: number;
  link_source?: string;
  link_status?: string;
  confidence?: number;
  created_by?: string;
}

interface TaskPR {
  id: number;
  external_id: number;
  title: string;
  state: string;
  url?: string;
  source_branch?: string;
  target_branch?: string;
  additions: number;
  deletions: number;
  changed_files: number;
  reviewers: { login: string; state: string }[];
  ci_status?: string;
  ci_url?: string;
  link_id?: number;
  link_source?: string;
}

interface Suggestion {
  link_id: number;
  task_id: number;
  task_title: string;
  commit_id: number;
  sha: string;
  commit_message: string;
  confidence?: number;
  reason?: string;
  source: string;
  created_at?: string;
}

interface RejectedLink {
  link_id: number;
  target_id: number;
  sha: string;
  commit_message: string;
  reason?: string;
}

interface TaskDevCard {
  task_id: number;
  branches: { id: number; name: string; link_id?: number; link_source?: string }[];
  pull_requests: TaskPR[];
  commits: TaskCommit[];
  files: CommitFile[];
  totals: { commits?: number; files?: number; additions?: number; deletions?: number };
  /** Отклонённые моделью привязки — их можно вернуть к рассмотрению */
  rejected?: RejectedLink[];
}

/** Оформление типа коммита.
 *
 * Цвета не только украшение: приглушённый бейдж означает, что на этот
 * класс классификатор склонен ошибаться (см. reliability в описании).
 * Сама палитра и слова — общие с типом задачи, см. types/taskType.ts.
 */
function CommitTypeBadge({
  type,
  confidence,
  reliable,
  t,
}: {
  type?: string;
  confidence?: number;
  reliable?: boolean;
  t: any;
}) {
  if (!type) return null;
  // Палитра и подпись общие с типом задачи: тот же набор, те же слова.
  // Раньше здесь был свой список с другой раскраской, и «исправление»
  // у коммита не совпадало с «дефектом» у задачи.
  const style = TASK_TYPE_STYLE[type as TaskType];
  if (!style) return null;

  const label = t(`task_type.${type}`);

  return (
    <span
      title={
        `${label} — ` +
        (reliable
          ? t('tasks.dev.commit_type_reliable')
          : t('tasks.dev.commit_type_uncertain'))
      }
      className={`px-1.5 py-0.5 rounded text-[10px] font-bold border shrink-0 whitespace-nowrap ${
        style.badge
      } ${reliable ? '' : 'opacity-60'}`}
    >
      {label}
      {confidence !== undefined && confidence !== null && (
        <span className="ml-1 font-normal tabular-nums opacity-75">
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  );
}

const FILE_ICON: Record<string, React.ReactNode> = {
  added: <FilePlus2 size={13} className="text-green-600" />,
  removed: <FileX2 size={13} className="text-red-600" />,
  renamed: <FilePen size={13} className="text-purple-600" />,
  modified: <FileCode2 size={13} className="text-[#636c76]" />,
};

export default function DevCard({ card, onChanged, canEdit, repoId }: Props) {
  const { t } = useTranslation();
  const [expandedCommit, setExpandedCommit] = useState<number | null>(null);
  const [filesOpen, setFilesOpen] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [showRejected, setShowRejected] = useState(false);

  const restoreRejected = async (linkId: number) => {
    setBusy(linkId);
    try {
      await api.post(`/git/suggestions/${linkId}/restore`);
      setSuggestMessage(t('tasks.dev.suggestion_restored'));
      // Список предложений перечитывается обязательно: возвращённый
      // отказ снова становится предложением, и без перечитывания он
      // появлялся только после переоткрытия задачи. Та же причина,
      // по которой это делает decide выше.
      await loadSuggestions();
      onChanged();
    } catch (err: any) {
      setSuggestMessage(err.response?.data?.detail || t('tasks.dev.suggestion_failed'));
    } finally {
      setBusy(null);
    }
  };

  const unlink = async (linkId: number) => {
    if (!window.confirm(t('tasks.dev.unlink_confirm'))) return;
    setBusy(linkId);
    try {
      await api.delete(`/git/task/${card.task_id}/links/${linkId}`);
      onChanged();
    } finally {
      setBusy(null);
    }
  };

  // Предложения модели трассировки. Они ждут решения человека и
  // намеренно показываются отдельно от подтверждённых связей.
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestBusy, setSuggestBusy] = useState<number | null>(null);
  const [suggestMessage, setSuggestMessage] = useState('');

  const loadSuggestions = React.useCallback(async () => {
    if (!repoId) {
      setSuggestions([]);
      return;
    }
    try {
      // Просим предложения только этой задачи и дополнительно
      // фильтруем на клиенте. Эндпоинт без фильтра отдаёт предложения
      // всего проекта — в карточке они выглядели бы как чужие.
      const { data } = await api.get(
        `/git/${repoId}/suggestions`,
        { params: { task_id: card.task_id } }
      );
      setSuggestions((data || []).filter((s: Suggestion) => s.task_id === card.task_id));
    } catch {
      setSuggestions([]);
    }
  }, [repoId, card.task_id]);

  React.useEffect(() => {
    loadSuggestions();
  }, [loadSuggestions]);

  const decide = async (linkId: number, decision: 'confirm' | 'reject') => {
    setSuggestBusy(linkId);
    try {
      await api.post(`/git/suggestions/${linkId}/${decision}`);
      setSuggestMessage(
        decision === 'confirm'
          ? t('tasks.dev.suggestion_confirmed')
          : t('tasks.dev.suggestion_hidden')
      );
      await loadSuggestions();
      onChanged();
    } catch (err: any) {
      setSuggestMessage(err.response?.data?.detail || t('tasks.dev.suggestion_failed'));
    } finally {
      setSuggestBusy(null);
    }
  };

  // Пустой считаем только когда нет вообще ничего — включая предложения.
//
// Раньше здесь учитывались только подтверждённые связи, и компонент
// возвращал блок «ничего не связано» до того, как рисовались предложения.
// Получалось ровно наоборот задуманному: предложения и нужны тогда,
// когда подтверждённых связей ещё нет.
const isEmpty =
  card.branches.length === 0 &&
  card.pull_requests.length === 0 &&
  card.commits.length === 0 &&
  suggestions.length === 0 &&
  (card.rejected?.length ?? 0) === 0;

  if (isEmpty) {
    return (
      <div className="text-center py-10">
        <GitBranch size={36} className="mx-auto text-[#d0d7de] mb-3 opacity-30" />
        <p className="text-sm text-[#636c76]">{t('tasks.dev.nothing_linked')}</p>
        {canEdit && (
          <button
            onClick={() => setPickerOpen(true)}
            className="mt-3 px-3 py-1.5 bg-[#0969da] text-white rounded-md text-xs font-bold hover:bg-[#0861c5] transition flex items-center gap-1.5 mx-auto"
          >
            <Link2Off size={13} />
            {t('tasks.dev.relink')}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Оценка прогресса — над разработкой, потому что это итог,
          а детали ниже его обосновывают */}
      <ProgressBlock taskId={card.task_id} />

      {/* Предложения модели: пока не подтверждены, в «Коммиты» не попадают */}
      {repoId && suggestions.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-2">
            <SectionTitle>
              <span className="flex items-center gap-1.5">
                <Sparkles size={13} className="text-purple-600" />
                {t('tasks.dev.suggestions')} ({suggestions.length})
              </span>
            </SectionTitle>
          </div>

          <div className="space-y-2">
            {suggestions.map((s) => (
              <div
                key={s.link_id}
                className="p-3 bg-purple-50 border border-purple-200 rounded-lg"
              >
                <div className="flex items-start gap-2 mb-1.5">
                  <span className="font-mono text-[11px] font-bold text-purple-700 shrink-0">
                    {s.sha?.substring(0, 7)}
                  </span>
                  <span className="text-xs text-[#1f2328] flex-1">{s.commit_message}</span>
                  {s.confidence !== undefined && (
                    <span className="text-[10px] font-bold text-purple-700 bg-purple-100 border border-purple-200 rounded px-1.5 py-0.5 shrink-0 tabular-nums">
                      {Math.round(s.confidence * 100)}%
                    </span>
                  )}
                </div>

                <p className="text-[11px] text-[#636c76] mb-2">
                  {t('tasks.dev.suggestion_task')}{' '}
                  <span className="font-semibold text-[#1f2328]">{s.task_title}</span>
                </p>

                {canEdit && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => decide(s.link_id, 'confirm')}
                      disabled={suggestBusy === s.link_id}
                      className="px-2.5 py-1 bg-[#1a7f37] text-white rounded text-[11px] font-bold hover:bg-[#15803d] transition disabled:opacity-50 flex items-center gap-1"
                    >
                      <Check size={12} />
                      {t('tasks.dev.suggestion_accept')}
                    </button>
                    <button
                      onClick={() => decide(s.link_id, 'reject')}
                      disabled={suggestBusy === s.link_id}
                      className="px-2.5 py-1 bg-white border border-purple-300 text-[#636c76] rounded text-[11px] font-bold hover:bg-white transition disabled:opacity-50 flex items-center gap-1"
                    >
                      <X size={12} />
                      {t('tasks.dev.suggestion_reject')}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>

          {suggestMessage && (
            <p className="mt-2 text-[11px] text-[#636c76]">{suggestMessage}</p>
          )}
        </section>
      )}

      {/* Ветки */}
      {card.branches.length > 0 && (
        <section>
          <SectionTitle>{t('tasks.dev.branches')}</SectionTitle>
          <div className="space-y-1.5">
            {card.branches.map((b) => (
              <div
                key={b.id}
                className="flex items-center gap-2 p-2.5 bg-white border border-[#d0d7de] rounded-lg group"
              >
                <GitBranch size={15} className="text-emerald-600 shrink-0" />
                <span className="font-mono text-xs font-bold text-[#1f2328] truncate flex-1">
                  {b.name}
                </span>
                <SourceBadge source={b.link_source} t={t} />
                {canEdit && b.link_id && (
                  <IconBtn onClick={() => unlink(b.link_id!)} busy={busy === b.link_id} title={t('tasks.dev.unlink')}>
                    <Link2Off size={13} />
                  </IconBtn>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Pull Request */}
      {card.pull_requests.map((pr) => (
        <section key={pr.id}>
          <SectionTitle>{t('tasks.dev.pull_requests')}</SectionTitle>
          <div className="p-3 bg-white border border-[#d0d7de] rounded-lg space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <GitPullRequest size={15} className="text-purple-600 shrink-0" />
              <span className="text-xs font-bold text-[#1f2328]">#{pr.external_id}</span>
              <a
                href={pr.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-semibold text-[#0969da] hover:underline truncate"
              >
                {pr.title}
              </a>
              <span
                className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase border ${
                  pr.state === 'merged'
                    ? 'bg-purple-50 text-purple-700 border-purple-200'
                    : pr.state === 'closed'
                    ? 'bg-red-50 text-red-700 border-red-200'
                    : 'bg-green-50 text-green-700 border-green-200'
                }`}
              >
                {t(`tasks.dev.pr_state.${pr.state}`) || pr.state}
              </span>
              <SourceBadge source={pr.link_source} t={t} />
              {pr.url && <ExternalLink size={12} className="text-[#d0d7de]" />}
            </div>

            <div className="flex items-center gap-3 text-[10px] text-[#636c76] flex-wrap">
              {pr.source_branch && (
                <span className="font-mono">
                  {pr.source_branch} → {pr.target_branch}
                </span>
              )}
              <DiffStat additions={pr.additions} deletions={pr.deletions} t={t} />
              {pr.changed_files > 0 && (
                <span className="flex items-center gap-1">
                  <FileCode2 size={11} />
                  {t('tasks.dev.files_n', { count: pr.changed_files })}
                </span>
              )}
            </div>

            {/* CI */}
            {pr.ci_status && <CiBadge status={pr.ci_status} url={pr.ci_url} t={t} />}

            {/* Ревьюеры */}
            {pr.reviewers.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-bold text-[#636c76] uppercase">
                  {t('tasks.dev.reviewers')}
                </span>
                {pr.reviewers.map((r) => (
                  <span
                    key={r.login}
                    className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold border ${
                      r.state === 'approved'
                        ? 'bg-green-50 text-green-700 border-green-200'
                        : r.state === 'changes_requested'
                        ? 'bg-amber-50 text-amber-700 border-amber-200'
                        : r.state === 'commented'
                        ? 'bg-blue-50 text-blue-700 border-blue-200'
                        : 'bg-gray-50 text-gray-600 border-gray-200'
                    }`}
                  >
                    {r.login}
                    {r.state === 'requested' && ` · ${t('tasks.dev.awaiting')}`}
                  </span>
                ))}
              </div>
            )}

            {canEdit && pr.link_id && (
              <div className="flex justify-end">
                <IconBtn onClick={() => unlink(pr.link_id!)} busy={busy === pr.link_id} title={t('tasks.dev.unlink')}>
                  <Link2Off size={13} />
                </IconBtn>
              </div>
            )}
          </div>
        </section>
      ))}

      {/* Отклонённые привязки. Отказ — это решение человека, и он может
          передумать: коммит могли внести позже, или отказ был по
          невнимательности. Без возможности вернуть отказ был бы
          тупиком. */}
      {(card.rejected?.length ?? 0) > 0 && (
        <section>
          <button
            onClick={() => setShowRejected((v) => !v)}
            className="flex items-center justify-between mb-2 w-full text-left"
          >
            <SectionTitle>
              {t('tasks.dev.rejected')} ({card.rejected!.length})
            </SectionTitle>
            {showRejected ? (
              <ChevronDown size={14} className="text-[#636c76] shrink-0" />
            ) : (
              <ChevronRight size={14} className="text-[#636c76] shrink-0" />
            )}
          </button>
          {showRejected && (
            <div className="space-y-1">
              {card.rejected!.map((r) => (
                <div
                  key={r.link_id}
                  className="flex items-center gap-2 p-2.5 bg-white border border-[#d0d7de] rounded-lg"
                >
                  <span className="font-mono text-[11px] font-bold text-[#6e7781] shrink-0">
                    {r.sha?.substring(0, 7)}
                  </span>
                  <span className="text-xs text-[#636c76] truncate flex-1">
                    {r.commit_message}
                  </span>
                  <button
                    onClick={() => restoreRejected(r.link_id)}
                    disabled={busy === r.link_id}
                    className="px-2 py-1 bg-white border border-[#d0d7de] text-[#1f2328] rounded text-[10px] font-bold hover:bg-gray-50 disabled:opacity-50 shrink-0"
                  >
                    {busy === r.link_id ? (
                      <Loader2 size={11} className="animate-spin" />
                    ) : (
                      t('tasks.dev.restore')
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Коммиты */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <SectionTitle>
            {t('tasks.dev.commits')} ({card.commits.length})
          </SectionTitle>
          {canEdit && (
            <button
              onClick={() => setPickerOpen(!pickerOpen)}
              className="px-2 py-1 rounded-md text-[11px] font-bold bg-[#0969da] text-white hover:bg-[#0861c5] transition flex items-center gap-1"
            >
              <Plus size={12} />
              {t('tasks.dev.relink')}
            </button>
          )}
        </div>

        <div className="space-y-1.5">
          {card.commits.map((c) => {
            const open = expandedCommit === c.id;
            return (
              <div
                key={c.id}
                className={`bg-white border rounded-lg overflow-hidden ${
                  open ? 'border-[#0969da]' : 'border-[#d0d7de]'
                }`}
              >
                <div className="flex items-center gap-2 p-2.5">
                  <button
                    onClick={() => setExpandedCommit(open ? null : c.id)}
                    className="flex items-center gap-2 flex-1 min-w-0 text-left"
                  >
                    {open ? (
                      <ChevronDown size={14} className="text-[#636c76] shrink-0" />
                    ) : (
                      <ChevronRight size={14} className="text-[#636c76] shrink-0" />
                    )}
                    <span className="font-mono text-[11px] font-bold text-[#0969da] shrink-0">
                      {c.sha?.substring(0, 7)}
                    </span>
                    <span className="text-xs text-[#1f2328] truncate flex-1">{c.message}</span>
                  </button>

                  <DiffStat additions={c.additions} deletions={c.deletions} t={t} />
                  <CommitTypeBadge
                    type={c.commit_type}
                    confidence={c.commit_type_confidence}
                    reliable={c.commit_type_reliable}
                    t={t}
                  />
                  <SourceBadge source={c.link_source} confidence={c.confidence} t={t} />

                  {canEdit && c.link_id && (
                    <IconBtn onClick={() => unlink(c.link_id!)} busy={busy === c.link_id} title={t('tasks.dev.unlink')}>
                      <Link2Off size={13} />
                    </IconBtn>
                  )}
                </div>

                {open && (
                  <div className="px-3 pb-3 pt-1 border-t border-[#f0f2f4] space-y-2">
                    {/* В свёрнутом виде сообщение обрезано одной строкой,
                        а у коммита оно часто многострочное: описание
                        причины изменения или тело запроса. Поэтому в
                        раскрытом блоке показываем текст целиком, без
                        truncate — иначе половина сообщения не читается
                        нигде. */}
                    {c.message && (
                      <div className="text-[11px] leading-relaxed">
                        <div className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider mb-0.5">
                          {t('tasks.dev.commit_message')}
                        </div>
                        <p className="text-[#1f2328] whitespace-pre-wrap break-words font-mono">
                          {c.message}
                        </p>
                      </div>
                    )}
                    <div className="flex items-center gap-2 text-[11px] text-[#636c76]">
                      <User size={11} />
                      {c.author || t('history.system')}
                      {c.timestamp && (
                        <span className="ml-auto">
                          {new Date(c.timestamp).toLocaleString()}
                        </span>
                      )}
                      {c.url && (
                        <a href={c.url} target="_blank" rel="noopener noreferrer" className="hover:text-[#0969da]">
                          <ExternalLink size={11} />
                        </a>
                      )}
                    </div>
                    {c.created_by && (
                      <p className="text-[10px] text-[#636c76]">
                        {t('tasks.dev.confirmed_by', { name: c.created_by })}
                      </p>
                    )}
                    {c.commit_type && (
                      <p className="text-[10px] text-[#636c76] leading-relaxed">
                        {t('tasks.dev.commit_type_hint')}{' '}
                        <span className="font-semibold text-[#1f2328]">
                          {t(`task_type.${c.commit_type}`)}
                        </span>
                        {c.commit_type_confidence !== undefined && c.commit_type_confidence !== null && (
                          <> · {Math.round(c.commit_type_confidence * 100)}%</>
                        )}
                        {!c.commit_type_reliable && (
                          <span className="text-amber-700">
                            {' '}
                            · {t('tasks.dev.commit_type_uncertain_short')}
                          </span>
                        )}
                      </p>
                    )}
                    {c.files.length > 0 && (
                      <div className="space-y-0.5">
                        {c.files.map((f) => (
                          <div key={f.path} className="flex items-center gap-2 text-[11px] py-0.5">
                            {FILE_ICON[f.status] ?? FILE_ICON.modified}
                            <span className="font-mono text-[#1f2328] truncate">{f.path}</span>
                            {f.previous_path && (
                              <span className="text-[10px] text-[#636c76] truncate">
                                ← {f.previous_path}
                              </span>
                            )}
                            {f.additions > 0 && (
                              <span className="text-[10px] text-green-600 font-bold">+{f.additions}</span>
                            )}
                            {f.deletions > 0 && (
                              <span className="text-[10px] text-red-600 font-bold">-{f.deletions}</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Все изменённые файлы */}
      {card.files.length > 0 && (
        <section>
          <button
            onClick={() => setFilesOpen(!filesOpen)}
            className="w-full flex items-center gap-2 text-left"
          >
            {filesOpen ? (
              <ChevronDown size={14} className="text-[#636c76]" />
            ) : (
              <ChevronRight size={14} className="text-[#636c76]" />
            )}
            <span className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">
              {t('tasks.dev.changed_files')} ({card.files.length})
            </span>
          </button>
          {filesOpen && (
            <div className="mt-2 max-h-64 overflow-y-auto bg-white border border-[#d0d7de] rounded-lg p-2 space-y-0.5">
              {card.files.map((f) => (
                <div key={f.path} className="flex items-center gap-2 text-[11px] py-0.5 px-1">
                  {FILE_ICON[f.status] ?? FILE_ICON.modified}
                  <span className="font-mono text-[#1f2328] truncate flex-1">{f.path}</span>
                  {f.additions > 0 && <span className="text-[10px] text-green-600 font-bold">+{f.additions}</span>}
                  {f.deletions > 0 && <span className="text-[10px] text-red-600 font-bold">-{f.deletions}</span>}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {pickerOpen && canEdit && (
        <LinkPicker
          taskId={card.task_id}
          onClose={() => setPickerOpen(false)}
          onLinked={() => {
            setPickerOpen(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{children}</span>
  );
}

function DiffStat({ additions, deletions, t }: { additions: number; deletions: number; t: any }) {
  if (!additions && !deletions) return null;
  return (
    <span className="text-[10px] font-mono shrink-0">
      {additions > 0 && <span className="text-green-600">+{additions}</span>}
      {deletions > 0 && <span className="text-red-600 ml-1">-{deletions}</span>}
    </span>
  );
}

function CiBadge({ status, url, t }: { status: string; url?: string; t: any }) {
  const map: Record<string, { cls: string; Icon: React.ElementType; label: string }> = {
    success: { cls: 'bg-green-50 text-green-700 border-green-200', Icon: CheckCircle2, label: t('tasks.dev.ci_passed') },
    failure: { cls: 'bg-red-50 text-red-700 border-red-200', Icon: AlertTriangle, label: t('tasks.dev.ci_failed') },
    pending: { cls: 'bg-amber-50 text-amber-700 border-amber-200', Icon: Clock, label: t('tasks.dev.ci_running') },
  };
  const conf = map[status];
  if (!conf) return null;
  const { cls, Icon, label } = conf;
  const inner = (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${cls}`}>
      <Icon size={11} />
      {label}
    </span>
  );
  return url ? (
    <a href={url} target="_blank" rel="noopener noreferrer" className="w-fit">
      {inner}
    </a>
  ) : (
    inner
  );
}

function SourceBadge({ source, confidence, t }: { source?: string; confidence?: number | null; t: any }) {
  if (!source) return null;
  const isManual = source === 'manual';
  const isModel = source === 'model';
  const color = isManual
    ? 'bg-blue-50 text-blue-700 border-blue-200'
    : isModel
    ? 'bg-purple-50 text-purple-700 border-purple-200'
    : 'bg-gray-50 text-gray-600 border-gray-200';
  const label = isManual
    ? t('tasks.dev.src_manual')
    : isModel
    ? t('tasks.dev.src_model')
    : t('tasks.dev.src_auto');

  return (
    <span
      className={`px-1.5 py-0.5 rounded text-[9px] font-bold border shrink-0 ${color}`}
      title={t('tasks.dev.source_hint')}
    >
      {label}
      {confidence != null && ` ${confidence.toFixed(2)}`}
      {confidence != null && confidence < 0.75 && (
        <AlertTriangle size={9} className="inline ml-0.5 text-amber-600" />
      )}
    </span>
  );
}

function IconBtn({
  children,
  onClick,
  busy,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  busy?: boolean;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      title={title}
      className="p-1 text-[#636c76] hover:text-red-600 hover:bg-red-50 rounded transition disabled:opacity-50 shrink-0"
    >
      {busy ? <Loader2 size={13} className="animate-spin" /> : children}
    </button>
  );
}

function LinkPicker({
  taskId,
  onClose,
  onLinked,
}: {
  taskId: number;
  onClose: () => void;
  onLinked: () => void;
}) {
  const { t } = useTranslation();
  const [data, setData] = useState<{ commits: any[]; pull_requests: any[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get(`/git/task/${taskId}/unlinked-candidates`)
      .then(({ data: d }) => {
        if (!cancelled) setData(d);
      })
      .catch((err: any) => {
        // Раньше ошибка молча превращалась в пустое окно: запрос падал,
        // а catch его съедал, и выглядело так, будто привязывать нечего.
        if (!cancelled) {
          setData(null);
          setError(
            err?.response?.data?.detail || t('tasks.dev.picker_failed')
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [taskId, t]);

  const link = async (linkType: string, targetId: number) => {
    setBusy(targetId);
    try {
      await api.post(`/git/task/${taskId}/links`, { link_type: linkType, target_id: targetId });
      onLinked();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-lg w-full max-w-lg max-h-[70vh] flex flex-col overflow-hidden shadow-2xl border border-[#d0d7de]">
        <div className="px-4 py-3 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
          <h4 className="text-sm font-bold text-[#1f2328]">{t('tasks.dev.picker_title')}</h4>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 rounded hover:bg-gray-200">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading ? (
            <div className="p-8 text-center">
              <Loader2 className="animate-spin mx-auto text-blue-500" size={20} />
            </div>
          ) : (
            <>
              {data?.commits.length ? (
                <div>
                  <SectionTitle>{t('tasks.dev.commits')}</SectionTitle>
                  <div className="mt-1.5 space-y-1">
                    {data.commits.map((c) => (
                      <div key={c.id} className="flex items-center gap-2 p-2 border border-[#d0d7de] rounded hover:bg-[#f6f8fa]">
                        <span className="font-mono text-[10px] text-[#0969da] shrink-0">
                          {c.sha?.substring(0, 7)}
                        </span>
                        <span className="text-xs text-[#1f2328] truncate flex-1">{c.message}</span>
                        <button
                          onClick={() => link('commit', c.id)}
                          disabled={busy === c.id}
                          className="px-2 py-1 bg-[#0969da] text-white rounded text-[10px] font-bold hover:bg-[#0861c5] disabled:opacity-50 shrink-0"
                        >
                          {busy === c.id ? <Loader2 size={11} className="animate-spin" /> : t('tasks.dev.link')}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {data?.pull_requests.length ? (
                <div>
                  <SectionTitle>{t('tasks.dev.pull_requests')}</SectionTitle>
                  <div className="mt-1.5 space-y-1">
                    {data.pull_requests.map((pr) => (
                      <div key={pr.id} className="flex items-center gap-2 p-2 border border-[#d0d7de] rounded hover:bg-[#f6f8fa]">
                        <span className="text-[10px] font-bold text-[#1f2328] shrink-0">#{pr.external_id}</span>
                        <span className="text-xs text-[#1f2328] truncate flex-1">{pr.title}</span>
                        <button
                          onClick={() => link('pull_request', pr.id)}
                          disabled={busy === pr.id}
                          className="px-2 py-1 bg-[#0969da] text-white rounded text-[10px] font-bold hover:bg-[#0861c5] disabled:opacity-50 shrink-0"
                        >
                          {busy === pr.id ? <Loader2 size={11} className="animate-spin" /> : t('tasks.dev.link')}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {error ? (
                <p className="text-center text-sm text-red-700 bg-red-50 border border-red-200 rounded-md py-4 px-3">
                  {error}
                </p>
              ) : data && data.commits.length === 0 && data.pull_requests.length === 0 ? (
                <p className="text-center text-sm text-[#636c76] py-8">{t('tasks.dev.picker_empty')}</p>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
