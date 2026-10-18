import React, { useState, useEffect, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { 
  Layout, 
  Plus, 
  Loader2, 
  ArrowRight, 
  GitBranch,
  Search,
  Folder,
  User as UserIcon,
  CheckSquare,
  Clock,
  AlertCircle,
  Filter,
  ChevronLeft,
  ChevronRight,
  Calendar,
  MessageSquare,
  Tag,
  Crown,
  ShieldCheck,
  Globe,
  Bell,
  Inbox
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import { Project, Task, Notification } from '../types';
import { useAuth } from '../context/AuthContext';
import NotificationItem, { NOTIFICATIONS_QUERY_KEY } from './NotificationItem';

interface DashboardSelectionProps {
  onSelectProject: (id: number) => void;
  onCreateProject: () => void;
}

type SortOption = 'deadline' | 'priority' | 'status' | 'newest';

type PanelId = 'projects' | 'tasks' | 'notifications';

/** Ширина свернутой панели (иконочная полоса) в пикселях */
const COLLAPSED_W = 48;
/** Границы доли панели проектов в общей ширине, % */
const MIN_PROJECTS_W = 20;
const MAX_PROJECTS_W = 60;
const DEFAULT_PROJECTS_W = 40;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const DashboardSelection: React.FC<DashboardSelectionProps> = ({ onSelectProject, onCreateProject }) => {
  const { user } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const canCreate = user?.can_create_projects || user?.is_superuser;

  // Projects Query
  const { data: projects, isLoading: projectsLoading } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: async () => {
      const { data } = await api.get('/projects/');
      return data;
    }
  });

  // User Tasks Query
  const { data: myTasks, isLoading: tasksLoading } = useQuery<Task[]>({
    queryKey: ['my-tasks'],
    queryFn: async () => {
      const { data } = await api.get('/tasks/my-tasks');
      return data;
    }
  });

  // Notifications Query (тот же ключ, что у колокольчика — общий кэш)
  const { data: notifications, isLoading: notificationsLoading } = useQuery<Notification[]>({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    queryFn: async () => {
      const { data } = await api.get('/notifications/', { params: { limit: 100 } });
      return data;
    }
  });

  const [projectSearch, setProjectSearch] = useState('');
  const [taskSearch, setTaskSearch] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('deadline');

  // Layout states
  const [leftWidth, setLeftWidth] = useState(() => {
    const saved = localStorage.getItem('dashboard_left_width');
    const value = saved ? parseFloat(saved) : DEFAULT_PROJECTS_W;
    return Number.isFinite(value) ? clamp(value, MIN_PROJECTS_W, MAX_PROJECTS_W) : DEFAULT_PROJECTS_W;
  });
  const [isResizing, setIsResizing] = useState(false);
  // Свернута может быть не более одной панели: при сворачивании любой панели
  // ранее свернутая разворачивается. Поэтому хотя бы две панели всегда раскрыты.
  const [collapsedPanel, setCollapsedPanel] = useState<PanelId | null>(null);

  const togglePanel = useCallback((id: PanelId) => {
    setCollapsedPanel((prev) => (prev === id ? null : id));
  }, []);

  const startResizing = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  const stopResizing = useCallback(() => {
    setIsResizing(false);
    localStorage.setItem('dashboard_left_width', leftWidth.toString());
  }, [leftWidth]);

  const resize = useCallback((e: MouseEvent) => {
    if (isResizing) {
      const newWidth = (e.clientX / window.innerWidth) * 100;
      setLeftWidth(clamp(newWidth, MIN_PROJECTS_W, MAX_PROJECTS_W));
    }
  }, [isResizing]);

  useEffect(() => {
    window.addEventListener('mousemove', resize);
    window.addEventListener('mouseup', stopResizing);
    return () => {
      window.removeEventListener('mousemove', resize);
      window.removeEventListener('mouseup', stopResizing);
    };
  }, [resize, stopResizing]);

  const filteredProjects = projects?.filter(p => 
    p.name.toLowerCase().includes(projectSearch.toLowerCase())
  );

  const filteredTasks = myTasks?.filter(t => 
    t.title.toLowerCase().includes(taskSearch.toLowerCase()) || 
    t.description?.toLowerCase().includes(taskSearch.toLowerCase())
  ).sort((a, b) => {
    if (sortBy === 'deadline') {
      if (!a.due_date) return 1;
      if (!b.due_date) return -1;
      return new Date(a.due_date).getTime() - new Date(b.due_date).getTime();
    }
    if (sortBy === 'priority') {
      return b.priority - a.priority;
    }
    if (sortBy === 'status') {
      return a.column_id - b.column_id;
    }
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const getRoleLabel = (role: string | undefined) => {
    if (!role) return t('members.member');
    
    // Map system role keys to translation keys or formatted strings
    const roleMap: Record<string, string> = {
      'project_manager': t('roles.project_manager') || 'Project Manager',
      'manager': t('roles.manager') || 'Manager',
      'developer': t('roles.developer') || 'Developer',
      'tester': t('roles.tester') || 'Tester',
      'observer': t('roles.observer') || 'Observer'
    };
    
    return roleMap[role] || role.replace(/_/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  if (projectsLoading || tasksLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#f6f8fa]">
        <Loader2 className="animate-spin text-blue-500" size={32} />
      </div>
    );
  }

  const navigateToTask = (projectId: number, taskId: number) => {
    navigate(`/project/${projectId}?taskId=${taskId}`);
  };

  // Доли панелей: проекты занимают настраиваемую долю, остаток делится поровну
  // между задачами и уведомлениями. Свёрнутая панель схлопывается в полосу.
  const restWeight = Math.max(100 - leftWidth, 10);
  const panelWeights: Record<PanelId, number> = {
    projects: leftWidth,
    tasks: restWeight / 2,
    notifications: restWeight / 2,
  };

  const panelStyle = (id: PanelId): React.CSSProperties =>
    collapsedPanel === id ? { flex: `0 0 ${COLLAPSED_W}px` } : { flex: `${panelWeights[id]} 1 0` };

  const notificationsList = notifications ?? [];
  const unreadCount = notificationsList.filter((n) => !n.is_read).length;

  return (
    <div className="flex-1 flex overflow-hidden bg-[#f6f8fa]">
      {/* Projects Panel */}
      <div
        style={panelStyle('projects')}
        className="flex flex-col border-r border-[#d0d7de] bg-white transition-[flex] duration-300 relative overflow-hidden"
      >
        <div className="p-4 flex items-center justify-between border-b border-[#d0d7de] bg-[#f6f8fa] shrink-0 min-h-[64px]">
          {collapsedPanel === 'projects' ? (
            <div className="flex flex-col items-center gap-3 w-full">
              <Folder size={18} className="text-[#636c76]" />
              <button
                onClick={() => togglePanel('projects')}
                title={t('dashboard.projects_panel')}
                className="p-1 text-[#636c76] hover:bg-gray-200 rounded-md transition"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          ) : (
            <>
              <h2 className="font-bold text-[#1f2328] truncate">{t('dashboard.projects_panel')}</h2>
              <div className="flex items-center gap-2">
                {canCreate && (
                  <button onClick={onCreateProject} className="p-1.5 text-[#1f883d] hover:bg-[#dafbe1] rounded-md transition" title={t('projects.new_project')}>
                    <Plus size={18} />
                  </button>
                )}
                <button
                  onClick={() => togglePanel('projects')}
                  title={t('dashboard.collapse')}
                  className="p-1.5 text-[#636c76] hover:bg-gray-200 rounded-md transition"
                >
                  <ChevronLeft size={18} />
                </button>
              </div>
            </>
          )}
        </div>

        {collapsedPanel !== 'projects' && (
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#636c76]" size={14} />
              <input 
                type="text"
                placeholder={t('dashboard.filter_projects')}
                value={projectSearch}
                onChange={(e) => setProjectSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-[#f6f8fa] border border-[#d0d7de] rounded-md text-sm outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all shadow-sm"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              {filteredProjects?.map(project => (
                <div 
                  key={project.id}
                  onClick={() => onSelectProject(project.id)}
                  className="group flex flex-col bg-white border border-[#d0d7de] rounded-xl hover:border-[#0969da] hover:shadow-lg transition-all cursor-pointer overflow-hidden h-full"
                >
                  <div className="h-2 bg-gradient-to-r from-blue-500 to-indigo-600 opacity-80 group-hover:opacity-100 transition-opacity"></div>
                  <div className="p-5 flex flex-col flex-1">
                    <div className="flex items-start justify-between mb-3">
                      <div className="w-10 h-10 rounded-lg bg-[#f0f7ff] border border-[#0969da20] flex items-center justify-center text-[#0969da] group-hover:scale-110 transition-transform">
                        <Folder size={20} />
                      </div>
                      <ArrowRight size={18} className="text-[#d0d7de] group-hover:text-[#0969da] group-hover:translate-x-1 transition-all" />
                    </div>
                    
                    <h3 className="text-base font-bold text-[#1f2328] mb-1 group-hover:text-[#0969da] transition-colors line-clamp-1">{project.name}</h3>
                    <p className="text-xs text-[#636c76] line-clamp-2 mb-3 flex-1">{project.description || t('projects.no_description')}</p>
                    
                    {/* Project Details */}
                    <div className="space-y-2 mb-4">
                      <div className="flex items-center gap-2 text-[11px] text-[#636c76]">
                        <Crown size={12} className="text-amber-500" />
                        <span className="font-semibold">{t('projects.owner')}:</span>
                        <span className="text-[#1f2328]">
                          {project.owner_id === user?.id 
                            ? user.full_name 
                            : (project.members?.find(m => m.id === project.owner_id)?.full_name || t('common.loading'))
                          }
                          {project.owner_id === user?.id && ` (${t('projects.you')})`}
                        </span>
                      </div>
                      
                      <div className="flex items-center gap-2 text-[11px] text-[#636c76]">
                        <ShieldCheck size={12} className="text-blue-500" />
                        <span className="font-semibold">{(t('members.role') || 'Role').replace(':', '')}:</span>
                        <span className="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded border border-blue-100 font-bold uppercase text-[9px]">
                          {getRoleLabel(project.user_role)}
                        </span>
                      </div>

                      {project.git_url && (
                        <div className="flex items-center gap-2 text-[11px] text-[#636c76] truncate" title={project.git_url}>
                          <GitBranch size={12} className="text-green-600" />
                          <span className="font-semibold">{t('projects.repository') || 'Repo'}:</span>
                          <span className="text-[#0969da] hover:underline truncate">
                            {project.git_url.split('/').pop()?.replace('.git', '')}
                          </span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-between mt-auto pt-3 border-t border-[#f0f2f4]">
                      <div className="flex items-center gap-2">
                        <div className="flex -space-x-2">
                          {project.members?.slice(0, 3).map((member, i) => (
                            <div key={i} className="w-6 h-6 rounded-full border-2 border-white bg-gray-200 overflow-hidden" title={member.full_name}>
                              {member.avatar_url ? <img src={member.avatar_url} alt="" /> : <div className="w-full h-full flex items-center justify-center bg-blue-100 text-[8px] font-bold text-blue-600">{member.full_name?.[0] || '?'}</div>}
                            </div>
                          ))}
                          {(project.members?.length || 0) > 3 && (
                            <div className="w-6 h-6 rounded-full border-2 border-white bg-[#f6f8fa] flex items-center justify-center text-[8px] font-bold text-[#636c76]">
                              +{(project.members?.length || 0) - 3}
                            </div>
                          )}
                        </div>
                        <span className="text-[10px] text-[#636c76] font-medium">
                          {project.members?.length || 0} {t('common.members').toLowerCase()}
                        </span>
                      </div>
                      
                      {project.git_url && (
                        <div className="flex items-center gap-1 text-[9px] font-bold text-[#1f883d] bg-[#dafbe1] px-1.5 py-0.5 rounded-full border border-[#1a7f3720]">
                          <Globe size={10} />
                          <span>
                            {project.git_url.includes('github.com') ? 'GitHub' : 
                             project.git_url.includes('gitlab.com') ? 'GitLab' : 
                             project.git_url.includes('bitbucket.org') ? 'Bitbucket' : 'Git'}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              
              {canCreate && (
                <button 
                  onClick={onCreateProject}
                  className="p-5 border-2 border-dashed border-[#d0d7de] rounded-xl flex flex-col items-center justify-center gap-3 text-[#636c76] hover:bg-[#f0f7ff] hover:border-[#0969da] hover:text-[#0969da] transition-all min-h-[180px]"
                >
                  <div className="w-12 h-12 rounded-full bg-[#f6f8fa] group-hover:bg-white flex items-center justify-center border border-[#d0d7de]">
                    <Plus size={24} />
                  </div>
                  <span className="text-sm font-bold">{t('projects.create_new_workspace')}</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Resizer */}
      {collapsedPanel !== 'projects' && collapsedPanel !== 'tasks' && (
        <div
          onMouseDown={startResizing}
          className={`w-1 cursor-col-resize hover:bg-blue-400 transition-colors z-10 shrink-0 ${isResizing ? 'bg-blue-500' : 'bg-transparent'}`}
        />
      )}

      {/* My Tasks Panel */}
      <div
        style={panelStyle('tasks')}
        className="flex flex-col border-r border-[#d0d7de] bg-white transition-[flex] duration-300 relative overflow-hidden"
      >
        <div className="p-4 flex items-center justify-between border-b border-[#d0d7de] bg-[#f6f8fa] shrink-0 min-h-[64px]">
          {collapsedPanel === 'tasks' ? (
            <div className="flex flex-col items-center gap-3 w-full">
              <CheckSquare size={18} className="text-[#636c76]" />
              <button
                onClick={() => togglePanel('tasks')}
                title={t('dashboard.tasks_panel')}
                className="p-1 text-[#636c76] hover:bg-gray-200 rounded-md transition"
              >
                <ChevronLeft size={18} />
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => togglePanel('tasks')}
                  title={t('dashboard.collapse')}
                  className="p-1.5 text-[#636c76] hover:bg-gray-200 rounded-md transition"
                >
                  <ChevronRight size={18} />
                </button>
                <h2 className="font-bold text-[#1f2328] truncate">{t('dashboard.tasks_panel')}</h2>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1 bg-white border border-[#d0d7de] rounded-md px-2 py-1 shadow-sm">
                  <Filter size={12} className="text-[#636c76]" />
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as SortOption)}
                    className="text-[10px] font-bold text-[#1f2328] outline-none bg-transparent"
                  >
                    <option value="deadline">{t('dashboard.sort.deadline')}</option>
                    <option value="priority">{t('dashboard.sort.priority')}</option>
                    <option value="status">{t('dashboard.sort.status')}</option>
                    <option value="newest">{t('dashboard.sort.newest')}</option>
                  </select>
                </div>
              </div>
            </>
          )}
        </div>

        {collapsedPanel !== 'tasks' && (
          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#f6f8fa]/50">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#636c76]" size={14} />
              <input 
                type="text"
                placeholder={t('dashboard.filter_tasks')}
                value={taskSearch}
                onChange={(e) => setTaskSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-white border border-[#d0d7de] rounded-md text-xs outline-none focus:ring-2 focus:ring-blue-500 transition-all shadow-sm"
              />
            </div>

            <div className="space-y-3">
              {filteredTasks && filteredTasks.length > 0 ? (
                filteredTasks.map(task => (
                  <div 
                    key={task.id}
                    onClick={() => navigateToTask(task.project_id, task.id)}
                    className={`p-4 bg-white border border-[#d0d7de] rounded-lg hover:border-[#0969da] hover:shadow-md transition-all cursor-pointer group border-l-4 ${
                      task.priority === 3 ? 'border-l-red-500' : task.priority === 2 ? 'border-l-amber-500' : 'border-l-blue-400'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex flex-col">
                        <span className="text-[10px] font-mono text-[#636c76] mb-1">#{task.id}</span>
                        <h3 className="text-sm font-bold text-[#1f2328] group-hover:text-[#0969da] transition-colors">{task.title}</h3>
                      </div>
                      <div className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border ${
                        task.priority === 3 ? 'bg-red-50 text-red-700 border-red-100' :
                        task.priority === 2 ? 'bg-amber-50 text-amber-700 border-amber-100' :
                        'bg-blue-50 text-blue-700 border-blue-100'
                      }`}>
                        {task.priority === 3 ? t('tasks.high') : task.priority === 2 ? t('tasks.medium') : t('tasks.low')}
                      </div>
                    </div>

                    {task.description && (
                      <p className="text-xs text-[#636c76] line-clamp-2 mb-3 leading-relaxed">{task.description}</p>
                    )}

                    <div className="flex flex-wrap gap-3 mt-auto pt-3 border-t border-[#f0f2f4]">
                      {task.due_date && (
                        <div className={`flex items-center gap-1 text-[10px] font-bold ${
                          new Date(task.due_date) < new Date() ? 'text-red-600' : 'text-[#636c76]'
                        }`}>
                          <Clock size={12} />
                          <span>{new Date(task.due_date).toLocaleDateString()}</span>
                        </div>
                      )}
                      
                      <div className="flex items-center gap-1 text-[10px] text-[#636c76] font-bold">
                        <Tag size={12} />
                        <span>Project ID: {task.project_id}</span>
                      </div>

                      <div className="flex items-center gap-3 ml-auto">
                        {task.subtasks?.length > 0 && (
                          <div className="flex items-center gap-1 text-[10px] text-[#636c76] font-bold">
                            <CheckSquare size={12} />
                            <span>{task.subtasks.filter(s => s.is_completed).length}/{task.subtasks.length}</span>
                          </div>
                        )}
                        {task.comments?.length > 0 && (
                          <div className="flex items-center gap-1 text-[10px] text-[#636c76] font-bold">
                            <MessageSquare size={12} />
                            <span>{task.comments.length}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-12 bg-white border border-dashed border-[#d0d7de] rounded-lg">
                  <CheckSquare size={48} className="mx-auto text-[#d0d7de] mb-4 opacity-20" />
                  <p className="text-sm text-[#636c76]">{t('tasks.no_tasks') || 'No tasks assigned to you'}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Notifications Panel */}
      <div
        style={panelStyle('notifications')}
        className="flex flex-col bg-white transition-[flex] duration-300 relative overflow-hidden"
      >
        <div className="p-4 flex items-center justify-between border-b border-[#d0d7de] bg-[#f6f8fa] shrink-0 min-h-[64px]">
          {collapsedPanel === 'notifications' ? (
            <div className="flex flex-col items-center gap-3 w-full">
              <Bell size={18} className="text-[#636c76]" />
              <button
                onClick={() => togglePanel('notifications')}
                title={t('dashboard.notifications_panel')}
                className="p-1 text-[#636c76] hover:bg-gray-200 rounded-md transition"
              >
                <ChevronLeft size={18} />
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 min-w-0">
                <h2 className="font-bold text-[#1f2328] truncate">{t('dashboard.notifications_panel')}</h2>
                {unreadCount > 0 && (
                  <span className="px-1.5 py-0.5 bg-red-500 text-white text-[10px] font-bold rounded-full shrink-0">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </div>

              <button
                onClick={() => togglePanel('notifications')}
                title={t('dashboard.collapse')}
                className="p-1.5 text-[#636c76] hover:bg-gray-200 rounded-md transition shrink-0"
              >
                <ChevronRight size={18} />
              </button>
            </>
          )}
        </div>

        {collapsedPanel !== 'notifications' && (
          <div className="flex-1 overflow-y-auto bg-white">
            {notificationsLoading ? (
              <div className="p-8 text-center">
                <Loader2 className="animate-spin mx-auto text-gray-400" size={24} />
              </div>
            ) : notificationsList.length === 0 ? (
              <div className="text-center py-12 mx-4 mt-4 border border-dashed border-[#d0d7de] rounded-lg">
                <Inbox size={48} className="mx-auto text-[#d0d7de] mb-4 opacity-20" />
                <p className="text-sm text-[#636c76]">{t('dashboard.no_notifications')}</p>
              </div>
            ) : (
              notificationsList.map((n) => <NotificationItem key={n.id} notification={n} />)
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default DashboardSelection;
