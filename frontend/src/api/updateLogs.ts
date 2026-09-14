import client from "./client";
import type { UpdateLogItem, UpdateLogListResponse, UpdateLogPayload } from "@/types";

export function listUpdateLogs(page = 1, pageSize = 20): Promise<UpdateLogListResponse> {
  return client.get("/update-logs", {
    params: { page, page_size: pageSize },
  });
}

export function getUpdateLogDetail(logId: string): Promise<UpdateLogItem> {
  return client.get(`/update-logs/${logId}`);
}

export function listAdminUpdateLogs(page = 1, pageSize = 20): Promise<UpdateLogListResponse> {
  return client.get("/admin/update-logs", {
    params: { page, page_size: pageSize },
  });
}

export function createAdminUpdateLog(payload: UpdateLogPayload): Promise<UpdateLogItem> {
  return client.post("/admin/update-logs", payload);
}

export function getAdminUpdateLogDetail(logId: string): Promise<UpdateLogItem> {
  return client.get(`/admin/update-logs/${logId}`);
}

export function updateAdminUpdateLog(logId: string, payload: UpdateLogPayload): Promise<UpdateLogItem> {
  return client.put(`/admin/update-logs/${logId}`, payload);
}

export function deleteAdminUpdateLog(logId: string): Promise<void> {
  return client.delete(`/admin/update-logs/${logId}`);
}
