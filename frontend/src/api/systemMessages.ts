import client from "./client";
import type {
  SystemMessageCreatePayload,
  SystemMessageDetail,
  SystemMessageListResponse,
  SystemMessageReadCountResponse,
} from "@/types";

export function listMySystemMessages(page = 1, pageSize = 20): Promise<SystemMessageListResponse> {
  return client.get("/system-messages", {
    params: { page, page_size: pageSize },
  });
}

export function getMySystemMessageDetail(messageId: string): Promise<SystemMessageDetail> {
  return client.get(`/system-messages/${messageId}`);
}

export function getMyUnreadSystemMessageCount(): Promise<SystemMessageReadCountResponse> {
  return client.get("/system-messages/unread-count");
}

export function markAllMySystemMessagesAsRead(): Promise<SystemMessageReadCountResponse> {
  return client.post("/system-messages/read-all");
}

export function createAdminSystemMessage(payload: SystemMessageCreatePayload): Promise<SystemMessageDetail> {
  return client.post("/admin/system-messages", payload);
}

export function listAdminSystemMessages(page = 1, pageSize = 20): Promise<SystemMessageListResponse> {
  return client.get("/admin/system-messages", {
    params: { page, page_size: pageSize },
  });
}

export function getAdminSystemMessageDetail(messageId: string): Promise<SystemMessageDetail> {
  return client.get(`/admin/system-messages/${messageId}`);
}
