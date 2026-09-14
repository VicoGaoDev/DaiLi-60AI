const AUTH_SESSION_EXPIRED_EVENT = "auth-session-expired";

type AuthSessionExpiredDetail = {
  redirectPath: string;
};

function isBrowser() {
  return typeof window !== "undefined";
}

export function emitAuthSessionExpiredNotice(redirectPath: string): void {
  if (!isBrowser()) return;
  window.dispatchEvent(
    new CustomEvent<AuthSessionExpiredDetail>(AUTH_SESSION_EXPIRED_EVENT, {
      detail: { redirectPath },
    })
  );
}

export function subscribeAuthSessionExpired(callback: (detail: AuthSessionExpiredDetail) => void): () => void {
  if (!isBrowser()) return () => {};

  const handleCustom = (event: Event) => {
    const detail = (event as CustomEvent<AuthSessionExpiredDetail>).detail;
    callback({
      redirectPath: detail?.redirectPath || "/templates",
    });
  };

  window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleCustom as EventListener);

  return () => {
    window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleCustom as EventListener);
  };
}
