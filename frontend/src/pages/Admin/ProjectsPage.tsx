import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../api/client';
import { Project, User } from '../../types';
import { Loader2, Search, Users, Settings, FolderKanban, Shield, X, UserPlus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import ProjectMembersModal from '../../components/ProjectMembersModal';
import ProjectSettingsModal from '../../components/ProjectSettingsModal';

export default function ProjectsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [isMembersModalOpen, setIsMembersModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  
  const { data: projects, isLoading } = useQuery<Project[]>({
    queryKey: ['admin', 'projects'],
    queryFn: async () => {
      const { data } = await api.get('/admin/projects');
      return data;
    },
  });

  const filteredProjects = projects?.filter(p => 
    p.name.toLowerCase().includes(search.toLowerCase()) || 
    p.description?.toLowerCase().includes(search.toLowerCase())
  );

  const handleMembers = (project: Project) => {
    setSelectedProject(project);
    setIsMembersModalOpen(true);
  };

  const handleSettings = (project: Project) => {
    setSelectedProject(project);
    setIsSettingsModalOpen(true);
  };

  return (
    <div className="p-8 max-w-6xl mx-auto w-full space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#1f2328]">{t('admin.projects_management')}</h1>
          <p className="text-sm text-[#636c76]">Oversee all projects in the system and manage their configurations.</p>
        </div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#636c76]" size={18} />
        <input
          type="text"
          placeholder={t('projects.find_project')}
          className="w-full bg-white border border-[#d0d7de] rounded-md pl-10 pr-4 py-2 text-sm outline-none focus:border-[#0969da] shadow-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-blue-500" size={32} />
        </div>
      ) : (
        <div className="bg-white border border-[#d0d7de] rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#f6f8fa] border-b border-[#d0d7de] text-[#636c76] font-semibold">
              <tr>
                <th className="px-6 py-4">{t('projects.project_name')}</th>
                <th className="px-6 py-4">{t('projects.description')}</th>
                <th className="px-6 py-4">{t('projects.owner')}</th>
                <th className="px-6 py-4 text-right">{t('admin.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#d0d7de]">
              {filteredProjects?.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-gray-500">
                    {t('admin.projects.no_projects')}
                  </td>
                </tr>
              ) : filteredProjects?.map((project: any) => (
                <tr key={project.id} className="hover:bg-[#f6f8fa]/50 transition-colors group">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-orange-50 rounded-lg text-orange-600 border border-orange-100">
                        <FolderKanban size={20} />
                      </div>
                      <div>
                        <div className="font-semibold text-[#1f2328]">{project.name}</div>
                        <div className="text-[10px] text-[#636c76] font-mono uppercase tracking-wider">ID: {project.id}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 max-w-xs">
                    <div className="text-xs text-[#636c76] line-clamp-2 italic">
                      {project.description || t('projects.no_description')}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-[#1f2328]">{project.owner_name}</span>
                      <span className="text-[10px] text-[#636c76]">{project.owner_email}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button 
                        onClick={() => handleMembers(project)}
                        className="flex items-center gap-2 px-3 py-1.5 bg-[#f6f8fa] border border-[#d0d7de] text-[#1f2328] rounded-md hover:bg-[#ebf0f4] transition font-semibold text-xs shadow-sm"
                      >
                        <Users size={14} />
                        {t('admin.projects.members')}
                      </button>
                      <button 
                        onClick={() => handleSettings(project)}
                        className="flex items-center gap-2 px-3 py-1.5 bg-[#f6f8fa] border border-[#d0d7de] text-[#1f2328] rounded-md hover:bg-[#ebf0f4] transition font-semibold text-xs shadow-sm"
                      >
                        <Settings size={14} />
                        {t('admin.projects.settings')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isMembersModalOpen && selectedProject && (
        <AdminProjectMembersModal 
          projectId={selectedProject.id}
          onClose={() => setIsMembersModalOpen(false)}
        />
      )}

      {isSettingsModalOpen && selectedProject && (
        <ProjectSettingsModal 
          project={selectedProject}
          onClose={() => setIsSettingsModalOpen(false)}
          onUpdated={() => queryClient.invalidateQueries({ queryKey: ['admin', 'projects'] })}
        />
      )}
    </div>
  );
}

// Special version of ProjectMembersModal for Admin
function AdminProjectMembersModal({ projectId, onClose }: { projectId: number, onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [isAddOpen, setIsAddOpen] = useState(false);

  const { data: members, isLoading } = useQuery({
    queryKey: ['admin', 'projects', projectId, 'members'],
    queryFn: async () => {
      const { data } = await api.get(`/admin/projects/${projectId}/members`);
      return data;
    }
  });

  const { data: roles } = useQuery({
    queryKey: ['admin', 'roles'],
    queryFn: async () => {
      const { data } = await api.get('/admin/roles');
      return data;
    }
  });

  const updateMemberMutation = useMutation({
    mutationFn: async ({ userId, roleId }: { userId: number, roleId: number }) => {
      return api.post(`/admin/projects/${projectId}/members?user_id=${userId}&role_id=${roleId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'projects', projectId, 'members'] });
    }
  });

  const removeMemberMutation = useMutation({
    mutationFn: async (userId: number) => {
      return api.delete(`/admin/projects/${projectId}/members/${userId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'projects', projectId, 'members'] });
    }
  });

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-2xl shadow-2xl border border-[#d0d7de] overflow-hidden flex flex-col max-h-[80vh]">
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <Users size={20} className="text-blue-600" />
            <h2 className="text-lg font-bold text-[#1f2328]">{t('members.title')}</h2>
          </div>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328] p-1 hover:bg-gray-200 rounded-lg transition-colors">
            <X size={20}/>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-thin">
          <div className="flex items-center justify-between">
             <h3 className="text-sm font-bold text-[#1f2328] uppercase tracking-wider">{t('members.members_tab')}</h3>
             <button 
               onClick={() => setIsAddOpen(!isAddOpen)}
               className="text-xs font-bold text-blue-600 hover:text-blue-800 flex items-center gap-1 transition-colors"
             >
               <UserPlus size={14} />
               {isAddOpen ? t('common.cancel') : t('members.add')}
             </button>
          </div>

          {isAddOpen && (
            <AddMemberSection 
              onAdd={(userId, roleId) => {
                updateMemberMutation.mutate({ userId, roleId });
                setIsAddOpen(false);
              }}
              roles={roles || []}
            />
          )}

          {isLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin text-blue-500" /></div>
          ) : (
            <div className="space-y-2">
              {members?.map((member: any) => (
                <div key={member.user_id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-100 group">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-xs border border-blue-200">
                      {member.full_name?.[0] || member.email?.[0]}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-[#1f2328]">{member.full_name || member.email}</div>
                      <div className="text-[10px] text-gray-500">{member.email}</div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4">
                    <select 
                      value={member.role_id || ''}
                      onChange={(e) => updateMemberMutation.mutate({ userId: member.user_id, roleId: Number(e.target.value) })}
                      className="text-xs bg-white border border-[#d0d7de] rounded px-2 py-1 outline-none focus:border-blue-500 font-medium"
                    >
                      {roles?.map((r: any) => (
                        <option key={r.id} value={r.id}>{r.name}</option>
                      ))}
                    </select>
                    <button 
                      onClick={() => removeMemberMutation.mutate(member.user_id)}
                      className="text-gray-400 hover:text-red-600 transition-colors p-1"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end shrink-0">
          <button onClick={onClose} className="px-4 py-2 bg-white border border-[#d0d7de] text-[#1f2328] rounded-lg text-sm font-semibold hover:bg-gray-50 transition-colors shadow-sm">
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
}

function AddMemberSection({ onAdd, roles }: { onAdd: (userId: number, roleId: number) => void, roles: any[] }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [selectedRole, setSelectedRole] = useState(roles[0]?.id || '');

  const { data: users } = useQuery({
    queryKey: ['admin', 'users', 'search', search],
    queryFn: async () => {
      const { data } = await api.get(`/users/?query=${search}`);
      return data;
    },
    enabled: search.length > 2
  });

  return (
    <div className="p-4 bg-blue-50 rounded-lg border border-blue-100 space-y-3">
       <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
          <input 
            placeholder={t('members.search_placeholder')}
            className="w-full bg-white border border-[#d0d7de] rounded-md pl-9 pr-4 py-1.5 text-xs outline-none focus:border-blue-500"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {users && users.length > 0 && search && !selectedUser && (
            <div className="absolute left-0 right-0 mt-1 bg-white border border-[#d0d7de] rounded-md shadow-lg z-10 max-h-40 overflow-y-auto">
              {users.map((u: User) => (
                <button 
                  key={u.id}
                  onClick={() => { setSelectedUser(u); setSearch(u.email); }}
                  className="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 flex items-center justify-between border-b border-gray-100 last:border-0"
                >
                  <span>{u.full_name || u.email}</span>
                  <span className="text-[10px] text-gray-400">{u.email}</span>
                </button>
              ))}
            </div>
          )}
       </div>

       {selectedUser && (
         <div className="flex items-center gap-3">
            <select 
              value={selectedRole}
              onChange={e => setSelectedRole(Number(e.target.value))}
              className="flex-1 text-xs bg-white border border-[#d0d7de] rounded px-3 py-1.5 outline-none font-medium"
            >
              {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
            <button 
              onClick={() => onAdd(selectedUser.id, Number(selectedRole))}
              className="bg-blue-600 text-white px-4 py-1.5 rounded text-xs font-bold hover:bg-blue-700 shadow-sm"
            >
              {t('common.add')}
            </button>
         </div>
       )}
    </div>
  );
}
