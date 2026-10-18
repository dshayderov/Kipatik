import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ChevronRight,
  ChevronDown,
  Gauge,
  Info,
  TrendingUp,
  AlertTriangle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api from '../api/client';

interface Props {
  taskId: number;
}

interface ProgressInput {
  commits: number;
  additions: number;
  deletions: number;
  lines_changed: number;
  expected_volume: number;
  expected_volume_source: string;
  expected_volume_sample: number;
  expected_volume_raw?: number | null;
  expected_volume_weight?: number;
  subtasks_total: number;
  subtasks_done: number;
  files_touched: number;
  files_mentioned: number;
  files_matched: number;
}

interface ProgressData {
  available: boolean;
  reason?: string;
  percent: number;
  confidence: 'high' | 'medium' | 'low';
  confidence_reasons: string[];
  components: {
    structural: number;
    volume: number;
    semantic: number;
    targeting: number;
    completion: number;
  };
  weights: { structural: number; completion: number };
  inputs: ProgressInput | null;
  days_since_last_commit: number | null;
  history: { date: string; lines: number; volume_ratio: number }[];
}

const CONFIDENCE_STYLE: Record<string, { dot: string; text: string }> = {
  high: { dot: 'bg-green-500', text: 'text-green-700' },
  medium: { dot: 'bg-amber-500', text: 'text-amber-700' },
  low: { dot: 'bg-[#afb8c1]', text: 'text-[#636c76]' },
};

/**
 * Блок оценки прогресса задачи.
 *
 * Данные приходят с /ai/task/{id}/progress. Показывать блок имеет смысл
 * только когда есть чем объяснять оценку: без привязанных коммитов
 * прогресс всегда ноль, и он только занимает место в карточке.
 */
