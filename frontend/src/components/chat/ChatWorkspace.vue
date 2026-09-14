<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message, Modal } from "ant-design-vue";
import {
  ArrowDownOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  LoadingOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons-vue";
import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatMessages,
  listChatSessions,
  sendChatMessage,
  sendChatMessageStream,
  updateChatSession,
} from "@/api/chat";
import { getAdminChatSession, listAdminChatMessages, listAdminChatSessions } from "@/api/admin";
import { getChatModels } from "@/api/chatConfig";
import { getAvatarImageSrc, getPreviewImageSrc, toOriginalImageUrl } from "@/api/images";
import { isImageUploadTooLarge, MAX_IMAGE_UPLOAD_SIZE_TEXT, uploadReferenceImage } from "@/api/upload";
import { withBaseUrl } from "@/lib/assets";
import {
  isAiAssistantDockTabEnabled,
  setAiAssistantDockTabEnabled,
  subscribeAiAssistantDockTabEnabled,
} from "@/lib/aiAssistantDock";
import { applyChatGenerateDraftInPlace, requestCloseAiAssistantDock, saveChatGenerateDraft } from "@/lib/chatGenerateDraft";
import { stripGenerateImageFence } from "@/lib/simpleMarkdown";
import type { AdminUser, ChatGenerationModelOption, ChatImage, ChatMessage, ChatSendMessageResponse, ChatSession } from "@/types";
import { useAuthStore } from "@/stores/auth";
import AdminUserInfoDialog from "@/components/admin/AdminUserInfoDialog.vue";
import ChatGenerateCard from "@/components/chat/ChatGenerateCard.vue";

const props = withDefaults(defineProps<{
  embedded?: boolean;
  syncRoute?: boolean;
  readonly?: boolean;
  adminViewer?: boolean;
}>(), {
  embedded: false,
  syncRoute: true,
  readonly: false,
  adminViewer: false,
});

const emit = defineEmits<{
  "update:sessionId": [value: string | null];
}>();

const isReadOnly = computed(() => props.readonly || props.adminViewer);
const showDockSwitch = computed(() => !props.embedded && !isReadOnly.value);
const dockTabEnabled = ref(isAiAssistantDockTabEnabled());
let unsubscribeAiAssistantDockTabEnabled: (() => void) | null = null;
const xiaobaAvatarSrc = withBaseUrl("chat-xiaoba-avatar.png");
const userInfoDialogOpen = ref(false);
const userInfoDialogUser = ref<AdminUser | null>(null);
let adminSearchTimer = 0;
let sessionsRequestSeq = 0;
const MarkdownMessage = defineAsyncComponent(() => import("@/components/chat/MarkdownMessage.vue"));

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const selectingSession = ref(false);
const models = ref<ChatGenerationModelOption[]>([]);
const sessions = ref<ChatSession[]>([]);
const messages = ref<ChatMessage[]>([]);
const activeSessionId = ref<string | null>(null);
const selectedModel = ref("");
const draft = ref("");
type DraftChatImage = {
  id: string;
  localUrl: string;
  remoteUrl: string;
  status: "uploading" | "success" | "failed";
};
const MAX_CHAT_IMAGES = 4;
const draftImages = ref<DraftChatImage[]>([]);
const chatImageInputRef = ref<HTMLInputElement | null>(null);
const composerDragActive = ref(false);
const previewVisible = ref(false);
const previewSrc = ref("");
const loadingSessions = ref(false);
const loadingMessages = ref(false);
const loadingOlder = ref(false);
const sendingSessionIds = ref<string[]>([]);
const sessionsPage = ref(1);
const sessionsNextBeforeId = ref<string | null>(null);
const sessionsHasMore = ref(false);
const messagesHasMore = ref(false);
const messagesNextBeforeId = ref<number | null>(null);
const messageListRef = ref<HTMLElement | null>(null);
const composerSettingWrapRef = ref<HTMLElement | null>(null);
const composerPopoverOpen = ref(false);
const showScrollToBottom = ref(false);
const stickToBottom = ref(true);
const sidebarCollapsed = ref(props.embedded);
const chatPanelFaded = ref(false);
const sessionSearchOpen = ref(false);
const sessionSearchKeyword = ref("");
const sessionSearchInputRef = ref<HTMLInputElement | null>(null);
const streamingMessageId = ref<number | null>(null);
const streamingAssistantMessage = ref<ChatMessage | null>(null);
const streamingVisibleText = ref("");
const SESSION_PANEL_FADE_MS = 180;
const MESSAGE_CACHE_LIMIT = 8;
/** 逐字输出间隔 */
const STREAM_CHAR_INTERVAL_MS = 10;
let streamTimer: number | null = null;
let streamWorker: Worker | null = null;
let streamWorkerObjectUrl: string | null = null;
let streamVisibilityHandler: (() => void) | null = null;
let lastMessageListScrollTop = 0;
let ignoreMessageListScrollSync = false;
const sendAbortControllers = new Map<string, AbortController>();
type SessionStreamState = {
  messageId: number | null;
  assistant: ChatMessage | null;
  visibleText: string;
  live: boolean;
};
const sessionStreamStates = new Map<string, SessionStreamState>();
const liveStreaming = ref(false);
const sending = computed(() => sendingSessionIds.value.length > 0);

function isSessionSending(sessionId?: string | null) {
  return Boolean(sessionId) && sendingSessionIds.value.includes(sessionId as string);
}

function beginSessionSend(sessionId: string, controller: AbortController) {
  if (!sessionId) return;
  sendAbortControllers.set(sessionId, controller);
  if (!sendingSessionIds.value.includes(sessionId)) {
    sendingSessionIds.value = [...sendingSessionIds.value, sessionId];
  }
}

function endSessionSend(sessionId: string, controller: AbortController) {
  if (!sessionId || sendAbortControllers.get(sessionId) !== controller) return;
  sendAbortControllers.delete(sessionId);
  sendingSessionIds.value = sendingSessionIds.value.filter((id) => id !== sessionId);
}

function abortSessionSend(sessionId?: string | null) {
  if (!sessionId) return;
  sendAbortControllers.get(sessionId)?.abort();
}

function getSessionStream(sessionId: string): SessionStreamState {
  let state = sessionStreamStates.get(sessionId);
  if (!state) {
    state = { messageId: null, assistant: null, visibleText: "", live: false };
    sessionStreamStates.set(sessionId, state);
  }
  return state;
}

function clearSessionStream(sessionId: string) {
  sessionStreamStates.delete(sessionId);
  if (activeSessionId.value === sessionId) {
    streamingMessageId.value = null;
    streamingAssistantMessage.value = null;
    streamingVisibleText.value = "";
    liveStreaming.value = false;
  }
}

function syncActiveStreamDisplay() {
  const state = activeSessionId.value ? sessionStreamStates.get(activeSessionId.value) : null;
  streamingMessageId.value = state?.messageId ?? null;
  streamingAssistantMessage.value = state?.assistant ?? null;
  streamingVisibleText.value = state?.visibleText ?? "";
  liveStreaming.value = state?.live ?? false;
}

function isRequestAborted(err: any) {
  return (
    err?.code === "ERR_CANCELED"
    || err?.name === "CanceledError"
    || err?.name === "AbortError"
    || /cancel(led)?|aborted/i.test(String(err?.message || ""))
  );
}

type MessageCacheEntry = {
  items: ChatMessage[];
  hasMore: boolean;
  nextBeforeId: number | null;
};

/** 最近会话消息 LRU 缓存，减少来回切换重复请求 */
const messageCache = new Map<string, MessageCacheEntry>();

function cloneMessages(items: ChatMessage[]) {
  return items.map((item) => ({
    ...item,
    images: (item.images || []).map((img) => ({ ...img })),
  }));
}

function messageImages(item: ChatMessage): ChatImage[] {
  return (item.images || []).filter((img) => Boolean(img?.url));
}

function chatImageDisplaySrc(url: string) {
  return getPreviewImageSrc((url || "").trim());
}

function openChatImagePreview(url: string) {
  const src = getPreviewImageSrc(toOriginalImageUrl((url || "").trim()));
  if (!src) return;
  previewSrc.value = src;
  previewVisible.value = true;
}

function revokeDraftImageUrl(item: DraftChatImage) {
  if (item.localUrl.startsWith("blob:")) {
    URL.revokeObjectURL(item.localUrl);
  }
}

function clearDraftImages() {
  draftImages.value.forEach(revokeDraftImageUrl);
  draftImages.value = [];
}

const isActiveSessionSending = computed(() => isSessionSending(activeSessionId.value));

const canSend = computed(() => {
  const hasText = Boolean(draft.value.trim());
  const hasImage = draftImages.value.some((item) => item.status === "success" && item.remoteUrl);
  const uploading = draftImages.value.some((item) => item.status === "uploading");
  return (hasText || hasImage) && !uploading && Boolean(models.value.length) && !isActiveSessionSending.value;
});

function collectImageFiles(files: ArrayLike<File> | null | undefined): File[] {
  return Array.from(files || []).filter((file) => file.type.startsWith("image/"));
}

function getClipboardImageFiles(event: ClipboardEvent): File[] {
  const itemFiles = Array.from(event.clipboardData?.items || [])
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file && file.type.startsWith("image/")));
  if (itemFiles.length) return itemFiles;
  return collectImageFiles(event.clipboardData?.files);
}

function isImageFileDragEvent(event: DragEvent) {
  return Array.from(event.dataTransfer?.types || []).includes("Files");
}

function openChatImagePicker() {
  if (isActiveSessionSending.value || !models.value.length) return;
  if (draftImages.value.length >= MAX_CHAT_IMAGES) {
    message.warning(`一次最多上传 ${MAX_CHAT_IMAGES} 张图片`);
    return;
  }
  chatImageInputRef.value?.click();
}

