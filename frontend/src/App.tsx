import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Routes, Route, Navigate, useNavigate, useParams, Link, useLocation } from 'react-router-dom'
import { 
  Layout, 
  Plus, 
  Loader2, 
  X, 
  Sparkles, 
  MoreHorizontal, 
  Circle, 
  CheckCircle2, 
  ShieldCheck,
  Clock, 
  GitBranch,
  Settings,
  MessageSquare,
  LogOut,
  Trash2,
  Edit2,
  ChevronDown,
  CheckSquare,
  Calendar,
  Grid,
  User as UserIcon,
  Users,
  List as ListIcon,
  Map as MapIcon,
  Pencil,
  Check,
  HelpCircle
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useBoard, useTasks } from './hooks/useBoard'
import api from './api/client'
import { Task, Project, Column } from './types'
import { projectBackgroundStyle } from './background'
import GlobalSearch from './components/GlobalSearch'
import TaskFilterButton from './components/TaskFilter'
import { EMPTY_FILTERS, TaskFilters, filterTasks } from './taskFilters'
import {
  TASK_TYPES,
  TASK_TYPE_STYLE,
  selectedTaskTypeClass,
  type TaskType,
} from './types/taskType'
import { useAuth } from './context/AuthContext'
import Login from './components/Auth/Login'
import Register from './components/Auth/Register'
import ProtectedRoute from './components/Auth/ProtectedRoute'
import TaskDetailModal from './components/TaskDetailModal'
import DashboardSelection from './components/DashboardSelection'
import Profile from './components/Profile'
import ProjectMembersModal from './components/ProjectMembersModal'
import ProjectRulesModal from './components/ProjectRulesModal'
import ProjectSettingsModal from './components/ProjectSettingsModal'
import RepoConnectWizard from './components/RepoConnectWizard'
import TaskListView from './components/TaskListView'
import RoadmapView from './components/RoadmapView'
import ProjectActivityView from './components/ProjectActivityView'
import GraphView from './components/GraphView'

import AdminRoute from './components/Auth/AdminRoute'
import AdminPanel from './pages/Admin/AdminPanel'
import UsersPage from './pages/Admin/UsersPage'
import RolesPage from './pages/Admin/RolesPage'
import ProjectsPage from './pages/Admin/ProjectsPage'
import NeuralModelsPage from './pages/Admin/NeuralModelsPage'
import StoragePage from './pages/Admin/StoragePage'
import HelpPage from './pages/HelpPage'
import NotificationsBell from './components/NotificationsBell'

