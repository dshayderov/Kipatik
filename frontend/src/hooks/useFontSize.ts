import { useCallback, useEffect, useState } from 'react';

export const FONT_SIZE_STORAGE_KEY = 'ui_font_size';
export const FONT_SIZE_MIN = 13;
export const FONT_SIZE_MAX = 20;
export const FONT_SIZE_DEFAULT = 16;

export function clampFontSize(value: number): number {
  if (!Number.isFinite(value)) return FONT_SIZE_DEFAULT;
  return Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, Math.round(value)));
}

export function readStoredFontSize(): number {
  try {
    const raw = localStorage.getItem(FONT_SIZE_STORAGE_KEY);
    if (raw === null) return FONT_SIZE_DEFAULT;
    const parsed = parseInt(raw, 10);
    return clampFontSize(parsed);
  } catch {
    return FONT_SIZE_DEFAULT;
  }
}

/**
 * Масштабирует интерфейс через базовый размер шрифта <html>.
 * Размеры в rem (text-xs/sm/base/lg и т.д.) масштабируются,
 * фиксированные text-[10px] — нет.
 */
export function applyFontSize(size: number): void {
  document.documentElement.style.fontSize = `${clampFontSize(size)}px`;
}

/** Вызывается до первого рендера, чтобы не было «прыжка» шрифта */
export function initFontSize(): void {
  applyFontSize(readStoredFontSize());
}

export function useFontSize() {
  const [size, setSize] = useState<number>(() => readStoredFontSize());

  useEffect(() => {
    applyFontSize(size);
  }, [size]);

  const set = useCallback((value: number) => {
    const next = clampFontSize(value);
    setSize(next);
    applyFontSize(next);
    try {
      localStorage.setItem(FONT_SIZE_STORAGE_KEY, String(next));
    } catch {
      /* приватный режим браузера — просто не сохраняем */
    }
  }, []);

  const increase = useCallback(() => set(size + 1), [set, size]);
  const decrease = useCallback(() => set(size - 1), [set, size]);
  const reset = useCallback(() => set(FONT_SIZE_DEFAULT), [set]);

  return {
    size,
    set,
    increase,
    decrease,
    reset,
    min: FONT_SIZE_MIN,
    max: FONT_SIZE_MAX,
    isDefault: size === FONT_SIZE_DEFAULT,
    canIncrease: size < FONT_SIZE_MAX,
    canDecrease: size > FONT_SIZE_MIN,
  };
}
