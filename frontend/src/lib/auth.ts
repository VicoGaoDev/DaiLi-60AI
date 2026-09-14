import type { UserInfo } from "@/types";

export const NEW_USER_TRIAL_CREDITS = 6;
export const PHONE_USER_TRIAL_CREDITS = 20;
export const PROMO_CODE_REWARD_CREDITS = 20;

const TOKEN_KEY = "token";
const USER_KEY = "user";

function decodeBase64Url(value: string): string | null {
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return atob(padded);
  } catch {
    return null;
  }
}

function getTokenExpiresAt(token: string): number | null {
  const [, payload] = token.split(".");
  if (!payload) {
    return null;
  }

  const decoded = decodeBase64Url(payload);
  if (!decoded) {
    return null;
  }

  try {
    const parsed = JSON.parse(decoded) as { exp?: number };
    if (typeof parsed.exp === "number") {
      return parsed.exp * 1000;
    }
  } catch {
    return null;
  }

  return null;
}

export function clearStoredAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredToken(): string {
  const token = localStorage.getItem(TOKEN_KEY) || "";
  if (!token) {
    return "";
  }

  const expiresAt = getTokenExpiresAt(token);
  const isExpired = expiresAt ? expiresAt <= Date.now() : false;

  if (isExpired) {
    clearStoredAuth();
    return "";
  }

  return token;
}

export function getStoredUser(): UserInfo | null {
  const token = getStoredToken();
  if (!token) {
    return null;
  }

  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as UserInfo) : null;
  } catch {
    clearStoredAuth();
    return null;
  }
}

export function persistAuth(token: string, user: UserInfo): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function persistUser(user: UserInfo): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
