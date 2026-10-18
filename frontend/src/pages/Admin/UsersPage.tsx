import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api/client';
import { User } from '../../types';
import { Loader2, Search, UserPlus, Shield, Check, X, Edit2, Key, Mail, User as UserIcon, Trash2, Eye, EyeOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../context/AuthContext';

export default function UsersPage() {
  const { t } = useTranslation();
  const { user: currentUser } = useAuth();
  const [search, setSearch] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const queryClient = useQueryClient();

  const { data: users, isLoading } = useQuery<User[]>({
    queryKey: ['admin', 'users', search],
    queryFn: async () => {
      const { data } = await api.get(`/admin/users?query=${search}`);
      return data;
    },
  });

  const updateUserMutation = useMutation({
    mutationFn: async ({ userId, data }: { userId: number; data: any }) => {
      const { data: updated } = await api.patch(`/admin/users/${userId}`, data);
      return updated;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      setIsModalOpen(false);
      setEditingUser(null);
    },
  });

  const createUserMutation = useMutation({
    mutationFn: async (data: any) => {
      const { data: created } = await api.post('/admin/users', data);
      return created;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      setIsModalOpen(false);
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: async (userId: number) => {
      await api.delete(`/admin/users/${userId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });

  const toggleFlag = (user: User, field: keyof User) => {
    updateUserMutation.mutate({
      userId: user.id,
      data: { [field]: !user[field] },
    });
  };

  const handleEdit = (user: User) => {
    setEditingUser(user);
    setIsModalOpen(true);
  };

  const handleAddNew = () => {
    setEditingUser(null);
    setIsModalOpen(true);
  };

  const handleDelete = (user: User) => {
    if (user.id === currentUser?.id) {
      alert("You cannot delete yourself");
      return;
    }
    if (window.confirm(`Are you sure you want to delete user ${user.email}? This action cannot be undone.`)) {
      deleteUserMutation.mutate(user.id);
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto w-full space-y-6">
      <div className="flex items-center justify-between">
        <div>
           <h1 className="text-2xl font-bold text-[#1f2328]">{t('admin.users_management')}</h1>
           <p className="text-sm text-[#636c76]">Manage all users across the platform.</p>
        </div>
        <button 
          onClick={handleAddNew}
          className="flex items-center gap-2 bg-[#1f883d] text-white px-4 py-2 rounded-md font-semibold text-sm hover:bg-[#1a7f37] shadow-sm transition-colors"
        >
          <UserPlus size={16} />
          {t('admin.add_user')}
        </button>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#636c76]" size={18} />
        <input
          type="text"
          placeholder={t('admin.search_users')}
          className="w-full bg-white border border-[#d0d7de] rounded-md pl-10 pr-4 py-2 text-sm outline-none focus:border-[#0969da] focus:ring-1 focus:ring-[#0969da] shadow-sm transition-all"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="bg-white border border-[#d0d7de] rounded-lg overflow-hidden shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#f6f8fa] border-b border-[#d0d7de] text-[#636c76] font-semibold">
            <tr>
              <th className="px-6 py-4">{t('admin.user')}</th>
              <th className="px-6 py-4">{t('admin.status')}</th>
              <th className="px-6 py-4">{t('admin.is_superuser')}</th>
              <th className="px-6 py-4">{t('admin.can_create_projects')}</th>
              <th className="px-6 py-4 text-right">{t('admin.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#d0d7de]">
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="animate-spin text-[#0969da]" size={32} />
                    <span className="text-gray-500 font-medium">Loading users...</span>
                  </div>
                </td>
              </tr>
            ) : users?.length === 0 ? (
              <tr>
                 <td colSpan={5} className="px-6 py-12 text-center text-[#636c76]">
                    No users found matching your search.
                 </td>
              </tr>
            ) : users?.map((user) => (
              <tr key={user.id} className="hover:bg-[#f6f8fa]/50 transition-colors group">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full border border-[#d0d7de] overflow-hidden bg-gradient-to-tr from-gray-100 to-gray-50 flex items-center justify-center">
                      {user.avatar_url ? (
                        <img src={user.avatar_url} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <UserIcon size={18} className="text-gray-400" />
                      )}
                    </div>
                    <div>
                      <div className="font-semibold text-[#1f2328] group-hover:text-blue-600 transition-colors">{user.full_name || 'No Name'}</div>
                      <div className="text-xs text-[#636c76]">{user.email}</div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <button 
                    onClick={() => toggleFlag(user, 'is_active')}
                    className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all shadow-sm ${
                      user.is_active 
                        ? 'bg-green-100 text-green-700 border border-green-200 hover:bg-green-200' 
                        : 'bg-red-100 text-red-700 border border-red-200 hover:bg-red-200'
                    }`}
                  >
                    {user.is_active ? t('admin.active') : t('admin.inactive')}
                  </button>
                </td>
                <td className="px-6 py-4">
                  <button 
                    onClick={() => toggleFlag(user, 'is_superuser')}
                    disabled={user.id === currentUser?.id}
                    className={`p-2 rounded-lg transition-all ${
                      user.is_superuser 
                        ? 'text-blue-600 bg-blue-50 border border-blue-100' 
                        : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 border border-transparent'
                    } ${user.id === currentUser?.id ? 'opacity-50 cursor-not-allowed' : ''}`}
                    title={user.id === currentUser?.id ? "You cannot remove your own admin status" : ""}
                  >
                    <Shield size={20} className={user.is_superuser ? 'fill-current opacity-20' : ''} />
                  </button>
                </td>
                <td className="px-6 py-4">
                  <button 
                    onClick={() => toggleFlag(user, 'can_create_projects')}
                    className={`p-2 rounded-lg transition-all ${
                      user.can_create_projects 
                        ? 'text-emerald-600 bg-emerald-50 border border-emerald-100' 
                        : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 border border-transparent'
                    }`}
                  >
                    <Check size={20} />
                  </button>
                </td>
                <td className="px-6 py-4 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button 
                      onClick={() => handleEdit(user)}
                      className="text-[#636c76] hover:text-[#0969da] p-2 hover:bg-blue-50 rounded-lg transition-all"
                    >
                      <Edit2 size={18} />
                    </button>
                    <button 
                      onClick={() => handleDelete(user)}
                      disabled={user.id === currentUser?.id}
                      className={`p-2 rounded-lg transition-all ${
                        user.id === currentUser?.id 
                          ? 'text-gray-300 cursor-not-allowed' 
                          : 'text-[#636c76] hover:text-red-600 hover:bg-red-50'
                      }`}
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {isModalOpen && (
        <UserModal 
          user={editingUser}
          onClose={() => { setIsModalOpen(false); setEditingUser(null); }}
          onSave={(data) => {
            if (editingUser) {
              updateUserMutation.mutate({ userId: editingUser.id, data });
            } else {
              createUserMutation.mutate(data);
            }
          }}
          loading={updateUserMutation.isPending || createUserMutation.isPending}
        />
      )}
    </div>
  );
}

function UserModal({ user, onClose, onSave, loading }: { user: User | null, onClose: () => void, onSave: (data: any) => void, loading: boolean }) {
  const { t } = useTranslation();
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({
    email: user?.email || '',
    full_name: user?.full_name || '',
    password: '',
    is_superuser: user?.is_superuser || false,
    can_create_projects: user?.can_create_projects || false
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data: any = { ...formData };
    if (!data.password) delete data.password;
    onSave(data);
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-md shadow-2xl border border-[#d0d7de] overflow-hidden">
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
          <h2 className="text-lg font-bold text-[#1f2328]">
            {user ? t('admin.edit_user') : t('admin.add_user')}
          </h2>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 hover:bg-gray-200 rounded-lg transition-colors">
            <X size={20}/>
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-[#1f2328] mb-1.5 uppercase tracking-wider">{t('admin.login')}</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                <input 
                  required
                  type="email"
                  value={formData.email} 
                  onChange={e => setFormData({ ...formData, email: e.target.value })}
                  className="w-full bg-white border border-[#d0d7de] rounded-lg pl-10 pr-4 py-2 text-sm outline-none focus:border-[#0969da] focus:ring-1 focus:ring-[#0969da] shadow-sm"
                  placeholder="user@example.com"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#1f2328] mb-1.5 uppercase tracking-wider">{t('admin.full_name')}</label>
              <div className="relative">
                <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                <input 
                  value={formData.full_name} 
                  onChange={e => setFormData({ ...formData, full_name: e.target.value })}
                  className="w-full bg-white border border-[#d0d7de] rounded-lg pl-10 pr-4 py-2 text-sm outline-none focus:border-[#0969da] focus:ring-1 focus:ring-[#0969da] shadow-sm"
                  placeholder="John Doe"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#1f2328] mb-1.5 uppercase tracking-wider">
                {t('admin.password')} {user && <span className="text-[10px] text-gray-400 normal-case font-normal">(Leave blank to keep current)</span>}
              </label>
              <div className="relative">
                <Key className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                <input 
                  type={showPassword ? "text" : "password"}
                  required={!user}
                  value={formData.password} 
                  onChange={e => setFormData({ ...formData, password: e.target.value })}
                  className="w-full bg-white border border-[#d0d7de] rounded-lg pl-10 pr-10 py-2 text-sm outline-none focus:border-[#0969da] focus:ring-1 focus:ring-[#0969da] shadow-sm"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
          </div>

          <div className="p-4 bg-gray-50 rounded-lg border border-gray-100 space-y-3">
             <label className="flex items-center gap-3 cursor-pointer group">
                <input 
                  type="checkbox"
                  checked={formData.is_superuser}
                  onChange={e => setFormData({ ...formData, is_superuser: e.target.checked })}
                  className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-gray-300"
                />
                <span className="text-sm font-medium text-gray-700 group-hover:text-[#1f2328] transition-colors">{t('admin.is_superuser')}</span>
             </label>
             <label className="flex items-center gap-3 cursor-pointer group">
                <input 
                  type="checkbox"
                  checked={formData.can_create_projects}
                  onChange={e => setFormData({ ...formData, can_create_projects: e.target.checked })}
                  className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-gray-300"
                />
                <span className="text-sm font-medium text-gray-700 group-hover:text-[#1f2328] transition-colors">{t('admin.can_create_projects')}</span>
             </label>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button 
              type="button"
              onClick={onClose} 
              className="px-4 py-2 bg-white border border-[#d0d7de] text-[#1f2328] rounded-lg text-sm font-semibold hover:bg-gray-50 transition-colors shadow-sm"
            >
              {t('common.cancel')}
            </button>
            <button 
              type="submit"
              disabled={loading}
              className="px-6 py-2 bg-[#1f883d] text-white border border-[#1a7f37] rounded-lg text-sm font-semibold hover:bg-[#1a7f37] disabled:opacity-50 flex items-center gap-2 shadow-sm transition-all"
            >
              {loading ? <Loader2 className="animate-spin" size={16}/> : t('common.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
