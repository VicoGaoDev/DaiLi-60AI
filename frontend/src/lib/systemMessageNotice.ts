const SYSTEM_MESSAGE_COUNT_KEY = "userUnreadSystemMessageCount";
const SYSTEM_MESSAGE_EVENT = "user-unread-system-message-count-change";

function isBrowser() {
  return typeof window !== "undefined";
}

export function getStoredUnreadSystemMessageCount(): number {
  if (!isBrowser()) return 0;
  const raw = window.localStorage.getItem(SYSTEM_MESSAGE_COUNT_KEY);
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function setStoredUnreadSystemMessageCount(count: number): number {
  if (!isBrowser()) return 0;
  const normalized = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
  window.localStorage.setItem(SYSTEM_MESSAGE_COUNT_KEY, String(normalized));
  window.dispatchEvent(
    new CustomEvent<number>(SYSTEM_MESSAGE_EVENT, {
      detail: normalized,
    }),
  );
  return normalized;
}

export function subscribeUnreadSystemMessageCount(callback: (count: number) => void): () => void {
  if (!isBrowser()) return () => {};

  const handleStorage = (event: StorageEvent) => {
    if (event.key !== SYSTEM_MESSAGE_COUNT_KEY) return;
    callback(getStoredUnreadSystemMessageCount());
  };

  const handleCustom = (event: Event) => {
    const nextCount = (event as CustomEvent<number>).detail;
    callback(Number.isFinite(nextCount) && nextCount > 0 ? Math.floor(nextCount) : 0);
  };

  window.addEventListener("storage", handleStorage);
  window.addEventListener(SYSTEM_MESSAGE_EVENT, handleCustom as EventListener);

  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(SYSTEM_MESSAGE_EVENT, handleCustom as EventListener);
  };
}
