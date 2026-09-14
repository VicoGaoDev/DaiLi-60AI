export const OPEN_GENERATE_TUTORIAL_DOCK_EVENT = "banana:open-generate-tutorial-dock";
export const CLOSE_GENERATE_TUTORIAL_DOCK_EVENT = "banana:close-generate-tutorial-dock";
export const TUTORIAL_DOCK_TAB_STORAGE_KEY = "banana:tutorial-dock-tab-enabled";
export const TUTORIAL_DOCK_TAB_CHANGE_EVENT = "banana:tutorial-dock-tab-change";

export function requestOpenGenerateTutorialDock() {
  window.dispatchEvent(new CustomEvent(OPEN_GENERATE_TUTORIAL_DOCK_EVENT));
}

export function requestCloseGenerateTutorialDock() {
  window.dispatchEvent(new CustomEvent(CLOSE_GENERATE_TUTORIAL_DOCK_EVENT));
}

export function isTutorialDockTabEnabled(): boolean {
  try {
    return localStorage.getItem(TUTORIAL_DOCK_TAB_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setTutorialDockTabEnabled(enabled: boolean) {
  try {
    localStorage.setItem(TUTORIAL_DOCK_TAB_STORAGE_KEY, enabled ? "1" : "0");
  } catch {
    /* ignore quota / private mode */
  }
  window.dispatchEvent(new CustomEvent(TUTORIAL_DOCK_TAB_CHANGE_EVENT, { detail: { enabled } }));
}

export function subscribeTutorialDockTabEnabled(listener: (enabled: boolean) => void) {
  const handleChange = (event: Event) => {
    const enabled = (event as CustomEvent<{ enabled?: boolean }>).detail?.enabled;
    listener(typeof enabled === "boolean" ? enabled : isTutorialDockTabEnabled());
  };
  window.addEventListener(TUTORIAL_DOCK_TAB_CHANGE_EVENT, handleChange);
  return () => window.removeEventListener(TUTORIAL_DOCK_TAB_CHANGE_EVENT, handleChange);
}
