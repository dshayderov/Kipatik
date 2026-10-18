/** Тест логики фильтра задач.
 *
 *  Модуль src/taskFilters.ts не зависит ни от React, ни от переводов,
 *  поэтому его можно собрать esbuild и прогнать в обычном node — без
 *  браузера и без запуска dev-сервера.
 */
import {
  EMPTY_FILTERS,
  countActiveFilters,
  filterTasks,
  taskMatches,
} from '../src/taskFilters';
import type { Task } from '../src/types';

const DAY = 24 * 60 * 60 * 1000;

function task(id: number, over: Partial<Task> = {}): Task {
  return {
    id,
    title: `Задача ${id}`,
    priority: 1,
    project_id: 1,
    column_id: 1,
    created_at: '2026-01-01T00:00:00Z',
    subtasks: [],
    comments: [],
    ...over,
  } as Task;
}

/** Дата в прошлом/будущем — чтобы проверка просроченности не зависела от часов. */
const past = new Date(Date.now() - 5 * DAY).toISOString();
const future = new Date(Date.now() + 5 * DAY).toISOString();

const results: [string, boolean][] = [];

function check(name: string, cond: boolean, extra: unknown = '') {
  results.push([name, cond]);
  console.log(
    `  ${cond ? 'OK  ' : 'FAIL'}  ${name}${extra !== '' ? ' — ' + String(extra) : ''}`,
  );
}

const SAMPLE: Task[] = [
  task(1, { assignee_id: 7, priority: 3, task_type: 'bugfix', due_date: past }),
  task(2, { assignee_id: 8, priority: 1, task_type: 'docs' }),
  task(3, { assignee_id: 7, priority: 2, task_type: 'chore', due_date: future }),
  task(4, { priority: 3, task_type: 'feature' }), // без исполнителя и без срока
  task(5, { assignee_id: 8, priority: 2, task_type: 'test', due_date: past }),
];

console.log('=== пустой фильтр ничего не убирает ===');
check('все 5 задач на месте', filterTasks(SAMPLE, EMPTY_FILTERS)!.length === 5);
check('возвращается тот же массив, не копия',
  filterTasks(SAMPLE, EMPTY_FILTERS) === SAMPLE);
check('countActiveFilters = 0', countActiveFilters(EMPTY_FILTERS) === 0);

console.log('\n=== по исполнителю ===');
const by7 = { ...EMPTY_FILTERS, assignees: [7] };
check('исполнитель 7 → задачи 1 и 3',
  JSON.stringify(filterTasks(SAMPLE, by7)!.map((t) => t.id)) === '[1,3]',
  filterTasks(SAMPLE, by7)!.map((t) => t.id).join(','));

const by7and8 = { ...EMPTY_FILTERS, assignees: [7, 8] };
check('исполнители 7 и 8 → задачи 1, 2, 3, 5 (без исполнителя исключена)',
  JSON.stringify(filterTasks(SAMPLE, by7and8)!.map((t) => t.id)) === '[1,2,3,5]',
  filterTasks(SAMPLE, by7and8)!.map((t) => t.id).join(','));

check('задача без исполнителя отбрасывается при выборе',
  taskMatches(SAMPLE[3], by7) === false);
check('задача чужого исполнителя отбрасывается',
  taskMatches(SAMPLE[1], by7) === false);

console.log('\n=== по приоритету ===');
const high = { ...EMPTY_FILTERS, priorities: [3] };
check('высокий → задачи 1 и 4',
  JSON.stringify(filterTasks(SAMPLE, high)!.map((t) => t.id)) === '[1,4]',
  filterTasks(SAMPLE, high)!.map((t) => t.id).join(','));

const highLow = { ...EMPTY_FILTERS, priorities: [1, 3] };
check('высокий и низкий → 1, 2, 4 (логика ИЛИ внутри признака)',
  JSON.stringify(filterTasks(SAMPLE, highLow)!.map((t) => t.id)) === '[1,2,4]',
  filterTasks(SAMPLE, highLow)!.map((t) => t.id).join(','));

console.log('\n=== по типу ===');
const byType = { ...EMPTY_FILTERS, types: ['bugfix' as const] };
check('тип bugfix → задача 1',
  JSON.stringify(filterTasks(SAMPLE, byType)!.map((t) => t.id)) === '[1]');
check('задача без типа отбрасывается при выборе типа',
  taskMatches(task(6, { priority: 1 }), byType) === false);

console.log('\n=== просроченные ===');
const overdue = { ...EMPTY_FILTERS, overdue: true };
check('просроченные → задачи 1 и 5',
  JSON.stringify(filterTasks(SAMPLE, overdue)!.map((t) => t.id)) === '[1,5]',
  filterTasks(SAMPLE, overdue)!.map((t) => t.id).join(','));
check('задача без срока не считается просроченной',
  taskMatches(task(7, { priority: 1 }), overdue) === false);
check('будущий срок не просрочен',
  taskMatches(SAMPLE[2], overdue) === false);

console.log('\n=== признаки складываются по И ===');
const combo = { ...EMPTY_FILTERS, assignees: [7], priorities: [3], overdue: true };
check('исполнитель 7 + высокий + просроченная → задача 1',
  JSON.stringify(filterTasks(SAMPLE, combo)!.map((t) => t.id)) === '[1]',
  filterTasks(SAMPLE, combo)!.map((t) => t.id).join(','));
check('счётчик считает каждый признак', countActiveFilters(combo) === 3,
  countActiveFilters(combo));

console.log('\n=== счётчик на кнопке ===');
check('пустой → 0', countActiveFilters(EMPTY_FILTERS) === 0);
check('два типа и просрочка → 3',
  countActiveFilters({ ...EMPTY_FILTERS, types: ['bugfix', 'feature'], overdue: true }) === 3);
check('два исполнителя → 2',
  countActiveFilters({ ...EMPTY_FILTERS, assignees: [1, 2] }) === 2);

console.log('\n=== крайние случаи ===');
check('undefined задачи не падает', filterTasks(undefined, by7) === undefined);
check('пустой список задач', (filterTasks([], by7) ?? []).length === 0);
check('исходный список не меняется',
  (() => {
    const copy = SAMPLE.map((t) => t.id);
    filterTasks(SAMPLE, { ...EMPTY_FILTERS, assignees: [7] });
    return JSON.stringify(SAMPLE.map((t) => t.id)) === JSON.stringify(copy);
  })());

console.log('\n' + '='.repeat(60));
const failed = results.filter(([, ok]) => !ok);
console.log(`ИТОГ: ${results.length - failed.length}/${results.length} проверок пройдено`);
for (const [n] of failed) console.log(`  ПРОВАЛ: ${n}`);
if (failed.length > 0) process.exit(1);