import { 
  DndContext, 
  closestCorners, 
  KeyboardSensor, 
  PointerSensor, 
  useSensor, 
  useSensors,
  DragOverlay,
  defaultDropAnimationSideEffects
} from '@dnd-kit/core';
import { 
  arrayMove, 
  SortableContext, 
  sortableKeyboardCoordinates, 
  verticalListSortingStrategy,
  useSortable
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

type StateCategory = 'TODO' | 'IN_PROGRESS' | 'DONE';
type DashboardView = 'board' | 'list' | 'roadmap' | 'activity' | 'graph';

function Header({ currentProject }: { currentProject?: Project }) {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const location = useLocation()

  // Последняя крошка раньше была жёстко задана разделом «пользователи»
  // для всех страниц админки, поэтому в «ролях» или «моделях» она
  // показывала чужое название. Берём раздел из адреса и сопоставляем
  // с ключом перевода; неизвестный адрес подпись не добавляет.
  const ADMIN_SECTIONS: Record<string, string> = {
    users: 'admin.users_management',
    roles: 'admin.roles_management',
    projects: 'admin.projects_management',
    models: 'admin.models_management',
    storage: 'admin.storage_management',
  }
  const adminSection = user?.is_superuser
    ? ADMIN_SECTIONS[location.pathname.split('/')[2] ?? '']
    : undefined

  return (
    <header className="bg-[#1f2328] text-white px-6 py-3 flex items-center justify-between border-b border-[#30363d] shrink-0">
      <div className="flex items-center gap-4">
        <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition">
          <img src="/logo.png" alt="" className="h-7 w-7" />
          <span className="text-sm font-semibold">Kipatik</span>
        </Link>
        <span className="opacity-50 text-sm">/</span>
        <Link to={user?.is_superuser ? "/admin" : "/dashboard"} className="text-sm font-semibold opacity-70 hover:opacity-100 hover:underline">
          {user?.is_superuser ? t('admin.title') : t('common.dashboard')}
        </Link>
        {adminSection && (
          <>
            <span className="opacity-50 text-sm">/</span>
            <Link
              to={`/admin/${location.pathname.split('/')[2]}`}
              className="text-sm font-semibold text-orange-400 hover:text-orange-300"
            >
              {t(adminSection)}
            </Link>
          </>
        )}
        {currentProject && (
          <>
            <span className="opacity-50 text-sm">/</span>
            <span className="text-sm font-semibold cursor-default text-blue-400">
              {currentProject.name}
            </span>
          </>
        )}
      </div>
      
      <div className="flex items-center gap-3">
        <GlobalSearch />

        {/* Справка. Открывается в новой вкладке: чтение руководства
            не должно уводить с доски, на которой человек работал.
            Маршрут тот же, что и раньше, — новая вкладка просто
            не трогает текущую. */}
        <a
          href="/help"
          target="_blank"
          rel="noopener noreferrer"
          title={t('help.title')}
          className="flex items-center gap-1 px-2 py-1 text-xs font-semibold text-gray-300 hover:text-white hover:bg-[#30363d] rounded-md transition"
        >
          <HelpCircle size={14} />
          <span className="hidden lg:inline">{t('help.link')}</span>
        </a>

        <div className="flex items-center gap-2 ml-2 border-l border-[#30363d] pl-4">
          <NotificationsBell />
          <Link to="/profile" className="flex items-center gap-2 hover:bg-[#30363d] p-1 rounded-md transition group">
            <div className="flex flex-col items-end mr-1">
              <span className="text-[11px] font-bold text-white leading-none group-hover:text-blue-400 transition">{user?.full_name || 'User'}</span>
              <span className="text-[9px] text-gray-400 leading-none mt-1">{user?.email}</span>
            </div>
            <div className="w-8 h-8 rounded-full border border-[#30363d] overflow-hidden bg-gradient-to-tr from-gray-700 to-gray-600 flex items-center justify-center">
              {user?.avatar_url ? (
                <img src={user.avatar_url} alt="Avatar" className="w-full h-full object-cover" />
              ) : (
                <UserIcon size={14} className="text-gray-300" />
              )}
            </div>
          </Link>
          <button onClick={logout} className="p-1.5 hover:bg-[#30363d] rounded-md text-gray-400 hover:text-white transition" title={t('common.logout')}>
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
  )
}

function Dashboard() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const { user } = useAuth()
  const activeProjectId = projectId ? Number(projectId) : null
  
  const { data: projects, isLoading: projectsLoading, refetch: refetchProjects } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: async () => {
      const { data } = await api.get('/projects/')
      return data
    }
  })

  const { data: board, isLoading: boardLoading, refetch: refetchBoard } = useBoard(activeProjectId || 0)
  const { data: tasks, isLoading: tasksLoading, refetch: refetchTasks } = useTasks(activeProjectId || 0)
  
  const [activeView, setActiveView] = useState<DashboardView>('board')
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false)
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false)
  const [isMembersModalOpen, setIsMembersModalOpen] = useState(false)
  const [isProjectSettingsOpen, setIsProjectSettingsOpen] = useState(false)
  const [isRulesModalOpen, setIsRulesModalOpen] = useState(false)
  const [isColumnModalOpen, setIsColumnModalOpen] = useState<{ isOpen: boolean, category?: StateCategory, column?: Column }>({ isOpen: false })
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null)
  const [activeColumnId, setActiveColumnId] = useState<number | null>(null)
  
  const [activeDragId, setActiveDragId] = useState<number | null>(null);

  // Фильтр задач. Пустые массивы означают «любой признак», поэтому
  // изначально видно всё, а состояние по умолчанию не надо сбрасывать.
  const [filters, setFilters] = useState<TaskFilters>(EMPTY_FILTERS);
  const visibleTasks = useMemo(
    () => filterTasks(tasks, filters),
    [tasks, filters],
  );

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 5,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragStart = (event: any) => {
    setActiveDragId(event.active.id);
  };

  const handleDragEnd = async (event: any) => {
    const { active, over } = event;
    setActiveDragId(null);

    if (!over) return;

    const taskId = active.id;
    const overId = over.id;

    let newColumnId: number | null = null;

    if (typeof overId === 'string' && overId.startsWith('col-')) {
      newColumnId = Number(overId.replace('col-', ''));
    } else {
      const overTask = tasks?.find(t => t.id === overId);
      if (overTask) {
        newColumnId = overTask.column_id;
      }
    }

    const task = tasks?.find(t => t.id === taskId);
    if (task && newColumnId && task.column_id !== newColumnId) {
      try {
        await api.patch(`/tasks/${taskId}`, { column_id: newColumnId });
        refetchTasks();
      } catch (err) {
        alert(t('tasks.update_error'));
      }
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const taskId = params.get('taskId');
    if (taskId) {
      setSelectedTaskId(Number(taskId));
    }
  }, [location.search]);
  
  const isLoading = projectsLoading || (activeProjectId ? (boardLoading || tasksLoading) : false)
  const hasProject = projects && projects.length > 0
  const currentProject = projects?.find(p => p.id === activeProjectId)

  // Фон страницы проекта. Общий для всех участников: хранится в
  // проекте, а не в браузере, поэтому смена сразу видна всем.
  const backgroundStyle = useMemo(
    () => projectBackgroundStyle(currentProject?.background, currentProject?.background_url),
    [currentProject?.background, currentProject?.background_url],
  );

  // Название проекта прямо в заголовке.
  //
  // Право на правку то же, что и в окне настроек проекта: владелец или
  // суперюзер. Иначе заголовок и окно настроек разрешали бы разное, и
  // непонятно было бы, где именно можно переименовать проект.
  const canRenameProject = Boolean(
    currentProject && (user?.id === currentProject.owner_id || user?.is_superuser),
  );
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);
  const [savingName, setSavingName] = useState(false);

  const startRename = () => {
    if (!currentProject || !canRenameProject) return;
    setNameDraft(currentProject.name);
    setNameError(null);
    setEditingName(true);
  };

  const saveName = async () => {
    const next = nameDraft.trim();
    if (!currentProject) return;
    if (!next) {
      setNameError(t('projects.name_empty'));
      return;
    }
    if (next === currentProject.name) {
      setEditingName(false);
      return;
    }
    setSavingName(true);
    setNameError(null);
    try {
      await api.patch(`/projects/${currentProject.id}`, { name: next });
      await refetchProjects();
      setEditingName(false);
    } catch (err: any) {
      setNameError(err.response?.data?.detail || t('projects.update_error'));
    } finally {
      setSavingName(false);
    }
  };

  const openCreateTask = (columnId?: number) => {
    setActiveColumnId(columnId || (board?.columns[0]?.id || null));
    setIsTaskModalOpen(true);
  };

  const groupedColumns = useMemo(() => {
    if (!board) return { TODO: [], IN_PROGRESS: [], DONE: [] };
    const groups = {
      TODO: board.columns.filter(c => c.state_category === 'TODO').sort((a, b) => a.position - b.position),
      IN_PROGRESS: board.columns.filter(c => c.state_category === 'IN_PROGRESS').sort((a, b) => a.position - b.position),
      DONE: board.columns.filter(c => c.state_category === 'DONE').sort((a, b) => a.position - b.position),
    };
    return groups;
  }, [board]);

  const handleDeleteColumn = async (id: number) => {
    if (!window.confirm(t('columns.delete_confirm'))) return;
    try {
      await api.delete(`/boards/columns/${id}`);
      refetchBoard();
    } catch (err) {
      alert(t('columns.delete_error'));
    }
  };

  const projectMembers = useQuery({
    queryKey: ['members', activeProjectId],
    queryFn: async () => {
      const { data } = await api.get(`/projects/${activeProjectId}/members`);
      return data;
    },
    enabled: !!activeProjectId
  });

  const handleAddDependency = async (taskId: number, dependsOnId: number) => {
    const task = tasks?.find(t => t.id === taskId);
    if (!task) return;
    
    const newDependencies = [...(task.dependencies || []), dependsOnId];
    try {
      await api.patch(`/tasks/${taskId}`, { dependency_ids: newDependencies });
      refetchTasks();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Error adding dependency');
    }
  };

  if (!activeProjectId && hasProject && !projectsLoading) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
