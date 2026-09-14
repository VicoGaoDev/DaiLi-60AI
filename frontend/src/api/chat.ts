import client from "./client";
import router from "@/router";
import { clearStoredAuth, getStoredToken } from "@/lib/auth";
import { isSessionExpiredError } from "@/lib/authError";
import { emitAuthSessionExpiredNotice } from "@/lib/authSessionNotice";
import type {
  ChatMessage,
  ChatMessageListResponse,
  ChatSendMessageResponse,
  ChatSession,
  ChatSessionListResponse,
} from "@/types";

export function listChatSessions(params?: {
  page?: number;
  page_size?: number;
}): Promise<ChatSessionListResponse> {
  return client.get("/chat/sessions", { params });
}

export function createChatSession(payload: {
  title?: string;
  model: string;
}): Promise<ChatSession> {
  return client.post("/chat/sessions", payload);
}

export function getChatSession(sessionId: string): Promise<ChatSession> {
  return client.get(`/chat/sessions/${sessionId}`);
}

export function updateChatSession(
  sessionId: string,
  payload: { title?: string; model?: string },
): Promise<ChatSession> {
  return client.patch(`/chat/sessions/${sessionId}`, payload);
}

export function deleteChatSession(sessionId: string): Promise<void> {
  return client.delete(`/chat/sessions/${sessionId}`);
}

export function listChatMessages(
  sessionId: string,
  params?: { before_id?: number; page_size?: number },
): Promise<ChatMessageListResponse> {
  return client.get(`/chat/sessions/${sessionId}/messages`, { params });
}

export function confirmChatMessageGenerate(
  sessionId: string,
  messageId: number,
  payload: {
    action: "confirm" | "cancel" | "retry";
    model?: string;
    num_images?: number;
    size?: string;
    resolution?: string;
    custom_size?: string;
  },
): Promise<ChatMessage> {
  return client.post(`/chat/sessions/${sessionId}/messages/${messageId}/generate`, payload);
}

/** 对话发送会同步等待上游模型，需覆盖后端 AI_TIMEOUT（默认 600s） */
const CHAT_SEND_TIMEOUT_MS = 630_000;
const BASE = import.meta.env.VITE_API_BASE_URL || "";
const DEV_STREAM_BASE = import.meta.env.DEV ? "http://127.0.0.1:8000" : "";

export function sendChatMessage(
  sessionId: string,
  payload: {
    content: string;
    images?: { url: string }[];
    model?: string;
    client_message_id: string;
  },
  signal?: AbortSignal,
): Promise<ChatSendMessageResponse> {
  return client.post(`/chat/sessions/${sessionId}/messages`, payload, {
    timeout: CHAT_SEND_TIMEOUT_MS,
    signal,
  });
}

export type ChatStreamMeta = {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  session: ChatSession;
};

export type ChatStreamErrorEvent = {
  message: string;
  assistant_message?: ChatMessage;
  balance?: number | null;
  session?: ChatSession;
};

function chatMessagesUrl(sessionId: string) {
  // 开发环境下绕过 Vite proxy，避免代理层缓冲 SSE，生产仍使用配置的 API base 或同源。
  const base = String(BASE || DEV_STREAM_BASE).replace(/\/+$/, "");
  return `${base}/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`;
}

function throwChatHttpError(statusCode: number, detail: string, timeout = false): never {
  const error: any = new Error(detail || "发送失败");
  error.response = { status: statusCode, data: { detail } };
  if (timeout) {
    error.code = "ECONNABORTED";
  }
  if (isSessionExpiredError(error)) {
    clearStoredAuth();
    emitAuthSessionExpiredNotice(router.currentRoute.value.fullPath);
  }
  throw error;
}

async function parseSseStream(
  response: Response,
  onEvent: (event: string, data: any) => void,
) {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("对话接口未返回流");
  }
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    let separator = buffer.indexOf("\n\n");
    while (separator >= 0) {
      const block = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      if (block.trim()) {
        let eventName = "message";
        const dataLines: string[] = [];
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trimStart());
          }
        }
        const rawData = dataLines.join("\n");
        if (rawData) {
          let data: any = rawData;
          try {
            data = JSON.parse(rawData);
          } catch {
            data = rawData;
          }
          onEvent(eventName, data);
        }
      }
      separator = buffer.indexOf("\n\n");
    }
  }
}

export async function sendChatMessageStream(
  sessionId: string,
  payload: {
    content: string;
    images?: { url: string }[];
    model?: string;
    client_message_id: string;
  },
  handlers: {
    onMeta?: (data: ChatStreamMeta) => void;
    onDelta?: (text: string) => void;
    onDone?: (data: ChatSendMessageResponse) => void;
    onErrorEvent?: (data: ChatStreamErrorEvent) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const token = getStoredToken();
  const timeoutController = new AbortController();
  const onParentAbort = () => timeoutController.abort();
  signal?.addEventListener("abort", onParentAbort);
  const timer = window.setTimeout(() => timeoutController.abort(), CHAT_SEND_TIMEOUT_MS);
  let timedOut = false;
  const onTimeoutAbort = () => {
    if (!signal?.aborted) timedOut = true;
  };
  timeoutController.signal.addEventListener("abort", onTimeoutAbort);
  try {
    const response = await fetch(chatMessagesUrl(sessionId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal: timeoutController.signal,
    });
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok) {
      let detail = "发送失败";
      try {
        const data = await response.json();
        detail = String(data?.detail || detail);
      } catch {
        detail = (await response.text()) || detail;
      }
      throwChatHttpError(response.status, detail);
    }
    if (!contentType.includes("text/event-stream")) {
      const data = (await response.json()) as ChatSendMessageResponse;
      handlers.onMeta?.({
        user_message: data.user_message,
        assistant_message: data.assistant_message,
        session: data.session,
      });
      if ((data.assistant_message?.content || "").trim()) {
        handlers.onDelta?.(data.assistant_message.content);
      }
      handlers.onDone?.(data);
      return;
    }
    let settled = false;
    let gotDelta = false;
    await parseSseStream(response, (event, data) => {
      if (event === "meta") {
        handlers.onMeta?.(data as ChatStreamMeta);
        return;
      }
      if (event === "delta") {
        const text = typeof data?.text === "string" ? data.text : "";
        if (text) {
          gotDelta = true;
          handlers.onDelta?.(text);
        }
        return;
      }
      if (event === "done") {
        settled = true;
        handlers.onDone?.(data as ChatSendMessageResponse);
        return;
      }
      if (event === "error") {
        settled = true;
        if (gotDelta) {
          const maybeDone = data as ChatSendMessageResponse;
          if (maybeDone?.assistant_message && (maybeDone.assistant_message.content || "").trim()) {
            handlers.onDone?.(maybeDone);
            return;
          }
        }
        handlers.onErrorEvent?.(data as ChatStreamErrorEvent);
      }
    });
    if (!settled && !gotDelta && !timeoutController.signal.aborted) {
      throw new Error("对话流已中断");
    }
  } catch (err: any) {
    if (timedOut && (err?.name === "AbortError" || /abort/i.test(String(err?.message || "")))) {
      throwChatHttpError(408, "请求超时，请稍后重试", true);
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener("abort", onParentAbort);
    timeoutController.signal.removeEventListener("abort", onTimeoutAbort);
  }
}
