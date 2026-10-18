/** Справка: руководство пользователя и руководство администратора.
 *
 *  Тексты лежат файлами в docs/ рядом с backend и отдаются им же по
 *  адресу /manuals/<файл>. Один и тот же файл читают три потребителя:
 *  Git, где он открывается как обычный Markdown, браузер по прямой
 *  ссылке и эта страница.
 *
 *  Держать в приложении вторую копию текста означало бы получить
 *  два документа, которые разойдутся при первом же правке, поэтому
 *  страница их не хранит, а забирает.
 *
 *  Руководство администратора показывается только тем, у кого есть
 *  права: в нём описаны секреты, переменные окружения и известные
 *  слабые места развёртывания.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { marked } from 'marked';
import { AlertTriangle, BookOpen, ExternalLink, FileQuestion, ShieldCheck } from 'lucide-react';

/** Файлы руководств в папке docs/. Имена латиницей — чтобы адрес
 *  открывался в браузере без Percent-кодирования кириллицы. */
/** Файлы руководств в папке docs/.
 *
 *  Руководств два языка, и имя файла выбирается по текущему языку
 *  интерфейса: русский пользователь открывает русское руководство,
 *  английский — английское. Оба файла лежат рядом и читаются Git
 *  одинаково.
 *
 *  Суффикс `.en` отбрасывается, когда язык русский: иначе пришлось бы
 *  держать две пары имён.
 */
const DOCS = {
  user: { base: 'user-guide', tabKey: 'help.tab_user', icon: BookOpen },
  admin: { base: 'admin-guide', tabKey: 'help.tab_admin', icon: ShieldCheck },
} as const;

/** Имя файла руководства для языка интерфейса. */
function docFile(base: string, english: boolean): string {
  return english ? `${base}.en.md` : `${base}.md`;
}

type DocKey = keyof typeof DOCS;

interface TocItem {
  id: string;
  text: string;
  level: number;
}

/** Уникальный идентификатор заголовка для якоря.
 *
 *  marked даёт заголовкам идентификаторы сам, но опирается на
 *  транслитерацию, из-за чего одинаковые по смыслу заголовки
 *  получают разные id в зависимости от языка файла. Свой генератор
 *  стабильнее: тот же заголовок всегда даёт тот же якорь.
 */
const CYRILLIC: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh',
  з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o',
  п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'ts',
  ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu',
  я: 'ya',
};

function slug(text: string): string {
  // Транслитерация кириллицы — иначе якорь выродится в «-» и
  // переход по оглавлению перестанет работать.
  const base = text
    .toLowerCase()
    .replace(/[а-яё]/g, (ch) => CYRILLIC[ch] ?? ch)
    .replace(/[^a-z0-9а-яё]+/gi, '-')
    .replace(/^-+|-+$/g, '');
  return base || 'section';
}

