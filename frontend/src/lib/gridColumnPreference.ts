export const GENERATE_RESULT_COLUMN_COUNT_KEY = "generateResultColumnCount";
export const HISTORY_GRID_COLUMN_COUNT_KEY = "historyGridColumnCount";

export function readStoredGridColumnCount<T extends number>(
  storageKey: string,
  allowedValues: readonly T[],
  fallback: T,
): T {
  if (typeof window === "undefined") return fallback;
  const raw = window.localStorage.getItem(storageKey);
  const parsed = Number(raw);
  if (allowedValues.includes(parsed as T)) {
    return parsed as T;
  }
  return fallback;
}

export function writeStoredGridColumnCount(storageKey: string, count: number) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(storageKey, String(count));
}
