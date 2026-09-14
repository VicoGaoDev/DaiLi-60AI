import {
  APP_PAGE_THEME_ATTRIBUTE,
  APP_THEME_ATTRIBUTE,
  APP_THEME_STORAGE_KEY,
  DEFAULT_APP_THEME,
  isAppThemeName,
  type AppThemeName,
} from "@/config/theme";

type BananaThemeApi = {
  get: () => AppThemeName;
  set: (theme: AppThemeName, persist?: boolean) => void;
  reset: () => void;
};

declare global {
  interface Window {
    BananaTheme?: BananaThemeApi;
  }
}

function readStoredTheme(): AppThemeName | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(APP_THEME_STORAGE_KEY);
  return isAppThemeName(raw) ? raw : null;
}

function applyTheme(theme: AppThemeName) {
  if (typeof document === "undefined") return;

  document.documentElement.setAttribute(APP_THEME_ATTRIBUTE, theme);
  document.documentElement.removeAttribute(APP_PAGE_THEME_ATTRIBUTE);
  document.documentElement.style.colorScheme = theme === "midnight" ? "dark" : "light";
}

export function getCurrentTheme(): AppThemeName {
  if (typeof document !== "undefined") {
    const applied = document.documentElement.getAttribute(APP_THEME_ATTRIBUTE);
    if (isAppThemeName(applied)) {
      return applied;
    }
  }

  return readStoredTheme() ?? DEFAULT_APP_THEME;
}

export function setAppTheme(theme: AppThemeName, persist = true) {
  applyTheme(theme);

  if (persist && typeof window !== "undefined") {
    window.localStorage.setItem(APP_THEME_STORAGE_KEY, theme);
  }
}

export function resetAppTheme() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(APP_THEME_STORAGE_KEY);
  }

  applyTheme(DEFAULT_APP_THEME);
}

export function initializeAppTheme() {
  const theme = readStoredTheme() ?? DEFAULT_APP_THEME;
  applyTheme(theme);

  if (typeof window !== "undefined") {
    window.BananaTheme = {
      get: getCurrentTheme,
      set: setAppTheme,
      reset: resetAppTheme,
    };
  }
}
