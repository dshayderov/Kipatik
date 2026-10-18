/** Логика фильтрации задач.
 *
 *  Вынесена отдельно от компонента панели фильтра намеренно: здесь нет
 *  ни React, ни переводов, только проверки на данных задачи. Так её можно
 *  прогнать тестом без браузера и без поднятия интерфейса.
 *
 *  Признаки, по которым фильтруем: исполнитель, приоритет, тип задачи и
 *  просроченность. Пустой список по признаку означает «любой», поэтому
 *  пустое состояние фильтра — это «видно всё» и сбрасывать его вручную
 *  не нужно.
 */
import type { Task } from './types';
import type { TaskType } from './types/taskType';

export interface TaskFilters {
  /** Пустой массив означает «все исполнители». */
  assignees: number[];
  /** Пустой массив означает «все приоритеты». */
  priorities: number[];
  /** Пустой массив означает «все типы». */
  types: TaskType[];
  /** Только задачи, у которых срок уже прошёл. */
  overdue: boolean;
}

export const EMPTY_FILTERS: TaskFilters = {
  assignees: [],
  priorities: [],
  types: [],
  overdue: false,
};

/** Приоритеты: в модели 1 — низкий, 2 — средний, 3 — высокий. */
export const PRIORITIES: { value: number; labelKey: string }[] = [
  { value: 1, labelKey: 'tasks.low' },
  { value: 2, labelKey: 'tasks.medium' },
  { value: 3, labelKey: 'tasks.high' },
];

/** Сколько признаков включено — показывается счётчиком на кнопке. */
export function countActiveFilters(f: TaskFilters): number {
  return (
    f.assignees.length +
    f.priorities.length +
    f.types.length +
    (f.overdue ? 1 : 0)
  );
}

/** Проверка одной задачи. */
export function taskMatches(task: Task, f: TaskFilters): boolean {
  if (f.assignees.length > 0) {
    // Задача без исполнителя отбрасывается, если выбран хоть кто-то:
    // иначе фильтр «по моему исполнителю» молча показывал бы чужие и
    // неназначенные задачи.
    if (!task.assignee_id || !f.assignees.includes(task.assignee_id)) return false;
  }
  if (f.priorities.length > 0 && !f.priorities.includes(task.priority)) {
    return false;
  }
  if (f.types.length > 0) {
    if (!task.task_type || !f.types.includes(task.task_type as TaskType)) return false;
  }
  if (f.overdue) {
    if (!task.due_date) return false;
    if (new Date(task.due_date).getTime() >= Date.now()) return false;
  }
  return true;
}

/** Отбор из списка задач проекта. */
export function filterTasks(
  tasks: Task[] | undefined,
  f: TaskFilters,
): Task[] | undefined {
  if (!tasks) return tasks;
  // Без активных признаков возвращаем исходный массив, а не его копию:
  // так дешёвая проверка не мешает отрисовке и не ломает сравнения.
  if (countActiveFilters(f) === 0) return tasks;
  return tasks.filter((t) => taskMatches(t, f));
}