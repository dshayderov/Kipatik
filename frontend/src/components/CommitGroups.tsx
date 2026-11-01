import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d';
import { forceCollide } from 'd3-force';
import {
  AlertCircle,
  ArrowRight,
  Check,
  ChevronRight,
  ExternalLink,
  FileCode2,
  GitCommit,
  Layers,
  Loader2,
  Minus,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  Scan,
  User,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';
import { TASK_TYPE_STYLE, type TaskType } from '../types/taskType';

interface GroupCommitFile {
  path: string;
  previous_path?: string;
  status: string;
  additions: number;
  deletions: number;
}

interface GroupCommit {
  id: number;
  sha?: string;
  message?: string;
  commit_type?: string;
  commit_type_confidence?: number;
  commit_type_reliable?: boolean;
  timestamp?: string;
  author?: string;
  url?: string;
  additions?: number;
  deletions?: number;
  files?: GroupCommitFile[];
}

interface GroupRelation {
  id: number;
  source_commit_id: number;
  target_commit_id: number;
  source_sha?: string;
  target_sha?: string;
  source_short?: string;
  target_short?: string;
  relation_type: string;
  confidence: number;
  direction?: string;
  type_source?: string;
  evidence?: string;
  status?: string;
  in_graph?: boolean;
}

interface CommitGroup {
  id: number;
  title: string;
  title_source: string;
  title_type?: string;
  title_area?: string;
  description?: string;
  rationale?: string;
  confidence?: number;
  status: string;
  position: number;
  size: number;
  commits: GroupCommit[];
  relations: GroupRelation[];
  graph_relations: GroupRelation[];
}

interface GroupsData {
  task_id: number;
  available: boolean;
  reason?: string;
  model_used?: string;
  algorithm_version?: string;
  generated_at?: string;
  groups: CommitGroup[];
  ungrouped: GroupCommit[];
  summary: {
    commits: number;
    grouped: number;
    ungrouped: number;
    groups: number;
    relations: number;
  };
}

interface Props {
  taskId: number;
  commits: GroupCommit[];
  canEdit: boolean;
}

const RELATION_TYPES = ['related', 'extends', 'fixes', 'tests'] as const;

const RELATION_STYLE: Record<
  string,
  { color: string; badge: string; dot: string }
> = {
  related: {
    color: '#8b949e',
    badge: 'bg-[#f6f8fa] text-[#57606a] border-[#d0d7de]',
    dot: 'bg-[#8b949e]',
  },
  extends: {
    color: '#0969da',
    badge: 'bg-[#ddf4ff] text-[#0969da] border-[#54aeff4d]',
    dot: 'bg-[#0969da]',
  },
  fixes: {
    color: '#cf222e',
    badge: 'bg-[#ffebe9] text-[#cf222e] border-[#ff818266]',
    dot: 'bg-[#cf222e]',
  },
  tests: {
    color: '#1a7f37',
    badge: 'bg-[#e6f6ec] text-[#1a7f37] border-[#7ee2a880]',
    dot: 'bg-[#1a7f37]',
  },
};

const TYPE_COLOR: Record<string, string> = {
  bugfix: '#cf222e',
  feature: '#0969da',
  test: '#1a7f37',
  docs: '#6b21a8',
  refactor: '#4f46e5',
  chore: '#57606a',
};

const TYPE_GLYPH: Record<string, string> = {
  bugfix: '!',
  feature: '</>',
  test: '✓',
  docs: '¶',
  refactor: '↻',
  chore: '⚙',
};

const RELATION_STATUS_STYLE: Record<string, string> = {
  confirmed: 'bg-[#e6f6ec] text-[#1a7f37] border-[#7ee2a880]',
  proposed: 'bg-[#fff8c5] text-[#7d4e00] border-[#d4a72c66]',
};

const NODE_WIDTH = 132;
const NODE_HEIGHT = 58;

function commitTypeColor(type?: string) {
  return TYPE_COLOR[type || ''] || TYPE_COLOR.chore;
}

function withAlpha(hex: string, alpha: number) {
  const value = hex.replace('#', '');
  const full =
    value.length === 3
      ? value
          .split('')
          .map((part) => part + part)
          .join('')
      : value;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function roundedRectPath(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number
) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function rectBoundaryPoint(
  from: { x: number; y: number },
  to: { x: number; y: number }
) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (!dx && !dy) return { x: from.x, y: from.y };
  const tx = dx === 0 ? Infinity : NODE_WIDTH / 2 / Math.abs(dx);
  const ty = dy === 0 ? Infinity : NODE_HEIGHT / 2 / Math.abs(dy);
  const t = Math.min(tx, ty);
  return { x: from.x + dx * t, y: from.y + dy * t };
}

function formatEvidence(evidence?: string) {
  return (evidence || '').replace(/;\s*/g, ' · ');
}

const RELIABLE_TYPES = new Set(['bugfix', 'feature', 'docs', 'chore']);

function ShortSha({ value }: { value?: string }) {
  if (!value) return <span className="font-mono text-[11px] text-[#8c959f]">—</span>;
  return (
    <span className="font-mono text-[11px] text-[#57606a] bg-[#f6f8fa] border border-[#d0d7de] rounded px-1 py-0.5">
      {value.slice(0, 7)}
    </span>
  );
}

function TypeBadge({ type, uncertain }: { type?: string; uncertain?: boolean }) {
  const { t } = useTranslation();
  if (!type) {
    return (
      <span className="text-[10px] px-1.5 py-0.5 rounded border border-[#d0d7de] text-[#8c959f]">
        {t('tasks.type_none')}
      </span>
    );
  }
  const style = TASK_TYPE_STYLE[type as TaskType] || TASK_TYPE_STYLE.chore;
  return (
    <span
      title={
        uncertain
          ? t('tasks.dev.commit_type_uncertain')
          : t('tasks.dev.commit_type_reliable')
      }
      className={`text-[10px] px-1.5 py-0.5 rounded border ${style.badge} ${
        uncertain ? 'border-dashed opacity-70' : ''
      }`}
    >
      {t(`task_type.${type}`, { defaultValue: type })}
    </span>
  );
}

function relationLabel(t: (key: string) => string, type: string) {
  return t(`tasks.dev.groups.relations.${type}`);
}

function relationTitle(t: any, type: string) {
  return t(`tasks.dev.groups.relation_titles.${type}`, {
    defaultValue: relationLabel(t, type),
  });
}

function relationDescription(t: any, type: string) {
  return t(`tasks.dev.groups.relation_descriptions.${type}`, {
    defaultValue: '',
  });
}

function RelationLine({ relation }: { relation: GroupRelation }) {
  const { t } = useTranslation();
  const style =
    RELATION_STYLE[relation.relation_type] || RELATION_STYLE.related;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      <span className="font-mono text-[#57606a]">
        {relation.source_sha?.slice(0, 8) || relation.source_short || '—'}
      </span>
      <span className="text-[#8c959f]">→</span>
      <span className="font-mono text-[#57606a]">
        {relation.target_sha?.slice(0, 8) || relation.target_short || '—'}
      </span>
      <span
        className={`text-[10px] px-1.5 py-0.5 rounded border ${style.badge}`}
      >
        {relationLabel(t, relation.relation_type)}
      </span>
      <span className="ml-auto text-[10px] text-[#8c959f]">
        {t('tasks.dev.groups.confidence_short', {
          value: Math.round((relation.confidence || 0) * 100),
        })}
      </span>
    </div>
  );
}