export default function ProgressBlock({ taskId }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['task-progress', taskId],
    queryFn: async () => {
      const { data } = await api.get(`/ai/task/${taskId}/progress`);
      return data as ProgressData;
    },
    enabled: !!taskId,
  });

  if (isLoading) return null;
  if (!data || !data.available) return null;

  const inp = data.inputs;
  if (!inp) return null;

  // Без коммитов оценки нет: показывать нулевую полосу значило бы
  // утверждать, что задача не начата, хотя данных просто недостаточно.
  if (inp.commits === 0) {
    return (
      <section>
        <SectionTitle>{t('tasks.dev.progress')}</SectionTitle>
        <div className="p-3 bg-[#fff8c5] border border-[#d4a72c4d] rounded-lg text-xs text-[#735c0f] flex items-start gap-2">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" />
          {t('tasks.dev.progress_no_commits')}
        </div>
      </section>
    );
  }

  const pct = Math.round(data.percent);
  const conf = CONFIDENCE_STYLE[data.confidence] || CONFIDENCE_STYLE.low;
  const hasHistory = data.history.length > 0;

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <SectionTitle>
          <span className="flex items-center gap-1.5">
            <Gauge size={13} className="text-emerald-600" />
            {t('tasks.dev.progress')}
          </span>
        </SectionTitle>
        <span className={`flex items-center gap-1.5 text-[11px] font-bold ${conf.text}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${conf.dot}`} />
          {t(`tasks.dev.confidence.${data.confidence}`)}
        </span>
      </div>

      <div className="p-3 bg-white border border-[#d0d7de] rounded-lg space-y-2.5">
        {/* Полоса прогресса */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 bg-[#eaeef2] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all"
              style={{ width: `${Math.max(pct, pct > 0 ? 2 : 0)}%` }}
            />
          </div>
          <span className="text-xs font-bold text-[#1f2328] tabular-nums w-10 text-right">
            {pct}%
          </span>
        </div>

        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1 text-[11px] text-[#636c76] hover:text-[#0969da] transition"
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          {t('tasks.dev.progress_why')}
        </button>

        {open && (
          <div className="space-y-3 pt-1">
            {/* Составляющие.
                Подписи переименованы намеренно: «Файлы — 100%» читалось
                как «разработка закончена», хотя означало лишь попадание
                в названные в описании файлы. Теперь это видно из
                подписи, и семантика стоит там, где её роль —
                множитель прицельности, а не самостоятельный балл. */}
            <div className="grid grid-cols-3 gap-2">
              <Component
                label={t('tasks.dev.progress_subtasks')}
                value={data.components.structural}
                weight={data.weights.structural}
                note={
                  inp.subtasks_total > 0
                    ? `${inp.subtasks_done}/${inp.subtasks_total}`
                    : t('tasks.dev.progress_no_subtasks')
                }
              />
              <Component
                label={t('tasks.dev.progress_volume')}
                value={data.components.volume}
                weight={data.weights.completion}
                note={`${inp.lines_changed} / ${inp.expected_volume}`}
              />
              <Component
                label={t('tasks.dev.progress_targeting')}
                value={data.components.targeting}
                note={
                  inp.files_mentioned > 0
                    ? `${inp.files_matched}/${inp.files_mentioned}`
                    : t('tasks.dev.progress_no_files_named')
                }
              />
            </div>

            {/* Почему уверенность такая */}
            {data.confidence_reasons.length > 0 && (
              <div className="p-2.5 bg-[#f6f8fa] border border-[#d0d7de] rounded-lg">
                <p className="flex items-center gap-1.5 text-[11px] font-bold text-[#1f2328] mb-1.5">
                  <Info size={12} className="text-[#636c76]" />
                  {t('tasks.dev.progress_confidence_hint')}
                </p>
                <ul className="space-y-1">
                  {data.confidence_reasons.map((r) => (
                    <li key={r} className="text-[11px] text-[#636c76] leading-relaxed">
                      • {t(`tasks.dev.progress_reason.${r}`)}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Калибровка */}
            <p className="text-[10px] text-[#636c76] leading-relaxed">
              {t(`tasks.dev.progress_expected_source.${inp.expected_volume_source}`, {
                volume: inp.expected_volume,
                sample: inp.expected_volume_sample,
                raw: inp.expected_volume_raw ?? inp.expected_volume,
                weight: inp.expected_volume_weight ?? 0,
              })}
            </p>

            {/* Динамика */}
            {hasHistory && <ProgressSpark points={data.history.map((h) => h.volume_ratio)} t={t} />}

            {data.days_since_last_commit !== null && data.days_since_last_commit >= 4 && (
              <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5 flex items-center gap-1.5">
                <AlertTriangle size={12} className="shrink-0" />
                {t('tasks.dev.progress_idle_days', { days: data.days_since_last_commit })}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function Component({
  label,
  value,
  weight,
  note,
}: {
  label: string;
  value: number;
  /** Вес составляющей в итоговой формуле. Не передан — 1. */
  weight?: number;
  note: string;
}) {
  const inactive = weight === 0;
  return (
    <div
      className={`p-2 rounded-lg border ${
        inactive ? 'bg-[#f6f8fa] border-[#d0d7de]' : 'bg-white border-[#d0d7de]'
      }`}
    >
      <p className="text-[10px] font-bold text-[#636c76] uppercase truncate">{label}</p>
      <p
        className={`text-sm font-bold tabular-nums ${
          inactive ? 'text-[#afb8c1]' : 'text-[#1f2328]'
        }`}
      >
        {Math.round(value * 100)}%
      </p>
      <p className="text-[10px] text-[#636c76] truncate">{note}</p>
    </div>
  );
}

/** Мини-график накопления объёма по дням. */
function ProgressSpark({ points, t }: { points: number[]; t: any }) {
  if (points.length < 2) return null;

  const W = 100;
  const H = 28;
  const step = W / (points.length - 1);
  const coords = points.map((p, i) => `${(i * step).toFixed(2)},${(H - p * H).toFixed(2)}`);
  const path = `M ${coords.join(' L ')}`;

  return (
    <div>
      <p className="flex items-center gap-1 text-[10px] font-bold text-[#636c76] uppercase mb-1">
        <TrendingUp size={11} />
        {t('tasks.dev.progress_history')}
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="w-full h-7">
        <polyline
          points={coords.join(' ')}
          fill="none"
          stroke="#1a7f37"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[11px] font-bold text-[#636c76] uppercase tracking-wide">
      {children}
    </h3>
  );
}