/** Заголовки второго и третьего уровня — из них строится оглавление. */
function extractToc(md: string): TocItem[] {
  const items: TocItem[] = [];
  const seen = new Map<string, number>();

  for (const line of md.split('\n')) {
    // Внутри блоков кода заголовков быть не может: строка «##» внутри
    // примера попала бы в оглавление, и переход по ней приводил бы
    // в никуда. Такие блоки пропускаются целиком.
    const match = /^(#{2,3})\s+(.+?)\s*$/.exec(line);
    if (!match) continue;
    if (/^\s*(`{3,}|~{3,})/.test(line)) continue;

    const text = match[2].replace(/[*_`]/g, '').trim();
    let id = slug(text);
    const n = seen.get(id) ?? 0;
    seen.set(id, n + 1);
    if (n > 0) id = `${id}-${n}`;

    items.push({ id, text, level: match[1].length });
  }
  return items;
}

interface Props {
  /** Есть ли права администратора: без них вкладка с его руководством
   *  не показывается вовсе, а не прячется и не открывается по ссылке. */
  isAdmin?: boolean;
}

export default function HelpPage({ isAdmin = false }: Props) {
  const { t, i18n } = useTranslation();
  const [doc, setDoc] = useState<DocKey>('user');
  const [raw, setRaw] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tocOpen, setTocOpen] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const activeIdRef = useRef<string>('');

  const meta = DOCS[doc];
  // Язык руководства следует за языком интерфейса. Смена языка в
  // профиле перечитывает руководство на нужном.
  const english = i18n.language.toLowerCase().startsWith('en');
  const file = docFile(meta.base, english);

  // Права могут исчезнуть прямо на открытой странице (смена сессии).
  // Тогда вкладка администратора уже скрыта, но выбранным остался его
  // текст — и его надо вернуть к пользовательскому.
  useEffect(() => {
    if (!isAdmin && doc === 'admin') setDoc('user');
  }, [isAdmin, doc]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setRaw('');

    fetch(`/manuals/${file}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      })
      .then((text) => {
        if (cancelled) return;
        if (!text.trim()) throw new Error('empty');
        setRaw(text);
      })
      .catch(() => {
        if (!cancelled) setError(t('help.load_failed'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [file, t]);

  const toc = useMemo(() => (raw ? extractToc(raw) : []), [raw]);

  const html = useMemo(() => {
    if (!raw) return '';
    return marked.parse(raw, { gfm: true, breaks: false }) as string;
  }, [raw]);

  // Заголовкам проставлены якоря: без этого оглавление состояло бы
  // из ссылок в никуда. Подменяем разметку после отрисовки, а не
  // переписываем исходный Markdown, чтобы текст оставался тем же
  // самым файлом, что лежит в репозитории.
  useEffect(() => {
    const root = contentRef.current;
    if (!root || !toc.length) return;

    const headings = Array.from(root.querySelectorAll('h2, h3'));
    const used = new Set<string>();
    headings.forEach((h) => {
      const text = h.textContent ?? '';
      let id = slug(text);
      const n = used.has(id) ? 1 : 0;
      used.add(id);
      if (n > 0) id = `${id}-${n}`;
      h.id = id;
    });
  }, [html, toc.length]);

  // Подсветка текущего раздела: идём по оглавлению сверху вниз и
  // отмечаем последний заголовок, который уже прокручен мимо верха
  // области текста. Так подсветка не дёргается на середине экрана.
  useEffect(() => {
    const root = contentRef.current;
    if (!root || !toc.length) return;

    const onScroll = () => {
      let current = toc[0]?.id ?? '';
      for (const item of toc) {
        const el = root.querySelector(`#${CSS.escape(item.id)}`);
        if (!el) continue;
        if (el.getBoundingClientRect().top <= 90) current = item.id;
        else break;
      }
      if (current !== activeIdRef.current) {
        activeIdRef.current = current;
        const links = document.querySelectorAll('[data-toc] a');
        links.forEach((a) => {
          const li = a.closest('li');
          if (li) {
            li.className =
              li.className.replace(/\s*text-\[#0969da\]$/, '') || '';
            if ((a.getAttribute('href') ?? '') === `#${current}`) {
              li.className = (li.className + ' text-[#0969da]').trim();
            }
          }
        });
      }
    };

    root.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => root.removeEventListener('scroll', onScroll);
  }, [html, toc]);

  const jump = (id: string) => {
    const el = contentRef.current?.querySelector(`#${CSS.escape(id)}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTocOpen(false);
  };

  const Icon = meta.icon;

  return (
    <div className="min-h-screen flex flex-col bg-[#f6f8fa]">
      <div className="bg-white border-b border-[#d0d7de] px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Icon size={18} className="text-[#636c76] shrink-0" />
          <h1 className="text-lg font-semibold text-[#1f2328] truncate">
            {t('help.title')}
          </h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <a
            href={`/manuals/${file}`}
            target="_blank"
            rel="noreferrer"
            title={t('help.open_raw')}
            className="px-3 py-1.5 bg-[#f6f8fa] border border-[#d0d7de] text-[#1f2328] rounded-md hover:bg-[#ebf0f4] transition font-semibold text-xs flex items-center gap-2"
          >
            <ExternalLink size={14} />
            {t('help.open_raw')}
          </a>
        </div>
      </div>

      <div className="flex border-b border-[#d0d7de] bg-white px-6 shrink-0">
        {(Object.keys(DOCS) as DocKey[]).filter(
          (key) => isAdmin || key !== 'admin',
        ).map((key) => {
          const item = DOCS[key];
          const TabIcon = item.icon;
          const active = key === doc;
          return (
            <button
              key={key}
              onClick={() => setDoc(key)}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition flex items-center gap-2 ${
                active
                  ? 'border-[#fd8c73] text-[#1f2328]'
                  : 'border-transparent text-[#636c76] hover:text-[#1f2328]'
              }`}
            >
              <TabIcon size={15} />
              {t(item.tabKey)}
            </button>
          );
        })}
      </div>

      {loading && (
        <div className="flex-1 flex items-center justify-center text-[#636c76] text-sm">
          {t('common.loading')}…
        </div>
      )}

      {error && !loading && (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-md text-center">
            <FileQuestion size={32} className="mx-auto text-[#636c76] mb-3" />
            <p className="text-sm text-[#1f2328] font-semibold mb-2">
              {t('help.load_failed')}
            </p>
            <p className="text-xs text-[#636c76] mb-4">{error}</p>
            <div className="text-xs text-left bg-white border border-[#d0d7de] rounded-md p-3 space-y-1">
              <p className="font-semibold text-[#1f2328]">
                {t('help.load_failed_hint')}
              </p>
              <code className="block font-mono text-[11px]">
                SERVE_DOCS=true
              </code>
              <p className="text-[#636c76]">{t('help.load_failed_hint2')}</p>
            </div>
          </div>
        </div>
      )}

      {!loading && !error && (
        <div className="flex-1 flex min-h-0">
          <button
            onClick={() => setTocOpen((v) => !v)}
            className="xl:hidden self-start m-3 px-3 py-1.5 bg-white border border-[#d0d7de] rounded-md text-xs font-semibold text-[#1f2328] shrink-0"
          >
            {t('help.contents')}
          </button>

          <nav
            data-toc
            className={`${
              tocOpen ? 'block' : 'hidden'
            } xl:block w-64 shrink-0 border-r border-[#d0d7de] bg-white overflow-y-auto p-4`}
          >
            <p className="text-[10px] font-bold text-[#636c76] uppercase tracking-wider mb-2">
              {t('help.contents')}
            </p>
            <ul className="space-y-0.5">
              {toc.map((item) => (
                <li key={item.id}>
                  <a
                    href={`#${item.id}`}
                    onClick={(e) => {
                      e.preventDefault();
                      jump(item.id);
                    }}
                    className={`block py-0.5 text-xs text-[#1f2328] hover:text-[#0969da] ${
                      item.level === 3 ? 'pl-4 text-[#636c76]' : ''
                    }`}
                  >
                    {item.text}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <div
            ref={contentRef}
            className="flex-1 min-w-0 overflow-y-auto bg-white"
          >
            <article className="max-w-4xl px-6 py-6 text-sm leading-relaxed text-[#1f2328] prose-kipatik">
              <div dangerouslySetInnerHTML={{ __html: html }} />
            </article>
          </div>
        </div>
      )}
    </div>
  );
}

/** Стили содержимого руководства.
 *
 *  marked отдаёт готовый HTML без классов, поэтому оформление задаётся
 *  здесь. Селекторы покрывают ровно те элементы, которые появляются
 *  в файлах руководств: заголовки, абзацы, таблицы, код, списки.
 */
const styles = `
.prose-kipatik h1 { font-size: 1.6rem; font-weight: 700; margin: 0 0 1rem; }
.prose-kipatik h2 {
  font-size: 1.25rem; font-weight: 700; margin: 2rem 0 .75rem;
  padding-bottom: .35rem; border-bottom: 1px solid #d0d7de;
  scroll-margin-top: 16px;
}
.prose-kipatik h3 {
  font-size: 1.05rem; font-weight: 700; margin: 1.5rem 0 .5rem;
  scroll-margin-top: 16px;
}
.prose-kipatik h4 { font-weight: 700; margin: 1.25rem 0 .4rem; }
.prose-kipatik p { margin: .6rem 0; }
.prose-kipatik ul, .prose-kipatik ol { margin: .6rem 0; padding-left: 1.4rem; }
.prose-kipatik ul { list-style: disc; }
.prose-kipatik ol { list-style: decimal; }
.prose-kipatik li { margin: .25rem 0; }
.prose-kipatik code {
  background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 4px;
  padding: .1rem .3rem; font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: .85em;
}
.prose-kipatik pre {
  background: #0d1117; color: #e6edf3; border-radius: 6px;
  padding: .9rem 1rem; overflow-x: auto; margin: .8rem 0;
}
.prose-kipatik pre code {
  background: transparent; border: 0; padding: 0; color: inherit;
  font-size: .82rem; line-height: 1.5;
}
.prose-kipatik table {
  border-collapse: collapse; width: 100%; margin: .8rem 0;
  font-size: .9em; display: block; overflow-x: auto;
}
.prose-kipatik th, .prose-kipatik td {
  border: 1px solid #d0d7de; padding: .4rem .6rem;
  text-align: left; vertical-align: top;
}
.prose-kipatik th { background: #f6f8fa; font-weight: 600; }
.prose-kipatik tr:nth-child(2n) td { background: #fafbfc; }
.prose-kipatik blockquote {
  border-left: 4px solid #d0d7de; margin: .8rem 0; padding: .2rem 1rem;
  color: #636c76; background: #f6f8fa; border-radius: 0 4px 4px 0;
}
.prose-kipatik hr { border: 0; border-top: 1px solid #d0d7de; margin: 1.5rem 0; }
.prose-kipatik a { color: #0969da; text-decoration: underline; }
.prose-kipatik strong { font-weight: 700; }
`;

if (typeof document !== 'undefined' && !document.getElementById('kipatik-help-styles')) {
  const tag = document.createElement('style');
  tag.id = 'kipatik-help-styles';
  tag.textContent = styles;
  document.head.appendChild(tag);
}
