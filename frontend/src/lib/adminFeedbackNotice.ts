const ADMIN_FEEDBACK_COUNT_KEY = "adminUnresolvedFeedbackCount";
const ADMIN_FEEDBACK_EVENT = "admin-unresolved-feedback-count-change";

function isBrowser() {
  return typeof window !== "undefined";
}

export function getStoredAdminUnresolvedFeedbackCount(): number {
  if (!isBrowser()) return 0;
  const raw = window.localStorage.getItem(ADMIN_FEEDBACK_COUNT_KEY);
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function setStoredAdminUnresolvedFeedbackCount(count: number): number {
  if (!isBrowser()) return 0;
  const normalized = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
  window.localStorage.setItem(ADMIN_FEEDBACK_COUNT_KEY, String(normalized));
  window.dispatchEvent(
    new CustomEvent<number>(ADMIN_FEEDBACK_EVENT, {
      detail: normalized,
    }),
  );
  return normalized;
}

export function subscribeAdminUnresolvedFeedbackCount(callback: (count: number) => void): () => void {
  if (!isBrowser()) return () => {};

  const handleStorage = (event: StorageEvent) => {
    if (event.key !== ADMIN_FEEDBACK_COUNT_KEY) return;
    callback(getStoredAdminUnresolvedFeedbackCount());
  };

  const handleCustom = (event: Event) => {
    const nextCount = (event as CustomEvent<number>).detail;
    callback(Number.isFinite(nextCount) && nextCount > 0 ? Math.floor(nextCount) : 0);
  };

  window.addEventListener("storage", handleStorage);
  window.addEventListener(ADMIN_FEEDBACK_EVENT, handleCustom as EventListener);

  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(ADMIN_FEEDBACK_EVENT, handleCustom as EventListener);
  };
}