<div
      className="min-h-screen flex flex-col overflow-hidden bg-[#f6f8fa]"
      style={backgroundStyle}
    >
      <Header currentProject={currentProject} />

      <div className="bg-white border-b border-[#d0d7de] px-6 flex flex-col shrink-0 shadow-sm">
        <div className="py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
               <Layout size={18} className="text-[#636c76] shrink-0" />
               {editingName ? (
                 <div className="flex items-center gap-1.5">
                   <input
                     autoFocus
                     value={nameDraft}
                     onChange={(e) => setNameDraft(e.target.value)}
                     onKeyDown={(e) => {
                       if (e.key === 'Enter') saveName();
                       if (e.key === 'Escape') setEditingName(false);
                     }}
                     className="px-2 py-0.5 bg-white border border-[#0969da] rounded text-lg font-semibold text-[#1f2328] outline-none ring-1 ring-[#0969da] min-w-[240px] max-w-[420px]"
                   />
                   <button
                     onClick={saveName}
                     disabled={savingName}
                     className="p-1 bg-[#1f883d] text-white rounded hover:bg-[#1a7f37] disabled:opacity-50"
                     title={t('common.save')}
                   >
                     {savingName
                       ? <Loader2 size={13} className="animate-spin" />
                       : <Check size={13} />}
                   </button>
                   <button
                     onClick={() => setEditingName(false)}
                     className="p-1 bg-[#f6f8fa] border border-[#d0d7de] text-[#636c76] rounded hover:bg-[#ebf0f4]"
                     title={t('common.cancel')}
                   >
                     <X size={13} />
                   </button>
                 </div>
               ) : (
                 <h1
                   onClick={startRename}
                   title={canRenameProject ? t('projects.rename_hint') : undefined}
                   className={`text-lg font-semibold text-[#1f2328] truncate ${
                     canRenameProject
                       ? 'cursor-text hover:bg-[#f6f8fa] rounded px-1 -mx-1'
                       : 'cursor-default'
                   }`}
                 >
                   {currentProject?.name || t('dashboard.kanban_board')}
                 </h1>
               )}
               {canRenameProject && !editingName && (
                 <button
                   onClick={startRename}
                   title={t('projects.rename_hint')}
                   className="p-1 text-[#636c76] hover:text-[#1f2328] hover:bg-[#f6f8fa] rounded"
                 >
                   <Pencil size={13} />
                 </button>
               )}
            </div>
            {nameError && (
              <span className="text-[11px] text-red-700">{nameError}</span>
            )}
            <div className="h-4 w-[1px] bg-gray-200"></div>
            <TaskFilterButton
              filters={filters}
              onChange={setFilters}
              members={projectMembers.data || []}
              shown={visibleTasks?.length || 0}
              total={tasks?.length || 0}
            />
          </div>
          
          <div className="flex items-center gap-2">
             {currentProject && ['project_manager', 'manager'].includes(currentProject.user_role || '') && (
               <button onClick={() => setIsRulesModalOpen(true)} className="px-3 py-1.5 bg-[#f6f8fa] border border-[#d0d7de] text-[#1f2328] rounded-md hover:bg-[#ebf0f4] transition font-semibold text-xs flex items-center gap-2 shadow-sm">
                 <ShieldCheck size={14} className="text-blue-600" />
                 {t('projects.rules.title')}
               </button>
             )}
             <button onClick={() => setIsMembersModalOpen(true)} disabled={!activeProjectId} className="px-3 py-1.5 bg-[#f6f8fa] border border-[#d0d7de] text-[#1f2328] rounded-md hover:bg-[#ebf0f4] transition font-semibold text-xs flex items-center gap-2 shadow-sm disabled:opacity-50">
              <Users size={14} />
              {t('common.members')}
            </button>
            <button onClick={() => setIsProjectSettingsOpen(true)} disabled={!activeProjectId} className="px-3 py-1.5 bg-[#f6f8fa] border border-[#d0d7de] text-[#1f2328] rounded-md hover:bg-[#ebf0f4] transition font-semibold text-xs flex items-center gap-2 shadow-sm disabled:opacity-50">
              <Settings size={14} />
              {t('common.settings')}
            </button>
             <button onClick={() => navigate('/dashboard')} className="px-3 py-1.5 bg-[#f6f8fa] border border-[#d0d7de] text-[#1f2328] rounded-md hover:bg-[#ebf0f4] transition font-semibold text-xs flex items-center gap-2 shadow-sm">
              <Grid size={14} />
              {t('dashboard.switch_project')}
            </button>
            <button 
              onClick={() => openCreateTask()}
              disabled={!hasProject || board?.columns.length === 0}
              className="px-3 py-1.5 bg-[#1f883d] text-white border border-[#1a7f37] rounded-md hover:bg-[#1a7f37] transition font-semibold text-xs flex items-center gap-1 shadow-sm disabled:opacity-50"
            >
              <Plus size={14} />
              {t('dashboard.new_task')}
            </button>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex gap-4">
           <button 
            onClick={() => setActiveView('board')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${activeView === 'board' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}
           >
             <Grid size={16} />
             {t('dashboard.views.board')}
           </button>
           <button 
            onClick={() => setActiveView('list')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${activeView === 'list' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}
           >
             <ListIcon size={16} />
             {t('dashboard.views.list')}
           </button>
           <button 
            onClick={() => setActiveView('roadmap')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${activeView === 'roadmap' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}
           >
             <MapIcon size={16} />
             {t('dashboard.views.roadmap')}
           </button>
           <button 
            onClick={() => setActiveView('graph')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${activeView === 'graph' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}
           >
             <GitBranch size={16} />
             {t('dashboard.views.graph')}
           </button>
           <button 
            onClick={() => setActiveView('activity')}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${activeView === 'activity' ? 'border-[#fd8c73] text-[#1f2328]' : 'border-transparent text-[#636c76] hover:text-[#1f2328]'}`}
           >
             <Clock size={16} />
             {t('tasks.tabs.history')}
           </button>
        </div>
      </div>

      <main className="flex-1 overflow-x-auto overflow-y-hidden p-6 flex flex-col">
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center"><Loader2 className="animate-spin text-blue-500" size={32} /></div>
        ) : !hasProject ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
             <Layout size={64} className="text-[#d0d7de] mb-4" />
             <h2 className="text-xl font-semibold mb-2 text-gray-800">{t('common.welcome')}</h2>
             <p className="text-[#636c76] mb-6 max-w-xs text-sm">Create your first project to start tracking tasks.</p>
             <button onClick={() => setIsProjectModalOpen(true)} className="bg-[#1f883d] text-white px-8 py-2 rounded-md font-semibold text-sm hover:bg-[#1a7f37] shadow-lg">{t('projects.create_first')}</button>
          </div>
        ) : !activeProjectId ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
             <Grid size={64} className="text-[#d0d7de] mb-4" />
             <h2 className="text-xl font-semibold mb-2 text-gray-800">{t('common.no_project_selected')}</h2>
             <p className="text-[#636c76] mb-6 max-w-xs text-sm">{t('common.select_project_hint')}</p>
             <button onClick={() => navigate('/projects')} className="bg-[#0969da] text-white px-8 py-2 rounded-md font-semibold text-sm hover:bg-[#0861c5] shadow-lg">{t('dashboard.go_to_projects')}</button>
          </div>
        ) : (
          <>
            {activeView === 'board' && (
              <DndContext 
                sensors={sensors}
                collisionDetection={closestCorners}
                onDragStart={handleDragStart}
                onDragEnd={handleDragEnd}
              >
                <div className="flex gap-6 h-full overflow-x-auto min-w-max pb-4">
                  {(['TODO', 'IN_PROGRESS', 'DONE'] as StateCategory[]).map((cat) => (
                    <section key={cat} className="flex flex-col gap-4 min-w-[280px] bg-[#f1f3f5]/50 p-3 rounded-lg border border-[#d0d7de]/40">
                      <div className="flex items-center justify-between border-b-2 border-[#d0d7de] pb-2">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${cat === 'TODO' ? 'bg-gray-400' : cat === 'IN_PROGRESS' ? 'bg-amber-500' : 'bg-green-500'}`} />
                          <h2 className="text-[11px] font-bold text-[#636c76] uppercase tracking-wider">{cat.replace('_', ' ')}</h2>
                          <span className="text-[10px] bg-white px-1.5 py-0.5 rounded-full border border-[#d0d7de] text-[#636c76] font-bold">
                            {groupedColumns[cat].reduce((acc, col) => acc + (visibleTasks?.filter(t => t.column_id === col.id).length || 0), 0)}
                          </span>
                        </div>
                        <button 
                          onClick={() => setIsColumnModalOpen({ isOpen: true, category: cat })}
                          className="p-1 hover:bg-white rounded text-[#636c76] transition shadow-sm"
                          title={t('dashboard.add_column')}
                        >
                          <Plus size={14} />
                        </button>
                      </div>

                      <div className="flex gap-3 items-start h-full">
                        {groupedColumns[cat].map((column) => (
                          <DroppableColumn 
                            key={column.id} 
                            column={column} 
                            tasks={visibleTasks?.filter(t => t.column_id === column.id) || []}
                            onTaskClick={setSelectedTaskId}
                            onAddTask={() => openCreateTask(column.id)}
                            onEditColumn={() => setIsColumnModalOpen({ isOpen: true, category: cat, column })}
                            onDeleteColumn={() => handleDeleteColumn(column.id)}
                            t={t}
                          />
                        ))}
                        {groupedColumns[cat].length === 0 && (
                          <div className="w-[240px] border-2 border-dashed border-[#d0d7de] rounded-md p-4 flex flex-col items-center justify-center text-center opacity-40">
                             <span className="text-[10px] font-medium text-[#636c76]">{t('dashboard.empty')}</span>
                          </div>
                        )}
                      </div>
                    </section>
                  ))}
                </div>
                <DragOverlay>
                  {activeDragId ? (
                    <div className="scale-105 rotate-2">
                       <TaskCard task={tasks?.find(t => t.id === activeDragId)!} onClick={() => {}} isOverlay />
                    </div>
                  ) : null}
                </DragOverlay>
              </DndContext>
            )}

            {activeView === 'list' && board && visibleTasks && (
              <TaskListView 
                tasks={visibleTasks} 
                columns={board.columns} 
                members={projectMembers.data || []} 
                onTaskClick={setSelectedTaskId} 
              />
            )}

            {activeView === 'roadmap' && board && visibleTasks && (
              <RoadmapView 
                tasks={visibleTasks} 
                columns={board.columns} 
                members={projectMembers.data || []} 
                onTaskClick={setSelectedTaskId} 
              />
            )}

            {activeView === 'activity' && activeProjectId && (
              <ProjectActivityView 
                projectId={activeProjectId} 
                onTaskClick={setSelectedTaskId}
              />
            )}

            {activeView === 'graph' && visibleTasks && (
              <GraphView 
                tasks={visibleTasks} 
                onTaskClick={setSelectedTaskId}
                onAddDependency={handleAddDependency}
              />
            )}
          </>
        )}
      </main>

      {/* Modals */}
      {isTaskModalOpen && activeProjectId && board && (
        <CreateTaskModal 
          onClose={() => setIsTaskModalOpen(false)} 
          projectId={activeProjectId} 
          project={currentProject}
          columns={board.columns}
          initialColumnId={activeColumnId}
          onCreated={refetchTasks}
        />
      )}
      
      {isProjectModalOpen && (
        <CreateProjectModal 
          onClose={() => setIsProjectModalOpen(false)} 
          onCreated={() => { refetchProjects(); refetchBoard(); }}
        />
      )}

      {isMembersModalOpen && activeProjectId && currentProject && (
        <ProjectMembersModal 
          projectId={activeProjectId}
          project={currentProject}
          onClose={() => setIsMembersModalOpen(false)}
        />
      )}

      {isProjectSettingsOpen && activeProjectId && currentProject && (
        <ProjectSettingsModal 
          project={currentProject}
          onClose={() => setIsProjectSettingsOpen(false)}
          onUpdated={() => { refetchProjects(); refetchBoard(); }}
        />
      )}

      {isRulesModalOpen && activeProjectId && currentProject && board && (
        <ProjectRulesModal
          project={currentProject}
          columns={board.columns}
          onClose={() => setIsRulesModalOpen(false)}
          onUpdated={() => { refetchProjects(); }}
        />
      )}

      {isColumnModalOpen.isOpen && isColumnModalOpen.category && activeProjectId && board && (
        <ManageColumnModal 
          onClose={() => setIsColumnModalOpen({ isOpen: false })}
          boardId={board.id}
          category={isColumnModalOpen.category}
          column={isColumnModalOpen.column}
          onSaved={refetchBoard}
        />
      )}

      {selectedTaskId && board && (
        <TaskDetailModal 
          taskId={selectedTaskId}
          columns={board.columns}
          onClose={() => setSelectedTaskId(null)}
          onUpdated={() => { refetchTasks(); }}
        />
      )}
    </div>
  )
}

