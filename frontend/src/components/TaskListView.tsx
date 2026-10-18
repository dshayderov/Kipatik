import React, { useState } from 'react';
import { 
  Search, 
  ArrowUpDown, 
  Calendar, 
  User as UserIcon, 
  CheckSquare, 
  MessageSquare,
  MoreHorizontal,
  ChevronRight,
  Filter
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Task, Column, User } from '../types';

interface TaskListViewProps {
  tasks: Task[];
  columns: Column[];
  members: User[];
  onTaskClick: (id: number) => void;
}

const TaskListView: React.FC<TaskListViewProps> = ({ tasks, columns, members, onTaskClick }) => {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState<'title' | 'priority' | 'status' | 'due_date'>('title');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  const filteredTasks = tasks.filter(task => 
    task.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    task.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const sortedTasks = [...filteredTasks].sort((a, b) => {
    let comparison = 0;
    if (sortField === 'title') comparison = a.title.localeCompare(b.title);
    if (sortField === 'priority') comparison = b.priority - a.priority;
    if (sortField === 'status') {
      const colA = columns.find(c => c.id === a.column_id)?.name || '';
      const colB = columns.find(c => c.id === b.column_id)?.name || '';
      comparison = colA.localeCompare(colB);
    }
    if (sortField === 'due_date') {
      const dateA = a.due_date ? new Date(a.due_date).getTime() : 0;
      const dateB = b.due_date ? new Date(b.due_date).getTime() : 0;
      comparison = dateA - dateB;
    }
    return sortOrder === 'asc' ? comparison : -comparison;
  });

  const toggleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  const getPriorityInfo = (p: number) => {
    if (p === 3) return { label: t('tasks.high'), color: 'text-red-600 bg-red-50 border-red-100' };
    if (p === 2) return { label: t('tasks.medium'), color: 'text-amber-600 bg-amber-50 border-amber-100' };
    return { label: t('tasks.low'), color: 'text-blue-600 bg-blue-50 border-blue-100' };
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-white rounded-lg border border-[#d0d7de] overflow-hidden">
      {/* List Toolbar */}
      <div className="p-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#636c76]" size={16} />
          <input 
            type="text"
            placeholder={t('projects.filter_placeholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-1.5 bg-white border border-[#d0d7de] rounded-md text-sm outline-none focus:ring-2 focus:ring-blue-500 transition-all"
          />
        </div>
        <div className="flex items-center gap-2">
           <button className="px-3 py-1.5 bg-white border border-[#d0d7de] rounded-md text-xs font-semibold text-[#1f2328] hover:bg-[#f6f8fa] flex items-center gap-2">
             <Filter size={14} /> {t('common.filter')}
           </button>
        </div>
      </div>

      {/* Table Header */}
      <div className="flex items-center px-4 py-2 border-b border-[#d0d7de] bg-[#f6f8fa] text-[11px] font-bold text-[#636c76] uppercase tracking-wider">
        <div className="flex-[2] flex items-center gap-2 cursor-pointer hover:text-[#1f2328]" onClick={() => toggleSort('title')}>
          {t('tasks.title')} <ArrowUpDown size={12} />
        </div>
        <div className="flex-1 flex items-center gap-2 cursor-pointer hover:text-[#1f2328]" onClick={() => toggleSort('status')}>
          {t('tasks.status')} <ArrowUpDown size={12} />
        </div>
        <div className="flex-1 flex items-center gap-2 cursor-pointer hover:text-[#1f2328]" onClick={() => toggleSort('priority')}>
          {t('tasks.priority')} <ArrowUpDown size={12} />
        </div>
        <div className="flex-1 flex items-center gap-2 cursor-pointer hover:text-[#1f2328]" onClick={() => toggleSort('due_date')}>
          {t('tasks.due_date')} <ArrowUpDown size={12} />
        </div>
        <div className="w-32">{t('tasks.assignee')}</div>
        <div className="w-20 text-center">{t('common.stats')}</div>
      </div>

      {/* Task Rows */}
      <div className="flex-1 overflow-y-auto">
        {sortedTasks.length > 0 ? (
          sortedTasks.map((task) => {
            const priority = getPriorityInfo(task.priority);
            const column = columns.find(c => c.id === task.column_id);
            const assignee = members.find(m => m.id === task.assignee_id);
            const completedSubtasks = task.subtasks.filter(s => s.is_completed).length;

            return (
              <div 
                key={task.id}
                onClick={() => onTaskClick(task.id)}
                className="flex items-center px-4 py-3 border-b border-[#d0d7de] hover:bg-[#f6f8fa] transition-colors cursor-pointer group"
              >
                <div className="flex-[2] min-w-0 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="text-[#636c76] font-mono text-[10px]">#{task.id}</span>
                    <h4 className="text-sm font-semibold text-[#1f2328] truncate group-hover:text-[#0969da]">{task.title}</h4>
                  </div>
                  {task.description && <p className="text-xs text-[#636c76] truncate mt-0.5">{task.description}</p>}
                </div>

                <div className="flex-1">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${
                    column?.state_category === 'DONE' ? 'bg-green-100 text-green-700 border-green-200' :
                    column?.state_category === 'IN_PROGRESS' ? 'bg-amber-100 text-amber-700 border-amber-200' :
                    'bg-gray-100 text-gray-700 border-gray-200'
                  }`}>
                    {column?.name || 'Unknown'}
                  </span>
                </div>

                <div className="flex-1">
                  <span className={`text-[10px] px-2 py-0.5 rounded-md font-bold border ${priority.color}`}>
                    {priority.label}
                  </span>
                </div>

                <div className="flex-1 text-xs text-[#636c76]">
                  {task.due_date ? (
                    <div className="flex items-center gap-1">
                      <Calendar size={12} />
                      {new Date(task.due_date).toLocaleDateString()}
                    </div>
                  ) : '-'}
                </div>

                <div className="w-32">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full border border-[#d0d7de] overflow-hidden bg-gray-100 flex items-center justify-center shrink-0">
                      {assignee?.avatar_url ? <img src={assignee.avatar_url} className="w-full h-full object-cover" /> : <UserIcon size={12} className="text-gray-400" />}
                    </div>
                    <span className="text-xs text-[#1f2328] truncate">{assignee?.full_name || assignee?.email || t('tasks.unassigned')}</span>
                  </div>
                </div>

                <div className="w-20 flex items-center justify-center gap-3 text-[#636c76]">
                  {task.subtasks.length > 0 && (
                    <div className="flex items-center gap-1 text-[10px] font-bold">
                      <CheckSquare size={12} />
                      {completedSubtasks}/{task.subtasks.length}
                    </div>
                  )}
                  {task.comments.length > 0 && (
                    <div className="flex items-center gap-1 text-[10px] font-bold">
                      <MessageSquare size={12} />
                      {task.comments.length}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-[#636c76]">
            <Search size={48} className="opacity-20 mb-4" />
            <p className="text-sm">{t('projects.no_projects_found')}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TaskListView;
