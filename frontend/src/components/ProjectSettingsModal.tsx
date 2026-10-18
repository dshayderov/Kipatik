import React, { useState, useEffect } from 'react';
import {
  X,
  Loader2,
  Check,
  Settings as SettingsIcon,
  Trash2,
  AlertTriangle,
  Github,
  Copy,
  ExternalLink,
  RefreshCw,
  GitCommit,
  ArrowRight,
  Info,
  Zap,
  Users,
  Upload
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import { Project, ProjectBackground, UnlinkedGitEvent } from '../types';
import { backgroundImageUrl } from '../background';
import { useAuth } from '../context/AuthContext';
import RepoConnectWizard from './RepoConnectWizard';
import AuthorMappingModal from './AuthorMappingModal';

interface ProjectSettingsModalProps {
  project: Project;
  onClose: () => void;
  onUpdated: () => void;
}

interface VerificationResult {
  repo_found: boolean;
  secret_configured: boolean;
  event_received: boolean;
  signature_verified: boolean;
  last_event_at?: string;
  last_event_verified_at?: string;
}

const ProjectSettingsModal: React.FC<ProjectSettingsModalProps> = ({ project, onClose, onUpdated }) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'general' | 'git' | 'unlinked'>('general');
  
  const repositories = project.repositories || [];
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(repositories[0]?.id ?? null);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [isAuthorsOpen, setIsAuthorsOpen] = useState(false);
  const mainRepo = repositories.find((r) => r.id === selectedRepoId) || repositories[0];

  // General Info
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description || '');

  // Фон страницы проекта.
  //
  // Сохраняется сразу, а не кнопкой «Сохранить» формы: картинка
  // передаётся файлом, а общая кнопка отправляет только поля формы.
  // Если бы фон ждал её нажатия, смена фона выглядела бы отменённой
  // до последнего — и наоборот, сохранение названия сбрасывало бы
  // несохранённый выбор фона.
  const [background, setBackground] = useState<ProjectBackground>(
    project.background ?? 'none',
  );
  const [backgroundUrl, setBackgroundUrl] = useState<string | null>(
    project.background_url ?? null,
  );
  const [bgBusy, setBgBusy] = useState(false);
  const [bgError, setBgError] = useState<string | null>(null);
  const bgInputRef = React.useRef<HTMLInputElement>(null);
  
  // Git Settings
  //
  // Полей ввода здесь больше нет: подключением и настройкой репозитория
  // занимается мастер (RepoConnectWizard). Состояния repoUrl/repoName/
  // apiUrl/provider/webhookSecret остались бы мёртвыми.
  const [isSaving, setIsSaving] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState<VerificationResult | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  // Прогресс фонового разбора, который идёт после синхронизации.
  // Отдельное состояние, потому что сервер отдаёт его только в момент
  // ответа, а разбор продолжается уже без нас.
  const [syncProgress, setSyncProgress] = useState<{ done: number; total: number } | null>(null);
  const [unlinkedEvents, setUnlinkedEvents] = useState<UnlinkedGitEvent[]>([]);
  const [isLoadingUnlinked, setIsLoadingUnlinked] = useState(false);
  const [linkTaskId, setLinkTaskId] = useState<Record<number, string>>({});
  
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (activeTab === 'unlinked') {
      fetchUnlinkedEvents();
    }
  }, [activeTab]);

  const fetchUnlinkedEvents = async () => {
    setIsLoadingUnlinked(true);
    try {
      const { data } = await api.get(`/git/unlinked/${project.id}`);
      setUnlinkedEvents(data);
    } catch (err) {
      console.error("Failed to fetch unlinked events", err);
    } finally {
      setIsLoadingUnlinked(false);
    }
  };

  const handleLinkEvent = async (eventId: number) => {
    const taskId = linkTaskId[eventId];
    if (!taskId) return;
    
    try {
      await api.post(`/git/link-event/${eventId}/${taskId}`);
      setUnlinkedEvents(prev => prev.filter(e => e.id !== eventId));
      onUpdated();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to link event");
    }
  };

  const handleVerify = async () => {
    if (!mainRepo?.id) return;
    setIsVerifying(true);
    setVerificationResult(null);
    try {
      const { data } = await api.post(`/git/verify/${mainRepo.id}`);
      setVerificationResult(data);
    } catch (err) {
      setError("Verification failed");
    } finally {
      setIsVerifying(false);
    }
  };

  // Ручная сверка с провайдером. Без неё после подключения нечего
  // показать: ближайшая фоновая синхронизация — через
  // GIT_SYNC_INTERVAL_SECONDS (5 минут), и выглядит это
  // как «ничего не произошло».
  const handleSync = async () => {
    if (!mainRepo?.id) return;
    setIsSyncing(true);
    setSyncMessage(null);
    setSyncProgress(null);
    try {
      const { data } = await api.post(`/git/${mainRepo.id}/sync`);

      if (data.status !== 'ok') {
        setSyncMessage(
          data.last_sync_error || data.error || t('projects.git.sync_failed')
        );
      } else if (data.still_running) {
        // Сервер дождался потолка ожидания и отпустил запрос, а разбор
        // ещё идёт. Так и говорим: не «готово», а «идёт» — иначе
        // пользователь решит, что предложения не появятся.
        setSyncMessage(
          t('projects.git.sync_ok_continuing', {
            commits: data.commits ?? 0,
            done: data.enrichment_done ?? 0,
            total: data.enrichment_total ?? 0,
          })
        );
      } else if (data.enrichment_status === 'error') {
        setSyncMessage(
          t('projects.git.sync_ok_enrichment_failed', {
            commits: data.commits ?? 0,
          }) + ' ' + (data.enrichment_error || '')
        );
      } else {
        setSyncMessage(
          t('projects.git.sync_ok', {
            commits: data.commits ?? 0,
            branches: data.branches ?? 0,
          })
        );
      }
      onUpdated();

      // Если разбор ещё идёт, опрашиваем статус: без этого экран
      // навсегда остаётся с «Идёт разбор 0/50», хотя фоновая задача
      // давно закончилась, и результат выглядит как зависший.
      if (data.still_running) {
        await waitForEnrichment(project.id);
        onUpdated();
        setSyncMessage(
          data.enrichment_status === 'error'
            ? (data.enrichment_error || t('projects.git.enrichment_error'))
            : t('projects.git.sync_ok', {
                commits: data.commits ?? 0,
                branches: data.branches ?? 0,
              })
        );
      }    } catch (err: any) {
      setSyncMessage(err.response?.data?.detail || t('projects.git.sync_failed'));
    } finally {
      setIsSyncing(false);
    }
  };

  /** Ждёт окончания фонового разбора, опрашивая статус репозитория. */
  const waitForEnrichment = async (pid: number) => {
    const deadline = Date.now() + 120_000;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const { data } = await api.get(`/projects/${pid}/repositories`);
        const found = (data || []).find((r: any) => r.id === mainRepo?.id);
        if (!found) return;
        setSyncProgress({
          done: found.enrichment_done ?? 0,
          total: found.enrichment_total ?? 0,
        });
        if (found.enrichment_status && found.enrichment_status !== 'running') {
          return;
        }
      } catch {
        return;
      }
    }
  };

  const isOwner = user?.id === project.owner_id;
  const isEditable = isOwner || user?.is_superuser;

  const handleSaveGeneral = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isEditable) return;
    
    setIsSaving(true);
    setError(null);
    try {
      await api.patch(`/projects/${project.id}`, {
        name,
        description
      });
      onUpdated();
      onClose();
    } catch (err: any) {
      setError(err.response?.data?.detail || t('projects.update_error'));
    } finally {
      setIsSaving(false);
    }
  };

  // Раньше здесь была handleSaveGit — форма подключения репозитория.
  // Она удалена вместе с полями: подключением занимается мастер.

  // --- Фон ------------------------------------------------------------
  //
  // Вид «custom» через обновление проекта поставить нельзя: сервер
  // его там не принимает, потому что файл ещё не загружен и фон был бы
  // битым. Поэтому выбор своего фона сразу открывает выбор файла, а
  // всё остальное применяется обычным запросом.
  const applyBackground = async (kind: 'none' | 'default') => {
    setBgBusy(true);
    setBgError(null);
    try {
      const { data } = await api.patch(`/projects/${project.id}`, {
        background: kind,
      });
      setBackground(data.background ?? 'none');
      setBackgroundUrl(data.background_url ?? null);
      onUpdated();
    } catch (err: any) {
      setBgError(err.response?.data?.detail || t('projects.background_error'));
    } finally {
      setBgBusy(false);
    }
  };

  const uploadBackground = async (file: File) => {
    setBgBusy(true);
    setBgError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const { data } = await api.post(
        `/projects/${project.id}/background`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      setBackground(data.background ?? 'custom');
      setBackgroundUrl(data.background_url ?? null);
      onUpdated();
    } catch (err: any) {
      setBgError(err.response?.data?.detail || t('projects.background_error'));
    } finally {
      setBgBusy(false);
      if (bgInputRef.current) bgInputRef.current.value = '';
    }
  };

  const removeBackground = async () => {
    setBgBusy(true);
    setBgError(null);
    try {
      const { data } = await api.delete(`/projects/${project.id}/background`);
      setBackground(data.background ?? 'none');
      setBackgroundUrl(data.background_url ?? null);
      onUpdated();
    } catch (err: any) {
      setBgError(err.response?.data?.detail || t('projects.background_error'));
    } finally {
      setBgBusy(false);
    }
  };

  const pickBackgroundFile = () => {
    setBgError(null);
    if (!isEditable || bgBusy) return;
    bgInputRef.current?.click();
  };

  // Виды фона в порядке «от простого к сложному». Значение хранится
  // тем же, что и на сервере.
  const BG_OPTIONS: { value: ProjectBackground; labelKey: string }[] = [
    { value: 'none', labelKey: 'projects.background_none' },
    { value: 'default', labelKey: 'projects.background_default' },
    { value: 'custom', labelKey: 'projects.background_custom' },
  ];

  const webhookUrl = `${window.location.origin}/api/v1/git/webhook/${mainRepo?.id || '{id}'}`;

  const copyToClipboard = () => {
    navigator.clipboard.writeText(webhookUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDeleteProject = async () => {
    if (confirm(t('projects.delete_confirm_text') || "Are you sure you want to delete this project? This action cannot be undone.")) {
      try {
        await api.delete(`/projects/${project.id}`);
        window.location.href = '/projects'; 
      } catch (err: any) {
        alert(err.response?.data?.detail || t('projects.delete_failed'));
      }
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
      <div className="bg-white rounded-xl w-full max-w-lg shadow-2xl border border-[#d0d7de] flex flex-col overflow-hidden max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <SettingsIcon size={18} className="text-[#636c76]" />
            <h2 className="text-base font-bold text-[#1f2328]">{t('projects.settings_title')}</h2>
          </div>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 rounded-md hover:bg-gray-200 transition">
            <X size={20} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#d0d7de] bg-[#f6f8fa] px-4">
          <button 
            onClick={() => setActiveTab('general')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${activeTab === 'general' ? 'border-[#0969da] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}
          >
            {t('tasks.tabs.general')}
          </button>
          <button 
            onClick={() => setActiveTab('git')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${activeTab === 'git' ? 'border-[#0969da] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}
          >
            Git
          </button>
          <button 
            onClick={() => setActiveTab('unlinked')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 flex items-center gap-2 ${activeTab === 'unlinked' ? 'border-[#0969da] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}
          >
            {t('projects.git.unlinked_events')}
            {unlinkedEvents.length > 0 && <span className="bg-red-100 text-red-600 px-1.5 py-0.5 rounded-full text-[10px] font-bold">{unlinkedEvents.length}</span>}
          </button>
        </div>

        <div className="overflow-y-auto flex-1 min-h-[400px]">
          {error && (
            <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 text-red-600 rounded-lg text-sm flex items-center gap-2">
              <AlertTriangle size={16} />
              {error}
            </div>
          )}

          {/* Условие isEditable, а не isOwner: суперюзер править может,
              иначе плашка врала бы тем, кто редактирование разрешено. */}
          {!isEditable && (
            <div className="mx-6 mt-4 p-3 bg-amber-50 border border-amber-200 text-amber-700 rounded-lg text-xs flex items-center gap-2">
              <AlertTriangle size={16} />
              {t('projects.owner_only_hint')}
            </div>
          )}

          {activeTab === 'general' ? (
            <form id="general-form" onSubmit={handleSaveGeneral} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-bold text-[#1f2328] mb-2">{t('projects.project_name')}</label>
                <input 
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={!isEditable}
                  className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-50"
                  placeholder="e.g. My Awesome Project"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-[#1f2328] mb-2">{t('projects.description')}</label>
                <textarea 
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={!isEditable}
                  rows={4}
                  className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all resize-none disabled:opacity-50"
                  placeholder={t('projects.description_placeholder')}
                />
              </div>

              {/* Фон страницы. Общий для всех участников проекта: меняют
                  его те же, кто меняет название. Применяется сразу, а не
                  кнопкой формы, потому что картинка идёт файлом. */}
              <div className="pt-2 border-t border-[#d0d7de]">
                <label className="block text-sm font-bold text-[#1f2328] mb-1">
                  {t('projects.background')}
                </label>
                <p className="text-[11px] text-[#636c76] mb-2">
                  {t('projects.background_hint')}
                </p>

                <div className="grid grid-cols-3 gap-2">
                  {BG_OPTIONS.map((opt) => {
                    const active = background === opt.value;
                    const preview = backgroundImageUrl(
                      opt.value,
                      backgroundUrl,
                    );
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        disabled={!isEditable || bgBusy}
                        onClick={() =>
                          opt.value === 'custom'
                            ? pickBackgroundFile()
                            : applyBackground(opt.value as 'none' | 'default')
                        }
                        className={`relative rounded-lg border-2 overflow-hidden text-left transition ${
                          active
                            ? 'border-[#0969da] ring-1 ring-[#0969da]'
                            : 'border-[#d0d7de] hover:border-[#8c959f]'
                        } disabled:opacity-50 disabled:hover:border-[#d0d7de]`}
                      >
                        {/* Превью рисует тот же фон, что и страница,
                            иначе выбор приходилось бы проверять,
                            закрыв окно. */}
                        <div
                          className="h-12 bg-cover bg-center bg-white"
                          style={
                            preview
                              ? { backgroundImage: `url("${preview}")` }
                              : undefined
                          }
                        />
                        <div className="px-2 py-1.5 flex items-center gap-1.5 bg-white">
                          <span className="text-[11px] font-bold text-[#1f2328] truncate">
                            {t(opt.labelKey)}
                          </span>
                          {active && (
                            <Check size={12} className="text-[#0969da] shrink-0" />
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {background === 'custom' && (
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={pickBackgroundFile}
                      disabled={!isEditable || bgBusy}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-[#d0d7de] rounded text-[11px] font-bold hover:bg-gray-50 disabled:opacity-50"
                    >
                      {bgBusy ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Upload size={12} />
                      )}
                      {t('projects.background_replace')}
                    </button>
                    <button
                      type="button"
                      onClick={removeBackground}
                      disabled={!isEditable || bgBusy}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-[#d0d7de] rounded text-[11px] font-bold text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      <Trash2 size={12} />
                      {t('projects.background_remove')}
                    </button>
                  </div>
                )}

                {bgBusy && (
                  <p className="mt-2 text-[11px] text-[#636c76] flex items-center gap-1.5">
                    <Loader2 size={11} className="animate-spin" />
                    {t('projects.background_saving')}
                  </p>
                )}

                {bgError && (
                  <p className="mt-2 text-[11px] text-red-700 flex items-start gap-1.5">
                    <AlertTriangle size={12} className="shrink-0 mt-px" />
                    {bgError}
                  </p>
                )}

                {/* Поле выбора файла скрыто и живёт внутри формы: отправить его
                    значение форма не может — у input нет кнопки
                    отправки, а вызывается он только по клику. Фокус
                    с него снимаем сразу, иначе повторный выбор того же
                    файла не сработал бы. */}
                <input
                  ref={bgInputRef}
                  type="file"
                  accept="image/png,image/jpeg"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadBackground(f);
                  }}
                />
              </div>
            </form>
          ) : activeTab === 'git' ? (
              <div className="p-6 space-y-4">
              {/* Кнопка запуска мастера подключения. Старая форма
                  подключения удалена: она задавала те же поля, что и
                  мастер, но ветку при этом не сохраняла — из-за чего
                  репозиторий уезжал в main и синхронизация искала
                  несуществующую ветку. */}
              <button
                type="button"
                onClick={() => setIsWizardOpen(true)}
                className="w-full px-4 py-3 bg-[#0969da] text-white rounded-lg text-sm font-bold hover:bg-[#0861c5] transition flex items-center justify-center gap-2"
              >
                <Zap size={16} />
                {repositories.length > 0
                  ? t('projects.git.wizard.add_another')
                  : t('projects.git.wizard.start')}
              </button>

              {/* Список подключённых репозиториев (проект может иметь несколько) */}
              {repositories.length > 0 && (
                <div className="space-y-1.5">
                  <label className="block text-[10px] font-bold text-[#636c76] uppercase tracking-wider">
                    {t('projects.git.repositories_list')}
                  </label>
                  <button
                    type="button"
                    onClick={() => setIsAuthorsOpen(true)}
                    className="w-full px-3 py-2 bg-white border border-[#d0d7de] rounded-lg text-xs font-bold text-[#1f2328] hover:bg-[#f6f8fa] transition flex items-center justify-center gap-2"
                  >
                    <Users size={14} />
                    {t('projects.git.authors.open')}
                  </button>
                  {repositories.map((r) => {
                    const active = r.id === mainRepo?.id;
                    return (
                      <button
                        key={r.id}
                        type="button"
                        onClick={() => { setSelectedRepoId(r.id); setVerificationResult(null); }}
                        className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition ${
                          active
                            ? 'border-[#0969da] bg-[#ddf4ff]'
                            : 'border-[#d0d7de] hover:border-[#8b949e]'
                        }`}
                      >
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                            active ? 'bg-white text-[#0969da]' : 'bg-[#f6f8fa] text-[#636c76]'
                          }`}
                        >
                          <Github size={16} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-bold text-[#1f2328] truncate">{r.repo_name || r.url}</p>
                          <p className="text-[10px] text-[#636c76] truncate">{r.url}</p>
                        </div>
                        {r.last_sync_status === 'error' && (
                          <AlertTriangle size={14} className="text-red-500 shrink-0" />
                        )}
                        {r.last_sync_status === 'ok' && (
                          <Check size={14} className="text-green-600 shrink-0" />
                        )}
                      </button>
                    );
                  })}
                </div>
              )}

              <div className="p-4 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg ${mainRepo?.id ? 'bg-[#dafbe1] text-[#1a7f37]' : 'bg-[#fff8c5] text-[#9a6700]'}`}>
                    <Github size={20} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-[#1f2328]">{t('projects.git.repository_settings')}</h4>
                    <span className="text-xs text-[#636c76]">
                      {mainRepo?.id ? t('projects.git.connected') : t('projects.git.not_configured')}
                    </span>
                  </div>
                </div>
                {mainRepo?.id && (
                  <button
                    type="button"
                    onClick={handleVerify}
                    disabled={isVerifying}
                    className="p-2 hover:bg-gray-200 rounded-md transition-all text-[#636c76] flex items-center gap-2 text-xs font-bold"
                  >
                    {isVerifying ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                    {t('projects.git.verification')}
                  </button>
                )}
              </div>

              {/* Синхронизация вынесена отдельным блоком: она не про
                  настройки, а про состояние данных, и её результат —
                  то, ради чего сюда и приходят. */}
              {mainRepo?.id && (
                <div className="p-4 border border-[#d0d7de] rounded-lg bg-white space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-bold text-[#1f2328]">
                      {t('projects.git.sync_title')}
                    </h4>
                    <button
                      type="button"
                      onClick={handleSync}
                      disabled={isSyncing}
                      className="px-3 py-1.5 bg-[#0969da] text-white hover:bg-[#0861c5] disabled:opacity-50 rounded-md transition-all flex items-center gap-2 text-xs font-bold"
                    >
                      {isSyncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                      {t('projects.git.sync_now')}
                    </button>
                  </div>

                  <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
                    <dt className="text-[#636c76]">{t('projects.git.wizard.default_branch')}</dt>
                    <dd className="text-[#1f2328] font-mono">{mainRepo.default_branch || '—'}</dd>

                    <dt className="text-[#636c76]">{t('projects.git.sync_last')}</dt>
                    <dd className="text-[#1f2328]">
                      {mainRepo.last_sync_at
                        ? new Date(mainRepo.last_sync_at).toLocaleString()
                        : t('projects.git.sync_never')}
                    </dd>

                    <dt className="text-[#636c76]">{t('projects.git.sync_status')}</dt>
                    <dd className="flex items-center gap-1.5 text-[#1f2328]">
                      {mainRepo.last_sync_status === 'error' ? (
                        <>
                          <AlertTriangle size={12} className="text-red-500" />
                          <span className="text-red-600">{t('projects.git.sync_status_error')}</span>
                        </>
                      ) : mainRepo.last_sync_status === 'ok' ? (
                        <>
                          <Check size={12} className="text-green-600" />
                          {t('projects.git.sync_status_ok')}
                        </>
                      ) : (
                        t('projects.git.sync_status_unknown')
                      )}
                    </dd>

                    {/* Разбор идёт в фоне после синхронизации. Без этой
                        строки выглядит так, будто после загрузки коммитов
                        ничего не происходит, а он идёт — медленно, потому
                        что ходит в модель. */}
                    <dt className="text-[#636c76]">{t('projects.git.enrichment_title')}</dt>
                    <dd className="flex items-center gap-1.5 text-[#1f2328]">
                      {(isSyncing || mainRepo.enrichment_status === 'running') ? (
                        <>
                          <Loader2 size={12} className="animate-spin text-[#0969da]" />
                          <span>
                            {t('projects.git.enrichment_running')}
                            {/* Показываем только сделанное, без «/total»:
                                лимит прохода (50 правок, 10 коммитов) —
                                это потолок за один запуск, а не объём
                                работы. «0/50» выглядело как зависание. */}
                            {` ${syncProgress?.done ?? mainRepo.enrichment_done ?? 0}`}
                          </span>
                        </>
                      ) : mainRepo.enrichment_status === 'error' ? (
                        <>
                          <AlertTriangle size={12} className="text-red-500" />
                          <span className="text-red-600">{t('projects.git.enrichment_error')}</span>
                        </>
                      ) : mainRepo.enrichment_status === 'done' ? (
                        <>
                          <Check size={12} className="text-green-600" />
                          {t('projects.git.enrichment_done')}
                        </>
                      ) : (
                        t('projects.git.enrichment_pending')
                      )}
                    </dd>
                  </dl>

                  {mainRepo.enrichment_error && (
                    <p className="text-[11px] text-red-600 bg-[#fff5f5] border border-[#ff818266] rounded p-2 break-words">
                      {mainRepo.enrichment_error}
                    </p>
                  )}

                  {mainRepo.last_sync_error && (
                    <p className="text-[11px] text-red-600 bg-[#fff5f5] border border-[#ff818266] rounded p-2 break-words">
                      {mainRepo.last_sync_error}
                    </p>
                  )}

                  {syncMessage && (
                    <p className="text-[11px] text-[#1f2328] bg-[#f6f8fa] border border-[#d0d7de] rounded p-2 break-words">
                      {syncMessage}
                    </p>
                  )}
                </div>
              )}

              {verificationResult && (
                <div className="p-4 border border-[#d0d7de] rounded-lg bg-white space-y-3 shadow-sm">
                   <h5 className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('projects.git.verification')}</h5>
                   <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-[#1f2328]">{t('projects.git.verify_step_repo')}</span>
                        {verificationResult.repo_found ? <Check size={16} className="text-green-600" /> : <X size={16} className="text-red-600" />}
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-[#1f2328]">{t('projects.git.verify_step_secret')}</span>
                        {verificationResult.secret_configured ? <Check size={16} className="text-green-600" /> : <X size={16} className="text-red-600" />}
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-[#1f2328]">{t('projects.git.verify_step_event')}</span>
                        {verificationResult.event_received ? <Check size={16} className="text-green-600" /> : <X size={16} className="text-red-600" />}
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-[#1f2328]">{t('projects.git.verify_step_signature')}</span>
                        {verificationResult.signature_verified ? <Check size={16} className="text-green-600" /> : <X size={16} className="text-red-600" />}
                      </div>
                   </div>
                   {verificationResult.last_event_at && (
                     <p className="text-[10px] text-[#636c76] pt-2 border-t border-[#d0d7de]">
                        Last activity: {new Date(verificationResult.last_event_at).toLocaleString()}
                     </p>
                   )}
                </div>
              )}

              {/* Старую форму подключения (выбор провайдера, URL,
                  Owner/Repo, API URL, ручной ввод секрета) убрали:
                  подключением занимается мастер. Дублирование давало
                  два расходящихся пути задать одно и то же — ветку,
                  в частности, мастер её сохранял, а форма нет. */}
              {mainRepo?.id && (
                  <div className="p-4 bg-[#f0f9ff] border border-[#0969da4d] rounded-lg space-y-3">
                    <h5 className="text-xs font-bold text-[#0969da] flex items-center gap-2">
                      <ExternalLink size={14} />
                      {t('projects.git.webhook_url_title')}
                    </h5>
                    <div className="flex gap-2">
                      <code className="flex-1 bg-white p-2 rounded border border-[#d0d7de] text-[10px] break-all font-mono text-[#1f2328]">
                        {webhookUrl}
                      </code>
                      <button 
                        type="button"
                        onClick={copyToClipboard}
                        className="p-2 bg-white border border-[#d0d7de] rounded hover:bg-gray-50 text-[#636c76] transition-colors"
                        title="Copy to clipboard"
                      >
                        {copied ? <Check size={16} className="text-green-600" /> : <Copy size={16} />}
                      </button>
                    </div>
                    <p className="text-[10px] text-[#0969da] leading-relaxed">
                      {t('projects.git.webhook_hint')}
                    </p>
                  </div>
                )}
              </div>
          ) : (
            <div className="p-6 space-y-6">
               <div className="flex items-center gap-3 p-4 bg-blue-50 border border-blue-100 rounded-lg">
                  <Info className="text-blue-500 shrink-0" size={20} />
                  <p className="text-xs text-blue-700 leading-relaxed">
                    {t('projects.git.unlinked_desc')}
                  </p>
               </div>

               <div className="space-y-3">
                  {isLoadingUnlinked ? (
                    <div className="flex justify-center py-12"><Loader2 className="animate-spin text-[#636c76]" size={24} /></div>
                  ) : unlinkedEvents.length === 0 ? (
                    <div className="text-center py-12 bg-gray-50 rounded-lg border border-dashed border-[#d0d7de]">
                       <Check className="mx-auto mb-2 text-green-500" size={32} />
                       <p className="text-sm text-[#636c76]">All Git events are linked!</p>
                    </div>
                  ) : (
                    unlinkedEvents.map(event => (
                      <div key={event.id} className="p-4 border border-[#d0d7de] rounded-lg space-y-3 bg-white hover:border-[#afb8c1] transition-colors">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                             <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${event.event_type === 'push' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'}`}>
                                {event.event_type}
                             </span>
                             <span className="text-[11px] font-mono text-[#636c76]">{event.external_id?.substring(0, 7)}</span>
                          </div>
                          <span className="text-[10px] text-[#636c76]">{new Date(event.created_at).toLocaleString()}</span>
                        </div>
                        
                        <div className="text-xs text-[#1f2328] font-medium bg-[#f6f8fa] p-2 rounded">
                           {event.event_type === 'push' ? (
                             <div className="flex items-center gap-2">
                               <GitCommit size={14} className="text-[#636c76]" />
                               <span className="truncate">{event.payload.commits?.[0]?.message || 'No message'}</span>
                             </div>
                           ) : (
                             <div className="flex items-center gap-2">
                               <ExternalLink size={14} className="text-[#636c76]" />
                               <span className="truncate">{event.payload.pull_request?.title || 'No title'}</span>
                             </div>
                           )}
                        </div>

                        <div className="flex gap-2">
                           <input 
                              type="text"
                              className="flex-1 px-3 py-1.5 border border-[#d0d7de] rounded-md text-xs outline-none focus:ring-2 focus:ring-blue-500"
                              placeholder="Task #ID"
                              value={linkTaskId[event.id] || ''}
                              onChange={(e) => setLinkTaskId(prev => ({ ...prev, [event.id]: e.target.value }))}
                           />
                           <button 
                             onClick={() => handleLinkEvent(event.id)}
                             disabled={!linkTaskId[event.id]}
                             className="px-3 py-1.5 bg-[#1f2328] text-white rounded-md text-xs font-bold hover:bg-black transition flex items-center gap-2 disabled:opacity-30"
                           >
                             <ArrowRight size={14} />
                             Link
                           </button>
                        </div>
                      </div>
                    ))
                  )}
               </div>
            </div>
          )}

        </div>

        <div className="px-6 py-3 bg-[#f6f8fa] border-t border-[#d0d7de] flex items-center justify-between shrink-0">
          {isEditable && activeTab === 'general' ? (
            <button 
              type="button"
              className="px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-md text-xs font-bold hover:bg-red-100 transition shadow-sm flex items-center gap-2"
              onClick={handleDeleteProject}
            >
              <Trash2 size={14} />
              {t('projects.delete_project')}
            </button>
          ) : <div />}

          <div className="flex gap-2">
            <button 
              type="button" 
              onClick={onClose}
              className="px-3 py-1.5 bg-white border border-[#d0d7de] text-[#1f2328] rounded-md text-xs font-bold hover:bg-[#ebf0f4] transition shadow-sm"
            >
              {t('common.cancel')}
            </button>
            {isEditable && activeTab === 'general' && (
              <button
                type="submit"
                form="general-form"
                disabled={isSaving}
                className="px-3 py-1.5 bg-[#1f883d] text-white rounded-md hover:bg-[#1a7f37] transition font-bold text-xs shadow-sm flex items-center gap-2 disabled:opacity-50"
              >
                {isSaving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                {t('common.save')}
              </button>
            )}
          </div>
        </div>
      </div>
      {isAuthorsOpen && mainRepo?.id && (
        <AuthorMappingModal
          repositoryId={mainRepo.id}
          repositoryName={mainRepo.repo_name || mainRepo.url}
          onClose={() => setIsAuthorsOpen(false)}
          onUpdated={() => { onUpdated(); }}
        />
      )}
      {isWizardOpen && (
        <RepoConnectWizard
          projectId={project.id}
          onClose={() => setIsWizardOpen(false)}
          onSaved={() => { onUpdated(); }}
        />
      )}
    </div>
  );
};

export default ProjectSettingsModal;
