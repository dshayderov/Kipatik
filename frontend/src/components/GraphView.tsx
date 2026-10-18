import { useRef, useMemo, useCallback, useState } from 'react';
import ForceGraph2D, { ForceGraphMethods } from 'react-force-graph-2d';
import { Task } from '../types';
import { Link, Plus, X, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface GraphViewProps {
  tasks: Task[];
  onTaskClick: (taskId: number) => void;
  onAddDependency?: (taskId: number, dependsOnId: number) => void;
}

const GraphView = ({ tasks, onTaskClick, onAddDependency }: GraphViewProps) => {
  const fgRef = useRef<ForceGraphMethods>();
  const { t } = useTranslation();
  const [linkMode, setLinkMode] = useState<boolean>(false);
  const [sourceNode, setSourceNode] = useState<any>(null);

  const graphData = useMemo(() => {
    const nodes = tasks.map(task => ({
      id: task.id,
      name: task.title,
      priority: task.priority,
      val: 2
    }));

    const links: { source: number; target: number }[] = [];
    tasks.forEach(task => {
      if (task.dependencies) {
        task.dependencies.forEach(depId => {
          links.push({
            source: task.id,
            target: depId
          });
        });
      }
    });

    return { nodes, links };
  }, [tasks]);

  const handleNodeClick = useCallback((node: any) => {
    if (linkMode) {
      if (!sourceNode) {
        setSourceNode(node);
      } else {
        if (sourceNode.id !== node.id && onAddDependency) {
          onAddDependency(sourceNode.id, node.id);
        }
        setSourceNode(null);
        setLinkMode(false);
      }
    } else {
      onTaskClick(node.id);
    }
  }, [linkMode, sourceNode, onTaskClick, onAddDependency]);

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const label = node.name;
    const fontSize = 12 / globalScale;
    ctx.font = `${fontSize}px Sans-Serif`;
    
    // Draw node circle
    const r = (node === sourceNode ? 7 : 4) / globalScale;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
    
    if (node === sourceNode) {
      ctx.fillStyle = '#10b981'; // Green for source
    } else if (node.priority >= 3) {
      ctx.fillStyle = '#ef4444'; 
    } else if (node.priority === 2) {
      ctx.fillStyle = '#f59e0b';
    } else {
      ctx.fillStyle = '#3b82f6';
    }
    
    ctx.fill();
    
    // Selection ring
    if (node === sourceNode) {
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2 / globalScale;
        ctx.stroke();
    }

    if (globalScale > 1.5) {
      const textWidth = ctx.measureText(label).width;
      const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2);
      
      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.fillRect(node.x - (bckgDimensions[0] as number) / 2, node.y - (bckgDimensions[1] as number) / 2 - 10 / globalScale, bckgDimensions[0] as number, bckgDimensions[1] as number);

      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#1f2328';
      ctx.fillText(label, node.x, node.y - 10 / globalScale);
    }
  }, [sourceNode]);

  return (
    <div className="flex-1 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg overflow-hidden relative shadow-inner flex flex-col">
      <div className="bg-white border-b border-[#d0d7de] px-4 py-2 flex items-center justify-between z-10 shadow-sm">
        <div className="flex items-center gap-4">
           <span className="text-xs font-semibold text-[#636c76] flex items-center gap-1">
             <Info size={14} />
             {linkMode ? (sourceNode ? t('tasks.dependencies.select_target') : t('tasks.dependencies.select_source')) : t('tasks.dependencies.view_hint')}
           </span>
        </div>
        <button 
          onClick={() => {
            setLinkMode(!linkMode);
            setSourceNode(null);
          }}
          className={`flex items-center gap-2 px-3 py-1 rounded-md text-xs font-bold transition shadow-sm ${linkMode ? 'bg-red-50 text-red-600 border border-red-200 hover:bg-red-100' : 'bg-[#1f883d] text-white border border-[#1a7f37] hover:bg-[#1a7f37]'}`}
        >
          {linkMode ? <X size={14} /> : <Plus size={14} />}
          {linkMode ? t('common.cancel') : t('tasks.dependencies.add')}
        </button>
      </div>

      <div className="flex-1 relative">
        <ForceGraph2D
            ref={fgRef}
            graphData={graphData}
            nodeLabel="name"
            nodeRelSize={4}
            linkDirectionalArrowLength={3.5}
            linkDirectionalArrowRelPos={1}
            linkCurvature={0.25}
            linkColor={() => '#9ca3af'}
            onNodeClick={handleNodeClick}
            cooldownTicks={100}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            nodeCanvasObject={nodeCanvasObject}
            nodeCanvasObjectMode={() => 'replace'}
        />
        
        <div className="absolute top-4 left-4 bg-white/80 backdrop-blur p-2 rounded-md border border-[#d0d7de] shadow-sm pointer-events-none">
            <h3 className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider mb-2">{t('common.stats')}</h3>
            <div className="space-y-1">
                <div className="flex items-center gap-2 text-xs font-medium text-[#1f2328]">
                    <div className="w-2 h-2 rounded-full bg-[#ef4444]" /> 
                    <span>{tasks.filter(t => t.priority >= 3).length} {t('tasks.high')}</span>
                </div>
                <div className="flex items-center gap-2 text-xs font-medium text-[#1f2328]">
                    <div className="w-2 h-2 rounded-full bg-[#f59e0b]" /> 
                    <span>{tasks.filter(t => t.priority === 2).length} {t('tasks.medium')}</span>
                </div>
                <div className="flex items-center gap-2 text-xs font-medium text-[#1f2328]">
                    <div className="w-2 h-2 rounded-full bg-[#3b82f6]" /> 
                    <span>{tasks.filter(t => t.priority < 2).length} {t('tasks.low')}</span>
                </div>
            </div>
            <div className="mt-3 pt-2 border-t border-[#d0d7de] text-[10px] text-[#636c76]">
                {tasks.length} {t('dashboard.tasks_panel').toLowerCase()}
            </div>
        </div>
      </div>
    </div>
  );
};

export default GraphView;
