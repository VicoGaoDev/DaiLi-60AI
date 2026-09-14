export const AI_ASSISTANT_DOCK_TAB_STORAGE_KEY = "banana:ai-assistant-dock-tab-enabled";
export const AI_ASSISTANT_DOCK_TAB_CHANGE_EVENT = "banana:ai-assistant-dock-tab-change";

export function isAiAssistantDockTabEnabled(): boolean {
  try {
    return localStorage.getItem(AI_ASSISTANT_DOCK_TAB_STORAGE_KEY) !== "0";
  } catch {
    return true;
  }
}

export function setAiAssistantDockTabEnabled(enabled: boolean) {
  try {
    localStorage.setItem(AI_ASSISTANT_DOCK_TAB_STORAGE_KEY, enabled ? "1" : "0");
  } catch {
    /* ignore quota / private mode */
  }
  window.dispatchEvent(new CustomEvent(AI_ASSISTANT_DOCK_TAB_CHANGE_EVENT, { detail: { enabled } }));
}

export function subscribeAiAssistantDockTabEnabled(listener: (enabled: boolean) => void) {
  const handleChange = (event: Event) => {
    const enabled = (event as CustomEvent<{ enabled?: boolean }>).detail?.enabled;
    listener(typeof enabled === "boolean" ? enabled : isAiAssistantDockTabEnabled());
  };
  window.addEventListener(AI_ASSISTANT_DOCK_TAB_CHANGE_EVENT, handleChange);
  return () => window.removeEventListener(AI_ASSISTANT_DOCK_TAB_CHANGE_EVENT, handleChange);
}
