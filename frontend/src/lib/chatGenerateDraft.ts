export const CHAT_DRAFT_KEY = "generateDraftFromChat";
export const APPLY_CHAT_GENERATE_DRAFT_EVENT = "banana:apply-chat-generate-draft";
export const CLOSE_AI_ASSISTANT_DOCK_EVENT = "banana:close-ai-assistant-dock";
export const CHAT_GENERATE_TASKS_CREATED_EVENT = "banana:chat-generate-tasks-created";

export type ChatGenerateTasksPayload = {
  taskIds: string[];
  prompt?: string;
  model?: string;
  numImages?: number;
  size?: string;
  resolution?: string;
  customSize?: string;
  referenceImages?: string[];
  modeHint?: string;
};

function normalizeChatGenerateTasksPayload(payload?: ChatGenerateTasksPayload | null): ChatGenerateTasksPayload | null {
  const taskIds = (payload?.taskIds || [])
    .map((taskId) => String(taskId || "").trim())
    .filter(Boolean);
  if (!taskIds.length) return null;
  return {
    ...payload,
    taskIds,
  };
}

export function saveChatGenerateDraft(prompt: string) {
  localStorage.setItem(
    CHAT_DRAFT_KEY,
    JSON.stringify({
      mode: "imageEdit",
      prompt,
    }),
  );
}

export function applyChatGenerateDraftInPlace() {
  window.dispatchEvent(new CustomEvent(APPLY_CHAT_GENERATE_DRAFT_EVENT));
}

export function requestCloseAiAssistantDock() {
  window.dispatchEvent(new CustomEvent(CLOSE_AI_ASSISTANT_DOCK_EVENT));
}

export function notifyGeneratePageOfChatTasks(payload: ChatGenerateTasksPayload) {
  const next = normalizeChatGenerateTasksPayload(payload);
  if (!next) return;
  window.dispatchEvent(new CustomEvent(CHAT_GENERATE_TASKS_CREATED_EVENT, { detail: next }));
}
