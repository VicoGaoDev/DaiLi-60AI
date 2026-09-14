const USER_FEEDBACK_COUNT_KEY = "userCompletedUnreadFeedbackCount";
const USER_FEEDBACK_EVENT = "user-completed-unread-feedback-count-change";

function isBrowser() {
  return typeof window !== "undefined";
}

export function getStoredUserCompletedUnreadFeedbackCount(): number {
  if (!isBrowser()) return 0;
  const raw = window.localStorage.getItem(USER_FEEDBACK_COUNT_KEY);
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function setStoredUserCompletedUnreadFeedbackCount(count: number): number {
  if (!isBrowser()) return 0;
  const normalized = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
  window.localStorage.setItem(USER_FEEDBACK_COUNT_KEY, String(normalized));
  window.dispatchEvent(
    new CustomEvent<number>(USER_FEEDBACK_EVENT, {
      detail: normalized,
    }),
  );
  return normalized;
}

export function subscribeUserCompletedUnreadFeedbackCount(callback: (count: number) => void): () => void {
  if (!isBrowser()) return () => {};

  const handleStorage = (event: StorageEvent) => {
    if (event.key !== USER_FEEDBACK_COUNT_KEY) return;
    callback(getStoredUserCompletedUnreadFeedbackCount());
  };

  const handleCustom = (event: Event) => {
    const nextCount = (event as CustomEvent<number>).detail;
    callback(Number.isFinite(nextCount) && nextCount > 0 ? Math.floor(nextCount) : 0);
  };

  window.addEventListener("storage", handleStorage);
  window.addEventListener(USER_FEEDBACK_EVENT, handleCustom as EventListener);

  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(USER_FEEDBACK_EVENT, handleCustom as EventListener);
  };
}
