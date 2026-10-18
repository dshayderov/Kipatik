import React, { useMemo, useState } from 'react';
import { 
  ChevronLeft, 
  ChevronRight, 
  Calendar as CalendarIcon,
  Clock,
  AlertCircle
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Task, Column, User } from '../types';

interface RoadmapViewProps {
  tasks: Task[];
  columns: Column[];
  members: User[];
  onTaskClick: (id: number) => void;
}

const RoadmapView: React.FC<RoadmapViewProps> = ({ tasks, columns, onTaskClick }) => {
  const { t } = useTranslation();
  
  // State to control the view window
  const [viewDate, setViewDate] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  // Calculate date range for the roadmap (3 months from viewDate)
  const { startDate, endDate, days } = useMemo(() => {
    const start = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1);
    const end = new Date(viewDate.getFullYear(), viewDate.getMonth() + 3, 0);
    
    const dayList = [];
    let current = new Date(start);
    while (current <= end) {
      dayList.push(new Date(current));
      current.setDate(current.getDate() + 1);
    }
    
    return { startDate: start, endDate: end, days: dayList };
  }, [viewDate]);

  const monthLabels = useMemo(() => {
    const labels: { name: string, days: number }[] = [];
    let currentMonth = -1;
    days.forEach(day => {
      if (day.getMonth() !== currentMonth) {
        currentMonth = day.getMonth();
        labels.push({ 
          name: day.toLocaleString('default', { month: 'long', year: 'numeric' }), 
          days: 1 
        });
      } else {
        labels[labels.length - 1].days++;
      }
    });
    return labels;
  }, [days]);

  const getTaskPosition = (task: Task) => {
    const taskStart = task.start_date ? new Date(task.start_date) : new Date(task.created_at);
    const taskEnd = task.due_date ? new Date(task.due_date) : new Date(taskStart.getTime() + 86400000); // Default 1 day
    
    // Check if task is within or overlaps the current view range
    if (taskEnd < startDate || taskStart > endDate) return null;

    // Calculate start offset (clamped to 0 if task started before the view window)
    const effectiveStart = taskStart < startDate ? startDate : taskStart;
    const startOffset = Math.floor((effectiveStart.getTime() - startDate.getTime()) / 86400000);
    
    // Calculate effective end (clamped to endDate if task ends after the view window)
    const effectiveEnd = taskEnd > endDate ? endDate : taskEnd;
    
    // Duration in days within the visible window
    const visibleDuration = Math.ceil((effectiveEnd.getTime() - effectiveStart.getTime()) / 86400000) || 1;
    
    const left = (startOffset / days.length) * 100;
    const width = (visibleDuration / days.length) * 100;
    
    return { 
      left: `${left}%`, 
      width: `${width}%`,
      isClippedLeft: taskStart < startDate,
      isClippedRight: taskEnd > endDate
    };
  };

  const getStatusColor = (columnId: number) => {
    const col = columns.find(c => c.id === columnId);
    if (col?.state_category === 'DONE') return 'bg-green-500';
    if (col?.state_category === 'IN_PROGRESS') return 'bg-amber-500';
    return 'bg-blue-500';
  };

  const handlePrev = () => {
    setViewDate(prev => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  };

  const handleNext = () => {
    setViewDate(prev => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  };

  const handleToday = () => {
    const now = new Date();
    setViewDate(new Date(now.getFullYear(), now.getMonth(), 1));
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-white rounded-lg border border-[#d0d7de] overflow-hidden">
      {/* Roadmap Header */}
      <div className="p-4 border-b border-[#d0d7de] bg-[#f6f8fa] flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h2 className="text-sm font-bold text-[#1f2328] flex items-center gap-2">
            <CalendarIcon size={18} className="text-[#636c76]" />
            {t('tasks.roadmap.title')}
          </h2>
          <div className="flex bg-white border border-[#d0d7de] rounded-md overflow-hidden">
            <button 
              onClick={handlePrev}
              className="p-1.5 hover:bg-[#f6f8fa] border-r border-[#d0d7de]"
              title={t('common.prev')}
            >
              <ChevronLeft size={14} />
            </button>
            <button 
              onClick={handleToday}
              className="px-3 py-1 text-xs font-semibold hover:bg-[#f6f8fa]"
            >
              {t('common.today')}
            </button>
            <button 
              onClick={handleNext}
              className="p-1.5 hover:bg-[#f6f8fa] border-l border-[#d0d7de]"
              title={t('common.next')}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-[#636c76]">
           <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-blue-500" /> TODO</div>
           <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-amber-500" /> IN PROGRESS</div>
           <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-green-500" /> DONE</div>
        </div>
      </div>

      {/* Roadmap Content */}
      <div className="flex-1 overflow-auto relative">
        <div className="min-w-[1200px] h-full flex flex-col">
          {/* Time scale */}
          <div className="flex border-b border-[#d0d7de] sticky top-0 bg-white z-20">
            {monthLabels.map((month, idx) => (
              <div 
                key={idx} 
                className="border-r border-[#d0d7de] py-2 px-4 text-[10px] font-bold text-[#636c76] uppercase tracking-wider bg-[#f6f8fa]"
                style={{ width: `${(month.days / days.length) * 100}%` }}
              >
                {month.name}
              </div>
            ))}
          </div>

          {/* Grid lines background */}
          <div className="absolute inset-0 pointer-events-none flex" style={{ top: '33px' }}>
            {days.map((day, idx) => (
              <div 
                key={idx} 
                className={`h-full border-r border-[#d0d7de]/30 ${day.getDay() === 0 || day.getDay() === 6 ? 'bg-gray-50/50' : ''}`}
                style={{ width: `${(1 / days.length) * 100}%` }}
              />
            ))}
          </div>

          {/* Task rows */}
          <div className="flex-1 relative pt-4 space-y-1 pb-20">
            {tasks.filter(t => t.due_date || t.start_date || t.created_at).length > 0 ? (
              tasks.filter(t => {
                 const pos = getTaskPosition(t);
                 return pos !== null;
              })
              .sort((a, b) => {
                const dateA = a.start_date ? new Date(a.start_date).getTime() : new Date(a.created_at).getTime();
                const dateB = b.start_date ? new Date(b.start_date).getTime() : new Date(b.created_at).getTime();
                return dateA - dateB;
              }).map((task) => {
                const pos = getTaskPosition(task);
                if (!pos) return null;
                
                return (
                  <div key={task.id} className="group relative h-10 flex items-center">
                    {/* Background hover effect */}
                    <div className="absolute inset-0 bg-blue-50/0 group-hover:bg-blue-50/50 transition-colors pointer-events-none" />
                    
                    {/* Task Bar */}
                    <div 
                      onClick={() => onTaskClick(task.id)}
                      className={`absolute h-7 shadow-sm border border-white/20 cursor-pointer flex items-center px-2 text-white overflow-hidden transition-all hover:scale-[1.01] hover:shadow-md z-10 
                        ${getStatusColor(task.column_id)}
                        ${pos.isClippedLeft ? 'rounded-r-md' : 'rounded-md'}
                        ${pos.isClippedRight ? 'rounded-l-md' : 'rounded-md'}
                      `}
                      style={{ 
                        left: pos.left, 
                        width: pos.width, 
                        minWidth: '30px',
                        borderLeftWidth: pos.isClippedLeft ? '0' : '1px',
                        borderRightWidth: pos.isClippedRight ? '0' : '1px'
                      }}
                    >
                      <span className="text-[10px] font-bold truncate whitespace-nowrap">{task.title}</span>
                    </div>
                    
                    {/* Label if bar is too small */}
                    <div className="absolute text-[10px] text-[#636c76] font-medium pointer-events-none truncate" style={{ left: `calc(${pos.left} + ${pos.width} + 8px)` }}>
                       #{task.id}
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-[#636c76]">
                <Clock size={48} className="opacity-20 mb-4" />
                <p className="text-sm">{t('tasks.roadmap.no_tasks')}</p>
                <p className="text-xs mt-1 italic">{t('tasks.roadmap.no_tasks_hint')}</p>
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Legend / Info */}
      <div className="p-3 bg-[#f6f8fa] border-t border-[#d0d7de] flex items-center gap-4">
         <div className="flex items-center gap-2 text-[10px] text-[#636c76]">
            <AlertCircle size={12} className="text-blue-500" />
            <span>{t('tasks.roadmap.date_hint')}</span>
         </div>
      </div>
    </div>
  );
};

export default RoadmapView;
