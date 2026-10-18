import React, { useState, useEffect } from 'react';
import { 
  X, 
  User as UserIcon, 
  Plus, 
  Search, 
  Loader2, 
  Check, 
  Shield, 
  Trash2,
  Mail,
  UserPlus,
  Users,
  Clock,
  AlertTriangle
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import { User, Project } from '../types';
import { useAuth } from '../context/AuthContext';

interface ProjectMembersModalProps {
  projectId: number;
  project: Project;
  onClose: () => void;
}

const ProjectMembersModal: React.FC<ProjectMembersModalProps> = ({ projectId, project, onClose }) => {
  const { t } = useTranslation();
  const { user: currentUser } = useAuth();
  const [activeTab, setActiveTab] = useState<'members' | 'invite'>('members');
  const [members, setMembers] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<User[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [isInviting, setIsInviting] = useState<number | null>(null);
  const [selectedRole, setSelectedRole] = useState('developer');

  const { data: roles } = useQuery<any[]>({
    queryKey: ['roles'],
    queryFn: async () => {
      const { data } = await api.get('/projects/roles');
      return data;
    },
  });

  const { data: invites, refetch: refetchInvites } = useQuery<any[]>({
    queryKey: ['projects', projectId, 'invites'],
    queryFn: async () => {
      const { data } = await api.get(`/projects/${projectId}/invites`);
      return data;
    }
  });

  const userRole = project.user_role || 'developer';
  const canManage = userRole === 'project_manager' || userRole === 'manager';

  useEffect(() => {
    fetchMembers();
  }, [projectId]);

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      if (searchQuery.trim().length >= 2) {
        searchUsers();
      } else {
        setSearchResults([]);
        setSearchError(null);
      }
    }, 500);

    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery]);

  const fetchMembers = async () => {
    try {
      const { data } = await api.get(`/projects/${projectId}/members`);
      setMembers(data);
    } catch (err) {
      console.error('Failed to fetch members');
    } finally {
      setIsLoading(false);
    }
  };

  const searchUsers = async () => {
    setIsSearching(true);
    setSearchError(null);
    try {
      const { data } = await api.get(`/users/`, { params: { query: searchQuery } });
      // Исключаем:
      // 1. Тех, кто уже в проекте
      // 2. Тех, кому уже отправлено приглашение
      // 3. Самого себя (текущего пользователя)
      const filtered = data.filter((u: User) =>
        !members.some(m => m.id === u.id) &&
        !invites?.some(inv => inv.user_id === u.id) &&
        u.id !== currentUser?.id
      );
      setSearchResults(filtered);
    } catch (err: any) {
      // Раньше ошибка молча превращалась в «пользователи не найдены»,
      // хотя поиск просто не отработал. Причину показываем: иначе
      // поломку нельзя отличить от «никто не подходит».
      console.error('Search failed', err);
      setSearchResults([]);
      setSearchError(
        err?.response?.data?.detail || t('members.search_failed'),
      );
    } finally {
      setIsSearching(false);
    }
  };

  const sendInvite = async (userId: number, email: string) => {
    setIsInviting(userId);
    try {
      await api.post(`/projects/${projectId}/invites/${userId}?role=${selectedRole}`);
      alert(t('members.invite_sent', { email }));
      setSearchQuery('');
      setSearchResults([]);
      refetchInvites();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to send invite');
    } finally {
      setIsInviting(null);
    }
  };

  const updateMemberRole = async (userId: number, role: string) => {
    try {
      // Для обновления роли мы можем использовать тот же эндпоинт, 
      // если пользователь уже в проекте, бэкенд обновит запись в ProjectMember
      await api.post(`/projects/${projectId}/members/${userId}?role=${role}`);
      fetchMembers();
    } catch (err) {
      alert('Failed to update role');
    }
  };

  const removeMember = async (userId: number) => {
    if (!window.confirm(t('members.remove_confirm'))) return;
    try {
      await api.delete(`/projects/${projectId}/members/${userId}`);
      fetchMembers();
    } catch (err) {
      alert('Failed to remove member');
    }
  };

  const getAvailableRoles = (currentRole: string) => {
    if (!roles) return [];
    // If project manager, can assign any role
    if (currentRole === 'project_manager') {
      return roles.map(r => ({ value: r.name, label: r.name.replace(/_/g, ' ').split(' ').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') }));
    }
    // If manager, can assign any role except project_manager
    if (currentRole === 'manager') {
      return roles.filter(r => r.name !== 'project_manager').map(r => ({ value: r.name, label: r.name.replace(/_/g, ' ').split(' ').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') }));
    }
    return [];
  };

  const availableRoles = getAvailableRoles(userRole);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
      <div className="bg-white rounded-xl w-full max-w-md shadow-2xl border border-[#d0d7de] flex flex-col overflow-hidden max-h-[80vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-[#1f2328]">{t('members.title')}</h2>
            <p className="text-xs text-[#636c76]">{t('members.subtitle')}</p>
          </div>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 rounded-md hover:bg-gray-200 transition">
            <X size={20} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#d0d7de] bg-white">
          <button 
            onClick={() => setActiveTab('members')}
            className={`flex-1 py-3 text-xs font-bold flex items-center justify-center gap-2 transition-colors ${
              activeTab === 'members' ? 'text-[#0969da] border-b-2 border-[#0969da]' : 'text-[#636c76] hover:text-[#1f2328] hover:bg-gray-50'
            }`}
          >
            <Users size={14} />
            {t('members.members_tab')}
          </button>
          {canManage && (
            <button 
              onClick={() => setActiveTab('invite')}
              className={`flex-1 py-3 text-xs font-bold flex items-center justify-center gap-2 transition-colors ${
                activeTab === 'invite' ? 'text-[#0969da] border-b-2 border-[#0969da]' : 'text-[#636c76] hover:text-[#1f2328] hover:bg-gray-50'
              }`}
            >
              <UserPlus size={14} />
              {t('members.invite_tab')}
            </button>
          )}
        </div>

        <div className="flex-1 overflow-hidden flex flex-col">
          {activeTab === 'members' ? (
            <div className="flex-1 overflow-y-auto p-2">
              {isLoading ? (
                <div className="flex items-center justify-center py-12"><Loader2 className="animate-spin text-blue-500" size={24} /></div>
              ) : members.length === 0 ? (
                <div className="text-center py-12 text-[#636c76]">
                  <UserIcon size={48} className="mx-auto mb-4 opacity-20" />
                  <p className="text-sm">{t('members.no_members')}</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {members.map(member => (
                    <div key={member.id} className="flex items-center justify-between p-3 rounded-lg hover:bg-[#f6f8fa] transition-colors group">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full border border-[#d0d7de] overflow-hidden bg-gray-100 flex items-center justify-center">
                          {member.avatar_url ? <img src={member.avatar_url} className="w-full h-full object-cover" /> : <UserIcon size={18} className="text-gray-400" />}
                        </div>
                        <div>
                          <div className="flex flex-col">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold text-[#1f2328]">{member.full_name || member.email.split('@')[0]}</span>
                              {member.id === currentUser?.id && (
                                <span className="text-[10px] text-[#0969da] font-bold">({t('members.you')})</span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                              {canManage && member.id !== currentUser?.id && member.id !== project.owner_id ? (
                                <select 
                                  value={member.role}
                                  onChange={(e) => updateMemberRole(member.id, e.target.value)}
                                  className="text-[10px] bg-white border border-[#d0d7de] rounded px-1.5 py-0.5 outline-none font-bold uppercase tracking-wider text-[#636c76]"
                                >
                                  {availableRoles.map(r => (
                                    <option key={r.value} value={r.value}>{r.label}</option>
                                  ))}
                                </select>
                              ) : (
                                <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold border uppercase tracking-wider ${
                                  member.role === 'project_manager' ? 'bg-[#fff8c5] text-[#735c0f] border-[#d4a72c4d]' : 'bg-[#f6f8fa] text-[#636c76] border-[#d0d7de]'
                                }`}>
                                  {member.role.replace('_', ' ')}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>

                      {canManage && member.id !== currentUser?.id && member.id !== project.owner_id && (
                        <button 
                          onClick={() => removeMember(member.id)}
                          className="opacity-0 group-hover:opacity-100 p-2 text-[#636c76] hover:text-red-600 hover:bg-red-50 rounded-lg transition-all" 
                          title={t('members.remove_member')}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col bg-white">
              <div className="p-4 border-b border-[#d0d7de] space-y-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                  <input 
                    type="text"
                    placeholder={t('members.search_placeholder')}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg text-sm outline-none focus:bg-white focus:ring-2 focus:ring-blue-500 transition-all"
                  />
                  {isSearching && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                      <Loader2 className="animate-spin text-blue-500" size={16} />
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-[#1f2328]">{t('members.invite_role')}:</span>
                  <select 
                    value={selectedRole}
                    onChange={(e) => setSelectedRole(e.target.value)}
                    className="text-xs bg-[#f6f8fa] border border-[#d0d7de] rounded px-2 py-1 outline-none"
                  >
                    {availableRoles.map(r => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-2">
                {searchQuery.length < 2 && invites && invites.length > 0 ? (
                  <div className="space-y-1">
                    <div className="px-3 py-2 text-[10px] font-bold text-[#636c76] uppercase tracking-wider">
                      {t('members.pending_invites')}
                    </div>
                    {invites.map(inv => (
                      <div key={inv.id} className="p-3 flex items-center justify-between bg-[#f6f8fa] rounded-lg border border-[#d0d7de]/50">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full border border-[#d0d7de] overflow-hidden bg-white flex items-center justify-center">
                            {inv.user?.avatar_url ? <img src={inv.user.avatar_url} className="w-full h-full object-cover" /> : <UserIcon size={14} className="text-gray-400" />}
                          </div>
                          <div>
                            <p className="text-xs font-bold text-[#1f2328]">{inv.user?.full_name || inv.user?.email.split('@')[0]}</p>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-[9px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-bold uppercase">{inv.role.replace('_', ' ')}</span>
                              <span className="text-[9px] text-[#636c76] italic">{t('members.awaiting')}</span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-[#636c76]">
                          <Clock size={14} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : searchError ? (
                  <div className="text-center py-12 text-[#636c76]">
                    <AlertTriangle size={48} className="mx-auto mb-4 opacity-20 text-red-600" />
                    <p className="text-xs text-red-700">{searchError}</p>
                  </div>
                ) : searchResults.length === 0 ? (
                  <div className="text-center py-12 text-[#636c76]">
                    <Search size={48} className="mx-auto mb-4 opacity-10" />
                    {/* Три разных состояния, а не одно «не найдены»:
                        пустой запрос — это приглашение начать печатать,
                        а не результат поиска. Раньше здесь всегда
                        показывалось «Пользователи не найдены», хотя
                        поиск ещё не запускался. */}
                    <p className="text-xs">
                      {isSearching
                        ? t('common.loading')
                        : searchQuery.trim().length === 0
                          ? t('members.search_start')
                          : searchQuery.trim().length < 2
                            ? t('members.search_min_chars')
                            : t('members.search_none')}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    {searchResults.map(u => (
                      <div key={u.id} className="p-3 flex items-center justify-between hover:bg-[#f6f8fa] rounded-lg transition-colors">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full border border-[#d0d7de] overflow-hidden bg-gray-100 flex items-center justify-center">
                            {u.avatar_url ? <img src={u.avatar_url} className="w-full h-full object-cover" /> : <UserIcon size={14} className="text-gray-400" />}
                          </div>
                          <div>
                            <p className="text-xs font-bold text-[#1f2328]">{u.full_name || u.email.split('@')[0]}</p>
                            <p className="text-[10px] text-[#636c76]">{u.email}</p>
                          </div>
                        </div>
                        <button 
                          onClick={() => sendInvite(u.id, u.email)}
                          disabled={isInviting === u.id}
                          className="px-3 py-1 bg-[#1f883d] text-white rounded-md text-[10px] font-bold hover:bg-[#1a7f37] transition flex items-center gap-1 shadow-sm disabled:opacity-50"
                        >
                          {isInviting === u.id ? <Loader2 className="animate-spin" size={10} /> : <Plus size={10} />}
                          {t('members.add')}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end">
          <button onClick={onClose} className="px-4 py-2 bg-white border border-[#d0d7de] text-[#1f2328] rounded-lg text-sm font-bold hover:bg-[#ebf0f4] transition shadow-sm">
            {t('members.close')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ProjectMembersModal;
