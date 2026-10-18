import React, { useState, useEffect, useRef } from 'react';
import { 
  User as UserIcon, 
  Mail, 
  Github, 
  Gitlab, 
  Globe, 
  Shield, 
  Camera,
  Loader2,
  Check,
  AlertCircle,
  Link as LinkIcon,
  Type,
  Minus,
  Plus,
  X,
  ExternalLink
} from 'lucide-react';
import { useAuth, normalizeLanguage, SupportedLanguage } from '../context/AuthContext';
import { useFontSize } from '../hooks/useFontSize';
import api from '../api/client';
import { useTranslation } from 'react-i18next';

type ProviderKey = 'github' | 'gitlab' | 'bitbucket' | 'gitea';

const Profile: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { user, refreshUser } = useAuth();
  const font = useFontSize();
  const [fullName, setFullName] = useState(user?.full_name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url || '');
  const [language, setLanguageState] = useState<SupportedLanguage>(
    normalizeLanguage(user?.language || i18n.language)
  );
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

  // VCS Connection Modal States
  const [showGithubModal, setShowGithubModal] = useState(false);
  const [showGitlabModal, setShowGitlabModal] = useState(false);
  const [showBitbucketModal, setShowBitbucketModal] = useState(false);
  const [showGiteaModal, setShowGiteaModal] = useState(false);
  
  const [githubToken, setGithubToken] = useState('');
  const [githubUsername, setGithubUsername] = useState(user?.github_username || '');
  
  const [gitlabToken, setGitlabToken] = useState('');
  const [bitbucketToken, setBitbucketToken] = useState('');
  const [giteaToken, setGiteaToken] = useState('');
  
  const [isConnecting, setIsConnecting] = useState(false);

  // Выбор файла аватара
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);

  // Какие провайдеры подключены через OAuth (а не ручным токеном)
  const [oauthInfo, setOauthInfo] = useState<Record<string, { available: boolean; connected: boolean }>>({});
  const [oauthBusy, setOauthBusy] = useState<ProviderKey | null>(null);

  useEffect(() => {
    if (user) {
      setFullName(user.full_name || '');
      setEmail(user.email || '');
      setAvatarUrl(user.avatar_url || '');
      setGithubUsername(user.github_username || '');
    }
  }, [user]);

  // Язык синхронизируем только с сервером. Раньше в зависимостях был
  // i18n.language: после переключения языка эффект перезаписывал выбор
  // устаревшим user.language, и подсветка «уезжала» на другой язык.
  useEffect(() => {
    if (user?.language) {
      setLanguageState(normalizeLanguage(user.language));
    }
  }, [user?.language]);

  // Какие OAuth-приложения вообще настроены на сервере
  const loadOAuthInfo = React.useCallback(async () => {
    try {
      const { data } = await api.get('/auth/oauth/providers');
      const map: Record<string, { available: boolean; connected: boolean }> = {};
      (data || []).forEach((p: any) => { map[p.provider] = { available: p.available, connected: p.connected }; });
      setOauthInfo(map);
    } catch {
      // Эндпоинт недоступен — покажем только ручной ввод токена
    }
  }, []);

  useEffect(() => {
    loadOAuthInfo();
  }, [loadOAuthInfo]);

  // Провайдер возвращает сюда ?oauth=<provider>&oauth_ok=1 либо oauth_error=...
  // Эффект отрабатывает один раз: refreshUser нестабилен (создаётся заново
  // при каждом рендере), а зависеть от него в deps означало бы перезапуск
  // эффекта на каждом рендере.
  const oauthResultHandled = React.useRef(false);
  useEffect(() => {
    if (oauthResultHandled.current) return;
    const params = new URLSearchParams(window.location.search);
    const provider = params.get('oauth');
    if (!provider) return;
    oauthResultHandled.current = true;

    const ok = params.get('oauth_ok');
    const err = params.get('oauth_error');
    const username = params.get('username');

    if (ok) {
      const name = PROVIDERS.find((p) => p.key === provider)?.name || provider;
      setMessage({ type: 'success', text: t('profile.oauth_connected', { provider: name, username: username || name }) });
      refreshUser();
      loadOAuthInfo();
    } else if (err) {
      // Неизвестный код ошибки не должен показывать пользователю ключ перевода
      setMessage({
        type: 'error',
        text: t(`profile.oauth_error.${err}`, { defaultValue: t('profile.oauth_error.exchange_failed') }),
      });
    }

    // Убираем параметры, чтобы перезагрузка страницы не повторяла эффект
    params.delete('oauth');
    params.delete('oauth_ok');
    params.delete('oauth_error');
    params.delete('username');
    const qs = params.toString();
    window.history.replaceState({}, '', `${window.location.pathname}${qs ? '?' + qs : ''}`);
  }, [t, refreshUser, loadOAuthInfo]);

  const handleOAuthConnect = async (provider: ProviderKey) => {
    setOauthBusy(provider);
    try {
      const { data } = await api.get(`/auth/oauth/${provider}/start`);
      if (data?.url) {
        window.location.href = data.url;
        return;
      }
      setMessage({ type: 'error', text: t('profile.oauth_error.no_url') });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || t('profile.oauth_error.exchange_failed') });
    } finally {
      setOauthBusy(null);
    }
  };

  /** Переключение языка с живым предпросмотром — выбор виден сразу */
  const setLanguage = (lang: SupportedLanguage) => {
    setLanguageState(lang);
    i18n.changeLanguage(lang);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setMessage(null);
    try {
      await api.patch('/users/me', {
        full_name: fullName,
        email: email,
        avatar_url: avatarUrl,
        language: language
      });
      // Обновляем профиль в контексте, иначе в нём остался бы старый язык
      await refreshUser();
      await i18n.changeLanguage(language);
      setMessage({ type: 'success', text: t('profile.update_success') });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to update profile' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleAvatarFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Сбрасываем значение, иначе повторный выбор того же файла не сработает
    e.target.value = '';
    if (!file) return;

    // Размер проверяем до отправки: сервер всё равно отклонит крупный файл,
    // но без этой проверки пользователь ждёт ответа сети зря
    if (file.size > 5 * 1024 * 1024) {
      setMessage({ type: 'error', text: t('profile.avatar_too_large') });
      return;
    }

    setIsUploadingAvatar(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const { data } = await api.post('/users/me/avatar', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setAvatarUrl(data.url);
      await refreshUser();
      setMessage({ type: 'success', text: t('profile.avatar_uploaded') });
    } catch (err: any) {
      setMessage({
        type: 'error',
        text: err.response?.data?.detail || t('profile.avatar_upload_failed'),
      });
    } finally {
      setIsUploadingAvatar(false);
    }
  };

  const handleRemoveAvatar = async () => {
    setIsUploadingAvatar(true);
    try {
      await api.delete('/users/me/avatar');
      setAvatarUrl('');
      await refreshUser();
    } catch (err: any) {
      setMessage({
        type: 'error',
        text: err.response?.data?.detail || t('profile.avatar_delete_failed'),
      });
    } finally {
      setIsUploadingAvatar(false);
    }
  };

  const handleConnectGithub = async () => {
    setIsConnecting(true);
    try {
      await api.patch('/users/me', {
        github_token: githubToken,
        github_username: githubUsername
      });
      setShowGithubModal(false);
      await refreshUser();
      loadOAuthInfo();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to connect GitHub');
    } finally {
      setIsConnecting(false);
    }
  };

  const handleConnectGitlab = async () => {
    setIsConnecting(true);
    try {
      await api.patch('/users/me', {
        gitlab_token: gitlabToken
      });
      setShowGitlabModal(false);
      await refreshUser();
      loadOAuthInfo();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to connect GitLab');
    } finally {
      setIsConnecting(false);
    }
  };

  const handleConnectBitbucket = async () => {
    setIsConnecting(true);
    try {
      await api.patch('/users/me', {
        bitbucket_token: bitbucketToken
      });
      setShowBitbucketModal(false);
      await refreshUser();
      loadOAuthInfo();
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || t('profile.connect_bitbucket') });
    } finally {
      setIsConnecting(false);
    }
  };

  const handleConnectGitea = async () => {
    setIsConnecting(true);
    try {
      await api.patch('/users/me', {
        gitea_token: giteaToken
      });
      setShowGiteaModal(false);
      await refreshUser();
      loadOAuthInfo();
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || t('profile.connect_gitea') });
    } finally {
      setIsConnecting(false);
    }
  };

  const handleDisconnectVCS = async (provider: 'github' | 'gitlab' | 'bitbucket' | 'gitea') => {
    if (!window.confirm(`Are you sure you want to disconnect ${provider}?`)) return;
    try {
      // Если аккаунт подключён через OAuth — удаляем его:
      // PATCH /users/me его не убирает, и он остался бы в системе.
      if (isProviderConnected(provider)) {
        await api.delete(`/auth/oauth/${provider}`);
      }

      let payload = {};
      if (provider === 'github') payload = { github_token: '' };
      else if (provider === 'gitlab') payload = { gitlab_token: '' };
      else if (provider === 'bitbucket') payload = { bitbucket_token: '' };
      else if (provider === 'gitea') payload = { gitea_token: '' };

      await api.patch('/users/me', payload);
      await refreshUser();
      loadOAuthInfo();
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to disconnect' });
    }
  };

  // Четыре провайдера описываются здесь, а не четырьмя копиями разметки:
  // иначе любое изменение приходится повторять четыре раза.
  const PROVIDERS: {
    key: ProviderKey;
    name: string;
    icon: React.FC<{ size?: number | string }>;
    badge: string;
    usernameKey: string;
    /** Окно ручного ввода токена остаётся как запасной путь */
    openModal: () => void;
  }[] = [
    { key: 'github', name: 'GitHub', icon: Github, badge: 'bg-black', usernameKey: 'profile.github_connected', openModal: () => setShowGithubModal(true) },
    { key: 'gitlab', name: 'GitLab', icon: Gitlab, badge: 'bg-orange-500', usernameKey: 'profile.gitlab_connected', openModal: () => setShowGitlabModal(true) },
    { key: 'bitbucket', name: 'Bitbucket', icon: Globe, badge: 'bg-blue-600', usernameKey: 'profile.bitbucket_connected', openModal: () => setShowBitbucketModal(true) },
    { key: 'gitea', name: 'Gitea', icon: Globe, badge: 'bg-[#634491]', usernameKey: 'profile.gitea_connected', openModal: () => setShowGiteaModal(true) },
  ];

  const isProviderConnected = (provider: string) => {
    return user?.git_accounts?.some(a => a.provider.toLowerCase() === provider.toLowerCase());
  };

  const getProviderUsername = (provider: string) => {
    return user?.git_accounts?.find(a => a.provider.toLowerCase() === provider.toLowerCase())?.username;
  };

  return (
    <div className="flex-1 overflow-y-auto bg-[#f6f8fa] p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-2xl font-bold text-[#1f2328] mb-8">{t('profile.title')}</h1>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Sidebar - Avatar */}
          <div className="space-y-6">
            <div className="bg-white border border-[#d0d7de] rounded-xl p-6 flex flex-col items-center">
              <div className="relative group mb-4">
                <div className="w-32 h-32 rounded-full border-2 border-[#d0d7de] overflow-hidden bg-[#f6f8fa] flex items-center justify-center">
                  {avatarUrl ? (
                    <img src={avatarUrl} alt="Avatar" className="w-full h-full object-cover" />
                  ) : (
                    <UserIcon size={64} className="text-[#afb8c1]" />
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => avatarInputRef.current?.click()}
                  disabled={isUploadingAvatar}
                  title={t('profile.avatar_pick')}
                  aria-label={t('profile.avatar_pick')}
                  className="absolute bottom-0 right-0 p-2 bg-white border border-[#d0d7de] rounded-full shadow-sm hover:bg-[#f6f8fa] transition-colors disabled:opacity-60"
                >
                  {isUploadingAvatar
                    ? <Loader2 size={16} className="animate-spin text-[#1f2328]" />
                    : <Camera size={16} className="text-[#1f2328]" />}
                </button>

                {/* Проводник открывается по нажатию на фотоаппарат */}
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  className="hidden"
                  onChange={handleAvatarFile}
                />
              </div>

              <h3 className="font-bold text-[#1f2328]">{fullName || 'User'}</h3>
              <p className="text-sm text-[#636c76] mb-4">{email}</p>

              {avatarUrl && (
                <button
                  type="button"
                  onClick={handleRemoveAvatar}
                  disabled={isUploadingAvatar}
                  className="text-xs font-semibold text-[#cf222e] hover:underline disabled:opacity-60"
                >
                  {t('profile.avatar_remove')}
                </button>
              )}
            </div>

            <div className="bg-[#fff8c5] border border-[#d4a72c4d] rounded-xl p-4 flex gap-3">
              <Shield className="text-[#9a6700] shrink-0" size={20} />
              <div className="text-xs text-[#735c0f] leading-relaxed">
                <p className="font-bold mb-1">Privacy Tip</p>
                {t('profile.privacy_tip')}
              </div>
            </div>
          </div>

          {/* Основное содержимое: форма слева, привязанные аккаунты справа.
            На узком окне сетка схлопывается в одну колонку и аккаунты
            уходят вниз — как раньше. */}
          <div className="lg:col-span-2 grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
            <form onSubmit={handleSave} className="bg-white border border-[#d0d7de] rounded-xl overflow-hidden shadow-sm">
              <div className="p-6 space-y-4">
                {message && (
                  <div className={`p-3 rounded-lg flex items-center gap-3 text-sm ${message.type === 'success' ? 'bg-[#dafbe1] text-[#1a7f37] border border-[#2da44e4d]' : 'bg-[#ffebe9] text-[#cf222e] border border-[#d73a494d]'}`}>
                    {message.type === 'success' ? <Check size={18} /> : <AlertCircle size={18} />}
                    {message.text}
                  </div>
                )}

                <div>
                  <label className="block text-sm font-bold text-[#1f2328] mb-2">{t('profile.name')}</label>
                  <input 
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                  />
                </div>

                <div>
                  <label className="block text-sm font-bold text-[#1f2328] mb-2">{t('profile.email')}</label>
                  <input 
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                  />
                </div>

                <div>
                  <label className="block text-sm font-bold text-[#1f2328] mb-2 flex items-center gap-2">
                    <Globe size={14} className="text-[#636c76]" />
                    {t('profile.language')}
                  </label>
                  <div className="flex bg-[#f6f8fa] border border-[#d0d7de] rounded-lg p-1 w-fit">
                    <button
                      type="button"
                      onClick={() => setLanguage('en')}
                      className={`px-4 py-1.5 rounded-md text-xs font-bold transition-all ${language === 'en' ? 'bg-white shadow-sm text-[#0969da]' : 'text-[#636c76] hover:text-[#1f2328]'}`}
                    >
                      English
                    </button>
                    <button
                      type="button"
                      onClick={() => setLanguage('ru')}
                      className={`px-4 py-1.5 rounded-md text-xs font-bold transition-all ${language === 'ru' ? 'bg-white shadow-sm text-[#0969da]' : 'text-[#636c76] hover:text-[#1f2328]'}`}
                    >
                      Русский
                    </button>
                  </div>
                  <p className="text-xs text-[#636c76] mt-2">{t('profile.language_desc')}</p>
                </div>

                <div>
                  <label className="block text-sm font-bold text-[#1f2328] mb-2 flex items-center gap-2">
                    <Type size={14} className="text-[#636c76]" />
                    {t('profile.font_size')}
                  </label>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center bg-[#f6f8fa] border border-[#d0d7de] rounded-lg p-1">
                      <button
                        type="button"
                        onClick={font.decrease}
                        disabled={!font.canDecrease}
                        title={t('profile.font_size_decrease')}
                        aria-label={t('profile.font_size_decrease')}
                        className="w-9 h-8 rounded-md flex items-center justify-center text-[#636c76] hover:bg-white hover:text-[#1f2328] transition disabled:opacity-30 disabled:hover:bg-transparent"
                      >
                        <Minus size={16} />
                      </button>

                      <span className="min-w-[68px] text-center text-xs font-bold text-[#1f2328] tabular-nums">
                        {font.size} px
                      </span>

                      <button
                        type="button"
                        onClick={font.increase}
                        disabled={!font.canIncrease}
                        title={t('profile.font_size_increase')}
                        aria-label={t('profile.font_size_increase')}
                        className="w-9 h-8 rounded-md flex items-center justify-center text-[#636c76] hover:bg-white hover:text-[#1f2328] transition disabled:opacity-30 disabled:hover:bg-transparent"
                      >
                        <Plus size={16} />
                      </button>
                    </div>

                    {!font.isDefault && (
                      <button
                        type="button"
                        onClick={font.reset}
                        className="text-xs font-semibold text-[#0969da] hover:underline"
                      >
                        {t('profile.font_size_reset')}
                      </button>
                    )}
                  </div>

                  {/* Наглядный образец в текущем размере */}
                  <div className="mt-3 p-3 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg">
                    <p className="text-sm font-bold text-[#1f2328]">{t('profile.font_size_preview')}</p>
                    <p className="text-xs text-[#636c76] mt-1">{t('profile.font_size_desc')}</p>
                  </div>
                  <p className="text-xs text-[#636c76] mt-2">
                    {t('profile.font_size_range', { min: font.min, max: font.max })}
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-bold text-[#1f2328] mb-2">{t('profile.avatar_url')}</label>
                  <input 
                    type="text"
                    value={avatarUrl}
                    onChange={(e) => setAvatarUrl(e.target.value)}
                    className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                  />
                </div>
              </div>
              <div className="px-6 py-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end">
                <button 
                  type="submit"
                  disabled={isSaving}
                  className="px-4 py-2 bg-[#1f883d] text-white rounded-lg hover:bg-[#1a7f37] transition font-bold text-sm shadow-sm flex items-center gap-2 disabled:opacity-50"
                >
                  {isSaving ? <Loader2 size={18} className="animate-spin" /> : <Check size={18} />}
                  {t('common.save')}
                </button>
              </div>
            </form>

            <div className="bg-white border border-[#d0d7de] rounded-xl overflow-hidden shadow-sm">
              <div className="p-4 border-b border-[#d0d7de] bg-[#f6f8fa]">
                <h2 className="text-sm font-bold text-[#1f2328]">{t('profile.connected_accounts')}</h2>
                <p className="text-xs text-[#636c76]">{t('profile.vcs_desc')}</p>
              </div>
              <div className="divide-y divide-[#d0d7de]">
                {PROVIDERS.map((p) => {
                  const Icon = p.icon;
                  const connected = isProviderConnected(p.key);
                  const oauthAvailable = !!oauthInfo[p.key]?.available;
                  const username = getProviderUsername(p.key);
                  return (
                    <div key={p.key} className="p-4 flex items-center justify-between hover:bg-[#f6f8fa] transition-colors">
                      <div className="flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-lg ${p.badge} flex items-center justify-center text-white shadow-sm`}>
                          <Icon size={20} />
                        </div>
                        <div>
                          <h4 className="text-sm font-bold text-[#1f2328]">{p.name}</h4>
                          <span className={`text-xs ${connected ? 'text-green-600 font-medium' : 'text-[#636c76]'}`}>
                            {connected
                              ? (username
                                  ? t(p.usernameKey, { username })
                                  : t(p.usernameKey))
                              : t('profile.not_connected')}
                          </span>
                        </div>
                      </div>

                      {connected ? (
                        <button
                          onClick={() => handleDisconnectVCS(p.key)}
                          className="px-3 py-1.5 border border-[#d0d7de] rounded-lg text-xs font-bold text-[#cf222e] hover:bg-[#fff1f0] transition-all shadow-sm"
                        >
                          {t('profile.disconnect')}
                        </button>
                      ) : (
                        <div className="flex items-center gap-2">
                          {oauthAvailable && (
                            <button
                              onClick={() => handleOAuthConnect(p.key)}
                              disabled={oauthBusy === p.key}
                              className="px-3 py-1.5 bg-[#1f2328] text-white rounded-lg text-xs font-bold hover:bg-black transition-all shadow-sm flex items-center gap-2 disabled:opacity-60"
                            >
                              {oauthBusy === p.key
                                ? <Loader2 size={14} className="animate-spin" />
                                : <Shield size={14} />}
                              {t('profile.connect_oauth', { provider: p.name })}
                            </button>
                          )}
                          <button
                            onClick={p.openModal}
                            className="px-3 py-1.5 border border-[#d0d7de] rounded-lg text-xs font-bold text-[#1f2328] hover:bg-white transition-all shadow-sm flex items-center gap-2"
                            title={t('profile.manual_token_hint')}
                          >
                            <LinkIcon size={14} /> {t('profile.connect_manual')}
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* GitHub Modal */}
      {showGithubModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-[#d0d7de] flex items-center justify-between bg-[#f6f8fa]">
              <div className="flex items-center gap-2">
                <Github size={20} />
                <h3 className="font-bold text-[#1f2328]">{t('profile.connect_github')}</h3>
              </div>
              <button onClick={() => setShowGithubModal(false)} className="text-[#636c76] hover:text-[#1f2328]">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold text-[#636c76] uppercase mb-1.5">GitHub Username</label>
                <input 
                  type="text"
                  value={githubUsername}
                  onChange={(e) => setGithubUsername(e.target.value)}
                  className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Octocat"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-[#636c76] uppercase mb-1.5">{t('profile.github_token')}</label>
                <input 
                  type="password"
                  value={githubToken}
                  onChange={(e) => setGithubToken(e.target.value)}
                  className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                  placeholder={t('profile.github_token_placeholder')}
                />
              </div>
              <p className="text-xs text-[#636c76] leading-relaxed">{t('profile.github_token_help')}</p>
            </div>
            <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end gap-3">
              <button onClick={() => setShowGithubModal(false)} className="px-4 py-2 text-sm font-bold text-[#636c76]">{t('common.cancel')}</button>
              <button onClick={handleConnectGithub} disabled={isConnecting || !githubToken} className="px-4 py-2 bg-[#1f2328] text-white rounded-lg text-sm font-bold flex items-center gap-2">
                {isConnecting && <Loader2 size={16} className="animate-spin" />}
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* GitLab Modal */}
      {showGitlabModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-[#d0d7de] flex items-center justify-between bg-[#f6f8fa]">
              <div className="flex items-center gap-2">
                <Gitlab size={20} className="text-orange-500" />
                <h3 className="font-bold text-[#1f2328]">{t('profile.connect_gitlab')}</h3>
              </div>
              <button onClick={() => setShowGitlabModal(false)} className="text-[#636c76] hover:text-[#1f2328]">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold text-[#636c76] uppercase mb-1.5">{t('profile.gitlab_token')}</label>
                <input 
                  type="password"
                  value={gitlabToken}
                  onChange={(e) => setGitlabToken(e.target.value)}
                  className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                  placeholder={t('profile.gitlab_token_placeholder')}
                />
              </div>
              <p className="text-xs text-[#636c76] leading-relaxed">{t('profile.gitlab_token_help')}</p>
            </div>
            <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end gap-3">
              <button onClick={() => setShowGitlabModal(false)} className="px-4 py-2 text-sm font-bold text-[#636c76]">{t('common.cancel')}</button>
              <button onClick={handleConnectGitlab} disabled={isConnecting || !gitlabToken} className="px-4 py-2 bg-[#e24329] text-white rounded-lg text-sm font-bold flex items-center gap-2">
                {isConnecting && <Loader2 size={16} className="animate-spin" />}
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bitbucket Modal */}
      {showBitbucketModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-[#d0d7de] flex items-center justify-between bg-[#f6f8fa]">
              <div className="flex items-center gap-2">
                <Globe size={20} className="text-blue-600" />
                <h3 className="font-bold text-[#1f2328]">{t('profile.connect_bitbucket')}</h3>
              </div>
              <button onClick={() => setShowBitbucketModal(false)} className="text-[#636c76] hover:text-[#1f2328]">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold text-[#636c76] uppercase mb-1.5">{t('profile.bitbucket_token')}</label>
                <input 
                  type="password"
                  value={bitbucketToken}
                  onChange={(e) => setBitbucketToken(e.target.value)}
                  className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                  placeholder={t('profile.bitbucket_token_placeholder')}
                />
              </div>
              <p className="text-xs text-[#636c76] leading-relaxed">{t('profile.bitbucket_token_help')}</p>
            </div>
            <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end gap-3">
              <button onClick={() => setShowBitbucketModal(false)} className="px-4 py-2 text-sm font-bold text-[#636c76]">{t('common.cancel')}</button>
              <button onClick={handleConnectBitbucket} disabled={isConnecting || !bitbucketToken} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-bold flex items-center gap-2">
                {isConnecting && <Loader2 size={16} className="animate-spin" />}
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Gitea Modal */}
      {showGiteaModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="p-4 border-b border-[#d0d7de] flex items-center justify-between bg-[#f6f8fa]">
              <div className="flex items-center gap-2">
                <Globe size={20} className="text-[#634491]" />
                <h3 className="font-bold text-[#1f2328]">{t('profile.connect_gitea')}</h3>
              </div>
              <button onClick={() => setShowGiteaModal(false)} className="text-[#636c76] hover:text-[#1f2328]">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold text-[#636c76] uppercase mb-1.5">{t('profile.gitea_token')}</label>
                <input 
                  type="password"
                  value={giteaToken}
                  onChange={(e) => setGiteaToken(e.target.value)}
                  className="w-full px-3 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                  placeholder={t('profile.gitea_token_placeholder')}
                />
              </div>
              <p className="text-xs text-[#636c76] leading-relaxed">{t('profile.gitea_token_help')}</p>
            </div>
            <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end gap-3">
              <button onClick={() => setShowGiteaModal(false)} className="px-4 py-2 text-sm font-bold text-[#636c76]">{t('common.cancel')}</button>
              <button onClick={handleConnectGitea} disabled={isConnecting || !giteaToken} className="px-4 py-2 bg-[#634491] text-white rounded-lg text-sm font-bold flex items-center gap-2">
                {isConnecting && <Loader2 size={16} className="animate-spin" />}
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Profile;
