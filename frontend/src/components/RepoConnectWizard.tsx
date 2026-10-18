import React, { useState } from 'react';
import {
  Check,
  X,
  Loader2,
  Github,
  Gitlab,
  Globe,
  Link2,
  AlertTriangle,
  Copy,
  RefreshCw,
  Zap,
  ChevronRight,
  ChevronLeft,
  CheckCircle2,
  Info,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';

interface Props {
  projectId: number;
  onClose: () => void;
  onSaved: () => void;
}

const PROVIDERS = [
  { value: 'github', label: 'GitHub', Icon: Github },
  { value: 'gitlab', label: 'GitLab', Icon: Gitlab },
  { value: 'gitlab_custom', label: 'GitLab (self-hosted)', Icon: Globe },
  { value: 'gitea', label: 'Gitea', Icon: Gitlab },
  { value: 'bitbucket', label: 'Bitbucket', Icon: Globe },
] as const;

interface WebhookStatus {
  auto_register_supported: boolean;
  callback_url: string;
  secret_configured: boolean;
  webhook_id?: string;
  registered_remotely: boolean;
  remote_webhooks: any[];
  message?: string;
}

export default function RepoConnectWizard({ projectId, onClose, onSaved }: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [step, setStep] = useState<1 | 2 | 3>(1);

  const [provider, setProvider] = useState<string>('github');
  const [token, setToken] = useState('');

  // Если аккаунт провайдера подключён в профиле (через OAuth или вручную),
  // поле токена можно оставить пустым — сервер возьмёт токен сам.
  // Раньше поле было обязательным и мастер ругался на пустое значение,
  // хотя токен в профиле уже был.
  const oauthProvider = provider === 'gitlab_custom' ? 'gitlab' : provider;
  const linkedAccount = user?.git_accounts?.find(
    (a) => a.provider.toLowerCase() === oauthProvider.toLowerCase()
  );
  const hasLinkedAccount = !!linkedAccount;
  const [url, setUrl] = useState('');
  const [apiUrl, setApiUrl] = useState('');
  const [defaultBranch, setDefaultBranch] = useState('main');
  const [pathFilter, setPathFilter] = useState('');

  const [tokenState, setTokenState] = useState<{
    checking: boolean;
    ok?: boolean;
    username?: string;
    error?: string;
  }>({ checking: false });

  const [repoId, setRepoId] = useState<number | null>(null);
  const [secret, setSecret] = useState('');
  const [hook, setHook] = useState<WebhookStatus | null>(null);
  const [hookBusy, setHookBusy] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const isCustom = provider === 'gitlab_custom';

  const checkToken = async () => {
    setTokenState({ checking: true });
    try {
      const { data } = await api.post('/git/token/check', {
        provider,
        token: token || undefined,
      });
      setTokenState({ checking: false, ok: data.ok, username: data.username, error: data.error });
    } catch (err: any) {
      setTokenState({
        checking: false,
        ok: false,
        error: err.response?.data?.detail || 'Request failed',
      });
    }
  };

  const loadWebhook = async (id: number) => {
    try {
      const { data } = await api.get(`/git/${id}/webhook`);
      setHook(data);
    } catch {
      setHook(null);
    }
  };

  const connectRepo = async () => {
    setSaving(true);
    setError('');
    try {
      const { data } = await api.post(`/projects/${projectId}/repositories`, {
        url: url.trim(),
        provider,
        api_url: isCustom && apiUrl ? apiUrl.trim() : undefined,
        default_branch: defaultBranch || 'main',
        path_filter: pathFilter || undefined,
      });
      setRepoId(data.id);
      setSecret(data.webhook_secret || '');
      setStep(3);
      await loadWebhook(data.id);
      onSaved();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось подключить репозиторий');
    } finally {
      setSaving(false);
    }
  };

  const registerWebhook = async () => {
    if (!repoId) return;
    setHookBusy(true);
    setError('');
    try {
      const { data } = await api.post(`/git/${repoId}/webhook/register`);
      setHook(data);
      if (data.registered_remotely) {
        // Секрет мог перевыпуститься — забираем актуальный
        const { data: repo } = await api.get(`/projects/${projectId}/repositories`);
        const found = (repo || []).find((r: any) => r.id === repoId);
        if (found?.webhook_secret) setSecret(found.webhook_secret);
      }
      onSaved();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось зарегистрировать вебхук');
    } finally {
      setHookBusy(false);
    }
  };

  const regenerateSecret = async () => {
    if (!repoId) return;
    setHookBusy(true);
    try {
      const { data } = await api.patch(`/projects/${projectId}/repositories/${repoId}`, {
        regenerate_secret: true,
      });
      setSecret(data.webhook_secret || '');
      await loadWebhook(repoId);
      onSaved();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось перевыпустить секрет');
    } finally {
      setHookBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
      <div className="bg-white rounded-lg w-full max-w-2xl max-h-[90vh] shadow-2xl border border-[#d0d7de] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
          <h2 className="text-lg font-bold text-[#1f2328]">{t('projects.git.wizard.title')}</h2>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 rounded-md hover:bg-gray-200 transition">
            <X size={20} />
          </button>
        </div>

        <div className="flex items-center gap-2 px-6 py-3 border-b border-[#d0d7de] bg-white">
          {[
            { n: 1, label: t('projects.git.wizard.step_provider') },
            { n: 2, label: t('projects.git.wizard.step_repo') },
            { n: 3, label: t('projects.git.wizard.step_webhook') },
          ].map((s, idx) => (
            <React.Fragment key={s.n}>
              {idx > 0 && <ChevronRight size={14} className="text-[#d0d7de] shrink-0" />}
              <div className="flex items-center gap-2">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                    step >= s.n ? 'bg-[#1f883d] text-white' : 'bg-[#d0d7de] text-white'
                  }`}
                >
                  {step > s.n ? <Check size={14} /> : s.n}
                </div>
                <span className={`text-xs font-bold ${step >= s.n ? 'text-[#1f2328]' : 'text-[#8b949e]'}`}>
                  {s.label}
                </span>
              </div>
            </React.Fragment>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {error && (
            <div className="p-3 rounded-lg bg-[#ffebe9] border border-[#f8514926] text-[#cf222e] text-sm flex items-start gap-2">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5">
              <div>
                <label className="block text-xs font-bold text-[#1f2328] mb-2">
                  {t('projects.git.wizard.provider_label')}
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {PROVIDERS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => setProvider(p.value)}
                      className={`flex items-center gap-3 p-3 rounded-lg border-2 transition text-left ${
                        provider === p.value
                          ? 'border-[#0969da] bg-[#ddf4ff]'
                          : 'border-[#d0d7de] hover:border-[#8b949e]'
                      }`}
                    >
                      <p.Icon size={20} className={provider === p.value ? 'text-[#0969da]' : 'text-[#636c76]'} />
                      <span className="text-sm font-semibold text-[#1f2328]">{p.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {isCustom && (
                <div>
                  <label className="block text-xs font-bold text-[#1f2328] mb-1">
                    {t('projects.git.wizard.api_url')}
                  </label>
                  <input
                    value={apiUrl}
                    onChange={(e) => setApiUrl(e.target.value)}
                    placeholder="https://gitlab.company.ru"
                    className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-md text-sm outline-none focus:bg-white focus:ring-2 focus:ring-blue-500 font-mono"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-[#1f2328] mb-1">
                  {t('projects.git.wizard.token_label')}
                  {!hasLinkedAccount && (
                    <span className="text-[#cf222e]"> *</span>
                  )}
                </label>

                {hasLinkedAccount && (
                  <div className="mb-2 p-2.5 rounded-lg bg-[#dafbe1] border border-[#2da44e26] text-[#1a7f37] text-xs flex items-center gap-2">
                    <CheckCircle2 size={14} className="shrink-0" />
                    {linkedAccount?.username
                      ? t('projects.git.wizard.token_from_account', { username: linkedAccount.username })
                      : t('projects.git.wizard.token_from_account_no_name')}
                    <span className="text-[#636c76]">
                      {t('projects.git.wizard.token_optional_hint')}
                    </span>
                  </div>
                )}
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder={t('projects.git.wizard.token_placeholder')}
                    className="flex-1 px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-md text-sm outline-none focus:bg-white focus:ring-2 focus:ring-blue-500 font-mono"
                  />
                  <button
                    onClick={checkToken}
                    disabled={tokenState.checking}
                    className="px-3 py-2 bg-white border border-[#d0d7de] rounded-md text-xs font-bold hover:bg-[#f6f8fa] transition disabled:opacity-50 flex items-center gap-1.5 shrink-0"
                  >
                    {tokenState.checking ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
                    {t('projects.git.wizard.check_token')}
                  </button>
                </div>
                <p className="text-[11px] text-[#636c76] mt-1.5 flex items-start gap-1">
                  <Info size={12} className="shrink-0 mt-0.5" />
                  {hasLinkedAccount
                    ? t('projects.git.wizard.token_help_optional')
                    : t('projects.git.wizard.token_help')}
                </p>

                {tokenState.ok === true && (
                  <div className="mt-2 p-2.5 rounded-lg bg-[#dafbe1] border border-[#2da44e26] text-[#1a7f37] text-xs flex items-center gap-2">
                    <CheckCircle2 size={14} />
                    {t('projects.git.wizard.token_ok', { username: tokenState.username })}
                  </div>
                )}
                {tokenState.ok === false && (
                  <div className="mt-2 p-2.5 rounded-lg bg-[#ffebe9] border border-[#f8514926] text-[#cf222e] text-xs flex items-start gap-2">
                    <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                    <span>{tokenState.error}</span>
                  </div>
                )}
              </div>

              <div className="flex justify-end">
                <button
                  onClick={() => setStep(2)}
                  className="px-4 py-2 bg-[#1f2328] text-white rounded-md text-sm font-bold hover:bg-black transition flex items-center gap-2"
                >
                  {t('projects.git.wizard.next')}
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <div>
                <label className="block text-xs font-bold text-[#1f2328] mb-1">
                  {t('projects.git.wizard.url_label')}
                </label>
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://github.com/owner/repository"
                  className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-md text-sm outline-none focus:bg-white focus:ring-2 focus:ring-blue-500 font-mono"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-[#1f2328] mb-1">
                    {t('projects.git.wizard.default_branch')}
                  </label>
                  <input
                    value={defaultBranch}
                    onChange={(e) => setDefaultBranch(e.target.value)}
                    className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-md text-sm outline-none focus:bg-white focus:ring-2 focus:ring-blue-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-[#1f2328] mb-1">
                    {t('projects.git.wizard.path_filter')}
                  </label>
                  <input
                    value={pathFilter}
                    onChange={(e) => setPathFilter(e.target.value)}
                    placeholder="backend/, frontend/"
                    className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-md text-sm outline-none focus:bg-white focus:ring-2 focus:ring-blue-500 font-mono"
                  />
                </div>
              </div>
              <p className="text-[11px] text-[#636c76] flex items-start gap-1">
                <Info size={12} className="shrink-0 mt-0.5" />
                {t('projects.git.wizard.path_filter_help')}
              </p>

              <div className="flex justify-between">
                <button
                  onClick={() => setStep(1)}
                  className="px-4 py-2 text-sm font-bold text-[#636c76] hover:bg-[#f6f8fa] rounded-md transition flex items-center gap-2"
                >
                  <ChevronLeft size={16} />
                  {t('projects.git.wizard.back')}
                </button>
                <button
                  onClick={connectRepo}
                  disabled={!url.trim() || saving}
                  className="px-4 py-2 bg-[#1f883d] text-white rounded-md text-sm font-bold hover:bg-[#1a7f37] transition disabled:opacity-40 flex items-center gap-2"
                >
                  {saving ? <Loader2 size={16} className="animate-spin" /> : <Link2 size={16} />}
                  {t('projects.git.wizard.connect')}
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5">
              {!hook ? (
                <div className="p-8 text-center">
                  <Loader2 className="animate-spin mx-auto text-blue-500" size={24} />
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <CheckItem ok={hook.secret_configured} label={t('projects.git.wizard.checklist_secret')} />
                    <CheckItem ok={hook.registered_remotely} label={t('projects.git.wizard.checklist_registered')} />
                  </div>

                  {hook.registered_remotely ? (
                    <div className="p-4 rounded-lg bg-[#dafbe1] border border-[#2da44e26] flex items-start gap-3">
                      <CheckCircle2 size={20} className="text-[#1a7f37] shrink-0" />
                      <div className="text-sm text-[#1a7f37]">
                        <p className="font-bold">{t('projects.git.wizard.webhook_ready')}</p>
                        <p className="text-xs mt-1 opacity-80">{t('projects.git.wizard.webhook_ready_desc')}</p>
                      </div>
                    </div>
                  ) : (
                    <>
                      {!hook.auto_register_supported ? (
                        <div className="p-4 rounded-lg bg-[#fff8c5] border border-[#d4a72c4d] flex items-start gap-3">
                          <AlertTriangle size={20} className="text-[#9a6700] shrink-0" />
                          <p className="text-xs text-[#735c0f]">{t('projects.git.wizard.manual_only')}</p>
                        </div>
                      ) : (
                        <button
                          onClick={registerWebhook}
                          disabled={hookBusy}
                          className="w-full px-4 py-3 bg-[#0969da] text-white rounded-lg text-sm font-bold hover:bg-[#0861c5] transition disabled:opacity-50 flex items-center justify-center gap-2"
                        >
                          {hookBusy ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                          {t('projects.git.wizard.auto_register')}
                        </button>
                      )}

                      <div className="space-y-3 p-4 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg">
                        <p className="text-xs font-bold text-[#636c76]">{t('projects.git.wizard.manual_title')}</p>
                        <CopyField label={t('projects.git.wizard.callback_url')} value={hook.callback_url} />
                        <CopyField label={t('projects.git.wizard.secret')} value={secret} mono />
                        <button
                          onClick={regenerateSecret}
                          disabled={hookBusy}
                          className="text-[11px] font-semibold text-[#0969da] hover:underline disabled:opacity-50 flex items-center gap-1"
                        >
                          <RefreshCw size={11} />
                          {t('projects.git.wizard.regenerate_secret')}
                        </button>
                        <p className="text-[11px] text-[#636c76]">{t('projects.git.wizard.events_hint')}</p>
                      </div>
                    </>
                  )}
                </>
              )}

              <div className="flex justify-between">
                <button
                  onClick={() => setStep(2)}
                  className="px-4 py-2 text-sm font-bold text-[#636c76] hover:bg-[#f6f8fa] rounded-md transition flex items-center gap-2"
                >
                  <ChevronLeft size={16} />
                  {t('projects.git.wizard.back')}
                </button>
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-[#1f883d] text-white rounded-md text-sm font-bold hover:bg-[#1a7f37] transition"
                >
                  {t('projects.git.wizard.finish')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CheckItem({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-[#1f2328]">{label}</span>
      {ok ? <Check size={16} className="text-green-600" /> : <X size={16} className="text-red-600" />}
    </div>
  );
}

function CopyField({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  const { t } = useTranslation();
  return (
    <div>
      <label className="block text-[11px] font-bold text-[#636c76] mb-1">{label}</label>
      <div className="flex gap-2">
        <input
          readOnly
          value={value || '—'}
          className={`flex-1 px-2 py-1.5 bg-white border border-[#d0d7de] rounded text-xs text-[#1f2328] outline-none ${
            mono ? 'font-mono' : ''
          }`}
        />
        <button
          onClick={() => value && navigator.clipboard?.writeText(value)}
          disabled={!value}
          className="px-2 py-1.5 bg-white border border-[#d0d7de] rounded text-[#636c76] hover:border-[#0969da] hover:text-[#0969da] transition disabled:opacity-40 shrink-0"
          title={t('projects.git.wizard.copy')}
        >
          <Copy size={14} />
        </button>
      </div>
    </div>
  );
}
