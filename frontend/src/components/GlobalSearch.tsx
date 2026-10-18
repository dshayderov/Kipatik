/** Поиск задач для строки в шапке.
 *
 *  Раньше в шапке стояла пустая строка ввода: элемент выглядел как
 *  поиск, но ничего не делал. Теперь запрос уходит на сервер и находит
 *  задачи по всем проектам, где пользователь участник, — строка стоит
 *  в шапке и работает на всех страницах, в том числе там, где проект не
 *  выбран.
 *
 *  Переход по результату идёт на страницу проекта с параметром
 *  taskId: модальное окно задачи уже умеет открываться таким образом,
 *  отдельно городить второе окно незачем.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, Search } from 'lucide-react';
import api from '../api/client';

interface SearchHit {
  task_id: number;
  title: string;
  task_type?: string | null;
  priority: number;
  project_id: number;
  project_name: string;
}

export default function GlobalSearch() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  // Запрос откладывается: без этого на каждую букву уходил бы запрос.
  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setHits([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const timer = setTimeout(async () => {
      try {
        const { data } = await api.get('/tasks/search', {
          params: { q: text, limit: 12 },
        });
        if (!cancelled) setHits(data || []);
      } catch (err: any) {
        if (!cancelled) {
          setHits([]);
          setError(
            err?.response?.data?.detail || t('common.search_failed'),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, t]);

  // Клик вне поля закрывает выдачу. Без этого она оставалась бы висеть
  // поверх страницы после перехода.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const goTo = (hit: SearchHit) => {
    setOpen(false);
    setQuery('');
    setHits([]);
    navigate(`/project/${hit.project_id}?taskId=${hit.task_id}`);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setOpen(false);
      setQuery('');
    }
    if (e.key === 'Enter' && hits.length > 0) {
      e.preventDefault();
      goTo(hits[0]);
    }
  };

  return (
    <div className="relative hidden md:block" ref={boxRef}>
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={t('common.search')}
        className="bg-[#0d1117] border border-[#30363d] rounded-md pl-8 pr-8 py-1 text-xs w-64 focus:w-80 transition-all focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      {loading && (
        <Loader2
          size={14}
          className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-blue-400"
        />
      )}

      {open && query.trim().length >= 2 && (
        <div className="absolute right-0 mt-1 w-96 bg-white border border-[#d0d7de] rounded-lg shadow-lg overflow-hidden z-50 text-[#1f2328]">
          {error ? (
            <p className="px-3 py-3 text-xs text-red-700 bg-red-50">{error}</p>
          ) : !loading && hits.length === 0 ? (
            <p className="px-3 py-4 text-xs text-[#636c76] text-center">
              {t('common.search_nothing')}
            </p>
          ) : (
            <div className="max-h-80 overflow-y-auto">
              {hits.map((hit) => (
                <button
                  key={hit.task_id}
                  onClick={() => goTo(hit)}
                  className="w-full text-left px-3 py-2 hover:bg-[#f6f8fa] border-b border-[#d0d7de]/40 last:border-b-0"
                >
                  <div className="text-xs font-semibold text-[#1f2328] truncate">
                    {hit.title}
                  </div>
                  <div className="text-[10px] text-[#636c76] mt-0.5 truncate">
                    {hit.project_name}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}