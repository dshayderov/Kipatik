import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api/client';
import { Loader2, Plus, Shield, Check, X, Edit2, Trash2, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Role {
  id: number;
  name: string;
  description: string;
  permissions: string; // JSON string
  is_system: boolean;
}

const ALL_PERMISSIONS = [
  "project:delete", "project:edit", "project:view", "project:invite", "project:remove_member", "project:manage_roles", "project:connect_repo", "project:manage_columns", "project:manage_labels", "project:view_settings",
  "board:view", "board:manage_columns", "board:move_task",
  "task:create", "task:view", "task:edit", "task:delete", "task:assign_self", "task:assign_other", "task:manage_priority", "task:manage_deadline", "task:manage_labels", "task:manage_subtasks", "task:close_reopen", "task:git_link", "task:ai_approve",
  "comment:create", "comment:edit_own", "comment:delete_any",
  "pr:view", "pr:comment", "pr:approve", "pr:merge"
];

export default function RolesPage() {
  const { t } = useTranslation();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);
  const queryClient = useQueryClient();

  const { data: roles, isLoading } = useQuery<Role[]>({
    queryKey: ['admin', 'roles'],
    queryFn: async () => {
      const { data } = await api.get('/admin/roles');
      return data;
    },
  });

  const saveRoleMutation = useMutation({
    mutationFn: async (data: any) => {
      if (editingRole) {
        return api.patch(`/admin/roles/${editingRole.id}`, data);
      }
      return api.post('/admin/roles', data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'roles'] });
      setIsModalOpen(false);
      setEditingRole(null);
    },
  });

  const deleteRoleMutation = useMutation({
    mutationFn: async (id: number) => {
      return api.delete(`/admin/roles/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'roles'] });
    },
  });

  const handleEdit = (role: Role) => {
    setEditingRole(role);
    setIsModalOpen(true);
  };

  const handleDelete = (id: number) => {
    if (window.confirm(t('admin.roles.delete_confirm'))) {
      deleteRoleMutation.mutate(id);
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto w-full space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#1f2328]">{t('admin.roles_management')}</h1>
          <p className="text-sm text-[#636c76]">Define project-level roles and their granular permissions.</p>
        </div>
        <button 
          onClick={() => { setEditingRole(null); setIsModalOpen(true); }}
          className="flex items-center gap-2 bg-[#1f883d] text-white px-4 py-2 rounded-md font-semibold text-sm hover:bg-[#1a7f37] shadow-sm transition-colors"
        >
          <Plus size={16} />
          {t('admin.roles.add')}
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-blue-500" size={32} />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {roles?.map(role => (
            <div key={role.id} className="bg-white border border-[#d0d7de] rounded-lg p-6 shadow-sm flex flex-col hover:border-blue-300 transition-colors group">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                   <Shield className={role.is_system ? "text-purple-600" : "text-blue-600"} size={20} />
                   <h3 className="font-bold text-[#1f2328]">{role.name}</h3>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={() => handleEdit(role)} className="p-1.5 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors">
                    <Edit2 size={16} />
                  </button>
                  {!role.is_system && (
                    <button onClick={() => handleDelete(role.id)} className="p-1.5 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors">
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              </div>
              <p className="text-sm text-[#636c76] mb-4 flex-1 leading-relaxed">
                {role.description || 'No description provided.'}
              </p>
              <div className="flex items-center justify-between pt-4 border-t border-[#f0f2f4]">
                <span className="text-xs font-semibold text-gray-500 bg-gray-50 px-2 py-1 rounded border border-gray-100">
                  {JSON.parse(role.permissions).length} {t('admin.roles.permissions').toLowerCase()}
                </span>
                {role.is_system && (
                  <span className="text-[10px] uppercase font-bold text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-100">
                    {t('admin.roles.system_role')}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {isModalOpen && (
        <RoleModal 
          role={editingRole}
          onClose={() => { setIsModalOpen(false); setEditingRole(null); }}
          onSave={(data) => saveRoleMutation.mutate(data)}
          loading={saveRoleMutation.isPending}
        />
      )}
    </div>
  );
}

function RoleModal({ role, onClose, onSave, loading }: any) {
  const { t } = useTranslation();
  const [name, setName] = useState(role?.name || '');
  const [desc, setDesc] = useState(role?.description || '');
  const [permissions, setPermissions] = useState<string[]>(role ? JSON.parse(role.permissions) : []);

  const togglePermission = (perm: string) => {
    if (permissions.includes(perm)) {
      setPermissions(permissions.filter(p => p !== perm));
    } else {
      setPermissions([...permissions, perm]);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      name,
      description: desc,
      permissions: JSON.stringify(permissions),
      is_system: role?.is_system || false
    });
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] shadow-2xl border border-[#d0d7de] overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between shrink-0">
          <h2 className="text-lg font-bold text-[#1f2328]">
            {role ? t('admin.roles.edit') : t('admin.roles.add')}
          </h2>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 hover:bg-gray-200 rounded-lg transition-colors">
            <X size={20}/>
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="flex-1 overflow-hidden flex flex-col">
          <div className="p-6 overflow-y-auto space-y-6 scrollbar-thin">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-xs font-bold text-[#1f2328] mb-1.5 uppercase tracking-wider">{t('admin.roles.name')}</label>
                <input 
                  required
                  value={name} 
                  onChange={e => setName(e.target.value)}
                  className="w-full bg-white border border-[#d0d7de] rounded-lg px-4 py-2 text-sm outline-none focus:border-[#0969da] focus:ring-1 focus:ring-[#0969da] shadow-sm"
                  placeholder="e.g. Lead Developer"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-[#1f2328] mb-1.5 uppercase tracking-wider">{t('admin.roles.description')}</label>
                <input 
                  value={desc} 
                  onChange={e => setDesc(e.target.value)}
                  className="w-full bg-white border border-[#d0d7de] rounded-lg px-4 py-2 text-sm outline-none focus:border-[#0969da] focus:ring-1 focus:ring-[#0969da] shadow-sm"
                  placeholder="What can this role do?"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                 <label className="block text-xs font-bold text-[#1f2328] uppercase tracking-wider">{t('admin.roles.permissions')}</label>
                 <span className="text-[10px] text-blue-600 font-bold bg-blue-50 px-2 py-0.5 rounded border border-blue-100">
                   {permissions.length} selected
                 </span>
              </div>
              
              <div className="bg-[#f6f8fa] border border-[#d0d7de] rounded-lg p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {ALL_PERMISSIONS.map(perm => (
                  <label key={perm} className="flex items-center gap-3 p-2 bg-white border border-[#d0d7de] rounded-md cursor-pointer hover:border-blue-400 hover:shadow-sm transition-all group">
                    <input 
                      type="checkbox"
                      checked={permissions.includes(perm)}
                      onChange={() => togglePermission(perm)}
                      className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-gray-300 transition-colors"
                    />
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold text-[#1f2328] group-hover:text-blue-700 transition-colors">{perm.split(':').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}</span>
                      <span className="text-[9px] text-gray-500 font-medium">{perm}</span>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end gap-3 shrink-0">
            <div className="mr-auto flex items-center gap-2 text-[#636c76] text-xs px-3">
              <Info size={14} />
              <span>Permissions are applied globally to projects using this role.</span>
            </div>
            <button 
              type="button"
              onClick={onClose} 
              className="px-4 py-2 bg-white border border-[#d0d7de] text-[#1f2328] rounded-lg text-sm font-semibold hover:bg-gray-50 transition-colors shadow-sm"
            >
              {t('common.cancel')}
            </button>
            <button 
              type="submit"
              disabled={loading || !name}
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