function GroupGraphModal({
  group,
  title,
  allCommits,
  onClose,
}: {
  group: CommitGroup;
  title: string;
  allCommits: GroupCommit[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  const graphWrapRef = useRef<HTMLDivElement | null>(null);
  const fittedRef = useRef(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [hoveredLinkId, setHoveredLinkId] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const [graphSize, setGraphSize] = useState({ width: 800, height: 460 });

  useEffect(() => {
    setSelectedId(group.commits[0]?.id ?? null);
    fittedRef.current = false;
  }, [group.id]);

  useEffect(() => {
    const el = graphWrapRef.current;
    if (!el) return;
    const update = () => {
      const rect = el.getBoundingClientRect();
      setGraphSize({
        width: Math.max(300, Math.floor(rect.width)),
        height: Math.max(280, Math.floor(rect.height)),
      });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const detailedCommits = useMemo(() => {
    const byId = new Map(allCommits.map((commit) => [commit.id, commit]));
    return group.commits.map((commit) => ({
      ...commit,
      ...(byId.get(commit.id) || {}),
    }));
  }, [group.commits, allCommits]);

  const selectedCommit = useMemo(
    () => detailedCommits.find((commit) => commit.id === selectedId),
    [detailedCommits, selectedId]
  );

  const fileCount = useMemo(() => {
    const paths = new Set<string>();
    for (const commit of detailedCommits) {
      for (const file of commit.files || []) paths.add(file.path);
    }
    return paths.size;
  }, [detailedCommits]);

  const typeName = useCallback(
    (type?: string) =>
      type
        ? t(`task_type.${type}`, { defaultValue: type })
        : t('tasks.type_none'),
    [t]
  );

  const shortTypeName = useCallback(
    (type?: string) =>
      type
        ? t(`tasks.dev.groups.short_types.${type}`, {
            defaultValue: typeName(type),
          })
        : t('tasks.type_none'),
    [t, typeName]
  );

  const graph = useMemo(() => {
    const baseNodes = detailedCommits.map((commit) => ({
      id: commit.id,
      sha: commit.sha || '',
      short: (commit.sha || '').slice(0, 8),
      message: commit.message || '',
      type: commit.commit_type || '',
      fill: commitTypeColor(commit.commit_type),
    }));
    const nodeIds = new Set(baseNodes.map((node) => node.id));
    const links = group.graph_relations
      .filter(
        (relation) =>
          nodeIds.has(relation.source_commit_id) &&
          nodeIds.has(relation.target_commit_id)
      )
      .map((relation) => ({
        ...relation,
        source: relation.source_commit_id,
        target: relation.target_commit_id,
        color: (RELATION_STYLE[relation.relation_type] || RELATION_STYLE.related)
          .color,
      }));
    const degree = new Map<number, number>();
    for (const link of links) {
      degree.set(link.source, (degree.get(link.source) || 0) + 1);
      degree.set(link.target, (degree.get(link.target) || 0) + 1);
    }
    const nodes = baseNodes.map((node) => ({
      ...node,
      degree: degree.get(node.id) || 0,
      label: `${node.short} · ${shortTypeName(node.type)}
${
        node.message || t('tasks.dev.groups.no_message')
      }`,
    }));
    return { nodes, links };
  }, [detailedCommits, group.graph_relations, t, shortTypeName]);

  const degreeById = useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node.degree])),
    [graph.nodes]
  );

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    const charge = fg.d3Force('charge') as any;
    if (charge?.strength) charge.strength(-280);
    const link = fg.d3Force('link') as any;
    if (link?.distance) link.distance(150);
    fg.d3Force('collision', forceCollide(82).strength(1) as any);
    fg.d3ReheatSimulation();
  }, [graph]);

  const zoomBy = (factor: number) => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.zoom((fg.zoom() || 1) * factor, 250);
  };

  const fitGraph = () => fgRef.current?.zoomToFit(320, 78);

  const selectedType = selectedCommit?.commit_type;
  const selectedColor = commitTypeColor(selectedType);
  const selectedFiles = selectedCommit?.files || [];

  return (
    <div
      className="fixed inset-0 z-[80] bg-black/55 backdrop-blur-sm flex items-center justify-center p-3 lg:p-5"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-xl shadow-2xl border border-[#d0d7de] w-full h-[94vh] max-w-[1440px] flex flex-col overflow-hidden">
        <div className="flex items-start justify-between gap-3 px-4 py-2.5 border-b border-[#d0d7de] bg-white">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#8c959f]">
              {t('tasks.dev.groups.graph_title')}
            </p>
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <h3 className="font-semibold text-sm text-[#1f2328] truncate">
                {t('tasks.dev.groups.graph_group_heading', {
                  index: group.position + 1,
                  title,
                })}
              </h3>
              <span className="text-[10px] text-[#8c959f]">
                {fileCount > 0
                  ? t('tasks.dev.groups.graph_group_meta', {
                      commits: detailedCommits.length,
                      files: fileCount,
                    })
                  : t('tasks.dev.groups.commits_count', {
                      count: detailedCommits.length,
                    })}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-[#636c76] hover:bg-[#eaeef2] transition shrink-0"
            aria-label={t('common.close', { defaultValue: 'Закрыть' })}
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 min-h-0 flex flex-col lg:flex-row overflow-hidden">
          <div className="flex-1 min-h-0 flex flex-col min-w-0">
            <div
              ref={graphWrapRef}
              className="relative flex-1 min-h-[320px] bg-[#f8fafc] bg-[radial-gradient(circle,#dbe3ec_1px,transparent_1px)] [background-size:18px_18px]"
            >
              {graph.links.length === 0 ? (
                <div className="absolute inset-0 flex items-center justify-center text-sm text-[#636c76]">
                  {t('tasks.dev.groups.graph_empty')}
                </div>
              ) : (
                <div className="absolute inset-0">
                  <ForceGraph2D
                    ref={fgRef as any}
                    graphData={graph}
                    width={graphSize.width}
                    height={graphSize.height}
                    backgroundColor="rgba(0,0,0,0)"
                    nodeRelSize={1}
                    cooldownTicks={180}
                    warmupTicks={30}
                    d3AlphaDecay={0.025}
                    dagMode="td"
                    dagLevelDistance={110}
                    onEngineStop={() => {
                      if (!fittedRef.current) {
                        fittedRef.current = true;
                        fitGraph();
                      }
                    }}
                    onZoom={(transform) => setZoom(transform.k)}
                    onNodeClick={(node: any) => setSelectedId(node.id)}
                    onLinkClick={(link: any) =>
                      setSelectedId(link.source_commit_id)
                    }
                    onLinkHover={(link: any) =>
                      setHoveredLinkId(link ? link.id : null)
                    }
                    linkHoverPrecision={12}
                    nodeLabel={(node: any) => node.label}
                    nodePointerAreaPaint={(
                      node: any,
                      color: string,
                      ctx: CanvasRenderingContext2D
                    ) => {
                      ctx.fillStyle = color;
                      roundedRectPath(
                        ctx,
                        node.x - NODE_WIDTH / 2,
                        node.y - NODE_HEIGHT / 2,
                        NODE_WIDTH,
                        NODE_HEIGHT,
                        12
                      );
                      ctx.fill();
                    }}
                    nodeCanvasObject={(
                      node: any,
                      ctx: CanvasRenderingContext2D
                    ) => {
                      const x = node.x - NODE_WIDTH / 2;
                      const y = node.y - NODE_HEIGHT / 2;
                      const selected = selectedId === node.id;
                      const color = node.fill;

                      ctx.save();
                      ctx.shadowColor = 'rgba(31, 35, 40, 0.10)';
                      ctx.shadowBlur = 10;
                      ctx.shadowOffsetY = 2;
                      roundedRectPath(ctx, x, y, NODE_WIDTH, NODE_HEIGHT, 12);
                      ctx.fillStyle = '#ffffff';
                      ctx.fill();
                      ctx.restore();

                      roundedRectPath(ctx, x, y, NODE_WIDTH, NODE_HEIGHT, 12);
                      ctx.lineWidth = selected ? 2 : 1.2;
                      ctx.strokeStyle = selected
                        ? color
                        : withAlpha(color, 0.45);
                      ctx.stroke();

                      roundedRectPath(
                        ctx,
                        x + 8,
                        y + 8,
                        36,
                        NODE_HEIGHT - 16,
                        8
                      );
                      ctx.fillStyle = withAlpha(color, 0.14);
                      ctx.fill();

                      ctx.fillStyle = color;
                      ctx.font = '700 12px Sans-Serif';
                      ctx.textAlign = 'center';
                      ctx.textBaseline = 'middle';
                      ctx.fillText(
                        TYPE_GLYPH[node.type] || '•',
                        x + 26,
                        y + NODE_HEIGHT / 2 + 0.5
                      );

                      ctx.textAlign = 'left';
                      ctx.textBaseline = 'top';
                      ctx.fillStyle = '#1f2328';
                      ctx.font = '700 12px Sans-Serif';
                      ctx.fillText(node.short, x + 52, y + 13);
                      ctx.fillStyle = color;
                      ctx.font = '9px Sans-Serif';
                      ctx.fillText(shortTypeName(node.type), x + 52, y + 32);

                      if (node.degree > 0) {
                        const cx = x + NODE_WIDTH - 10;
                        const cy = y + NODE_HEIGHT - 10;
                        ctx.beginPath();
                        ctx.arc(cx, cy, 8, 0, 2 * Math.PI);
                        ctx.fillStyle = '#ffffff';
                        ctx.fill();
                        ctx.strokeStyle = withAlpha(color, 0.45);
                        ctx.lineWidth = 1;
                        ctx.stroke();
                        ctx.fillStyle = '#636c76';
                        ctx.font = '700 9px Sans-Serif';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';
                        ctx.fillText(String(node.degree), cx, cy + 0.5);
                      }
                    }}
                    linkCanvasObjectMode={() => 'replace'}
                    linkCanvasObject={(
                      link: any,
                      ctx: CanvasRenderingContext2D
                    ) => {
                      const start = link.source;
                      const end = link.target;
                      if (
                        !start ||
                        !end ||
                        typeof start !== 'object' ||
                        typeof end !== 'object'
                      ) {
                        return;
                      }
                      const from = rectBoundaryPoint(start, end);
                      const to = rectBoundaryPoint(end, start);
                      const active = hoveredLinkId === link.id;
                      const color = active ? link.color : '#c9d1d9';
                      const dx = to.x - from.x;
                      const dy = to.y - from.y;
                      const distance = Math.hypot(dx, dy) || 1;
                      const nx = -dy / distance;
                      const ny = dx / distance;
                      const curve =
                        Math.min(18, distance * 0.16) *
                        ((link.id || 0) % 2 === 0 ? 1 : -1);
                      const cx = (from.x + to.x) / 2 + nx * curve;
                      const cy = (from.y + to.y) / 2 + ny * curve;

                      ctx.beginPath();
                      ctx.moveTo(from.x, from.y);
                      ctx.quadraticCurveTo(cx, cy, to.x, to.y);
                      ctx.strokeStyle = color;
                      ctx.lineWidth = active ? 2.4 : 1.6;
                      ctx.stroke();

                      const angle = Math.atan2(to.y - cy, to.x - cx);
                      const size = active ? 9 : 8;
                      ctx.beginPath();
                      ctx.moveTo(to.x, to.y);
                      ctx.lineTo(
                        to.x - size * Math.cos(angle - 0.42),
                        to.y - size * Math.sin(angle - 0.42)
                      );
                      ctx.lineTo(
                        to.x - size * Math.cos(angle + 0.42),
                        to.y - size * Math.sin(angle + 0.42)
                      );
                      ctx.closePath();
                      ctx.fillStyle = color;
                      ctx.fill();

                      const mx = 0.25 * from.x + 0.5 * cx + 0.25 * to.x;
                      const my = 0.25 * from.y + 0.5 * cy + 0.25 * to.y;
                      const offset = 11;
                      const lx = mx + nx * offset * (curve >= 0 ? 1 : -1);
                      const ly = my + ny * offset * (curve >= 0 ? 1 : -1);
                      ctx.font = '10px Sans-Serif';
                      ctx.textAlign = 'center';
                      ctx.textBaseline = 'middle';
                      ctx.lineWidth = 4;
                      ctx.strokeStyle = '#f8fafc';
                      ctx.strokeText(
                        relationLabel(t, link.relation_type),
                        lx,
                        ly
                      );
                      ctx.fillStyle = active ? link.color : '#6e7781';
                      ctx.fillText(
                        relationLabel(t, link.relation_type),
                        lx,
                        ly
                      );
                    }}
                  />
                </div>
              )}

              <div className="absolute top-3 right-3 flex items-center gap-0.5 rounded-lg border border-[#d0d7de] bg-white/95 px-1 py-1 shadow-sm backdrop-blur">
                <button
                  onClick={() => zoomBy(0.8)}
                  title={t('tasks.dev.groups.zoom_out')}
                  className="p-1.5 rounded hover:bg-[#f6f8fa] text-[#57606a]"
                >
                  <Minus size={13} />
                </button>
                <span className="min-w-[38px] text-center text-[10px] font-semibold text-[#57606a] tabular-nums">
                  {Math.round(zoom * 100)}%
                </span>
                <button
                  onClick={() => zoomBy(1.25)}
                  title={t('tasks.dev.groups.zoom_in')}
                  className="p-1.5 rounded hover:bg-[#f6f8fa] text-[#57606a]"
                >
                  <Plus size={13} />
                </button>
                <button
                  onClick={fitGraph}
                  title={t('tasks.dev.groups.fit_graph')}
                  className="p-1.5 rounded hover:bg-[#f6f8fa] text-[#57606a]"
                >
                  <Scan size={13} />
                </button>
              </div>

              <div className="pointer-events-none absolute bottom-3 left-3 rounded-md border border-[#d0d7de] bg-white/90 px-2 py-1 text-[10px] text-[#8c959f] shadow-sm">
                {t('tasks.dev.groups.graph_node_hint')}
              </div>
            </div>

            <div className="border-t border-[#d0d7de] bg-white px-3 py-2.5 max-h-[190px] overflow-y-auto">
              {selectedCommit ? (
                <div className="flex gap-3">
                  <div
                    className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 text-[11px] font-bold"
                    style={{
                      backgroundColor: withAlpha(selectedColor, 0.14),
                      color: selectedColor,
                    }}
                  >
                    {TYPE_GLYPH[selectedType || ''] || '•'}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-bold text-[#1f2328]">
                        {selectedCommit.sha?.slice(0, 8) || '—'}
                      </span>
                      <TypeBadge
                        type={selectedCommit.commit_type}
                        uncertain={
                          !!selectedCommit.commit_type &&
                          !RELIABLE_TYPES.has(selectedCommit.commit_type)
                        }
                      />
                      {selectedCommit.commit_type_confidence != null && (
                        <span className="text-[10px] text-[#8c959f] tabular-nums">
                          {Math.round(
                            selectedCommit.commit_type_confidence * 100
                          )}
                          %
                        </span>
                      )}
                      <span className="ml-auto flex items-center gap-2 text-[10px] text-[#8c959f]">
                        {selectedCommit.timestamp && (
                          <span>
                            {new Date(
                              selectedCommit.timestamp
                            ).toLocaleString()}
                          </span>
                        )}
                        {selectedCommit.author && (
                          <span className="inline-flex items-center gap-1">
                            <User size={10} />
                            {selectedCommit.author}
                          </span>
                        )}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[#1f2328] leading-snug break-words">
                      {selectedCommit.message ||
                        t('tasks.dev.groups.no_message')}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[10px] text-[#636c76]">
                      {selectedFiles.length > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <FileCode2 size={10} />
                          {t('tasks.dev.files_n', {
                            count: selectedFiles.length,
                          })}
                        </span>
                      )}
                      {!!selectedCommit.additions && (
                        <span className="text-[#1a7f37] font-mono">
                          +{selectedCommit.additions}
                        </span>
                      )}
                      {!!selectedCommit.deletions && (
                        <span className="text-[#cf222e] font-mono">
                          -{selectedCommit.deletions}
                        </span>
                      )}
                      <span>
                        {t('tasks.dev.groups.relations_title')}:{' '}
                        {degreeById.get(selectedCommit.id) || 0}
                      </span>
                      {selectedCommit.url && (
                        <a
                          href={selectedCommit.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[#0969da] hover:underline"
                        >
                          <ExternalLink size={10} />
                          {t('tasks.dev.groups.open_commit', {
                            defaultValue: 'Открыть коммит',
                          })}
                        </a>
                      )}
                    </div>
                    {selectedFiles.length > 0 && (
                      <div className="mt-1.5 space-y-0.5">
                        {selectedFiles.slice(0, 5).map((file) => (
                          <div
                            key={file.path}
                            className="flex items-center gap-2 text-[10px] text-[#57606a]"
                          >
                            <FileCode2
                              size={10}
                              className="text-[#8c959f] shrink-0"
                            />
                            <span className="font-mono truncate">
                              {file.path}
                            </span>
                            {file.additions > 0 && (
                              <span className="text-[#1a7f37] font-mono shrink-0">
                                +{file.additions}
                              </span>
                            )}
                            {file.deletions > 0 && (
                              <span className="text-[#cf222e] font-mono shrink-0">
                                -{file.deletions}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-[11px] text-[#8c959f]">
                  {t('tasks.dev.groups.graph_node_hint')}
                </p>
              )}
            </div>
          </div>

          <aside className="w-full lg:w-[360px] shrink-0 border-t lg:border-t-0 lg:border-l border-[#d0d7de] bg-white flex flex-col min-h-0 max-h-[38vh] lg:max-h-none">
            <div className="flex items-center gap-2 px-3 py-2.5 border-b border-[#d0d7de]">
              <Network size={14} className="text-[#0969da] shrink-0" />
              <span className="text-xs font-semibold text-[#1f2328]">
                {t('tasks.dev.groups.relations_between')}
              </span>
              <span className="text-[10px] text-[#8c959f] bg-[#f6f8fa] border border-[#d0d7de] rounded-full px-1.5 py-0.5">
                {group.relations.length}
              </span>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-2.5 space-y-2">
              {group.relations.map((relation) => {
                const style =
                  RELATION_STYLE[relation.relation_type] ||
                  RELATION_STYLE.related;
                const active = hoveredLinkId === relation.id;
                return (
                  <button
                    key={relation.id}
                    type="button"
                    onClick={() =>
                      setSelectedId(relation.source_commit_id)
                    }
                    onMouseEnter={() => setHoveredLinkId(relation.id)}
                    onMouseLeave={() => setHoveredLinkId(null)}
                    className={`w-full text-left rounded-lg border bg-white p-2.5 transition ${
                      active
                        ? 'border-[#0969da] shadow-sm'
                        : 'border-[#d0d7de] hover:border-[#afb8c1] hover:bg-[#f6f8fa]'
                    }`}
                    style={{ borderLeftColor: style.color, borderLeftWidth: 3 }}
                  >
                    <div className="flex items-center gap-1.5 text-[10px]">
                      <ArrowRight
                        size={12}
                        className="shrink-0"
                        style={{ color: style.color }}
                      />
                      <span className="font-mono text-[#57606a]">
                        {relation.source_sha?.slice(0, 7) || '—'}
                      </span>
                      <span className="text-[#8c959f]">→</span>
                      <span className="font-mono text-[#57606a]">
                        {relation.target_sha?.slice(0, 7) || '—'}
                      </span>
                      <span className="ml-auto font-semibold text-[#1f2328] tabular-nums">
                        {Math.round((relation.confidence || 0) * 100)}%
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="text-[11px] font-semibold text-[#1f2328]">
                        {relationTitle(t, relation.relation_type)}
                      </span>
                      <span
                        className={`ml-auto text-[9px] px-1.5 py-0.5 rounded border ${
                          RELATION_STATUS_STYLE[
                            relation.status || 'proposed'
                          ] || RELATION_STATUS_STYLE.proposed
                        }`}
                      >
                        {t(
                          `tasks.dev.groups.relation_status.${
                            relation.status || 'proposed'
                          }`,
                          { defaultValue: relation.status || 'proposed' }
                        )}
                      </span>
                    </div>
                    <p className="mt-1 text-[10px] leading-snug text-[#636c76]">
                      {relationDescription(t, relation.relation_type)}
                    </p>
                    {relation.evidence && (
                      <p className="mt-1 text-[9px] leading-snug text-[#8c959f] break-words">
                        {formatEvidence(relation.evidence)}
                      </p>
                    )}
                  </button>
                );
              })}
              {group.relations.length === 0 && (
                <p className="text-[11px] text-[#8c959f] px-1 py-2">
                  {t('tasks.dev.groups.graph_empty')}
                </p>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}


export default function CommitGroups({ taskId, commits, canEdit }: Props) {
  const { t } = useTranslation();
  const [data, setData] = useState<GroupsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [draftCommits, setDraftCommits] = useState<Set<number>>(new Set());
  const [graphGroup, setGraphGroup] = useState<CommitGroup | null>(null);

  const load = useCallback(
    async (ensure = true) => {
      setLoadError('');
      try {
        const { data } = await api.get(`/git/task/${taskId}/groups`, {
          params: { ensure },
        });
        setData(data);
      } catch (err: any) {
        setLoadError(err.response?.data?.detail || t('tasks.dev.groups.load_failed'));
      } finally {
        setLoading(false);
      }
    },
    [taskId, t]
  );

  useEffect(() => {
    setLoading(true);
    load(true);
  }, [load, commits.length]);

  const typeName = useCallback(
    (type?: string) =>
      type
        ? t(`task_type.${type}`, { defaultValue: type })
        : t('tasks.dev.groups.unknown_type'),
    [t]
  );

  const displayTitle = useCallback(
    (group: CommitGroup) => {
      if (group.title_source === 'manual') return group.title;
      return `${typeName(group.title_type)} — ${
        group.title_area || t('tasks.dev.groups.no_area')
      }`;
    },
    [t, typeName]
  );

  const occupant = useMemo(() => {
    const map = new Map<number, { groupId: number; title: string }>();
    for (const group of data?.groups || []) {
      for (const commit of group.commits) {
        map.set(commit.id, { groupId: group.id, title: displayTitle(group) });
      }
    }
    return map;
  }, [data, displayTitle]);

  const refresh = async () => {
    setBusy('refresh');
    await load(false);
    setBusy(null);
  };

  const runRebuild = async () => {
    if (!canEdit) return;
    if (!window.confirm(t('tasks.dev.groups.rebuild_confirm'))) return;
    setBusy('rebuild');
    setActionError('');
    try {
      const { data } = await api.post(`/git/task/${taskId}/groups/analyze`, {
        force: true,
      });
      setData(data);
      setEditingId(null);
    } catch (err: any) {
      setActionError(
        err.response?.data?.detail || t('tasks.dev.groups.rebuild_failed')
      );
    } finally {
      setBusy(null);
    }
  };

  const confirmGroup = async (group: CommitGroup) => {
    setBusy(`confirm:${group.id}`);
    setActionError('');
    try {
      const { data } = await api.patch(
        `/git/task/${taskId}/groups/${group.id}`,
        { status: group.status === 'confirmed' ? 'proposed' : 'confirmed' }
      );
      setData(data);
    } catch (err: any) {
      setActionError(
        err.response?.data?.detail || t('tasks.dev.groups.save_failed')
      );
    } finally {
      setBusy(null);
    }
  };

  const startEdit = (group: CommitGroup) => {
    setEditingId(group.id);
    setDraftTitle(displayTitle(group));
    setDraftCommits(new Set(group.commits.map((commit) => commit.id)));
    setActionError('');
  };

  const saveGroup = async (group: CommitGroup) => {
    if (draftCommits.size < 2) {
      setActionError(t('tasks.dev.groups.need_two'));
      return;
    }
    setBusy(`save:${group.id}`);
    setActionError('');
    try {
      const payload: { commit_ids: number[]; title?: string } = {
        commit_ids: Array.from(draftCommits),
      };
      const title = draftTitle.trim();
      if (title !== displayTitle(group)) {
        payload.title = title;
      }
      const { data } = await api.patch(
        `/git/task/${taskId}/groups/${group.id}`,
        payload
      );
      setData(data);
      setEditingId(null);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const mapped =
        detail === 'group_too_small'
          ? t('tasks.dev.groups.need_two')
          : detail === 'commit_in_other_group'
            ? t('tasks.dev.groups.commit_in_other_group')
            : detail === 'commit_not_linked'
              ? t('tasks.dev.groups.commit_not_linked')
              : detail || t('tasks.dev.groups.save_failed');
      setActionError(mapped);
    } finally {
      setBusy(null);
    }
  };

  if (loading && !data) {
    return (
      <section className="border border-[#d0d7de] rounded-lg p-3">
        <div className="flex items-center gap-2 text-sm text-[#636c76]">
          <Loader2 size={14} className="animate-spin" />
          {t('tasks.dev.groups.analyzing')}
        </div>
      </section>
    );
  }

  if (loadError) {
    return (
      <section className="border border-[#ff818266] rounded-lg p-3 bg-[#fff8f8]">
        <div className="flex items-start gap-2 text-sm text-[#cf222e]">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          <div className="flex-1">
            <p>{loadError}</p>
            <button
              onClick={() => load(true)}
              className="mt-1.5 text-[11px] font-semibold text-[#0969da] hover:underline"
            >
              {t('tasks.dev.groups.retry')}
            </button>
          </div>
        </div>
      </section>
    );
  }

  const groups = data?.groups || [];
  const summary = data?.summary;
  const unavailableReason = data?.reason;

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <Layers size={15} className="text-[#0969da] shrink-0" />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-[#1f2328]">
              {t('tasks.dev.groups.title')}
            </h3>
            {summary && (
              <p className="text-[11px] text-[#636c76]">
                {t('tasks.dev.groups.summary', {
                  groups: summary.groups,
                  grouped: summary.grouped,
                  commits: summary.commits,
                })}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={refresh}
            disabled={busy !== null}
            className="p-1.5 rounded-md text-[#636c76] hover:bg-[#f3f4f6] transition disabled:opacity-50"
            title={t('tasks.dev.refresh')}
          >
            <RefreshCw size={13} className={busy === 'refresh' ? 'animate-spin' : ''} />
          </button>
          {canEdit && (
            <button
              onClick={runRebuild}
              disabled={busy !== null}
              className="px-2 py-1 rounded-md text-[11px] font-semibold border border-[#d0d7de] text-[#57606a] hover:bg-[#f6f8fa] transition disabled:opacity-50 inline-flex items-center gap-1"
              title={t('tasks.dev.groups.rebuild_hint')}
            >
              {busy === 'rebuild' ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <RefreshCw size={12} />
              )}
              {t('tasks.dev.groups.rebuild')}
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="flex items-center gap-1.5 text-[11px] text-[#cf222e] bg-[#ffebe9] border border-[#ff818266] rounded-md px-2 py-1.5">
          <AlertCircle size={12} className="shrink-0" />
          {actionError}
        </div>
      )}

      {!data?.available ? (
        <div className="border border-dashed border-[#d0d7de] rounded-lg p-3 text-xs text-[#636c76] bg-[#f6f8fa]">
          <div className="flex items-start gap-2">
            <AlertCircle size={14} className="mt-0.5 text-[#8c959f] shrink-0" />
            <div>
              {unavailableReason === 'not_enough_commits'
                ? t('tasks.dev.groups.not_enough_commits')
                : unavailableReason === 'disabled'
                  ? t('tasks.dev.groups.disabled')
                  : unavailableReason && unavailableReason !== 'not_analyzed'
                    ? `${t('tasks.dev.groups.unavailable')}: ${unavailableReason}`
                    : t('tasks.dev.groups.not_analyzed')}
              {canEdit && (
                <button
                  onClick={() => load(true)}
                  className="ml-2 font-semibold text-[#0969da] hover:underline"
                >
                  {t('tasks.dev.groups.retry')}
                </button>
              )}
            </div>
          </div>
        </div>
      ) : groups.length === 0 ? (
        <div className="border border-dashed border-[#d0d7de] rounded-lg p-3 text-xs text-[#636c76] bg-[#f6f8fa]">
          {t('tasks.dev.groups.no_groups')}
          {summary && summary.ungrouped > 0 && (
            <span> {t('tasks.dev.groups.ungrouped_n', { count: summary.ungrouped })}</span>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {groups.map((group) => {
            const title = displayTitle(group);
            const confirmed = group.status === 'confirmed';
            const isEditing = editingId === group.id;
            const relationCounts = RELATION_TYPES.map((type) => ({
              type,
              count: group.relations.filter(
                (relation) => relation.relation_type === type
              ).length,
            })).filter((item) => item.count > 0);
            const busyHere = busy?.endsWith(`:${group.id}`);

            return (
              <article
                key={group.id}
                className={`rounded-lg border bg-white overflow-hidden ${
                  confirmed
                    ? 'border-[#7ee2a880] shadow-[inset_3px_0_0_#1a7f37]'
                    : 'border-[#d0d7de] shadow-[inset_3px_0_0_#bf8700]'
                }`}
              >
                <div className="px-3 py-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      {isEditing ? (
                        <input
                          value={draftTitle}
                          onChange={(event) => setDraftTitle(event.target.value)}
                          maxLength={255}
                          placeholder={t('tasks.dev.groups.name_placeholder')}
                          className="w-full text-sm font-semibold border border-[#0969da] rounded-md px-2 py-1 outline-none"
                        />
                      ) : (
                        <h4 className="text-sm font-semibold text-[#1f2328] leading-snug">
                          {title}
                        </h4>
                      )}
                      <div className="flex flex-wrap items-center gap-1.5 mt-1">
                        <TypeBadge type={group.title_type} />
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                            confirmed
                              ? 'bg-[#e6f6ec] text-[#1a7f37] border-[#7ee2a880]'
                              : 'bg-[#fff8c5] text-[#7d4e00] border-[#d4a72c66]'
                          }`}
                        >
                          {confirmed
                            ? t('tasks.dev.groups.confirmed')
                            : t('tasks.dev.groups.proposed')}
                        </span>
                        <span className="text-[10px] text-[#8c959f]">
                          {t('tasks.dev.groups.commits_count', {
                            count: group.size,
                          })}
                        </span>
                        {group.confidence != null && (
                          <span className="text-[10px] text-[#8c959f]">
                            {t('tasks.dev.groups.confidence_short', {
                              value: Math.round(group.confidence * 100),
                            })}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => setGraphGroup(group)}
                        className="p-1.5 rounded-md text-[#0969da] hover:bg-[#ddf4ff] transition"
                        title={t('tasks.dev.groups.graph')}
                      >
                        <Network size={14} />
                      </button>
                      {canEdit && !isEditing && (
                        <button
                          onClick={() => startEdit(group)}
                          className="p-1.5 rounded-md text-[#636c76] hover:bg-[#f3f4f6] transition"
                          title={t('tasks.dev.groups.edit')}
                        >
                          <Pencil size={13} />
                        </button>
                      )}
                      {canEdit && !isEditing && !confirmed && (
                        <button
                          onClick={() => confirmGroup(group)}
                          disabled={busy !== null}
                          className="px-2 py-1 rounded-md text-[11px] font-semibold bg-[#1a7f37] text-white hover:bg-[#166b2f] transition disabled:opacity-50 inline-flex items-center gap-1"
                        >
                          {busyHere ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <Check size={11} />
                          )}
                          {t('tasks.dev.groups.confirm')}
                        </button>
                      )}
                      {canEdit && !isEditing && confirmed && (
                        <button
                          onClick={() => confirmGroup(group)}
                          disabled={busy !== null}
                          className="px-2 py-1 rounded-md text-[11px] font-medium border border-[#7ee2a880] text-[#1a7f37] hover:bg-[#e6f6ec] transition disabled:opacity-50"
                          title={t('tasks.dev.groups.unconfirm_hint')}
                        >
                          {t('tasks.dev.groups.unconfirm')}
                        </button>
                      )}
                    </div>
                  </div>

                  {!isEditing && (
                    <>
                      <div className="mt-2 space-y-1">
                        {group.commits.map((commit) => {
                          const uncertain =
                            !!commit.commit_type &&
                            !RELIABLE_TYPES.has(commit.commit_type);
                          return (
                            <div
                              key={commit.id}
                              className="flex items-center gap-2 min-w-0"
                            >
                              <GitCommit
                                size={11}
                                className="text-[#8c959f] shrink-0"
                              />
                              <ShortSha value={commit.sha} />
                              <span className="text-[11px] text-[#57606a] truncate">
                                {commit.message || '—'}
                              </span>
                              <span className="ml-auto shrink-0">
                                <TypeBadge
                                  type={commit.commit_type}
                                  uncertain={uncertain}
                                />
                              </span>
                            </div>
                          );
                        })}
                      </div>

                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        {relationCounts.map(({ type, count }) => {
                          const style = RELATION_STYLE[type] || RELATION_STYLE.related;
                          return (
                            <span
                              key={type}
                              className={`text-[10px] px-1.5 py-0.5 rounded border inline-flex items-center gap-1 ${style.badge}`}
                            >
                              <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                              {relationLabel(t, type)}: {count}
                            </span>
                          );
                        })}
                        {group.relations.length === 0 && (
                          <span className="text-[10px] text-[#8c959f]">
                            {t('tasks.dev.groups.graph_empty')}
                          </span>
                        )}
                        <button
                          onClick={() => setGraphGroup(group)}
                          className="text-[10px] text-[#0969da] hover:underline inline-flex items-center gap-0.5"
                        >
                          {t('tasks.dev.groups.open_graph')}
                          <ChevronRight size={10} />
                        </button>
                      </div>

                      {group.relations.length > 0 && (
                        <details className="mt-1.5">
                          <summary className="cursor-pointer select-none text-[10px] text-[#0969da] hover:underline">
                            {t('tasks.dev.groups.relations_title')} ·{' '}
                            {group.relations.length}
                          </summary>
                          <div className="mt-1 space-y-0.5 border-l-2 border-[#d0d7de] pl-2">
                            {group.relations.map((relation) => (
                              <RelationLine
                                key={relation.id}
                                relation={relation}
                              />
                            ))}
                          </div>
                        </details>
                      )}
                    </>
                  )}

                  {isEditing && (
                    <div className="mt-2.5 border-t border-[#d0d7de] pt-2.5">
                      <p className="text-[11px] text-[#636c76] mb-1.5">
                        {t('tasks.dev.groups.edit_hint')}
                      </p>
                      <div className="max-h-44 overflow-auto border border-[#d0d7de] rounded-md divide-y divide-[#eaeef2]">
                        {commits.map((commit) => {
                          const occupied = occupant.get(commit.id);
                          const inThisGroup = occupied?.groupId === group.id;
                          const disabled = !!occupied && !inThisGroup;
                          return (
                            <label
                              key={commit.id}
                              className={`flex items-center gap-2 px-2 py-1.5 text-[11px] ${
                                disabled
                                  ? 'bg-[#f6f8fa] text-[#8c959f] cursor-not-allowed'
                                  : 'cursor-pointer hover:bg-[#f6f8fa]'
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={draftCommits.has(commit.id)}
                                disabled={disabled}
                                onChange={() => {
                                  setDraftCommits((current) => {
                                    const next = new Set(current);
                                    if (next.has(commit.id)) next.delete(commit.id);
                                    else next.add(commit.id);
                                    return next;
                                  });
                                }}
                                className="accent-[#0969da]"
                              />
                              <ShortSha value={commit.sha} />
                              <span className="truncate flex-1">
                                {commit.message || '—'}
                              </span>
                              {disabled && (
                                <span className="text-[10px] shrink-0">
                                  {t('tasks.dev.groups.in_other_group')}
                                </span>
                              )}
                            </label>
                          );
                        })}
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-[10px] text-[#8c959f]">
                          {t('tasks.dev.groups.selected_n', {
                            count: draftCommits.size,
                          })}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => setEditingId(null)}
                            disabled={busy !== null}
                            className="px-2 py-1 rounded-md text-[11px] border border-[#d0d7de] text-[#57606a] hover:bg-[#f6f8fa] transition disabled:opacity-50"
                          >
                            {t('tasks.dev.groups.cancel')}
                          </button>
                          <button
                            onClick={() => saveGroup(group)}
                            disabled={busy !== null}
                            className="px-2 py-1 rounded-md text-[11px] font-semibold bg-[#0969da] text-white hover:bg-[#0861c5] transition disabled:opacity-50 inline-flex items-center gap-1"
                          >
                            {busyHere ? (
                              <Loader2 size={11} className="animate-spin" />
                            ) : (
                              <Check size={11} />
                            )}
                            {t('tasks.dev.groups.save')}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {data?.ungrouped && data.ungrouped.length > 0 && (
        <details className="text-[11px] text-[#636c76] group">
          <summary className="cursor-pointer inline-flex items-center gap-1 select-none hover:text-[#1f2328]">
            <ChevronRight size={11} className="group-open:rotate-90 transition-transform" />
            {t('tasks.dev.groups.ungrouped_n', {
              count: data.ungrouped.length,
            })}
          </summary>
          <div className="mt-1.5 pl-4 space-y-1">
            {data.ungrouped.map((commit) => (
              <div key={commit.id} className="flex items-center gap-2 min-w-0">
                <ShortSha value={commit.sha} />
                <span className="truncate">{commit.message || '—'}</span>
                <TypeBadge type={commit.commit_type} />
              </div>
            ))}
          </div>
        </details>
      )}

      {data?.model_used === 'lexical' && data.available && (
        <p className="text-[10px] text-[#9a6700]">
          {t('tasks.dev.groups.lexical_hint')}
        </p>
      )}

      {graphGroup && (
        <GroupGraphModal
          group={
            data?.groups.find((group) => group.id === graphGroup.id) || graphGroup
          }
          title={displayTitle(
            data?.groups.find((group) => group.id === graphGroup.id) || graphGroup
          )}
          allCommits={commits}
          onClose={() => setGraphGroup(null)}
        />
      )}
    </section>
  );
}
