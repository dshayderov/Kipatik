/**
 * Типы задачи.
 *
 * Набор совпадает с типами, которые классификатор определяет для
 * коммитов (bugfix, feature, refactor, docs, test, chore). Совпадение
 * не случайно: оно позволяет сравнивать, что заявил человек в задаче,
 * с тем, что модель насчитала по её коммитам. Расхождение «задача —
 * дефект, а коммиты — функциональность» измеряется и показывается
 * в отчёте.
 *
 * Ключи строковые и совпадают с backend (app/schemas/task.py).
 * Backend отклоняет значения вне списка с 422, поэтому здесь набор —
 * единственное место, где его нужно править при расширении.
 */
export type TaskType = 'bugfix' | 'feature' | 'refactor' | 'docs' | 'test' | 'chore';

export const TASK_TYPES: readonly TaskType[] = [
  'bugfix',
  'feature',
  'refactor',
  'docs',
  'test',
  'chore',
] as const;

/**
 * Оформление бейджа и точки в форме выбора.
 *
 * Единственная палитра для обоих применений: бейдж типа на карточке
 * задачи и бейдж типа у коммита в блоке «Разработка». Раньше палитры
 * были разными, из-за чего один и тот же тип выглядел на доске одним
 * цветом, а в списке коммитов другим.
 *
 * Оттенки приглушённые: карточка — это фон, и насыщенные цвета
 * перетягивают внимание с заголовка задачи.
 */
export const TASK_TYPE_STYLE: Record<TaskType, { badge: string; dot: string }> = {
  bugfix: {
    badge: 'bg-[#ffebe9] text-[#cf222e] border-[#ff818266]',
    dot: 'bg-red-500',
  },
  feature: {
    badge: 'bg-[#ddf4ff] text-[#0969da] border-[#54aeff4d]',
    dot: 'bg-blue-400',
  },
  refactor: {
    badge: 'bg-[#dbeafe] text-[#1d4ed8] border-[#93c5fd80]',
    dot: 'bg-indigo-400',
  },
  docs: {
    badge: 'bg-[#f3e8ff] text-[#6b21a8] border-[#c084fc80]',
    dot: 'bg-purple-400',
  },
  test: {
    badge: 'bg-[#e6f6ec] text-[#1a7f37] border-[#7ee2a880]',
    dot: 'bg-green-500',
  },
  chore: {
    badge: 'bg-[#f6f8fa] text-[#57606a] border-[#d0d7de]',
    dot: 'bg-gray-400',
  },
};

/** Классы для выбранного пункта в форме выбора. */
export function selectedTaskTypeClass(type: TaskType): string {
  const map: Record<TaskType, string> = {
    bugfix: 'bg-red-50 border-red-200 text-red-700 ring-1 ring-red-100',
    feature: 'bg-blue-50 border-blue-200 text-blue-700 ring-1 ring-blue-100',
    refactor: 'bg-indigo-50 border-indigo-200 text-indigo-700 ring-1 ring-indigo-100',
    docs: 'bg-purple-50 border-purple-200 text-purple-700 ring-1 ring-purple-100',
    test: 'bg-green-50 border-green-200 text-green-700 ring-1 ring-green-100',
    chore: 'bg-gray-100 border-gray-300 text-gray-700 ring-1 ring-gray-200',
  };
  return map[type];
}