async function addChatImageFiles(files: File[]) {
  if (isActiveSessionSending.value || !models.value.length) return;
  const imageFiles = collectImageFiles(files);
  if (!imageFiles.length) return;
  if (!auth.isLoggedIn) {
    message.warning("请先登录");
    return;
  }
  const remain = MAX_CHAT_IMAGES - draftImages.value.length;
  if (remain <= 0) {
    message.warning(`一次最多上传 ${MAX_CHAT_IMAGES} 张图片`);
    return;
  }
  const selected = imageFiles.slice(0, remain);
  if (imageFiles.length > remain) {
    message.warning(`一次最多上传 ${MAX_CHAT_IMAGES} 张图片`);
  }
  for (const file of selected) {
    if (isImageUploadTooLarge(file)) {
      message.warning(`图片不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
      continue;
    }
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const localUrl = URL.createObjectURL(file);
    const draftItem: DraftChatImage = {
      id,
      localUrl,
      remoteUrl: "",
      status: "uploading",
    };
    draftImages.value.push(draftItem);
    try {
      const uploaded = await uploadReferenceImage(file, "chat");
      const current = draftImages.value.find((item) => item.id === id);
      if (!current) {
        URL.revokeObjectURL(localUrl);
        continue;
      }
      current.remoteUrl = uploaded.url;
      current.status = "success";
    } catch (err: any) {
      const current = draftImages.value.find((item) => item.id === id);
      if (current) current.status = "failed";
      message.error(err?.response?.data?.detail || err?.message || "图片上传失败");
    }
  }
}

async function handleChatImageChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = "";
  await addChatImageFiles(files);
}

async function handleComposerPaste(event: ClipboardEvent) {
  if (isActiveSessionSending.value || !models.value.length) return;
  const files = getClipboardImageFiles(event);
  if (!files.length) return;
  event.preventDefault();
  event.stopPropagation();
  await addChatImageFiles(files);
}

function handleComposerDragOver(event: DragEvent) {
  if (!isImageFileDragEvent(event) || isActiveSessionSending.value || !models.value.length) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  composerDragActive.value = true;
}

function handleComposerDragLeave(event: DragEvent) {
  const nextTarget = event.relatedTarget as Node | null;
  if (nextTarget && (event.currentTarget as HTMLElement | null)?.contains(nextTarget)) return;
  composerDragActive.value = false;
}

async function handleComposerDrop(event: DragEvent) {
  event.preventDefault();
  composerDragActive.value = false;
  if (isActiveSessionSending.value || !models.value.length) return;
  const files = collectImageFiles(event.dataTransfer?.files);
  if (!files.length) return;
  await addChatImageFiles(files);
}

function removeDraftImage(id: string) {
  const current = draftImages.value.find((item) => item.id === id);
  if (current) revokeDraftImageUrl(current);
  draftImages.value = draftImages.value.filter((item) => item.id !== id);
}

function putMessageCache(sessionId: string, entry: MessageCacheEntry) {
  if (!sessionId) return;
  messageCache.delete(sessionId);
  messageCache.set(sessionId, {
    items: cloneMessages(entry.items),
    hasMore: entry.hasMore,
    nextBeforeId: entry.nextBeforeId,
  });
  while (messageCache.size > MESSAGE_CACHE_LIMIT) {
    const oldest = messageCache.keys().next().value;
    if (oldest == null) break;
    messageCache.delete(oldest);
  }
}

function snapshotCurrentMessagesToCache() {
  if (!activeSessionId.value) return;
  putMessageCache(activeSessionId.value, {
    items: messages.value,
    hasMore: messagesHasMore.value,
    nextBeforeId: messagesNextBeforeId.value,
  });
}

function mutateSessionMessages(
  sessionId: string,
  updater: (items: ChatMessage[]) => ChatMessage[],
) {
  if (!sessionId) return;
  if (activeSessionId.value === sessionId) {
    messages.value = updater(messages.value);
    putMessageCache(sessionId, {
      items: messages.value,
      hasMore: messagesHasMore.value,
      nextBeforeId: messagesNextBeforeId.value,
    });
    return;
  }
  const cached = messageCache.get(sessionId);
  putMessageCache(sessionId, {
    items: updater(cached?.items || []),
    hasMore: cached?.hasMore ?? false,
    nextBeforeId: cached?.nextBeforeId ?? null,
  });
}

function applyMessageCache(sessionId: string): boolean {
  const cached = messageCache.get(sessionId);
  if (!cached) return false;
  messages.value = cloneMessages(cached.items);
  messagesHasMore.value = cached.hasMore;
  messagesNextBeforeId.value = cached.nextBeforeId;
  // LRU：挪到最近使用
  messageCache.delete(sessionId);
  messageCache.set(sessionId, cached);
  return true;
}

function clearMessageCache(sessionId?: string | null) {
  if (!sessionId) {
    messageCache.clear();
    return;
  }
  messageCache.delete(sessionId);
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
}

const filteredSessions = computed(() => {
  const keyword = sessionSearchKeyword.value.trim().toLowerCase();
  if (!keyword || props.adminViewer) return sessions.value;
  return sessions.value.filter((item) => {
    const title = (item.title || "新对话").toLowerCase();
    const username = (item.username || "").toLowerCase();
    return title.includes(keyword) || username.includes(keyword);
  });
});

async function openSessionSearch() {
  sessionSearchOpen.value = true;
  await nextTick();
  sessionSearchInputRef.value?.focus();
}

function closeSessionSearch() {
  sessionSearchOpen.value = false;
  sessionSearchKeyword.value = "";
}

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

const sessionPanelLoading = computed(
  () => selectingSession.value || loadingMessages.value,
);

async function withChatPanelFade(run: () => Promise<void>, options: { fadeOut?: boolean } = {}) {
  const shouldFadeOut = options.fadeOut !== false;
  if (shouldFadeOut) {
    chatPanelFaded.value = true;
    await wait(SESSION_PANEL_FADE_MS);
  }
  try {
    await run();
    await nextTick();
  } finally {
    chatPanelFaded.value = false;
  }
}

const PUBLIC_SESSION_ID_RE = /^[0-9]{12}[a-z0-9]{4}$/i;

function parseRouteSessionId(raw: unknown = route.params.sessionId): string | null {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (value == null || value === "") return null;
  const id = String(value).trim().toLowerCase();
  return PUBLIC_SESSION_ID_RE.test(id) ? id : null;
}

function sessionRoutePath(sessionId: string | null) {
  if (props.adminViewer) {
    return sessionId ? `/admin/user-conversations/${sessionId}` : "/admin/user-conversations";
  }
  return sessionId ? `/chat/${sessionId}` : "/chat";
}

function listSessionsRequest(params: {
  page?: number;
  page_size?: number;
  keyword?: string;
  before_session_id?: string;
}) {
  if (props.adminViewer) {
    return listAdminChatSessions({
      page_size: params.page_size,
      keyword: params.keyword,
      before_session_id: params.before_session_id,
    });
  }
  return listChatSessions({
    page: params.page,
    page_size: params.page_size,
  });
}

function getSessionRequest(sessionId: string) {
  if (props.adminViewer) return getAdminChatSession(sessionId);
  return getChatSession(sessionId);
}

function listMessagesRequest(sessionId: string, params?: { before_id?: number; page_size?: number }) {
  if (props.adminViewer) return listAdminChatMessages(sessionId, params);
  return listChatMessages(sessionId, params);
}

function sessionOwnerName(session?: ChatSession | null) {
  return (session?.username || "").trim() || "未知用户";
}

function sessionOwnerAvatar(session?: ChatSession | null) {
  return getAvatarImageSrc(session?.avatar_url || "") || "";
}

function sessionOwnerInitial(session?: ChatSession | null) {
  return sessionOwnerName(session).charAt(0).toUpperCase() || "?";
}

function openSessionUserInfo(session: ChatSession, event?: Event) {
  event?.stopPropagation();
  if (!props.adminViewer || !session.user_id) return;
  userInfoDialogUser.value = {
    id: session.user_id,
    username: sessionOwnerName(session),
    avatar_url: session.avatar_url || "",
    role: "user",
    status: "active",
    is_whitelisted: false,
    credits: 0,
    consumed_credits: 0,
    created_at: session.created_at,
  };
  userInfoDialogOpen.value = true;
}

function syncSessionRoute(sessionId: string | null) {
  emit("update:sessionId", sessionId);
  if (!props.syncRoute) return;
  const current = parseRouteSessionId();
  if (sessionId && current === sessionId) return;
  if (!sessionId && current == null) return;
  void router.replace(sessionRoutePath(sessionId));
}

async function ensureSessionInList(sessionId: string): Promise<ChatSession | null> {
  const existing = sessions.value.find((item) => item.id === sessionId);
  if (existing) return existing;
  try {
    const session = await getSessionRequest(sessionId);
    sessions.value = [session, ...sessions.value.filter((item) => item.id !== session.id)];
    return session;
  } catch {
    return null;
  }
}

const activeSession = computed(() => sessions.value.find((item) => item.id === activeSessionId.value) || null);
const selectedModelOption = computed(
  () => models.value.find((item) => item.model_key === selectedModel.value) || null,
);
const openingGreeting = computed(() => selectedModelOption.value?.opening_greeting || "");
const emptyChatTitle = computed(() => {
  if (isReadOnly.value) {
    return activeSession.value
      ? `${sessionOwnerName(activeSession.value)} 的对话`
      : "选择左侧会话查看用户对话";
  }
  const username = (auth.user?.username || "").trim();
  return username ? `👋你好，${username}` : "👋你好";
});
const sendButtonText = computed(() => {
  const cost = Number(selectedModelOption.value?.credit_cost || 0);
  return cost > 0 ? `发送 · ${cost} 积分` : "发送";
});
function sceneOptionLabel(item?: ChatGenerationModelOption | null) {
  if (!item) return "";
  return (item.model_label || item.display_name || item.model_key || "").trim();
}

type StarterPrompt = { id: string; tag: string; text: string; image_url: string };

const starterPrompts = computed(() => {
  const configured = (selectedModelOption.value?.starter_prompts || [])
    .map((item, index) => ({
      id: `starter-${index}`,
      tag: String(item?.tag || "").trim(),
      text: String(item?.text || "").trim(),
      image_url: String(item?.image_url || "").trim(),
    }))
    .filter((item) => item.text)
    .slice(0, 6);
  return configured;
});

function handleStarterPrompt(prompt: StarterPrompt) {
  if (isReadOnly.value || isActiveSessionSending.value || !prompt?.text) return;
  void handleSend(prompt.text, {
    images: prompt.image_url ? [{ url: prompt.image_url }] : [],
  });
}

const modelChipLabel = computed(() =>
  sceneOptionLabel(selectedModelOption.value) || "选择场景",
);

function createClientMessageId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function formatTime(value?: string | null) {
  if (!value) return "";
  // 后端存的是北京时间墙钟；无时区后缀时按 +08:00 解析，再按北京时间展示
  const raw = String(value).trim().replace(" ", "T");
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw);
  const date = new Date(hasTimezone ? raw : `${raw}+08:00`);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function messagePlainText(item: ChatMessage) {
  return stripGenerateImageFence((item.content || item.error_message || "").trim());
}

function isBrokenAssistantMessage(item: ChatMessage) {
  if (item.role !== "assistant") return false;
  if (item.status === "pending" || streamingMessageId.value === item.id || liveStreaming.value) {
    return false;
  }
  return !messagePlainText(item) && !item.generate?.status;
}

function modelWantsStream(modelKey: string) {
  return models.value.some((item) => item.model_key === modelKey && item.stream === true);
}

function applyChatBalance(balance?: number | null) {
  if (typeof balance !== "number" || !auth.user) return;
  auth.updateUser({ ...auth.user, credits: balance });
}

function upsertSendResultMessages(
  result: Pick<ChatSendMessageResponse, "user_message" | "assistant_message" | "session">,
  options: { skipOptimisticUser?: boolean; tempUserMessageId: number; clientMessageId: string },
) {
  const sessionId = result.session?.id || activeSessionId.value || "";
  mutateSessionMessages(sessionId, (items) => {
    const next = items.slice();
    if (!options.skipOptimisticUser) {
      const tempIndex = next.findIndex(
        (item) => item.id === options.tempUserMessageId || item.client_message_id === options.clientMessageId,
      );
      if (tempIndex >= 0) {
        next.splice(tempIndex, 1, result.user_message);
      } else if (!next.some((item) => item.id === result.user_message.id)) {
        next.push(result.user_message);
      }
    } else if (!next.some((item) => item.id === result.user_message.id)) {
      next.push(result.user_message);
    }
    const cleaned = next.filter((item) => !isBrokenAssistantMessage(item));
    const assistantIndex = cleaned.findIndex((item) => item.id === result.assistant_message.id);
    if (assistantIndex >= 0) {
      cleaned.splice(assistantIndex, 1, result.assistant_message);
    } else {
      cleaned.push(result.assistant_message);
    }
    return cleaned;
  });
  sessions.value = [
    result.session,
    ...sessions.value.filter((item) => item.id !== result.session.id),
  ];
}

function findPreviousUserMessage(assistant: ChatMessage): ChatMessage | null {
  const index = messages.value.findIndex((item) => item.id === assistant.id);
  if (index <= 0) return null;
  for (let i = index - 1; i >= 0; i -= 1) {
    const item = messages.value[i];
    if (item.role === "user" && ((item.content || "").trim() || messageImages(item).length)) {
      return item;
    }
  }
  return null;
}

function clearAssistantStreamScheduler() {
  if (streamTimer != null) {
    window.clearTimeout(streamTimer);
    window.clearInterval(streamTimer);
    streamTimer = null;
  }
  if (streamWorker) {
    try {
      streamWorker.postMessage("stop");
    } catch {
      // ignore
    }
    streamWorker.terminate();
    streamWorker = null;
  }
  if (streamWorkerObjectUrl) {
    URL.revokeObjectURL(streamWorkerObjectUrl);
    streamWorkerObjectUrl = null;
  }
}

function detachAssistantStreamVisibilityHandler() {
  if (streamVisibilityHandler) {
    document.removeEventListener("visibilitychange", streamVisibilityHandler);
    streamVisibilityHandler = null;
  }
}

function stopAssistantStreaming() {
  clearAssistantStreamScheduler();
  detachAssistantStreamVisibilityHandler();
  streamingMessageId.value = null;
  streamingAssistantMessage.value = null;
  streamingVisibleText.value = "";
}

function assistantDisplayText(item: ChatMessage) {
  if (streamingMessageId.value === item.id) {
    return stripGenerateImageFence(streamingVisibleText.value);
  }
  return messagePlainText(item);
}

function handleGenerateCardUpdated(next: ChatMessage) {
  const sessionId = next.session_id || activeSessionId.value || "";
  if (!sessionId) return;
  mutateSessionMessages(sessionId, (items) => items.map((item) => (
    item.id === next.id ? { ...item, ...next } : item
  )));
}

function createAssistantStreamWorker(): Worker | null {
  let objectUrl: string | null = null;
  try {
    const source = [
      "let timer = null;",
      "onmessage = (e) => {",
      "  if (e.data === 'start') {",
      "    if (timer != null) clearInterval(timer);",
      `    timer = setInterval(() => postMessage('tick'), ${STREAM_CHAR_INTERVAL_MS});`,
      "  } else if (e.data === 'stop') {",
      "    if (timer != null) clearInterval(timer);",
      "    timer = null;",
      "  }",
      "};",
    ].join("\n");
    objectUrl = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
    const worker = new Worker(objectUrl);
    streamWorkerObjectUrl = objectUrl;
    return worker;
  } catch {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    return null;
  }
}

function streamAssistantMessage(item: ChatMessage): Promise<void> {
  const fullText = messagePlainText(item);
  stopAssistantStreaming();
  if (!fullText || item.status === "failed") {
    return Promise.resolve();
  }
  const chars = Array.from(fullText);
  streamingMessageId.value = item.id;
  streamingVisibleText.value = "";
  // 按真实时间推进 + Worker 节拍：切走 tab/应用时进度不冻结，回来立刻对齐
  const startedAt = performance.now();
  let settled = false;
  let lastPaintedIndex = 0;

  return new Promise((resolve) => {
    const finish = () => {
      if (settled) return;
      settled = true;
      clearAssistantStreamScheduler();
      detachAssistantStreamVisibilityHandler();
      streamingMessageId.value = null;
      streamingVisibleText.value = "";
      resolve();
    };

    const paint = () => {
      if (settled) return;
      const elapsed = Math.max(0, performance.now() - startedAt);
      const index = Math.min(
        chars.length,
        Math.max(1, Math.floor(elapsed / STREAM_CHAR_INTERVAL_MS) + 1),
      );
      if (index === lastPaintedIndex && index < chars.length) return;
      lastPaintedIndex = index;
      streamingVisibleText.value = chars.slice(0, index).join("");
      // 仅在用户仍停留底部时跟随；上滑后不再强拉回底部
      if (stickToBottom.value) {
        void scrollToBottom(false);
      }
      if (index >= chars.length) {
        finish();
      }
    };

    streamVisibilityHandler = () => {
      if (settled) return;
      // 隐藏/显示都按墙钟补帧，避免后台节流导致停住
      paint();
    };
    document.addEventListener("visibilitychange", streamVisibilityHandler);

    const worker = createAssistantStreamWorker();
    if (worker) {
      streamWorker = worker;
      worker.onmessage = () => paint();
      worker.onerror = () => {
        // Worker 异常时回退到主线程 interval
        clearAssistantStreamScheduler();
        streamTimer = window.setInterval(paint, STREAM_CHAR_INTERVAL_MS);
      };
      worker.postMessage("start");
    } else {
      streamTimer = window.setInterval(paint, STREAM_CHAR_INTERVAL_MS);
    }
    paint();
  });
}

async function handleCopyMessage(item: ChatMessage) {
  const text = messagePlainText(item);
  if (!text) {
    message.warning("没有可复制的内容");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    message.success("已复制");
  } catch {
    message.error("复制失败，请检查剪贴板权限");
  }
}

function handleBlockJumpGenerate(prompt: string) {
  if (isReadOnly.value) return;
  jumpGenerateWithPrompt(prompt);
}

function jumpGenerateWithPrompt(prompt: string) {
  saveChatGenerateDraft(prompt);
  requestCloseAiAssistantDock();
  if (route.path.startsWith("/generate")) {
    applyChatGenerateDraftInPlace();
    return;
  }
  router.push({ path: "/generate", query: { mode: "imageEdit" } });
}

function updateScrollToBottomVisibility() {
  const el = messageListRef.value;
  if (!el) {
    showScrollToBottom.value = false;
    stickToBottom.value = true;
    return;
  }
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
  const nearBottom = distance <= 96;
  stickToBottom.value = nearBottom;
  showScrollToBottom.value = !nearBottom;
  lastMessageListScrollTop = el.scrollTop;
}

function handleMessageListScroll() {
  const el = messageListRef.value;
  if (!el) return;
  if (ignoreMessageListScrollSync) {
    lastMessageListScrollTop = el.scrollTop;
    return;
  }
  const top = el.scrollTop;
  // 任意上滑都立即取消贴底，避免逐字输出时小幅上滑被拉回闪缩
  if (top + 0.5 < lastMessageListScrollTop) {
    stickToBottom.value = false;
    showScrollToBottom.value = true;
    lastMessageListScrollTop = top;
    return;
  }
  lastMessageListScrollTop = top;
  updateScrollToBottomVisibility();
}

async function scrollToBottom(force = true) {
  await nextTick();
  const el = messageListRef.value;
  if (!el) return;
  if (!force && !stickToBottom.value) {
    showScrollToBottom.value = true;
    lastMessageListScrollTop = el.scrollTop;
    return;
  }
  ignoreMessageListScrollSync = true;
  el.scrollTop = el.scrollHeight;
  stickToBottom.value = true;
  showScrollToBottom.value = false;
  lastMessageListScrollTop = el.scrollTop;
  window.requestAnimationFrame(() => {
    ignoreMessageListScrollSync = false;
    if (messageListRef.value) {
      lastMessageListScrollTop = messageListRef.value.scrollTop;
    }
  });
}

function ensureDefaultModel() {
  if (!models.value.length) {
    selectedModel.value = "";
    return;
  }
  const exists = models.value.some((item) => item.model_key === selectedModel.value);
  if (!exists) {
    selectedModel.value = models.value[0].model_key;
  }
}

function applySessionModel(model?: string | null) {
  const key = (model || "").trim();
  if (key && models.value.some((item) => item.model_key === key)) {
    selectedModel.value = key;
    return;
  }
  ensureDefaultModel();
}

async function loadModels() {
  try {
    models.value = await getChatModels();
    ensureDefaultModel();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "加载对话场景失败");
  }
}

async function loadSessions(reset = true, preferredSessionId?: string | null) {
  if (reset) {
    sessionsPage.value = 1;
    sessionsNextBeforeId.value = null;
  }
  const requestSeq = ++sessionsRequestSeq;
  loadingSessions.value = true;
  try {
    const keyword = props.adminViewer ? sessionSearchKeyword.value.trim() : "";
    const result = await listSessionsRequest({
      page: sessionsPage.value,
      page_size: 50,
      keyword: keyword || undefined,
      before_session_id: reset || !props.adminViewer
        ? undefined
        : sessionsNextBeforeId.value || undefined,
    });
    if (requestSeq !== sessionsRequestSeq) return;
    sessions.value = reset ? result.items : [...sessions.value, ...result.items];
    sessionsHasMore.value = result.has_more;
    if (props.adminViewer) {
      sessionsNextBeforeId.value = result.next_before_session_id || null;
    }
    if (!reset) return;

    const preferredInResults = preferredSessionId
      ? result.items.some((item) => item.id === preferredSessionId)
      : false;
    const targetId = (keyword && preferredSessionId && !preferredInResults)
      ? (result.items[0]?.id ?? null)
      : preferredSessionId
        || (props.syncRoute ? parseRouteSessionId() : null)
        || sessions.value[0]?.id
        || null;
    if (targetId) {
      const session = await ensureSessionInList(targetId);
      if (session) {
        await selectSession(session.id, { syncRoute: true });
        return;
      }
      if (preferredSessionId || parseRouteSessionId()) {
        message.warning("会话不存在或已删除");
      }
    }
    activeSessionId.value = null;
    messages.value = [];
    messagesHasMore.value = false;
    messagesNextBeforeId.value = null;
    syncSessionRoute(null);
    ensureDefaultModel();
  } catch (err: any) {
    if (requestSeq !== sessionsRequestSeq) return;
    message.error(err?.response?.data?.detail || "加载会话失败");
  } finally {
    if (requestSeq === sessionsRequestSeq) {
      loadingSessions.value = false;
    }
  }
}

async function loadMoreSessions() {
  if (!sessionsHasMore.value || loadingSessions.value) return;
  if (props.adminViewer && !sessionsNextBeforeId.value) return;
  if (!props.adminViewer) {
    sessionsPage.value += 1;
  }
  await loadSessions(false);
}

async function selectSession(
  sessionId: string,
  options: { syncRoute?: boolean } = {},
) {
  const { syncRoute = true } = options;
  if (selectingSession.value && activeSessionId.value === sessionId) return;
  if (activeSessionId.value === sessionId && !selectingSession.value) return;

  selectingSession.value = true;
  try {
    const session = await ensureSessionInList(sessionId);
    if (!session) {
      message.warning("会话不存在或已删除");
      if (syncRoute) syncSessionRoute(null);
      return;
    }
    const shouldFadeOut = activeSessionId.value != null && activeSessionId.value !== sessionId;
    await withChatPanelFade(async () => {
      stopAssistantStreaming();
      snapshotCurrentMessagesToCache();
      const cacheHit = applyMessageCache(sessionId);
      activeSessionId.value = sessionId;
      applySessionModel(session.model);
      if (syncRoute) {
        syncSessionRoute(sessionId);
      }
      syncActiveStreamDisplay();
      if (cacheHit) {
        await scrollToBottom();
        if (!isSessionSending(sessionId)) {
          void refreshMessagesSilently(sessionId);
        }
        return;
      }
      loadingMessages.value = true;
      messages.value = [];
      messagesHasMore.value = false;
      messagesNextBeforeId.value = null;
      try {
        await loadMessages(sessionId);
      } finally {
        loadingMessages.value = false;
      }
    }, { fadeOut: shouldFadeOut });
  } finally {
    selectingSession.value = false;
  }
}

function applyMessagePage(
  sessionId: string,
  result: Awaited<ReturnType<typeof listChatMessages>>,
  options: { updateVisible: boolean } = { updateVisible: true },
) {
  const nextBeforeId = result.next_before_id ?? (result.items[0]?.id || null);
  putMessageCache(sessionId, {
    items: result.items,
    hasMore: result.has_more,
    nextBeforeId,
  });
  if (!options.updateVisible) return;
  messages.value = result.items;
  messagesHasMore.value = result.has_more;
  messagesNextBeforeId.value = nextBeforeId;
}

async function fetchLatestMessages(sessionId: string) {
  return listMessagesRequest(sessionId, { page_size: 50 });
}

async function loadMessages(sessionId: string) {
  try {
    const result = await fetchLatestMessages(sessionId);
    applyMessagePage(sessionId, result);
    await scrollToBottom();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "加载消息失败");
  }
}

async function refreshMessagesSilently(sessionId: string) {
  try {
    const result = await fetchLatestMessages(sessionId);
    const isActive = activeSessionId.value === sessionId;
    applyMessagePage(sessionId, result, { updateVisible: isActive });
  } catch {
    // 静默刷新失败时保留缓存内容，不打断当前浏览
  }
}

async function loadOlderMessages() {
  if (!activeSessionId.value || !messagesHasMore.value || loadingOlder.value) return;
  const beforeId = messagesNextBeforeId.value || messages.value[0]?.id;
  if (!beforeId) return;
  loadingOlder.value = true;
  const prevHeight = messageListRef.value?.scrollHeight || 0;
  try {
    const result = await listMessagesRequest(activeSessionId.value, {
      before_id: beforeId,
      page_size: 50,
    });
    messages.value = [...result.items, ...messages.value];
    messagesHasMore.value = result.has_more;
    messagesNextBeforeId.value = result.next_before_id ?? (result.items[0]?.id || null);
    putMessageCache(activeSessionId.value, {
      items: messages.value,
      hasMore: messagesHasMore.value,
      nextBeforeId: messagesNextBeforeId.value,
    });
    await nextTick();
    const el = messageListRef.value;
    if (el) {
      el.scrollTop = el.scrollHeight - prevHeight;
    }
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "加载更早消息失败");
  } finally {
    loadingOlder.value = false;
  }
}

async function handleCreateSession() {
  if (isReadOnly.value) return;
  if (!selectedModel.value) {
    message.warning("请先配置可用的对话场景");
    return;
  }
  try {
    const session = await createChatSession({ model: selectedModel.value });
    sessions.value = [session, ...sessions.value.filter((item) => item.id !== session.id)];
    const shouldFadeOut = activeSessionId.value != null || messages.value.length > 0;
    await withChatPanelFade(async () => {
      snapshotCurrentMessagesToCache();
      activeSessionId.value = session.id;
      messages.value = [];
      messagesHasMore.value = false;
      messagesNextBeforeId.value = null;
      putMessageCache(session.id, {
        items: [],
        hasMore: false,
        nextBeforeId: null,
      });
      syncSessionRoute(session.id);
      syncActiveStreamDisplay();
    }, { fadeOut: shouldFadeOut });
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "创建会话失败");
  }
}

function handleDeleteSession(session: ChatSession, event?: Event) {
  if (isReadOnly.value) return;
  event?.stopPropagation();
  Modal.confirm({
    title: "删除会话",
    content: `确认删除「${session.title || "新对话"}」？`,
    okType: "danger",
    onOk: async () => {
      await deleteChatSession(session.id);
      sessions.value = sessions.value.filter((item) => item.id !== session.id);
      clearMessageCache(session.id);
      if (activeSessionId.value === session.id) {
        if (sessions.value[0]) {
          await selectSession(sessions.value[0].id, { syncRoute: true });
        } else {
          await withChatPanelFade(async () => {
            activeSessionId.value = null;
            messages.value = [];
            messagesHasMore.value = false;
            messagesNextBeforeId.value = null;
            syncSessionRoute(null);
          });
        }
      }
      message.success("已删除");
    },
  });
}

function toggleComposerPopover() {
  if (isActiveSessionSending.value || !models.value.length) return;
  composerPopoverOpen.value = !composerPopoverOpen.value;
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (!composerPopoverOpen.value) return;
  const target = event.target as Node | null;
  if (!target) return;
  if (composerSettingWrapRef.value?.contains(target)) return;
  composerPopoverOpen.value = false;
}

async function handleModelChange(modelKey: string) {
  if (isReadOnly.value) return;
  selectedModel.value = modelKey;
  composerPopoverOpen.value = false;
  if (!activeSessionId.value) return;
  try {
    const updated = await updateChatSession(activeSessionId.value, { model: modelKey });
    sessions.value = sessions.value.map((item) => (item.id === updated.id ? updated : item));
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "更新场景失败");
  }
}

async function ensureActiveSession() {
  if (isReadOnly.value) {
    throw new Error("当前为只读查看");
  }
  if (activeSessionId.value) return activeSessionId.value;
  if (!selectedModel.value) {
    throw new Error("请先选择对话场景");
  }
  const session = await createChatSession({ model: selectedModel.value });
  sessions.value = [session, ...sessions.value];
  activeSessionId.value = session.id;
  // 保留发送中已插入的乐观消息，避免首条引导问题被清空
  syncSessionRoute(session.id);
  return session.id;
}

function handleStopSending() {
  abortSessionSend(activeSessionId.value);
  if (!isActiveSessionSending.value && streamingMessageId.value != null) {
    stopAssistantStreaming();
  }
}

async function handleSend(
  contentOverride?: string,
  options: { model?: string; skipOptimisticUser?: boolean; images?: ChatImage[] } = {},
) {
  if (isReadOnly.value) return;
  // @click 可能把事件对象传进来，只接受真正的字符串覆盖
  const overrideText = typeof contentOverride === "string" ? contentOverride : undefined;
  const content = (overrideText ?? draft.value).trim();
  const model = (options.model || selectedModel.value || "").trim();
  const sendingImages = (options.images || draftImages.value
    .filter((item) => item.status === "success" && item.remoteUrl)
    .map((item) => ({ url: item.remoteUrl })));
  if (isActiveSessionSending.value) return;
  if (overrideText == null && draftImages.value.some((item) => item.status === "uploading")) {
    message.warning("图片还在上传，请稍候");
    return;
  }
  if (!content && !sendingImages.length) return;
  if (!model) {
    message.warning("请先选择对话场景");
    return;
  }
  if (!auth.isLoggedIn) {
    message.warning("请先登录");
    return;
  }

  const controller = new AbortController();
  composerPopoverOpen.value = false;
  const snapshotDraftImages = overrideText == null ? draftImages.value.slice() : [];
  if (overrideText == null) {
    draft.value = "";
    draftImages.value = [];
  }
  if (!selectedModel.value) selectedModel.value = model;
  const clientMessageId = createClientMessageId();
  const tempUserMessageId = -Date.now();
  if (!options.skipOptimisticUser) {
    const optimisticUserMessage: ChatMessage = {
      id: tempUserMessageId,
      session_id: activeSessionId.value || "",
      role: "user",
      content,
      images: sendingImages,
      model,
      client_message_id: clientMessageId,
      credit_cost: 0,
      status: "pending",
      error_message: "",
      created_at: new Date().toISOString(),
    };
    messages.value.push(optimisticUserMessage);
    await scrollToBottom(true);
  }

  let sessionId = activeSessionId.value || "";
  try {
    if (!sessionId) {
      sessionId = await ensureActiveSession();
    }
    beginSessionSend(sessionId, controller);
    if (controller.signal.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const sendPayload = {
      content,
      images: sendingImages,
      model,
      client_message_id: clientMessageId,
    };
    const resultOptions = {
      skipOptimisticUser: options.skipOptimisticUser,
      tempUserMessageId,
      clientMessageId,
    };
    if (modelWantsStream(model)) {
      const stream = getSessionStream(sessionId);
      stream.live = true;
      if (activeSessionId.value === sessionId) liveStreaming.value = true;
      await sendChatMessageStream(
        sessionId,
        sendPayload,
        {
          onMeta(meta) {
            upsertSendResultMessages(meta, resultOptions);
            stream.messageId = meta.assistant_message.id;
            stream.assistant = meta.assistant_message;
            stream.visibleText = meta.assistant_message.content || "";
            if (activeSessionId.value === sessionId) {
              streamingMessageId.value = stream.messageId;
              streamingAssistantMessage.value = stream.assistant;
              streamingVisibleText.value = stream.visibleText;
            }
            if (!stream.visibleText.trim()) {
              mutateSessionMessages(sessionId, (items) => (
                items.filter((item) => item.id !== meta.assistant_message.id)
              ));
            }
            if (activeSessionId.value === sessionId) {
              void scrollToBottom(true);
            }
          },
          onDelta(text) {
            stream.visibleText += text;
            const assistantId = stream.messageId;
            if (assistantId != null) {
              const nextAssistant: ChatMessage = {
                ...(stream.assistant || {
                  id: assistantId,
                  session_id: sessionId,
                  role: "assistant" as const,
                  model,
                  client_message_id: null,
                  credit_cost: 0,
                  created_at: new Date().toISOString(),
                }),
                content: stream.visibleText,
                status: "pending",
                error_message: "",
              };
              stream.assistant = nextAssistant;
              mutateSessionMessages(sessionId, (items) => {
                const exists = items.some((item) => item.id === assistantId);
                if (exists) {
                  return items.map((item) => (item.id === assistantId ? nextAssistant : item));
                }
                return [...items, nextAssistant];
              });
            }
            if (activeSessionId.value === sessionId) {
              streamingVisibleText.value = stream.visibleText;
              streamingAssistantMessage.value = stream.assistant;
              streamingMessageId.value = stream.messageId;
              if (stickToBottom.value) {
                void scrollToBottom(false);
              }
            }
          },
          onDone(result) {
            stream.live = false;
            clearSessionStream(sessionId);
            upsertSendResultMessages(result, resultOptions);
            applyChatBalance(result.balance);
            if (result.assistant_message.status === "failed") {
              message.error(result.assistant_message.error_message || "对话失败");
            }
            if (activeSessionId.value === sessionId) {
              void scrollToBottom(true);
            }
          },
          onErrorEvent(errEvent) {
            const streamed = stream.visibleText.trim();
            if (streamed) {
              const assistantId = stream.messageId;
              clearSessionStream(sessionId);
              mutateSessionMessages(sessionId, (items) => items.map((item) => (
                assistantId != null && item.id === assistantId
                  ? {
                      ...item,
                      content: streamed,
                      status: "success" as const,
                      error_message: "",
                    }
                  : item
              )));
              return;
            }
            const failedAssistant = errEvent.assistant_message || {
              id: stream.messageId || Date.now(),
              session_id: sessionId,
              role: "assistant" as const,
              content: stream.visibleText || errEvent.message || "对话失败",
              model,
              credit_cost: 0,
              status: "failed",
              error_message: errEvent.message || "对话失败",
              created_at: new Date().toISOString(),
            };
            clearSessionStream(sessionId);
            mutateSessionMessages(sessionId, (items) => {
              const assistantIndex = items.findIndex((item) => item.id === failedAssistant.id);
              if (assistantIndex >= 0) {
                const next = items.slice();
                next.splice(assistantIndex, 1, failedAssistant);
                return next;
              }
              return [...items, failedAssistant];
            });
            if (errEvent.session) {
              sessions.value = [
                errEvent.session,
                ...sessions.value.filter((item) => item.id !== errEvent.session?.id),
              ];
            }
            applyChatBalance(errEvent.balance);
            message.error(errEvent.message || "对话失败");
          },
        },
        controller.signal,
      );
    } else {
      const result = await sendChatMessage(sessionId, sendPayload, controller.signal);
      upsertSendResultMessages(result, resultOptions);
      applyChatBalance(result.balance);
      if (result.assistant_message.status === "failed") {
        message.error(result.assistant_message.error_message || "对话失败");
      } else if (isBrokenAssistantMessage(result.assistant_message)) {
        message.error("系统出错，可进行重试");
      }
      if (activeSessionId.value === sessionId) {
        await scrollToBottom(true);
      }
      if (
        result.assistant_message.status !== "failed"
        && !isBrokenAssistantMessage(result.assistant_message)
        && activeSessionId.value === sessionId
      ) {
        await streamAssistantMessage(result.assistant_message);
      }
    }
    snapshotDraftImages.forEach(revokeDraftImageUrl);
  } catch (err: any) {
    if (isRequestAborted(err)) {
      const stream = sessionId ? sessionStreamStates.get(sessionId) : null;
      const interruptedAssistantId = stream?.messageId ?? null;
      const interruptedAssistantSeed = stream?.assistant ?? null;
      const interruptedContent = stream?.visibleText || "已中断";
      const interruptedSessionId = sessionId || activeSessionId.value || "";
      mutateSessionMessages(interruptedSessionId, (items) => {
        const next = items.map((item) => {
          if (item.id === tempUserMessageId) {
            return { ...item, status: "success" as const };
          }
          if (interruptedAssistantId != null && item.id === interruptedAssistantId) {
            return {
              ...item,
              content: interruptedContent || item.content,
              status: "failed" as const,
              error_message: "已中断",
            };
          }
          return item;
        });
        if (
          interruptedAssistantId != null
          && !next.some((item) => item.id === interruptedAssistantId)
        ) {
          next.push({
            ...(interruptedAssistantSeed || {
              id: interruptedAssistantId,
              session_id: interruptedSessionId,
              role: "assistant" as const,
              model,
              client_message_id: null,
              credit_cost: 0,
              created_at: new Date().toISOString(),
            }),
            content: interruptedContent,
            status: "failed",
            error_message: "已中断",
          });
        }
        return next;
      });
      clearSessionStream(interruptedSessionId);
      snapshotDraftImages.forEach(revokeDraftImageUrl);
      if (activeSessionId.value === interruptedSessionId) {
        message.info("已中断");
      }
      return;
    }
    if (!options.skipOptimisticUser) {
      mutateSessionMessages(sessionId || activeSessionId.value || "", (items) => (
        items.filter((item) => item.id !== tempUserMessageId)
      ));
    }
    if (overrideText == null) {
      draft.value = content;
      if (!draftImages.value.length && snapshotDraftImages.length) {
        draftImages.value = snapshotDraftImages;
      }
    }
    const detail = err?.response?.data?.detail;
    if (err?.code === "ECONNABORTED" || /timeout/i.test(String(err?.message || ""))) {
      message.error("请求超时，请稍后重试");
    } else {
      message.error(detail || err?.message || "发送失败");
    }
  } finally {
    endSessionSend(sessionId, controller);
  }
}

function canRetryAssistant(item: ChatMessage) {
  if (isReadOnly.value) return false;
  return item.role === "assistant" && (item.status === "failed" || isBrokenAssistantMessage(item));
}

async function handleRetryAssistant(item: ChatMessage) {
  if (isActiveSessionSending.value || !canRetryAssistant(item)) return;
  const previousUser = findPreviousUserMessage(item);
  const content = (previousUser?.content || "").trim();
  const images = previousUser ? messageImages(previousUser) : [];
  if (!content && !images.length) {
    message.warning("找不到可重试的用户消息");
    return;
  }
  messages.value = messages.value.filter((msg) => msg.id !== item.id);
  await handleSend(content, {
    model: previousUser?.model || item.model || selectedModel.value,
    skipOptimisticUser: true,
    images,
  });
}

function handleDockTabEnabledChange(enabled: boolean) {
  dockTabEnabled.value = enabled;
  setAiAssistantDockTabEnabled(enabled);
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (isActiveSessionSending.value) return;
    void handleSend();
  }
}

watch(activeSessionId, (value) => {
  emit("update:sessionId", value);
  if (!value) {
    ensureDefaultModel();
    return;
  }
  const session = sessions.value.find((item) => item.id === value);
  applySessionModel(session?.model);
});

watch(models, () => {
  ensureDefaultModel();
});

watch(
  () => route.params.sessionId,
  async (raw) => {
    if (!props.syncRoute) return;
    if (selectingSession.value || loadingSessions.value) return;
    const routeSessionId = parseRouteSessionId(raw);
    if (!routeSessionId) {
      if (activeSessionId.value) {
        // keep current selection when URL is bare /chat
        return;
      }
      return;
    }
    if (routeSessionId === activeSessionId.value) return;
    await selectSession(routeSessionId, { syncRoute: false });
  },
);

watch(
  [() => messages.value.length, sending],
  async () => {
    await scrollToBottom(false);
    await nextTick();
    updateScrollToBottomVisibility();
  },
);

watch(sessionSearchKeyword, (value) => {
  if (!props.adminViewer) return;
  window.clearTimeout(adminSearchTimer);
  adminSearchTimer = window.setTimeout(() => {
    void loadSessions(true, activeSessionId.value);
  }, value.trim() ? 300 : 0);
});

onMounted(async () => {
  document.addEventListener("pointerdown", handleDocumentPointerDown, true);
  unsubscribeAiAssistantDockTabEnabled = subscribeAiAssistantDockTabEnabled((enabled) => {
    dockTabEnabled.value = enabled;
  });
  await loadModels();
  await loadSessions(true, props.syncRoute ? parseRouteSessionId() : null);
});

onBeforeUnmount(() => {
  unsubscribeAiAssistantDockTabEnabled?.();
  unsubscribeAiAssistantDockTabEnabled = null;
  window.clearTimeout(adminSearchTimer);
  sendAbortControllers.forEach((controller) => controller.abort());
  sendAbortControllers.clear();
  sendingSessionIds.value = [];
  sessionStreamStates.clear();
  stopAssistantStreaming();
  clearDraftImages();
  document.removeEventListener("pointerdown", handleDocumentPointerDown, true);
});

defineExpose({
  createSession: handleCreateSession,
});
</script>

<template>
  <div
    class="chat-page"
    :class="{
      'sidebar-collapsed': sidebarCollapsed,
      'has-draft-images': draftImages.length,
      'is-embedded': embedded,
      'is-readonly': isReadOnly,
      'is-admin-viewer': adminViewer,
    }"
  >
    <aside class="chat-sidebar">
      <div class="chat-assistant-brand">
        <img :src="xiaobaAvatarSrc" alt="小八" class="chat-assistant-avatar" />
        <span class="chat-assistant-name">{{ adminViewer ? "用户对话" : "小八" }}</span>
      </div>
      <div class="sidebar-toolbar">
        <button
          v-if="!isReadOnly"
          class="new-chat-btn"
          :disabled="!models.length"
          @click="handleCreateSession"
        >
          <PlusOutlined />
          <span>新建对话</span>
        </button>
        <button
          v-if="!sessionSearchOpen"
          type="button"
          class="session-search-toggle"
          title="搜索对话"
          @click="openSessionSearch"
        >
          <SearchOutlined />
        </button>
      </div>
      <div v-if="sessionSearchOpen" class="session-search-bar">
        <SearchOutlined class="session-search-bar-icon" />
        <input
          ref="sessionSearchInputRef"
          v-model="sessionSearchKeyword"
          class="session-search-input"
          type="search"
          :placeholder="adminViewer ? '搜索用户或对话标题' : '搜索对话标题'"
          enterkeyhint="search"
        />
        <button type="button" class="session-search-close" title="关闭搜索" @click="closeSessionSearch">
          <CloseOutlined />
        </button>
      </div>
      <div class="session-section-title">历史对话</div>
      <div class="session-list" @scroll.passive="($event) => {
        const el = $event.target as HTMLElement;
        if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) loadMoreSessions();
      }">
        <div v-if="loadingSessions && !sessions.length" class="empty-tip">加载中...</div>
        <button
          v-for="session in filteredSessions"
          :key="session.id"
          class="session-item"
          :class="{ active: session.id === activeSessionId }"
          @click="selectSession(session.id)"
        >
          <span
            v-if="adminViewer"
            class="session-user-avatar"
            :title="sessionOwnerName(session)"
            @click="openSessionUserInfo(session, $event)"
          >
            <img
              v-if="sessionOwnerAvatar(session)"
              :src="sessionOwnerAvatar(session)"
              alt=""
            />
            <span v-else>{{ sessionOwnerInitial(session) }}</span>
          </span>
          <div class="session-main">
            <div class="session-title">{{ session.title || "新对话" }}</div>
            <div class="session-time">
              <template v-if="adminViewer">{{ sessionOwnerName(session) }} · </template>
              {{ formatTime(session.last_message_at || session.updated_at || session.created_at) }}
            </div>
          </div>
          <span
            v-if="!isReadOnly"
            class="session-delete"
            @click="handleDeleteSession(session, $event)"
          >
            <DeleteOutlined />
          </span>
        </button>
        <div v-if="!loadingSessions && !sessions.length" class="empty-tip">
          {{ isReadOnly ? "暂无用户会话" : "暂无会话，点击上方新建" }}
        </div>
        <div
          v-else-if="!loadingSessions && sessions.length && !filteredSessions.length"
          class="empty-tip"
        >
          没有匹配的对话
        </div>
      </div>
    </aside>

    <section class="chat-main">
      <label
        v-if="showDockSwitch"
        class="chat-dock-switch"
        title="在创作页显示侧边助手入口"
      >
        <span class="chat-dock-switch-label">在创作页显示侧边助手入口</span>
        <span class="chat-dock-switch-label-short">侧边助手</span>
        <a-switch
          class="warm-switch"
          size="small"
          :checked="dockTabEnabled"
          @change="handleDockTabEnabledChange"
        />
      </label>
      <button
        type="button"
        class="sidebar-toggle-btn"
        :title="sidebarCollapsed ? '展开会话列表' : '收起会话列表'"
        @click="toggleSidebar"
      >
        <svg class="sidebar-toggle-icon" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3.5" y="3.5" width="17" height="17" rx="4.5" ry="4.5" fill="none" stroke="currentColor" stroke-width="1.7" />
          <path d="M8.2 4.2v15.6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
        </svg>
      </button>
      <div v-if="adminViewer && activeSession" class="admin-session-owner">
        <button
          type="button"
          class="session-user-avatar"
          :title="sessionOwnerName(activeSession)"
          @click="openSessionUserInfo(activeSession)"
        >
          <img
            v-if="sessionOwnerAvatar(activeSession)"
            :src="sessionOwnerAvatar(activeSession)"
            alt=""
          />
          <span v-else>{{ sessionOwnerInitial(activeSession) }}</span>
        </button>
        <div class="admin-session-owner-copy">
          <strong>{{ sessionOwnerName(activeSession) }}</strong>
          <span>{{ activeSession.title || "新对话" }}</span>
        </div>
        <div class="admin-session-credit">
          消耗 {{ Number(activeSession.credit_cost || 0) }} 积分
        </div>
      </div>
      <div class="message-stage">
        <div v-if="sessionPanelLoading" class="message-panel-loading">
          <LoadingOutlined />
          <span>加载中...</span>
        </div>
        <div
          ref="messageListRef"
          class="message-list"
          :class="{ 'is-faded': chatPanelFaded || sessionPanelLoading }"
          @scroll.passive="handleMessageListScroll"
        >
          <div class="message-column">
            <div v-if="messagesHasMore" class="load-older">
              <a-button size="small" :loading="loadingOlder" @click="loadOlderMessages">加载更早消息</a-button>
            </div>
            <div v-if="!messages.length && !sessionPanelLoading" class="empty-state">
              <div class="empty-title">{{ emptyChatTitle }}</div>
              <div v-if="!isReadOnly && openingGreeting" class="greeting-card">{{ openingGreeting }}</div>
              <div v-else-if="isReadOnly" class="empty-desc">
                {{ activeSession ? "此会话暂无消息，仅支持查看。" : "从左侧历史对话中选择一个会话。" }}
              </div>
              <div v-else class="empty-desc">在下方输入内容，选择场景后发送。</div>
              <div v-if="!isReadOnly && starterPrompts.length" class="starter-prompts">
                <div class="starter-prompts-title">试试这样问</div>
                <div class="starter-prompt-list">
                  <button
                    v-for="item in starterPrompts"
                    :key="item.id"
                    type="button"
                    class="starter-prompt-btn"
                    :class="{ 'has-image': Boolean(item.image_url) }"
                    :disabled="isActiveSessionSending || !models.length"
                    @click="handleStarterPrompt(item)"
                  >
                    <span v-if="item.tag" class="starter-prompt-tag">{{ item.tag }}</span>
                    <img
                      v-if="item.image_url"
                      :src="chatImageDisplaySrc(item.image_url)"
                      alt=""
                      class="starter-prompt-image"
                      @click.stop="openChatImagePreview(item.image_url)"
                    />
                    <span class="starter-prompt-text">{{ item.text }}</span>
                  </button>
                </div>
              </div>
            </div>
            <div
              v-for="item in messages"
              :key="item.id"
              class="message-row"
              :class="item.role === 'user' ? 'is-user' : 'is-assistant'"
            >
              <div class="message-stack">
                <div
                  class="message-bubble"
                  :class="{
                    failed: item.status === 'failed' || isBrokenAssistantMessage(item),
                  }"
                >
                  <div v-if="item.role !== 'user'" class="message-meta">
                    <span>{{ sceneOptionLabel(models.find((m) => m.model_key === item.model)) || "助手" }}</span>
                    <div class="message-meta-right">
                      <span>{{ formatTime(item.created_at) }}</span>
                      <div v-if="messagePlainText(item) || canRetryAssistant(item)" class="message-actions">
                        <a-tooltip v-if="messagePlainText(item)" title="复制">
                          <button
                            type="button"
                            class="message-action-btn"
                            aria-label="复制"
                            @click="handleCopyMessage(item)"
                          >
                            <CopyOutlined />
                          </button>
                        </a-tooltip>
                        <a-tooltip v-if="canRetryAssistant(item)" title="重试">
                          <button
                            type="button"
                            class="message-action-btn"
                            aria-label="重试"
                            :disabled="isActiveSessionSending"
                            @click="handleRetryAssistant(item)"
                          >
                            <ReloadOutlined />
                          </button>
                        </a-tooltip>
                      </div>
                    </div>
                  </div>
                  <div v-if="isBrokenAssistantMessage(item)" class="message-error-block">
                    <div class="message-error">系统出错，可进行重试</div>
                    <button
                      type="button"
                      class="message-retry-btn"
                      :disabled="isActiveSessionSending"
                      @click="handleRetryAssistant(item)"
                    >
                      <ReloadOutlined />
                      <span>重试</span>
                    </button>
                  </div>
                  <template v-else>
                    <div v-if="item.role === 'user' && messageImages(item).length" class="message-images">
                      <button
                        v-for="image in messageImages(item)"
                        :key="image.url"
                        type="button"
                        class="message-image-link"
                        title="预览图片"
                        @click="openChatImagePreview(image.url)"
                      >
                        <img :src="chatImageDisplaySrc(image.url)" alt="" class="message-image" />
                      </button>
                    </div>
                    <MarkdownMessage
                      v-if="item.role === 'assistant' && (item.content || '').trim()"
                      :content="assistantDisplayText(item)"
                      :streaming="streamingMessageId === item.id"
                      @generate="handleBlockJumpGenerate"
                    />
                    <div
                      v-else-if="(item.content || '').trim()"
                      class="message-content is-plain"
                    >{{ item.content }}</div>
                    <div
                      v-else-if="!item.generate?.status && (item.role !== 'user' || !messageImages(item).length)"
                      class="message-content is-plain"
                    >{{ item.error_message || "系统出错，可进行重试" }}</div>
                    <ChatGenerateCard
                      v-if="item.role === 'assistant' && item.generate?.status"
                      :session-id="item.session_id || activeSessionId || ''"
                      :message-id="item.id"
                      :generate="item.generate"
                      :readonly="isReadOnly"
                      :admin-viewer="adminViewer"
                      @updated="handleGenerateCardUpdated"
                      @preview="openChatImagePreview"
                    />
                  </template>
                  <div
                    v-if="item.status === 'failed' && !isBrokenAssistantMessage(item)"
                    class="message-error"
                  >
                    发送失败：{{ item.error_message || "未知错误" }}
                  </div>
                </div>
                <div v-if="item.role === 'user'" class="message-footer">
                  <span class="message-footer-time">{{ formatTime(item.created_at) }}</span>
                  <a-tooltip v-if="messagePlainText(item)" title="复制">
                    <button
                      type="button"
                      class="message-action-btn"
                      aria-label="复制"
                      @click="handleCopyMessage(item)"
                    >
                      <CopyOutlined />
                    </button>
                  </a-tooltip>
                </div>
              </div>
            </div>
            <div v-if="isActiveSessionSending && !streamingVisibleText.trim()" class="message-row is-assistant">
              <div class="message-bubble loading-bubble">
                <LoadingOutlined />
                <span>正在思考...</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button
        v-if="showScrollToBottom"
        type="button"
        class="scroll-to-bottom-btn"
        title="回到底部"
        @click="scrollToBottom(true)"
      >
        <ArrowDownOutlined />
      </button>

      <div v-if="!isReadOnly" class="composer-dock" @click="composerPopoverOpen = false">
        <section
          class="chat-composer-shell"
          :class="{ 'is-drag-over': composerDragActive }"
          @click.stop
          @paste="handleComposerPaste"
          @dragenter="handleComposerDragOver"
          @dragover="handleComposerDragOver"
          @dragleave="handleComposerDragLeave"
          @drop="handleComposerDrop"
        >
          <input
            ref="chatImageInputRef"
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            multiple
            hidden
            @change="handleChatImageChange"
          />
          <div v-if="draftImages.length" class="composer-image-list">
            <div
              v-for="item in draftImages"
              :key="item.id"
              class="composer-image-thumb"
              :class="{ failed: item.status === 'failed' }"
              @click="openChatImagePreview(item.remoteUrl || item.localUrl)"
            >
              <img :src="item.remoteUrl ? chatImageDisplaySrc(item.remoteUrl) : item.localUrl" alt="" />
              <div v-if="item.status !== 'success'" class="composer-image-mask">
                <a-spin v-if="item.status === 'uploading'" size="small" />
                <span v-else>失败</span>
              </div>
              <button
                type="button"
                class="composer-image-remove"
                title="移除图片"
                :disabled="isActiveSessionSending"
                @click.stop="removeDraftImage(item.id)"
              >
                <CloseOutlined />
              </button>
            </div>
          </div>
          <textarea
            v-model="draft"
            class="composer-prompt-input"
            :disabled="!models.length"
            placeholder="输入想聊的内容，也可粘贴或拖入图片（Enter 发送，Shift + Enter 换行）"
            @keydown="handleComposerKeydown"
            @paste="handleComposerPaste"
            @focus="composerPopoverOpen = false"
          ></textarea>
          <div class="composer-footer">
            <div ref="composerSettingWrapRef" class="composer-setting-wrap">
              <div
                v-if="composerPopoverOpen"
                class="composer-popover-card"
                @click.stop
              >
                <div class="composer-option-field">
                  <label>对话场景</label>
                  <div class="composer-scene-list">
                    <button
                      v-for="item in models"
                      :key="item.model_key"
                      type="button"
                      class="composer-scene-option"
                      :class="{ active: item.model_key === selectedModel }"
                      :disabled="isActiveSessionSending"
                      @click="handleModelChange(item.model_key)"
                    >
                      <span class="composer-scene-option-title">{{ sceneOptionLabel(item) }}</span>
                      <span v-if="item.subtitle || item.model_description" class="composer-scene-option-desc">
                        {{ item.subtitle || item.model_description }}
                      </span>
                      <span class="composer-scene-option-meta">
                        {{ item.credit_cost > 0 ? `${item.credit_cost} 积分` : "免费" }}
                      </span>
                    </button>
                  </div>
                </div>
              </div>
              <button
                type="button"
                class="composer-setting-group"
                :disabled="isActiveSessionSending || !models.length"
                @click.stop="toggleComposerPopover"
              >
                <ThunderboltOutlined />
                <span class="composer-setting-model-text">{{ modelChipLabel }}</span>
                <template v-if="selectedModelOption?.subtitle">
                  <span class="composer-chip-divider"></span>
                  <span>{{ selectedModelOption.subtitle }}</span>
                </template>
                <template v-else-if="selectedModelOption?.credit_cost">
                  <span class="composer-chip-divider"></span>
                  <span>{{ selectedModelOption.credit_cost }} 积分</span>
                </template>
              </button>
            </div>
            <button
              type="button"
              class="composer-attach-btn"
              title="添加图片"
              :disabled="isActiveSessionSending || !models.length || draftImages.length >= MAX_CHAT_IMAGES"
              @click="openChatImagePicker"
            >
              <PictureOutlined />
            </button>
            <a-button
              v-if="isActiveSessionSending"
              type="primary"
              class="composer-generate-btn composer-stop-btn"
              title="中断"
              @click="handleStopSending"
            >
              <span class="composer-stop-icon" aria-hidden="true"></span>
              中断
            </a-button>
            <a-button
              v-else
              type="primary"
              class="composer-generate-btn"
              :disabled="!canSend"
              @click="() => handleSend()"
            >
              <template #icon><ThunderboltOutlined /></template>
              {{ sendButtonText }}
            </a-button>
          </div>
        </section>
        <div v-if="!models.length" class="composer-hint">暂无可用对话场景，请联系管理员在「对话接口」中配置场景绑定。</div>
      </div>
    </section>
    <div style="display: none">
      <a-image
        :key="previewSrc"
        :src="previewSrc"
        :preview="{
          visible: previewVisible,
          onVisibleChange: (visible: boolean) => (previewVisible = visible),
        }"
      />
    </div>
    <AdminUserInfoDialog
      v-if="adminViewer"
      v-model:open="userInfoDialogOpen"
      :user="userInfoDialogUser"
    />
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 112px);
  min-height: 560px;
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.06));
  background: var(--theme-page-base, #fffaf3);
}

.chat-page.is-embedded {
  height: 100%;
  min-height: 0;
  border: 0;
  border-radius: 0;
}

.chat-page.is-embedded .chat-sidebar {
  width: 220px;
}

.chat-page.is-embedded .composer-prompt-input {
  min-height: 72px;
}

.chat-page.is-readonly .chat-main {
  --chat-composer-reserve: 24px;
}

.chat-page.is-readonly :deep(.md-code-generate) {
  display: none;
}

.chat-page.is-readonly .sidebar-toolbar {
  justify-content: flex-end;
}

.session-user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  overflow: hidden;
  border: 0;
  border-radius: 50%;
  background: #f3e6d2;
  color: #8b5a1a;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.session-user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.admin-session-owner {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  min-height: 48px;
  padding: 8px 16px 8px 56px;
  border-bottom: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.06));
  background: var(--theme-page-base, #fffaf3);
}

.admin-session-owner-copy {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  line-height: 1.3;
}

.admin-session-credit {
  flex-shrink: 0;
  color: var(--theme-title, #3d2f22);
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}

.admin-session-owner-copy strong {
  color: var(--theme-title, #3d2f22);
  font-size: 14px;
}

.admin-session-owner-copy span {
  color: var(--theme-text-secondary, #7a614a);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-sidebar {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 12px;
  border-right: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.06));
  background: linear-gradient(180deg, var(--theme-panel-bg, #fff9f0), var(--theme-panel-bg-soft, #fff4e6));
  overflow: hidden;
  transition:
    width 0.22s ease,
    padding 0.22s ease,
    opacity 0.18s ease,
    border-color 0.18s ease;
}

.chat-page.sidebar-collapsed .chat-sidebar {
  width: 0;
  padding-left: 0;
  padding-right: 0;
  opacity: 0;
  border-right-color: transparent;
  pointer-events: none;
}

.chat-assistant-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 4px 4px;
}

.chat-assistant-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 4px 10px rgba(90, 60, 20, 0.08);
  flex-shrink: 0;
}

.chat-assistant-name {
  color: var(--theme-title, #3d2f22);
  font-size: 18px;
  font-weight: 800;
  line-height: 1.2;
  letter-spacing: 0.02em;
}

.session-section-title {
  padding: 4px 8px 0;
  color: var(--theme-text-secondary, #7a614a);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.sidebar-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.new-chat-btn {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 40px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  background: var(--theme-panel-bg-muted, #fff);
  color: var(--theme-title, #3d2f22);
  cursor: pointer;
  font-weight: 700;
}

.new-chat-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.session-search-toggle,
.session-search-close {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  background: var(--theme-panel-bg-muted, #fff);
  color: var(--theme-text-secondary, #7a614a);
  cursor: pointer;
}

.session-search-toggle:hover,
.session-search-close:hover {
  color: var(--theme-title, #3d2f22);
  background: var(--theme-panel-bg-soft, #fff4e6);
}

.session-search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 10px 0 12px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  background: var(--theme-panel-bg-muted, #fff);
}

.session-search-bar-icon {
  flex-shrink: 0;
  color: var(--theme-text-secondary, #7a614a);
  font-size: 14px;
}

.session-search-input {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: none;
  outline: none;
  background: transparent;
  color: var(--theme-title, #3d2f22);
  font-size: 13px;
}

.session-search-input::placeholder {
  color: var(--theme-text-secondary, #a08970);
}

.session-search-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 12px;
}

.session-list {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--theme-title, #3d2f22);
  text-align: left;
  cursor: pointer;
}

.session-item:hover,
.session-item.active {
  background: var(--theme-panel-bg-muted, rgba(0, 0, 0, 0.05));
}

.session-main {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 14px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-time,
.empty-tip,
.composer-hint,
.message-meta,
.message-error,
.empty-desc {
  color: var(--theme-text-secondary, #7a614a);
  font-size: 12px;
}

.session-delete {
  opacity: 0;
  color: var(--theme-text-secondary, #9ca3af);
}

.session-item:hover .session-delete {
  opacity: 1;
}

.chat-main {
  --chat-column-width: min(860px, calc(100% - 32px));
  --chat-composer-reserve: 148px;
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--theme-page-base, #f7f4ef);
}

.chat-page.has-draft-images .chat-main {
  --chat-composer-reserve: 228px;
}

.chat-dock-switch {
  position: absolute;
  top: 12px;
  right: 16px;
  z-index: 26;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--theme-panel-border, rgba(80, 52, 20, 0.08));
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-panel-bg) 92%, transparent);
  box-shadow: 0 6px 16px var(--theme-shadow-soft);
  color: var(--theme-text-secondary, #8b7457);
  font-size: 12px;
  line-height: 1.2;
  cursor: pointer;
}

.chat-dock-switch-label {
  white-space: nowrap;
}

.chat-dock-switch-label-short {
  display: none;
}

.sidebar-toggle-btn {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 26;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  border-radius: 10px;
  background: color-mix(in srgb, var(--theme-panel-bg, #fff9f0) 92%, #fff);
  color: var(--theme-title, #3d2f22);
  box-shadow: 0 6px 14px rgba(60, 40, 20, 0.08);
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    transform 0.15s ease;
}

.sidebar-toggle-btn:hover {
  background: var(--theme-panel-bg-soft, #fff4e6);
  border-color: var(--theme-border-strong, #d9c2a4);
  transform: translateY(-1px);
}

.sidebar-toggle-icon {
  width: 18px;
  height: 18px;
  display: block;
}

.chat-page.sidebar-collapsed .sidebar-toggle-icon {
  transform: scaleX(-1);
}

.message-stage {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.message-panel-loading {
  position: absolute;
  inset: 0 0 var(--chat-composer-reserve) 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--theme-text-secondary, #7a614a);
  font-size: 13px;
  font-weight: 600;
  pointer-events: none;
}

.message-panel-loading :deep(.anticon) {
  font-size: 22px;
  color: var(--theme-accent, #f7a831);
}

.message-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px 16px var(--chat-composer-reserve);
  opacity: 1;
  transition: opacity 0.18s ease;
}

.message-list.is-faded {
  opacity: 0;
  pointer-events: none;
}

.message-column {
  width: var(--chat-column-width);
  margin: 0 auto;
}

.load-older {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}

.empty-state {
  margin: 12vh auto 0;
  text-align: center;
}

.scroll-to-bottom-btn {
  position: absolute;
  left: 50%;
  bottom: calc(var(--chat-composer-reserve) - 18px);
  z-index: 24;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  border-radius: 999px;
  background: var(--theme-surface-strong);
  color: var(--theme-title, #3d2f22);
  box-shadow: 0 10px 24px var(--theme-shadow-medium);
  transform: translateX(-50%);
  cursor: pointer;
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
}

.scroll-to-bottom-btn:hover {
  transform: translateX(-50%) translateY(-1px);
  box-shadow: 0 14px 28px rgba(60, 40, 20, 0.18);
}

.empty-title {
  color: var(--theme-title, #3d2f22);
  font-size: 22px;
  font-weight: 800;
  margin-bottom: 12px;
}

.greeting-card {
  display: inline-block;
  max-width: min(560px, 100%);
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(180deg, var(--theme-panel-bg, #fff9f0), var(--theme-panel-bg-soft, #fff4e6));
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.06));
  box-shadow: 0 12px 28px var(--theme-card-shadow, rgba(90, 60, 20, 0.08));
  color: var(--theme-title, #3d2f22);
  text-align: left;
  white-space: pre-wrap;
}

.starter-prompts {
  width: min(560px, 100%);
  margin: 18px auto 0;
  text-align: left;
}

.starter-prompts-title {
  margin-bottom: 10px;
  color: var(--theme-text-secondary, #7a614a);
  font-size: 13px;
  font-weight: 700;
}

.starter-prompt-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.starter-prompt-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px 12px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  background: color-mix(in srgb, var(--theme-panel-bg, #fff9f0) 88%, #fff);
  color: var(--theme-title, #3d2f22);
  text-align: left;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    transform 0.15s ease;
}

.starter-prompt-btn:hover:not(:disabled) {
  background: var(--theme-panel-bg-soft, #fff4e6);
  border-color: color-mix(in srgb, var(--theme-accent, #f7a831) 45%, var(--theme-panel-border, #ebd9c1));
  transform: translateY(-1px);
}

.starter-prompt-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.starter-prompt-image {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  object-fit: cover;
  cursor: zoom-in;
}

.starter-prompt-tag {
  flex-shrink: 0;
  margin-top: 0;
  padding: 2px 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-accent, #f7a831) 22%, #fff);
  color: var(--theme-accent-text, #9a5a00);
  font-size: 11px;
  font-weight: 800;
  line-height: 1.4;
}

.starter-prompt-text {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.45;
}

.message-row {
  display: flex;
  margin-bottom: 32px;
}

.message-row.is-user {
  justify-content: flex-end;
}

.message-row.is-assistant {
  justify-content: flex-start;
}

.message-stack {
  display: flex;
  flex-direction: column;
  max-width: 100%;
  min-width: 0;
}

.message-row.is-user .message-stack {
  position: relative;
  align-items: flex-end;
}

/* 承接气泡与底部操作区之间的空隙，避免移向复制图标时 hover 断开 */
.message-row.is-user .message-stack::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  height: 32px;
}

.message-row.is-assistant .message-stack {
  align-items: stretch;
  width: 100%;
}

.message-bubble {
  width: 100%;
  max-width: 100%;
  padding: 12px 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, var(--theme-panel-bg, #fff9f0), var(--theme-panel-bg-soft, #fff4e6));
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.06));
  color: var(--theme-title, #3d2f22);
  box-shadow: 0 8px 18px var(--theme-card-shadow, rgba(90, 60, 20, 0.06));
  word-break: break-word;
}

.message-row.is-user .message-bubble,
.message-row.is-assistant .message-bubble.loading-bubble {
  width: auto;
  max-width: 100%;
}

.message-row.is-user .message-bubble {
  background: var(--theme-accent, #f7a831);
  color: var(--theme-accent-contrast, #3d2f22);
  border-color: transparent;
  padding: 12px 16px;
}

.message-footer {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  padding-top: 4px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.message-row.is-user:hover .message-footer,
.message-row.is-user:focus-within .message-footer {
  opacity: 1;
  pointer-events: auto;
}

.message-footer-time {
  color: var(--theme-text-secondary, #7a614a);
  font-size: 12px;
  line-height: 1;
}

.message-bubble.failed {
  border-color: #fca5a5;
  background: color-mix(in srgb, #ef4444 8%, var(--theme-panel-bg));
}

.message-error-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.message-retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border: 1px solid color-mix(in srgb, #ef4444 35%, var(--theme-panel-border, #ebd9c1));
  border-radius: 10px;
  background: var(--theme-surface-strong);
  color: #b42318;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.message-retry-btn:hover:not(:disabled) {
  background: color-mix(in srgb, #ef4444 8%, var(--theme-panel-bg));
}

.message-retry-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.message-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.message-meta-right {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.message-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.message-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--theme-text-secondary, #7a614a);
  cursor: pointer;
  font-size: 13px;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.message-action-btn:hover {
  background: var(--theme-panel-bg-muted, rgba(0, 0, 0, 0.06));
  color: var(--theme-title, #3d2f22);
}

.message-content.is-plain {
  white-space: pre-wrap;
  word-break: break-word;
}

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.message-images:last-child {
  margin-bottom: 0;
}

.message-image-link {
  display: block;
  width: 88px;
  height: 88px;
  padding: 0;
  border: 0;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.35);
  cursor: zoom-in;
}

.message-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.message-content.is-streaming::after {
  content: "";
  display: inline-block;
  width: 0.55em;
  height: 1.05em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: currentColor;
  opacity: 0.55;
  animation: chat-stream-caret 0.9s step-end infinite;
}

@keyframes chat-stream-caret {
  50% {
    opacity: 0;
  }
}

.md-body {
  color: inherit;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}

.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4),
.md-body :deep(h5),
.md-body :deep(h6),
.md-body :deep(.md-section-title) {
  margin: 14px 0 8px;
  color: var(--theme-title, #3d2f22);
  font-weight: 800;
  line-height: 1.35;
}

.md-body :deep(h1:first-child),
.md-body :deep(h2:first-child),
.md-body :deep(h3:first-child),
.md-body :deep(h4:first-child),
.md-body :deep(.md-section-title:first-child) {
  margin-top: 0;
}

.md-body :deep(h1) {
  font-size: 18px;
}

.md-body :deep(h2) {
  font-size: 16px;
}

.md-body :deep(h3),
.md-body :deep(.md-section-title) {
  font-size: 15px;
}

.md-body :deep(h4),
.md-body :deep(h5),
.md-body :deep(h6) {
  font-size: 14px;
}

.md-body :deep(p) {
  margin: 0 0 10px;
}

.md-body :deep(ul),
.md-body :deep(ol) {
  margin: 0 0 10px;
  padding-left: 1.3em;
}

.md-body :deep(li) {
  margin: 4px 0;
}

.md-body :deep(li > p) {
  margin-bottom: 6px;
}

.md-body :deep(li > p:last-child) {
  margin-bottom: 0;
}

.md-body :deep(hr) {
  margin: 14px 0;
  border: 0;
  border-top: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
}

.md-body :deep(blockquote) {
  margin: 0 0 10px;
  padding: 8px 12px;
  border-left: 3px solid var(--theme-accent, #f7a831);
  background: color-mix(in srgb, var(--theme-accent, #f7a831) 8%, transparent);
  border-radius: 0 10px 10px 0;
}

.md-body :deep(.md-copyable > blockquote) {
  margin: 0;
  padding: 12px 14px 14px;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.md-body :deep(blockquote p:last-child),
.md-body :deep(.md-copyable > blockquote > :last-child) {
  margin-bottom: 0;
}

.md-body :deep(.md-copyable .md-copyable) {
  margin: 8px 0 0;
  border: 0;
  background: transparent;
}

.md-body :deep(.md-copyable .md-copyable > .md-code-toolbar) {
  display: none;
}

.md-body :deep(.md-copyable .md-copyable pre) {
  padding: 0;
}

.md-body :deep(strong) {
  font-weight: 800;
}

.md-body :deep(a) {
  color: var(--theme-link, #d38a12);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.md-body :deep(a:hover) {
  color: var(--theme-link-hover, #b26c04);
}

.md-body :deep(img) {
  display: block;
  max-width: min(100%, 560px);
  height: auto;
  margin: 0 0 12px;
  border-radius: 12px;
}

.md-body :deep(code) {
  padding: 1px 6px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--theme-title, #3d2f22) 8%, transparent);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.md-body :deep(pre) {
  margin: 0 0 12px;
  padding: 12px;
  overflow: auto;
  border-radius: 12px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  background: color-mix(in srgb, var(--theme-title, #3d2f22) 5%, transparent);
}

.md-body :deep(pre code) {
  padding: 0;
  background: transparent;
  font-size: 12px;
  white-space: pre-wrap;
}

.md-body :deep(.md-code-block) {
  margin: 0 0 12px;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  background: rgb(247, 241, 233);
  font-size: 13px;
}

.md-body :deep(.md-code-toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 34px;
  padding: 0 10px 0 12px;
  border-bottom: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.06));
  background: rgb(247, 241, 233);
}

.md-body :deep(.md-code-lang) {
  color: var(--theme-text-secondary, #8b7457);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1;
  text-transform: lowercase;
}

.md-body :deep(.md-code-lang.is-plain) {
  font-family: inherit;
  text-transform: none;
}

.md-body :deep(.md-code-actions) {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.md-body :deep(.md-code-copy),
.md-body :deep(.md-code-generate) {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--theme-text-secondary, #8b7457);
  line-height: 0;
  cursor: pointer;
}

.md-body :deep(.md-code-copy-icon),
.md-body :deep(.md-code-copy-done),
.md-body :deep(.md-code-generate-icon),
.md-body :deep(.md-code-copy svg),
.md-body :deep(.md-code-generate svg) {
  display: block;
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.md-body :deep(.md-code-copy[data-tooltip]::after),
.md-body :deep(.md-code-generate[data-tooltip]::after) {
  content: attr(data-tooltip);
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 3;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(61, 47, 34, 0.88);
  color: #fff;
  font-size: 12px;
  line-height: 1.3;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transform: translateY(-2px);
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.md-body :deep(.md-code-copy:hover[data-tooltip]::after),
.md-body :deep(.md-code-generate:hover[data-tooltip]::after) {
  opacity: 1;
  transform: translateY(0);
}

.md-body :deep(.md-code-copy:hover),
.md-body :deep(.md-code-generate:hover) {
  background: color-mix(in srgb, var(--theme-title, #3d2f22) 8%, transparent);
  color: var(--theme-title, #3d2f22);
}

.md-body :deep(.md-code-copy-done),
.md-body :deep(.md-code-copy.is-copied .md-code-copy-icon) {
  display: none;
}

.md-body :deep(.md-code-copy.is-copied .md-code-copy-done) {
  display: inline-flex;
  color: #16a34a;
}

.md-body :deep(.md-code-block pre) {
  margin: 0;
  padding: 12px 14px 14px;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.md-body :deep(.md-code-block pre code) {
  font-size: 12px;
}

.md-body :deep(.md-tok-key) {
  color: #b45309;
}

.md-body :deep(.md-tok-str) {
  color: #15803d;
}

.md-body :deep(.md-tok-kw) {
  color: #be185d;
}

.md-body :deep(.md-tok-num) {
  color: #1d4ed8;
}

.md-body :deep(.md-tok-comment) {
  color: #9a8870;
}

.md-body :deep(.md-table-wrap) {
  width: 100%;
  margin: 0 0 12px;
  overflow: hidden;
  overflow-x: auto;
  border-radius: 12px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  background: color-mix(in srgb, var(--theme-panel-bg, #fff9f0) 70%, #fff);
  box-shadow: 0 1px 2px rgba(61, 47, 34, 0.04);
}

.md-body :deep(table.md-table) {
  min-width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  background: transparent;
}

.md-body :deep(table.md-table th),
.md-body :deep(table.md-table td) {
  padding: 10px 14px;
  border: 0;
  border-right: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  border-bottom: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  text-align: left;
  vertical-align: top;
  white-space: normal;
  word-break: break-word;
}

.md-body :deep(table.md-table th:last-child),
.md-body :deep(table.md-table td:last-child) {
  border-right: 0;
}

.md-body :deep(table.md-table tbody tr:last-child td) {
  border-bottom: 0;
}

.md-body :deep(table.md-table th) {
  font-weight: 800;
  background: var(--theme-table-head-bg, #fff5df);
}

.md-body :deep(table.md-table tbody tr:nth-child(even) td) {
  background: var(--theme-table-row-bg, rgba(255, 255, 255, 0.45));
}

.md-body :deep(table.md-table tbody tr:hover td) {
  background: color-mix(in srgb, var(--theme-accent, #f7a831) 10%, #fff);
}

.md-body :deep(p:last-child),
.md-body :deep(ul:last-child),
.md-body :deep(ol:last-child),
.md-body :deep(pre:last-child),
.md-body :deep(blockquote:last-child),
.md-body :deep(img:last-child),
.md-body :deep(.md-table-wrap:last-child),
.md-body :deep(.md-code-block:last-child),
.md-body :deep(.md-section-title:last-child) {
  margin-bottom: 0;
}

.loading-bubble {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  max-width: max-content;
}

.composer-stop-icon {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 6px;
  border-radius: 2px;
  background: currentColor;
  vertical-align: -1px;
}

.composer-dock {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  min-height: var(--chat-composer-reserve);
  padding: 10px 16px 12px;
  background: var(--theme-page-base, #f7f4ef);
  pointer-events: none;
}

.composer-dock::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: -16px;
  height: 16px;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--theme-page-base, #f7f4ef) 0%, transparent),
    var(--theme-page-base, #f7f4ef)
  );
  pointer-events: none;
}

.composer-dock > * {
  position: relative;
  z-index: 1;
  pointer-events: auto;
}

.chat-composer-shell {
  box-sizing: border-box;
  width: var(--chat-column-width);
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px 10px;
  border-radius: 18px;
  border: 1px solid var(--theme-panel-border, #ebd9c1);
  background: var(--theme-panel-bg, #fff9f0);
  box-shadow: 0 16px 34px var(--theme-card-shadow, rgba(90, 60, 20, 0.12));
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.chat-composer-shell.is-drag-over {
  border-color: var(--theme-accent, #f7a831);
  box-shadow: 0 16px 34px color-mix(in srgb, var(--theme-accent, #f7a831) 24%, transparent);
}

.composer-image-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 12px 8px;
}

.composer-image-thumb {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: 10px;
  overflow: hidden;
  background: var(--theme-panel-bg-muted, rgba(0, 0, 0, 0.04));
  cursor: zoom-in;
}

.composer-image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.composer-image-thumb.failed {
  outline: 1px solid #d4380d;
}

.composer-image-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  font-size: 11px;
}

.composer-image-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  cursor: pointer;
  padding: 0;
  font-size: 10px;
}

.composer-image-remove:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.composer-attach-btn {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--theme-panel-bg-muted, rgba(0, 0, 0, 0.05));
  color: var(--theme-title, #3d2f22);
  cursor: pointer;
}

.composer-attach-btn:hover:not(:disabled) {
  background: var(--theme-panel-bg, #fff4e6);
}

.composer-attach-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.composer-prompt-input {
  width: 100%;
  min-height: 40px;
  max-height: 120px;
  flex: 0 0 auto;
  border: 0;
  outline: 0;
  resize: none;
  background: transparent;
  color: var(--theme-title, #3d2f22);
  font-size: 13px;
  line-height: 1.45;
}

.composer-prompt-input::placeholder {
  color: var(--theme-text-secondary, #7a614a);
}

.composer-prompt-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.composer-footer {
  margin-top: 0;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  min-width: 0;
}

.composer-setting-wrap {
  position: relative;
  flex: 0 1 auto;
  width: auto;
  max-width: min(260px, 52%);
  min-width: 0;
}

.composer-setting-group {
  width: auto;
  max-width: 100%;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--theme-panel-border, #ebd9c1);
  border-radius: 12px;
  background: var(--theme-panel-bg-muted, rgba(255, 255, 255, 0.72));
  color: var(--theme-title, #3d2f22);
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
}

.composer-setting-group:hover:not(:disabled) {
  border-color: var(--theme-border-strong, #d9c2a4);
  background: var(--theme-panel-bg-soft, #fff4e6);
}

.composer-setting-group:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.composer-setting-model-text {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

.composer-chip-divider {
  width: 1px;
  height: 14px;
  flex: 0 0 auto;
  margin: 0 2px 0 4px;
  background: var(--theme-panel-border, #ebd9c1);
}

.composer-popover-card {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 0;
  z-index: 6;
  width: min(280px, 72vw);
  display: grid;
  gap: 10px;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid var(--theme-panel-border, #ebd9c1);
  background: linear-gradient(180deg, var(--theme-panel-bg, #fff9f0), var(--theme-panel-bg-soft, #fff4e6));
  box-shadow: 0 18px 36px var(--theme-card-shadow-strong, rgba(90, 60, 20, 0.16));
}

.composer-option-field {
  display: grid;
  gap: 6px;
}

.composer-option-field > label {
  color: var(--theme-text-secondary, #7a614a);
  font-size: 12px;
  font-weight: 800;
}

.composer-scene-list {
  display: grid;
  gap: 6px;
  max-height: 260px;
  overflow: auto;
}

.composer-scene-option {
  display: grid;
  gap: 2px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--theme-panel-border, #ebd9c1);
  border-radius: 12px;
  background: var(--theme-panel-bg, #fff9f0);
  color: var(--theme-title, #3d2f22);
  text-align: left;
  cursor: pointer;
}

.composer-scene-option:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--theme-accent, #f7a831) 45%, var(--theme-panel-border, #ebd9c1));
  background: var(--theme-panel-bg-soft, #fff4e6);
}

.composer-scene-option.active {
  border-color: transparent;
  background: var(--theme-accent, #f7a831);
  color: var(--theme-accent-contrast, #3d2f22);
  box-shadow: 0 8px 16px color-mix(in srgb, var(--theme-accent, #f7a831) 28%, transparent);
}

.composer-scene-option:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.composer-scene-option-title {
  font-size: 13px;
  font-weight: 800;
}

.composer-scene-option-desc,
.composer-scene-option-meta {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.78;
}

.composer-scene-option.active .composer-scene-option-desc,
.composer-scene-option.active .composer-scene-option-meta {
  opacity: 0.88;
}

.composer-generate-btn {
  flex: 0 0 auto;
  margin-left: auto;
  height: 34px !important;
  min-width: 112px;
  border-radius: 12px !important;
  font-size: 12px !important;
  font-weight: 800 !important;
}

.composer-hint {
  margin-top: 8px;
  text-align: center;
}

@media (max-width: 900px) {
  .chat-page {
    flex-direction: column;
    height: auto;
    min-height: calc(100vh - 72px);
  }

  .chat-page.is-embedded {
    height: 100%;
    min-height: 0;
  }

  .chat-page.is-embedded .chat-main {
    min-height: 0;
  }

  .chat-sidebar {
    width: 100%;
    max-height: 220px;
    border-right: none;
    border-bottom: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.06));
    transition:
      max-height 0.22s ease,
      padding 0.22s ease,
      opacity 0.18s ease,
      border-color 0.18s ease;
  }

  .chat-page.sidebar-collapsed .chat-sidebar {
    width: 100%;
    max-height: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-bottom-color: transparent;
  }

  .chat-main {
    --chat-composer-reserve: 160px;
    min-height: 480px;
  }

  .chat-page.has-draft-images .chat-main {
    --chat-composer-reserve: 240px;
  }

  .sidebar-toggle-btn {
    top: 10px;
    left: 10px;
  }

  .chat-dock-switch {
    top: 10px;
    right: 10px;
    padding: 5px 8px;
  }

  .chat-dock-switch-label {
    display: none;
  }

  .chat-dock-switch-label-short {
    display: inline;
    white-space: nowrap;
  }

  .composer-setting-wrap {
    max-width: min(200px, 56%);
  }
}
</style>