function DroppableColumn({ column, tasks, onTaskClick, onAddTask, onEditColumn, onDeleteColumn, t }: any) {
  return (
    <div className="w-[240px] flex flex-col max-h-full bg-[#ebedf0] rounded-md border border-[#d0d7de] p-2 shadow-sm">
      <div className="flex items-center justify-between mb-2 px-1">
        <div className="flex items-center gap-2 group">
            <h3 className="text-[11px] font-bold text-[#1f2328] truncate max-w-[160px]">{column.name}</h3>
            <button onClick={onEditColumn} className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-white rounded text-gray-400 transition shadow-sm">
              <Edit2 size={10} />
            </button>
        </div>
        <button onClick={onDeleteColumn} className="text-[#636c76] hover:text-red-600 p-1 rounded-md transition hover:bg-white shadow-sm">
          <Trash2 size={12} />
        </button>
      </div>
      
      <ColumnContent columnId={column.id} tasks={tasks} onTaskClick={onTaskClick} />
      
      <button 
        onClick={onAddTask}
        className="mt-2 flex items-center gap-2 w-full p-2 text-[#636c76] hover:bg-white rounded-md transition text-[10px] font-bold border border-transparent hover:border-[#d0d7de] shadow-sm"
      >
        <Plus size={12} /> {t('tasks.add_task')}
      </button>
    </div>
  );
}

