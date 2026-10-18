import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import enTranslations from './en.json';
import ruTranslations from './ru.json';

// Тип import.meta.hot есть только при разработке (vite). В сборке
// объявление не нужно, но без него tsc ругается на обращение.
declare global {
  interface ImportMeta {
    hot?: {
      accept: (deps: string[], callback: () => void) => void;
    };
  }
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: enTranslations },
      ru: { translation: ruTranslations },
    },
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  });

export default i18n;

// Переводы — обычный статический импорт, а i18next инициализируется один
// раз на загрузку модуля. Поэтому при правке ru.json/en.json горячая
// перезагрузка подменяет файл, но не пересоздаёт i18n, и в интерфейсе
// появляются сырые ключи вида projects.git.enrichment_title.
//
// Полная перезагрузка страницы после смены переводов — самое простое
// решение, которое точно работает: при разработке это мгновенно,
// а в сборке ветка не выполняется вовсе.
if (import.meta.hot) {
  import.meta.hot.accept(['./ru.json', './en.json'], () => {
    window.location.reload();
  });
}
