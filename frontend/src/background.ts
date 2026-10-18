/** Фон страницы проекта.
 *
 *  Адрес базового фона и способ его наложения живут здесь одним
 *  файлом, потому что используются в двух местах: на самой странице
 *  проекта и в превью выбора фона в настройках. Если бы они были
 *  написаны дважды, превью рано или поздно перестало бы совпадать с
 *  тем, что увидят остальные участники.
 */
import type { CSSProperties } from 'react';

export type ProjectBackground = 'none' | 'default' | 'custom';

/** Базовый фон из поставки (public/backgrounds). */
export const DEFAULT_BACKGROUND_URL = '/backgrounds/project-default.jpg';

/** Виды фона, которые сервер принимает в обычном обновлении проекта.
 *  «custom» среди них нет: он ставится только загрузкой файла. */
export const BACKGROUND_KINDS = ['none', 'default'] as const;

/** Раскладывает адрес картинки по виду фона.
 *
 *  Свой фон берётся только когда вид действительно custom и адрес
 *  есть: иначе на страницу попал бы адрес из устаревших данных, а
 *  фон молча пропал бы вместо того, чтобы показаться белым. */
export function backgroundImageUrl(
  kind: ProjectBackground | undefined,
  url?: string | null,
): string | null {
  if (kind === 'default') return DEFAULT_BACKGROUND_URL;
  if (kind === 'custom' && url) return url;
  return null;
}

/** Стиль фона для страницы проекта.
 *
 *  cover + center top: картинка не повторяется и не оставляет полей.
 *  fixed держит фон на месте при прокрутке доски — иначе декоративные
 *  углы уезжали бы вверх и фон выглядел бы обрезанным.
 */
export function projectBackgroundStyle(
  kind: ProjectBackground | undefined,
  url?: string | null,
): CSSProperties {
  const image = backgroundImageUrl(kind, url);
  if (!image) return {};
  return {
    backgroundImage: `url("${image}")`,
    backgroundSize: 'cover',
    backgroundPosition: 'center top',
    backgroundRepeat: 'no-repeat',
    backgroundAttachment: 'fixed',
  };
}