function ColumnContent({ columnId, tasks, onTaskClick }: any) {
  const { setNodeRef } = useSortable({
    id: `col-${columnId}`,
  });

  return (
    <div 
      ref={setNodeRef}
      className="flex-1 flex flex-col gap-2 overflow-y-auto min-h-[100px] max-h-[calc(100vh-250px)] scrollbar-thin pb-4"
    >
      <SortableContext items={tasks.map((t: any) => t.id)} strategy={verticalListSortingStrategy}>
        {tasks.map((task: any) => (
          <SortableTaskCard key={task.id} task={task} onClick={() => onTaskClick(task.id)} />
        ))}
      </SortableContext>
    </div>
  );
}

function SortableTaskCard({ task, onClick }: any) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging
  } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0 : 1
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <TaskCard task={task} onClick={onClick} />
    </div>
  );
}

function TaskCard({ task, onClick, isOverlay }: { task: Task, onClick: () => void, isOverlay?: boolean }) {
  const { t } = useTranslation()
  const getPriorityBorder = (p: number) => {
    if (p >= 3) return 'border-l-[4px] border-l-red-500'
    if (p === 2) return 'border-l-[4px] border-l-amber-500'
    return 'border-l-[4px] border-l-blue-400'
  }

  const completedSubtasks = task.subtasks.filter(s => s.is_completed).length;

  return (
    <div 
      onClick={onClick}
      className={`bg-white p-3 rounded-md border border-[#d0d7de] shadow-sm hover:shadow-md transition-all cursor-pointer group flex flex-col gap-2 ${getPriorityBorder(task.priority)} ${isOverlay ? 'shadow-xl border-blue-400 ring-2 ring-blue-100' : ''}`}
    >
      <div className="flex items-start justify-between">
        <h3 className="text-xs font-semibold text-[#1f2328] group-hover:text-[#0969da] leading-tight line-clamp-2">
          {task.title}
        </h3>
        <span className="text-[10px] text-[#636c76] font-medium opacity-0 group-hover:opacity-100 transition">#{task.id}</span>
      </div>
      
      {task.description && (
        <p className="text-[11px] text-[#636c76] line-clamp-1 leading-snug">
          {task.description}
        </p>
      )}

      <div className="flex flex-col gap-2 mt-1">
        <div className="flex items-center gap-2">
          {/* Тип задачи выбирает человек. Раньше здесь стояла заглушка
              «чётный id — Баг, нечётный — Фича»: подпись ничего не
              сообщала о задаче и просто чередовалась через раз. */}
          {task.task_type && TASK_TYPE_STYLE[task.task_type] && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full border font-semibold ${TASK_TYPE_STYLE[task.task_type].badge}`}
              title={t(`tasks.type_hint.${task.task_type}`)}
            >
              {t(`task_type.${task.task_type}`)}
            </span>
          )}
          {task.due_date && (
            <div className="flex items-center gap-1 text-[10px] text-red-600 font-bold bg-red-50 px-1.5 py-0.5 rounded-full border border-red-100">
              <Calendar size={10} />
              <span>{new Date(task.due_date).toLocaleDateString()}</span>
            </div>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {task.subtasks.length > 0 && (
            <div className={`flex items-center gap-1 text-[10px] font-bold ${completedSubtasks === task.subtasks.length ? 'text-[#1f883d]' : 'text-[#636c76]'}`}>
              <CheckSquare size={10} />
              <span>{completedSubtasks}/{task.subtasks.length}</span>
            </div>
          )}
          {task.comments.length > 0 && (
            <div className="flex items-center gap-1 text-[10px] text-[#636c76] font-bold ml-1">
              <MessageSquare size={10} />
              <span>{task.comments.length}</span>
            </div>
          )}
          {task.branches && task.branches.length > 0 && (
            <div className="flex items-center gap-1 text-[10px] text-[#0969da] font-bold ml-1">
              <GitBranch size={10} />
              <span>{task.branches.length}</span>
            </div>
          )}
        </div>

        {/* Progress bar if there is activity */}
        {(task.subtasks.length > 0 || (task.commits && task.commits.length > 0)) && (
          <div className="w-full bg-[#f6f8fa] h-1 rounded-full mt-1 overflow-hidden border border-[#d0d7de]/30">
             <div 
               className="bg-[#1f883d] h-full transition-all duration-500" 
               style={{ width: `${Math.round((completedSubtasks / (task.subtasks.length || 1)) * 100)}%` }}
             />
          </div>
        )}
      </div>
    </div>
  )
}

function ManageColumnModal({ onClose, boardId, category, column, onSaved }: any) {
  const { t } = useTranslation()
  const [name, setName] = useState(column?.name || '')
  const [loading, setLoading] = useState(false)

  const handleSave = async () => {
    setLoading(true)
    try {
      if (column) {
        await api.patch(`/boards/columns/${column.id}`, { name })
      } else {
        await api.post('/boards/columns', { name, board_id: boardId, state_category: category })
      }
      onSaved()
      onClose()
    } catch (err) {
      alert(t('columns.save_error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-md w-full max-w-xs shadow-xl border border-[#d0d7de]">
        <div className="px-4 py-3 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between rounded-t-md">
          <h2 className="text-sm font-semibold text-[#1f2328]">{column ? t('columns.edit_column') : t('columns.add_column')}</h2>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328]"><X size={16}/></button>
        </div>
        <div className="p-4">
          <label className="block text-xs font-semibold text-[#1f2328] mb-1">{t('columns.name')}</label>
          <input autoFocus value={name} onChange={e => setName(e.target.value)} className="w-full bg-white border border-[#d0d7de] rounded-md px-3 py-1.5 text-sm outline-none focus:border-blue-500" placeholder={t('columns.name_placeholder')} />
          <p className="text-[10px] text-gray-500 mt-2">{t('columns.state_hint', { category })}</p>
        </div>
        <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end gap-2 rounded-b-md">
           <button onClick={onClose} className="px-3 py-1.5 bg-white border border-[#d0d7de] text-[#1f2328] rounded-md text-xs font-semibold">{t('common.cancel')}</button>
           <button onClick={handleSave} disabled={!name || loading} className="px-3 py-1.5 bg-[#1f883d] text-white border border-[#1a7f37] rounded-md text-xs font-semibold hover:bg-[#1a7f37]">
            {loading ? <Loader2 className="animate-spin" size={14}/> : t('common.save')}
           </button>
        </div>
      </div>
    </div>
  )
}

function CreateTaskModal({ onClose, projectId, project, columns, initialColumnId, onCreated }: any) {
  const { t } = useTranslation()
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [columnId, setColumnId] = useState(initialColumnId || columns[0]?.id || '')
  const [dueDate, setDueDate] = useState('')
  const [startDate, setStartDate] = useState('')
  const [priority, setPriority] = useState(1)
    // Тип задачи выбирает человек: автоматического определения нет
    const [taskType, setTaskType] = useState<TaskType | ''>('')
  const [assigneeId, setAssigneeId] = useState<number | ''>('')
  const [subtasks, setSubtasks] = useState<{title: string, is_completed: boolean}[]>([])
  const [newSubtask, setNewSubtask] = useState('')
  const [loading, setLoading] = useState(false)
  const [aiAnalyzing, setAiAnalyzing] = useState(false)
  const [suggestions, setSuggestions] = useState<any>(null)

  const rules = project?.rules;

  useEffect(() => {
    if (initialColumnId) setColumnId(initialColumnId);
  }, [initialColumnId]);

  const handleAnalyze = async () => {
    if (!title) return
    setAiAnalyzing(true)
    try {
      const { data } = await api.post('/ai/analyze-task', { title, description: desc })
      setSuggestions(data)
      if (data.suggested_priority) setPriority(data.suggested_priority);
    } finally {
      setAiAnalyzing(false)
    }
  }

  const handleAddSubtask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubtask.trim()) return;
    setSubtasks([...subtasks, { title: newSubtask, is_completed: false }]);
    setNewSubtask('');
  };

  const handleCreate = async () => {
    // Validation based on rules
    if (rules?.required_fields.includes('description') && !desc) {
      alert(t('tasks.description') + ' is required'); return;
    }
    if (rules?.required_fields.includes('due_date') && !dueDate) {
      alert(t('tasks.due_date') + ' is required'); return;
    }
    if (rules?.required_fields.includes('assignee_id') && !assigneeId) {
      alert(t('tasks.assignee') + ' is required'); return;
    }

    setLoading(true)
    try {
      await api.post('/tasks/', { 
        title, 
        description: desc, 
        project_id: projectId, 
        column_id: columnId,
        due_date: dueDate || null,
        start_date: startDate || null,
        priority: priority,
        task_type: taskType || null,
        assignee_id: assigneeId || null,
        subtasks: subtasks
      })
      onCreated()
      onClose()
    } catch (err: any) {
      alert(err.response?.data?.detail || t('tasks.load_error'));
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-2xl shadow-2xl flex flex-col overflow-hidden max-h-[90vh]">
        <div className="px-6 py-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-blue-100 text-blue-600 rounded-md">
              <Plus size={18} />
            </div>
            <h2 className="text-lg font-bold text-[#1f2328]">{t('tasks.create_new')}</h2>
          </div>
          <button onClick={onClose} className="text-[#636c76] hover:bg-gray-200 p-1 rounded-full transition-colors"><X size={20}/></button>
        </div>
        
        <div className="p-6 space-y-6 overflow-y-auto">
          {/* Title */}
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.title')}*</label>
            <input 
              autoFocus
              value={title} 
              onChange={e => setTitle(e.target.value)}
              className="w-full bg-white border border-[#d0d7de] rounded-md px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 transition-all font-semibold"
              placeholder={t('tasks.title_placeholder')}
            />
          </div>

          {/* Description */}
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">
              {t('tasks.description')}{rules?.required_fields.includes('description') && '*'}
            </label>
            <textarea 
              value={desc} 
              onChange={e => setDesc(e.target.value)}
              rows={4}
              className="w-full bg-white border border-[#d0d7de] rounded-md px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 resize-none transition-all"
              placeholder={t('tasks.description_placeholder')}
            />
          </div>

          {/* Details Grid */}
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.column')}</label>
              <select 
                value={columnId} 
                onChange={e => setColumnId(Number(e.target.value))}
                className="w-full bg-[#f6f8fa] border border-[#d0d7de] rounded-md px-3 py-2 text-sm outline-none font-medium"
              >
                {columns.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">
                {t('tasks.assignee')}{rules?.required_fields.includes('assignee_id') && '*'}
              </label>
              <select 
                value={assigneeId} 
                onChange={e => setAssigneeId(e.target.value ? Number(e.target.value) : '')}
                className="w-full bg-[#f6f8fa] border border-[#d0d7de] rounded-md px-3 py-2 text-sm outline-none font-medium"
              >
                <option value="">{t('tasks.unassigned')}</option>
                {project?.members?.map(m => <option key={m.id} value={m.id}>{m.full_name || m.email}</option>)}
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.start_date')}</label>
              <input 
                type="datetime-local"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className="w-full bg-[#f6f8fa] border border-[#d0d7de] rounded-md px-3 py-2 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">
                {t('tasks.due_date')}{rules?.required_fields.includes('due_date') && '*'}
              </label>
              <input 
                type="datetime-local"
                value={dueDate}
                onChange={e => setDueDate(e.target.value)}
                className="w-full bg-[#f6f8fa] border border-[#d0d7de] rounded-md px-3 py-2 text-sm outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {/* Priority */}
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.type')}</label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setTaskType('')}
                className={`py-2 px-3 rounded-lg border text-xs font-bold transition-all ${
                  taskType === ''
                    ? 'bg-gray-100 border-[#d0d7de] text-[#1f2328] ring-1 ring-gray-200'
                    : 'bg-white border-[#d0d7de] text-[#636c76] hover:bg-gray-50'
                }`}
              >
                {t('tasks.type_none')}
              </button>
              {TASK_TYPES.map(k => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setTaskType(k)}
                  title={t(`tasks.type_hint.${k}`)}
                  className={`py-2 px-3 rounded-lg border text-xs font-bold transition-all flex items-center gap-2 ${
                    taskType === k
                      ? selectedTaskTypeClass(k)
                      : 'bg-white border-[#d0d7de] text-[#636c76] hover:bg-gray-50'
                  }`}
                >
                  <div className={`w-2 h-2 rounded-full ${TASK_TYPE_STYLE[k].dot}`} />
                  {t(`task_type.${k}`)}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.priority')}</label>
            <div className="flex gap-2">
              {[1, 2, 3].map(p => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPriority(p)}
                  className={`flex-1 py-2 px-3 rounded-lg border text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                    priority === p 
                      ? (p === 3 ? 'bg-red-50 border-red-200 text-red-700 ring-1 ring-red-100' : p === 2 ? 'bg-amber-50 border-amber-200 text-amber-700 ring-1 ring-amber-100' : 'bg-blue-50 border-blue-200 text-blue-700 ring-1 ring-blue-100')
                      : 'bg-white border-[#d0d7de] text-[#636c76] hover:bg-gray-50'
                  }`}
                >
                  <div className={`w-2 h-2 rounded-full ${p === 3 ? 'bg-red-500' : p === 2 ? 'bg-amber-500' : 'bg-blue-400'}`} />
                  {p === 3 ? t('tasks.high') : p === 2 ? t('tasks.medium') : t('tasks.low')}
                </button>
              ))}
            </div>
          </div>

          {/* Checklist */}
          <div className="space-y-3 pt-2 border-t border-[#d0d7de]">
            <label className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider">{t('tasks.checklist')}</label>
            <div className="space-y-2">
              {subtasks.map((st, idx) => (
                <div key={idx} className="flex items-center gap-2 bg-[#f6f8fa] p-2 rounded-md border border-[#d0d7de]">
                  <span className="text-xs flex-1 font-medium">{st.title}</span>
                  <button onClick={() => setSubtasks(subtasks.filter((_, i) => i !== idx))} className="text-gray-400 hover:text-red-500"><Trash2 size={14}/></button>
                </div>
              ))}
              <form onSubmit={handleAddSubtask} className="flex gap-2">
                <input 
                  value={newSubtask}
                  onChange={e => setNewSubtask(e.target.value)}
                  className="flex-1 bg-white border border-[#d0d7de] rounded-md px-3 py-1.5 text-xs outline-none focus:border-blue-500"
                  placeholder={t('tasks.add_subtask')}
                />
                <button type="submit" className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-md transition"><Plus size={18}/></button>
              </form>
            </div>
          </div>

          <div className="flex items-center justify-between pt-4">
            <button 
              onClick={handleAnalyze}
              disabled={!title || aiAnalyzing}
              className="flex items-center gap-2 px-4 py-2 bg-purple-50 text-purple-700 rounded-lg border border-purple-100 hover:bg-purple-100 transition font-bold text-xs"
            >
              {aiAnalyzing ? <Loader2 className="animate-spin" size={14}/> : <Sparkles size={14} />}
              {aiAnalyzing ? t('tasks.analyzing') : t('tasks.ai_analyze')}
            </button>

            {suggestions && (
              <div className="text-[10px] font-bold text-purple-600 bg-purple-50 px-3 py-1 rounded-full border border-purple-100">
                {t('tasks.suggested_priority')}: {suggestions.suggested_priority === 3 ? t('tasks.high') : t('tasks.normal')}
              </div>
            )}
          </div>
        </div>

        <div className="p-6 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 bg-white border border-[#d0d7de] text-[#1f2328] rounded-lg text-sm font-bold hover:bg-gray-50 transition-colors shadow-sm">{t('common.cancel')}</button>
          <button 
            onClick={handleCreate} 
            disabled={!title || loading}
            className="px-6 py-2 bg-[#1f883d] text-white rounded-lg text-sm font-bold hover:bg-[#1a7f37] transition-all shadow-md hover:shadow-lg flex items-center gap-2 disabled:opacity-50"
          >
            {loading ? <Loader2 className="animate-spin" size={16}/> : <Plus size={18}/>}
            {t('tasks.add_task')}
          </button>
        </div>
      </div>
    </div>
  )
}

function CreateProjectModal({ onClose, onCreated }: any) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // После создания предлагаем подключить репозиторий: раньше ссылка
  // вводилась здесь одним полем, и подключить второй репозиторий
  // или выбрать ветку было уже нельзя.
  const [wizardProjectId, setWizardProjectId] = useState<number | null>(null)

  const handleCreate = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.post('/projects/', { name, description: desc })
      onCreated()
      onClose()
      const id = data?.id
      if (id) setWizardProjectId(id)
    } catch (err: any) {
      setError(err.response?.data?.detail || t('projects.create_failed'))
    } finally {
      setLoading(false)
    }
  }

  if (wizardProjectId) {
    return (
      <RepoConnectWizard
        projectId={wizardProjectId}
        onClose={() => setWizardProjectId(null)}
        onSaved={() => onCreated()}
      />
    )
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-md w-full max-w-md shadow-xl border border-[#d0d7de]">
        <div className="px-4 py-3 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between rounded-t-md">
          <h2 className="text-sm font-semibold text-[#1f2328]">{t('projects.new_project')}</h2>
          <button onClick={onClose} className="text-[#636c76] hover:text-[#1f2328]"><X size={16}/></button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-[#1f2328] mb-1">{t('projects.project_name')}</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full bg-white border border-[#d0d7de] rounded-md px-3 py-1.5 text-sm outline-none focus:border-blue-500" placeholder="e.g. My Website" />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[#1f2328] mb-1">{t('projects.description')}</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} className="w-full bg-white border border-[#d0d7de] rounded-md px-3 py-1.5 text-sm outline-none focus:border-blue-500 resize-none" placeholder={t('projects.description_placeholder')} />
          </div>
          <p className="text-xs text-[#636c76] leading-relaxed">{t('project.git_step_hint')}</p>
          {error && (
            <p className="text-xs text-[#cf222e] bg-[#fff1f0] border border-[#ff8182] rounded-md px-3 py-2">{error}</p>
          )}
        </div>
        <div className="p-4 bg-[#f6f8fa] border-t border-[#d0d7de] flex justify-end gap-2 rounded-b-md">
           <button onClick={onClose} className="px-3 py-1.5 bg-white border border-[#d0d7de] text-[#1f2328] rounded-md text-xs font-semibold">{t('common.cancel')}</button>
           <button onClick={handleCreate} disabled={!name || loading} className="px-3 py-1.5 bg-[#1f883d] text-white border border-[#1a7f37] rounded-md text-xs font-semibold hover:bg-[#1a7f37]">
            {loading ? <Loader2 className="animate-spin" size={14}/> : t('projects.create_project')}
           </button>
        </div>
      </div>
    </div>
  )
}

function DashboardPage() {
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { refetch: refetchProjects } = useQuery({ 
    queryKey: ['projects'],
    queryFn: async () => {
      const { data } = await api.get('/projects/');
      return data;
    }
  });

  return (
    <div className="min-h-screen flex flex-col overflow-hidden bg-[#f6f8fa]">
      <Header />
      
      <DashboardSelection 
        onSelectProject={(id) => navigate(`/project/${id}`)}
        onCreateProject={() => setIsModalOpen(true)}
      />

      {isModalOpen && (
        <CreateProjectModal 
          onClose={() => setIsModalOpen(false)}
          onCreated={() => { refetchProjects(); }}
        />
      )}
    </div>
  );
}

function ProfilePage() {
  return (
    <div className="min-h-screen flex flex-col overflow-hidden bg-[#f6f8fa]">
      <Header />
      <Profile />
    </div>
  );
}

/** Справка с руководствами.
 *
 *  Обёртка нужна ради шапки и защиты маршрута: сама страница справки
 *  занимает всю высоту окна и своей шапки не имеет.
 */
function Help() {
  const { user } = useAuth();
  return (
    <ProtectedRoute>
      <div className="min-h-screen flex flex-col overflow-hidden bg-[#f6f8fa]">
        <Header />
        <HelpPage isAdmin={Boolean(user?.is_superuser)} />
      </div>
    </ProtectedRoute>
  );
}

function App() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/dashboard" element={
        <ProtectedRoute>
          {user?.is_superuser ? <Navigate to="/admin" replace /> : <DashboardPage />}
        </ProtectedRoute>
      } />
      <Route path="/project/:projectId" element={
        <ProtectedRoute>
          <Dashboard />
        </ProtectedRoute>
      } />
      <Route path="/admin" element={
        <AdminRoute>
          <div className="min-h-screen flex flex-col bg-[#f6f8fa]">
            <Header />
            <AdminPanel />
          </div>
        </AdminRoute>
      } />
      <Route path="/admin/users" element={
        <AdminRoute>
          <div className="min-h-screen flex flex-col bg-[#f6f8fa]">
            <Header />
            <UsersPage />
          </div>
        </AdminRoute>
      } />
      <Route path="/admin/roles" element={
        <AdminRoute>
          <div className="min-h-screen flex flex-col bg-[#f6f8fa]">
            <Header />
            <RolesPage />
          </div>
        </AdminRoute>
      } />
      <Route path="/admin/projects" element={
        <AdminRoute>
          <div className="min-h-screen flex flex-col bg-[#f6f8fa]">
            <Header />
            <ProjectsPage />
          </div>
        </AdminRoute>
      } />
      <Route path="/admin/models" element={
        <AdminRoute>
          <div className="min-h-screen flex flex-col bg-[#f6f8fa]">
            <Header />
            <NeuralModelsPage />
          </div>
        </AdminRoute>
      } />
      <Route path="/admin/storage" element={
        <AdminRoute>
          <div className="min-h-screen flex flex-col bg-[#f6f8fa]">
            <Header />
            <StoragePage />
          </div>
        </AdminRoute>
      } />
      <Route path="/profile" element={
        <ProtectedRoute>
          <ProfilePage />
        </ProtectedRoute>
      } />
      <Route path="/help" element={<Help />} />
      <Route path="/" element={
        <ProtectedRoute>
          {user?.is_superuser ? <Navigate to="/admin" replace /> : <Dashboard />}
        </ProtectedRoute>
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
