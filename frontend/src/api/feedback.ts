import client from "./client";
import type {
  FeedbackCreatePayload,
  FeedbackDetail,
  FeedbackListQuery,
  FeedbackListResponse,
  FeedbackMessage,
  FeedbackMessageCreatePayload,
  FeedbackMessageListResponse,
  FeedbackReadCountResponse,
} from "@/types";

export function createFeedback(
  taskId: string | null | undefined,
  content: string,
  options?: Pick<FeedbackCreatePayload, "feedback_type" | "attachments">,
): Promise<FeedbackDetail> {
  return client.post("/feedback", {
    task_id: taskId || undefined,
    feedback_type: options?.feedback_type,
    attachments: options?.attachments || [],
    content,
  });
}

export function listMyFeedbacks(
  page = 1,
  pageSize = 20,
  query?: FeedbackListQuery,
): Promise<FeedbackListResponse> {
  const params: Record<string, unknown> = {
    page,
    page_size: pageSize,
  };
  if (query?.task_id) params.task_id = query.task_id;
  if (query?.status) params.status = query.status;
  if (query?.feedback_type) params.feedback_type = query.feedback_type;
  return client.get("/feedback", { params });
}

export function getMyFeedbackDetail(feedbackId: string): Promise<FeedbackDetail> {
  return client.get(`/feedback/${feedbackId}`);
}

export function getMyUnreadFeedbackCount(): Promise<FeedbackReadCountResponse> {
  return client.get("/feedback/unread-count");
}

export function markMyFeedbackAsRead(feedbackId: string): Promise<FeedbackDetail> {
  return client.patch(`/feedback/${feedbackId}/read`);
}

export function markAllMyFeedbackAsRead(): Promise<FeedbackReadCountResponse> {
  return client.post("/feedback/read-all");
}

export function listMyFeedbackMessages(feedbackId: string): Promise<FeedbackMessageListResponse> {
  return client.get(`/feedback/${feedbackId}/messages`);
}

export function sendMyFeedbackMessage(
  feedbackId: string,
  payload: FeedbackMessageCreatePayload,
): Promise<FeedbackMessage> {
  return client.post(`/feedback/${feedbackId}/messages`, payload);
}
