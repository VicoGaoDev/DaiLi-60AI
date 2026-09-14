import client from "./client";
import type {
  AdminStats,
  AdminAnalyticsBreakdown,
  AdminErrorAnalytics,
  AdminErrorCategoryTimeseries,
  ErrorTrendGranularity,
  AdminErrorTaskList,
  AdminAnalyticsQuery,
  AdminAnalyticsRedeemRevenue,
  AdminAnalyticsRevenueTimeseries,
  AdminAnalyticsSummary,
  AdminAnalyticsTimeseries,
  AdminConfig,
  CosConfig,
  AdminUser,
  AdminUserListResponse,
  AdminPaymentOrder,
  AdminOfflineOrder,
  CreditLog,
  AdminRedeemKey,
  AdminRedeemKeyBatchResult,
  RedeemKeyStatus,
  ExternalApiConfig,
  ExternalApiConfigPayload,
  ExternalApiSecretConfig,
  ExternalApiSceneBinding,
  ExternalApiSceneBindingCreatePayload,
  ExternalApiSceneBindingMetaPayload,
  ExternalApiConfigStatus,
  ExternalApiConfigTestResult,
  VideoExternalApiConfig,
  VideoExternalApiConfigPayload,
  VideoExternalApiSceneBinding,
  VideoExternalApiSceneBindingCreatePayload,
  VideoExternalApiSceneBindingMetaPayload,
  VideoExternalApiConfigTestResult,
  ChatExternalApiConfig,
  ChatExternalApiConfigPayload,
  ChatExternalApiSceneBinding,
  ChatExternalApiSceneBindingCreatePayload,
  ChatExternalApiSceneBindingMetaPayload,
  ChatExternalApiConfigTestResult,
  AdminDailyReportTestResult,
  AdminDailyReportRangePayload,
  FeedbackDetail,
  FeedbackListResponse,
  FeedbackMessage,
  FeedbackMessageCreatePayload,
  FeedbackMessageListResponse,
  FeedbackReadCountResponse,
  FeedbackUnresolvedCountResponse,
  AdminFeedbackQuery,
  FeedbackUpdatePayload,
  HistoryFilter,
  HistoryResponse,
  UserHistoryCard,
  AdminUserPromoDashboard,
  CreateOfflineOrderPayload,
  ChatMessageListResponse,
  ChatSession,
  ChatSessionListResponse,
  TaskResult,
  UserCanvasListResponse,
  AdminVideoTaskListResponse,
  VideoStats,
  VideoAnalyticsQuery,
  VideoTaskResult,
  AdminInviteRewardDashboard,
  AdminInviteRewardUserDetail,
  AdminPromoStatsDashboard,
  AdminLedger,
  AdminLedgerListResponse,
  AdminLedgerPayload,
  PromptOptimizeStyle,
  PromptOptimizeStylePayload,
  PromptOptimizeStyleStatus,
  GenerationSceneCategory,
  GenerationSceneCategoryPayload,
  GenerationSceneCategoryStatus,
} from "@/types";

function buildAnalyticsParams(query: AdminAnalyticsQuery): Record<string, unknown> {
  const params: Record<string, unknown> = {
    granularity: query.granularity,
  };
  if (query.start_date) params.start_date = query.start_date;
  if (query.end_date) params.end_date = query.end_date;
  if (query.user_id) params.user_id = query.user_id;
  if (query.source) params.source = query.source;
  if (query.model) params.model = query.model;
  if (query.mode) params.mode = query.mode;
  if (query.status) params.status = query.status;
  if (query.canvas_task_filter && query.canvas_task_filter !== "all") params.canvas_task_filter = query.canvas_task_filter;
  if (typeof query.include_unsafe_tasks === "boolean") params.include_unsafe_tasks = query.include_unsafe_tasks;
  return params;
}

function buildVideoAnalyticsParams(query: VideoAnalyticsQuery): Record<string, unknown> {
  const params: Record<string, unknown> = {
    granularity: query.granularity,
  };
  if (query.start_date) params.start_date = query.start_date;
  if (query.end_date) params.end_date = query.end_date;
  if (query.user_id) params.user_id = query.user_id;
  if (query.source) params.source = query.source;
  if (query.model) params.model = query.model;
  if (query.mode) params.mode = query.mode;
  if (query.status) params.status = query.status;
  if (typeof query.include_unsafe_tasks === "boolean") params.include_unsafe_tasks = query.include_unsafe_tasks;
  return params;
}

export function listUsers(
  page = 1,
  pageSize = 30,
  filters?: {
    keyword?: string;
    status?: "active" | "disabled";
    whitelist?: boolean;
    sort?: "created_at_desc" | "credits_desc" | "consumed_credits_desc";
  }
): Promise<AdminUserListResponse> {
  return client.get("/admin/users", {
    params: {
      page,
      page_size: pageSize,
      keyword: filters?.keyword?.trim() || undefined,
      status: filters?.status || undefined,
      whitelist: typeof filters?.whitelist === "boolean" ? filters.whitelist : undefined,
      sort: filters?.sort || "created_at_desc",
    },
  });
}

export function listUserOptions(): Promise<AdminUser[]> {
  return client.get("/admin/user-options");
}

export function getAdminUserDetail(userId: string): Promise<AdminUser> {
  return client.get(`/admin/users/${encodeURIComponent(userId)}`);
}

export function getAdminCanvases(
  page = 1,
  pageSize = 20,
  filters?: { keyword?: string; userId?: string }
): Promise<UserCanvasListResponse> {
  return client.get("/admin/canvases", {
    params: {
      page,
      page_size: pageSize,
      keyword: filters?.keyword || undefined,
      user_id: filters?.userId || undefined,
    },
  });
}

export function listAdminChatSessions(params?: {
  page_size?: number;
  keyword?: string;
  user_id?: string;
  before_session_id?: string;
}): Promise<ChatSessionListResponse> {
  return client.get("/admin/chat/sessions", { params });
}

export function getAdminChatSession(sessionId: string): Promise<ChatSession> {
  return client.get(`/admin/chat/sessions/${encodeURIComponent(sessionId)}`);
}

export function listAdminChatMessages(
  sessionId: string,
  params?: { before_id?: number; page_size?: number },
): Promise<ChatMessageListResponse> {
  return client.get(`/admin/chat/sessions/${encodeURIComponent(sessionId)}/messages`, { params });
}

export function getAdminTasks(taskIds: string[]): Promise<TaskResult[]> {
  const params = new URLSearchParams();
  taskIds.forEach((taskId) => {
    params.append("task_ids", String(taskId));
  });
  return client.get(`/admin/tasks?${params.toString()}`);
}

export function createUser(data: { username: string; password: string; role?: string }): Promise<AdminUser> {
  return client.post("/admin/users", data);
}

export function updateUserStatus(userId: string, status: string): Promise<AdminUser> {
  return client.put(`/admin/users/${userId}/status`, { status });
}

export function updateUserRole(userId: string, role: string): Promise<AdminUser> {
  return client.put(`/admin/users/${userId}/role`, { role });
}

export function updateUserWhitelist(userId: string, isWhitelisted: boolean): Promise<AdminUser> {
  return client.put(`/admin/users/${userId}/whitelist`, { is_whitelisted: isWhitelisted });
}

export function resetUserPassword(userId: string, newPassword: string): Promise<AdminUser> {
  return client.put(`/admin/users/${userId}/reset-password`, { new_password: newPassword });
}

export function allocateCredits(userId: string, amount: number, description?: string): Promise<AdminUser> {
  return client.post(`/admin/users/${userId}/credits`, { amount, description: description || "" });
}

export function resetUserCredits(userId: string, description?: string): Promise<AdminUser> {
  return client.post(`/admin/users/${userId}/credits/reset`, { description: description || "" });
}

export function getUserPromoDashboard(userId: string): Promise<AdminUserPromoDashboard> {
  return client.get(`/admin/users/${userId}/promo-dashboard`);
}

export function getCreditLogs(
  page = 1,
  pageSize = 20,
  userId?: string,
  startDate?: string,
  endDate?: string,
  direction?: "increase" | "decrease",
  mode?: "text_generate" | "image_edit" | "inpaint" | "smart_cutout" | "promptReverse" | "promptOptimize" | "manual" | "redeem" | "purchase",
): Promise<{ total: number; items: CreditLog[] }> {
  const params: Record<string, unknown> = { page, page_size: pageSize };
  if (userId) params.user_id = userId;
  if (startDate) params.start_date = startDate;
  if (endDate) params.end_date = endDate;
  if (direction) params.direction = direction;
  if (mode) params.mode = mode;
  return client.get("/admin/credit-logs", { params });
}

export function listPaymentOrders(params: {
  page?: number;
  page_size?: number;
  user?: string;
  status?: AdminPaymentOrder["status"];
  start_date?: string;
  end_date?: string;
}): Promise<{ total: number; items: AdminPaymentOrder[] }> {
  return client.get("/admin/payment-orders", { params });
}

export function createOfflineOrder(payload: CreateOfflineOrderPayload): Promise<AdminOfflineOrder> {
  return client.post("/admin/offline-orders", payload);
}

export function listOfflineOrders(params: {
  page?: number;
  page_size?: number;
  user?: string;
  start_date?: string;
  end_date?: string;
}): Promise<{ total: number; items: AdminOfflineOrder[] }> {
  return client.get("/admin/offline-orders", { params });
}

export function listAdminLedgers(params: {
  page?: number;
  page_size?: number;
} = {}): Promise<AdminLedgerListResponse> {
  return client.get("/admin/ledgers", { params });
}

export function getAdminLedger(month: string): Promise<AdminLedger> {
  return client.get(`/admin/ledgers/${month}`);
}

export function createAdminLedger(payload: AdminLedgerPayload & { month: string }): Promise<AdminLedger> {
  return client.post("/admin/ledgers", payload);
}

export function updateAdminLedger(month: string, payload: AdminLedgerPayload): Promise<AdminLedger> {
  return client.put(`/admin/ledgers/${month}`, payload);
}

export function refreshAdminLedgerIncome(month: string): Promise<AdminLedger> {
  return client.post(`/admin/ledgers/${month}/refresh-income`);
}

export function createRedeemKeysBatch(count: number, creditAmount: number): Promise<AdminRedeemKeyBatchResult> {
  return client.post("/admin/redeem-keys/batch", {
    count,
    credit_amount: creditAmount,
  });
}

export function listRedeemKeys(params: {
  page?: number;
  page_size?: number;
  batch_no?: string;
  redeem_key?: string;
  credit_amount?: number;
  status?: RedeemKeyStatus;
  is_used?: boolean;
  used_by?: string;
  start_date?: string;
  end_date?: string;
}): Promise<{ total: number; items: AdminRedeemKey[] }> {
  return client.get("/admin/redeem-keys", { params });
}

export function updateRedeemKeyStatus(keyId: number, status: RedeemKeyStatus): Promise<AdminRedeemKey> {
  return client.post(`/admin/redeem-keys/${keyId}/status`, { status });
}

export function getStats(): Promise<AdminStats> {
  return client.get("/admin/stats");
}

export function getAdminInviteRewardDashboard(): Promise<AdminInviteRewardDashboard> {
  return client.get("/admin/invite-rewards");
}

export function getAdminInviteRewardUserDetail(userId: string): Promise<AdminInviteRewardUserDetail> {
  return client.get(`/admin/invite-rewards/users/${userId}`);
}

export function getAdminPromoStatsDashboard(params?: { month?: string }): Promise<AdminPromoStatsDashboard> {
  return client.get("/admin/promo-stats", { params });
}

export function getAdminPromoStatsUserDetail(
  userId: string,
  params?: {
    month?: string;
    start_date?: string;
    end_date?: string;
  },
): Promise<AdminUserPromoDashboard> {
  return client.get(`/admin/promo-stats/users/${userId}`, { params });
}

export function getVideoStats(): Promise<VideoStats> {
  return client.get("/admin/video-stats");
}

export function getAdminHistory(
  page: number = 1,
  pageSize: number = 20,
  filter?: HistoryFilter,
): Promise<HistoryResponse> {
  const params: Record<string, unknown> = { page, page_size: pageSize };
  if (filter?.status) params.status = filter.status;
  if (filter?.user_id) params.user_id = filter.user_id;
  if (filter?.source) params.source = filter.source;
  if (filter?.model) params.model = filter.model;
  if (filter?.mode) params.mode = filter.mode;
  if (filter?.canvas_task_filter && filter.canvas_task_filter !== "all") params.canvas_task_filter = filter.canvas_task_filter;
  if (typeof filter?.include_unsafe_tasks === "boolean") params.include_unsafe_tasks = filter.include_unsafe_tasks;
  if (filter?.start_date) params.start_date = filter.start_date;
  if (filter?.end_date) params.end_date = filter.end_date;
  return client.get("/admin/history", { params });
}

export function getAdminHistoryDetail(payload: {
  item_type: "task" | "prompt_history" | "prompt_optimize_task";
  task_id?: string | null;
  history_id?: number | null;
}): Promise<UserHistoryCard> {
  return client.get("/admin/history/detail", {
    params: {
      item_type: payload.item_type,
      task_id: payload.task_id || undefined,
      history_id: typeof payload.history_id === "number" ? payload.history_id : undefined,
    },
  });
}

export function getAdminHistoryCards(
  page: number = 1,
  pageSize: number = 20,
  filters: Pick<HistoryFilter, "mode" | "source" | "model" | "prompt" | "status" | "user_id" | "start_date" | "end_date" | "include_prompt_reverse" | "used_fallback_api"> = {},
): Promise<{ total: number; items: UserHistoryCard[] }> {
  return client.get("/admin/history/cards", {
    params: {
      page,
      page_size: pageSize,
      include_prompt_reverse: filters.include_prompt_reverse,
      mode: filters.mode,
      source: filters.source,
      model: filters.model,
      prompt: filters.prompt?.trim() || undefined,
      status: filters.status,
      user_id: filters.user_id,
      used_fallback_api: filters.used_fallback_api,
      start_date: filters.start_date,
      end_date: filters.end_date,
    },
  });
}

export function getAdminVideoTasks(
  page: number = 1,
  pageSize: number = 20,
  filters: {
    source?: "web" | "app" | "api";
    model?: string;
    mode?: "text_to_video" | "image_to_video" | "first_last_frame";
    prompt?: string;
    status?: "pending" | "queued" | "processing" | "success" | "failed";
    user_id?: string;
    used_fallback_api?: boolean;
    include_unsafe_tasks?: boolean;
    start_date?: string;
    end_date?: string;
  } = {},
): Promise<AdminVideoTaskListResponse> {
  return client.get("/admin/video-tasks", {
    params: {
      page,
      page_size: pageSize,
      source: filters.source,
      model: filters.model,
      mode: filters.mode,
      prompt: filters.prompt?.trim() || undefined,
      status: filters.status,
      user_id: filters.user_id,
      used_fallback_api: filters.used_fallback_api,
      include_unsafe_tasks: filters.include_unsafe_tasks,
      start_date: filters.start_date,
      end_date: filters.end_date,
    },
  });
}

export function getAdminVideoTaskDetail(taskId: string): Promise<VideoTaskResult> {
  return client.get(`/admin/video-tasks/${taskId}`);
}

export function listAdminFeedbacks(
  page = 1,
  pageSize = 20,
  query?: AdminFeedbackQuery,
): Promise<FeedbackListResponse> {
  const params: Record<string, unknown> = { page, page_size: pageSize };
  if (query?.feedback_id) params.feedback_id = query.feedback_id;
  if (query?.user_id) params.user_id = query.user_id;
  if (query?.task_id) params.task_id = query.task_id;
  if (query?.status) params.status = query.status;
  if (query?.feedback_type) params.feedback_type = query.feedback_type;
  return client.get("/admin/feedback", { params });
}

export function getAdminUnresolvedFeedbackCount(): Promise<FeedbackUnresolvedCountResponse> {
  return client.get("/admin/feedback/unresolved-count");
}


export function getAdminUnreadFeedbackCount(): Promise<FeedbackReadCountResponse> {
  return client.get("/admin/feedback/unread-count");
}

export function listAdminFeedbackMessages(feedbackId: string): Promise<FeedbackMessageListResponse> {
  return client.get(`/admin/feedback/${feedbackId}/messages`);
}

export function sendAdminFeedbackMessage(
  feedbackId: string,
  payload: FeedbackMessageCreatePayload,
): Promise<FeedbackMessage> {
  return client.post(`/admin/feedback/${feedbackId}/messages`, payload);
}

export function markAdminFeedbackAsRead(feedbackId: string): Promise<FeedbackReadCountResponse> {
  return client.patch(`/admin/feedback/${feedbackId}/read`);
}

export function closeAdminFeedback(feedbackId: string): Promise<FeedbackDetail> {
  return client.post(`/admin/feedback/${feedbackId}/close`);
}

export function getAdminFeedbackDetail(feedbackId: string): Promise<FeedbackDetail> {
  return client.get(`/admin/feedback/${feedbackId}`);
}

export function updateAdminFeedback(feedbackId: string, payload: FeedbackUpdatePayload): Promise<FeedbackDetail> {
  return client.patch(`/admin/feedback/${feedbackId}`, payload);
}

export function getAdminAnalyticsSummary(query: AdminAnalyticsQuery): Promise<AdminAnalyticsSummary> {
  return client.get("/admin/analytics/summary", { params: buildAnalyticsParams(query) });
}

export function getAdminAnalyticsTimeseries(query: AdminAnalyticsQuery): Promise<AdminAnalyticsTimeseries> {
  return client.get("/admin/analytics/timeseries", { params: buildAnalyticsParams(query) });
}

export function getAdminAnalyticsBreakdown(query: AdminAnalyticsQuery): Promise<AdminAnalyticsBreakdown> {
  return client.get("/admin/analytics/breakdown", { params: buildAnalyticsParams(query) });
}

export function getAdminVideoAnalyticsSummary(query: VideoAnalyticsQuery): Promise<AdminAnalyticsSummary> {
  return client.get("/admin/video-analytics/summary", { params: buildVideoAnalyticsParams(query) });
}

export function getAdminVideoAnalyticsTimeseries(query: VideoAnalyticsQuery): Promise<AdminAnalyticsTimeseries> {
  return client.get("/admin/video-analytics/timeseries", { params: buildVideoAnalyticsParams(query) });
}

export function getAdminVideoAnalyticsBreakdown(query: VideoAnalyticsQuery): Promise<AdminAnalyticsBreakdown> {
  return client.get("/admin/video-analytics/breakdown", { params: buildVideoAnalyticsParams(query) });
}

export function getAdminAnalyticsRedeemRevenue(query: AdminAnalyticsQuery): Promise<AdminAnalyticsRedeemRevenue> {
  return client.get("/admin/analytics/redeem-revenue", {
    params: {
      granularity: query.granularity,
      start_date: query.start_date,
      end_date: query.end_date,
    },
  });
}

export function getAdminAnalyticsPaymentRevenue(query: AdminAnalyticsQuery): Promise<AdminAnalyticsRedeemRevenue> {
  return client.get("/admin/analytics/payment-revenue", {
    params: {
      granularity: query.granularity,
      start_date: query.start_date,
      end_date: query.end_date,
    },
  });
}

export function getAdminAnalyticsOfflineOrderRevenue(query: AdminAnalyticsQuery): Promise<AdminAnalyticsRedeemRevenue> {
  return client.get("/admin/analytics/offline-order-revenue", {
    params: {
      granularity: query.granularity,
      start_date: query.start_date,
      end_date: query.end_date,
    },
  });
}

export function getAdminAnalyticsRevenueTimeseries(query: AdminAnalyticsQuery): Promise<AdminAnalyticsRevenueTimeseries> {
  return client.get("/admin/analytics/revenue-timeseries", {
    params: {
      granularity: query.granularity,
      start_date: query.start_date,
      end_date: query.end_date,
    },
  });
}

export function getAdminErrorAnalytics(params: {
  task_kind?: "image" | "video";
  start_date?: string;
  end_date?: string;
  source?: "web" | "app" | "api";
  model?: string;
  error_category?: string;
  used_fallback_api?: boolean;
  include_unsafe_tasks?: boolean;
}): Promise<AdminErrorAnalytics> {
  return client.get("/admin/analytics/errors", { params });
}

export function getAdminErrorCategoryTimeseries(query: {
  task_kind?: "image" | "video";
  granularity: ErrorTrendGranularity;
  start_date?: string;
  end_date?: string;
  source?: "web" | "app" | "api";
  model?: string;
  used_fallback_api?: boolean;
  include_unsafe_tasks?: boolean;
  limit?: number;
}): Promise<AdminErrorCategoryTimeseries> {
  return client.get("/admin/analytics/errors/timeseries", { params: query });
}

export function getAdminErrorTasks(params: {
  task_kind?: "image" | "video";
  page?: number;
  page_size?: number;
  start_date?: string;
  end_date?: string;
  source?: "web" | "app" | "api";
  model?: string;
  error_category?: string;
  used_fallback_api?: boolean;
  include_unsafe_tasks?: boolean;
}): Promise<AdminErrorTaskList> {
  return client.get("/admin/analytics/errors/tasks", { params });
}

export function getAdminConfig(): Promise<AdminConfig | null> {
  return client.get("/admin/api-key");
}

export function setAdminConfig(payload: {
  contact_qr_image?: string;
  announcement_enabled?: boolean;
  announcement_content?: string;
}): Promise<AdminConfig> {
  return client.put("/admin/api-key", payload);
}

export function deleteAdminConfig(): Promise<void> {
  return client.delete("/admin/api-key");
}

export function testAdminDailyReportNotify(): Promise<AdminDailyReportTestResult> {
  return client.post("/admin/notify/daily-report/test");
}

export function sendAdminDailyReportRange(payload: AdminDailyReportRangePayload): Promise<AdminDailyReportTestResult> {
  return client.post("/admin/notify/daily-report/range", payload);
}

export function getExternalApiSecrets(): Promise<ExternalApiSecretConfig | null> {
  return client.get("/admin/external-api-secrets");
}

export function setExternalApiSecrets(payload: {
  key?: string;
  tongyi_key?: string;
}): Promise<ExternalApiSecretConfig> {
  return client.put("/admin/external-api-secrets", payload);
}

export function getCosConfig(): Promise<CosConfig | null> {
  return client.get("/admin/cos-config");
}

export function setCosConfig(payload: {
  cos_secret_id?: string;
  cos_secret_key?: string;
  cos_bucket?: string;
  cos_region?: string;
  cos_upload_domain?: string;
  cos_public_base_url?: string;
}): Promise<CosConfig> {
  return client.put("/admin/cos-config", payload);
}

export function deleteCosConfig(): Promise<void> {
  return client.delete("/admin/cos-config");
}

export function listExternalApiConfigs(): Promise<ExternalApiConfig[]> {
  return client.get("/admin/external-api-configs");
}

export function createExternalApiConfig(payload: ExternalApiConfigPayload): Promise<ExternalApiConfig> {
  return client.post("/admin/external-api-configs", payload);
}

export function updateExternalApiConfig(configId: number, payload: ExternalApiConfigPayload): Promise<ExternalApiConfig> {
  return client.put(`/admin/external-api-configs/${configId}`, payload);
}

export function updateExternalApiConfigStatus(configId: number, status: ExternalApiConfigStatus): Promise<ExternalApiConfig> {
  return client.patch(`/admin/external-api-configs/${configId}/status`, { status });
}

export function deleteExternalApiConfig(configId: number): Promise<void> {
  return client.delete(`/admin/external-api-configs/${configId}`);
}

export function listExternalApiSceneBindings(): Promise<ExternalApiSceneBinding[]> {
  return client.get("/admin/external-api-scene-bindings");
}

export function createExternalApiSceneBinding(
  payload: ExternalApiSceneBindingCreatePayload,
): Promise<ExternalApiSceneBinding> {
  return client.post("/admin/external-api-scene-bindings", payload);
}

export function updateExternalApiSceneBindingMeta(
  sceneKey: ExternalApiSceneBinding["scene_key"],
  payload: ExternalApiSceneBindingMetaPayload,
): Promise<ExternalApiSceneBinding> {
  return client.patch(`/admin/external-api-scene-bindings/${sceneKey}/meta`, payload);
}

export function updateExternalApiSceneBindingStatus(
  sceneKey: ExternalApiSceneBinding["scene_key"],
  status: ExternalApiConfigStatus,
): Promise<ExternalApiSceneBinding> {
  return client.patch(`/admin/external-api-scene-bindings/${sceneKey}/status`, { status });
}

export function deleteExternalApiSceneBinding(
  sceneKey: ExternalApiSceneBinding["scene_key"],
): Promise<void> {
  return client.delete(`/admin/external-api-scene-bindings/${sceneKey}`);
}

export function listPromptOptimizeStyles(): Promise<PromptOptimizeStyle[]> {
  return client.get("/admin/prompt-optimize-styles");
}

export function createPromptOptimizeStyle(payload: PromptOptimizeStylePayload): Promise<PromptOptimizeStyle> {
  return client.post("/admin/prompt-optimize-styles", payload);
}

export function updatePromptOptimizeStyle(styleId: number, payload: PromptOptimizeStylePayload): Promise<PromptOptimizeStyle> {
  return client.put(`/admin/prompt-optimize-styles/${styleId}`, payload);
}

export function updatePromptOptimizeStyleStatus(styleId: number, status: PromptOptimizeStyleStatus): Promise<PromptOptimizeStyle> {
  return client.patch(`/admin/prompt-optimize-styles/${styleId}/status`, { status });
}

export function setPromptOptimizeStyleDefault(styleId: number): Promise<PromptOptimizeStyle> {
  return client.post(`/admin/prompt-optimize-styles/${styleId}/set-default`);
}

export function deletePromptOptimizeStyle(styleId: number): Promise<void> {
  return client.delete(`/admin/prompt-optimize-styles/${styleId}`);
}

export function listGenerationSceneCategories(): Promise<GenerationSceneCategory[]> {
  return client.get("/admin/generation-scene-categories");
}

export function createGenerationSceneCategory(payload: GenerationSceneCategoryPayload): Promise<GenerationSceneCategory> {
  return client.post("/admin/generation-scene-categories", payload);
}

export function updateGenerationSceneCategory(categoryId: number, payload: GenerationSceneCategoryPayload): Promise<GenerationSceneCategory> {
  return client.put(`/admin/generation-scene-categories/${categoryId}`, payload);
}

export function updateGenerationSceneCategoryStatus(categoryId: number, status: GenerationSceneCategoryStatus): Promise<GenerationSceneCategory> {
  return client.patch(`/admin/generation-scene-categories/${categoryId}/status`, { status });
}

export function deleteGenerationSceneCategory(categoryId: number): Promise<void> {
  return client.delete(`/admin/generation-scene-categories/${categoryId}`);
}

export function updateExternalApiSceneBinding(
  sceneKey: ExternalApiSceneBinding["scene_key"],
  payload: {
    api_config_id: number | null;
    backup_api_config_id: number | null;
    credit_cost: number;
    resolution_credit_costs_json: string;
    display_name: string;
    subtitle: string;
  },
): Promise<ExternalApiSceneBinding> {
  return client.put(`/admin/external-api-scene-bindings/${sceneKey}`, payload);
}

export function testExternalApiConfig(payload: ExternalApiConfigPayload): Promise<ExternalApiConfigTestResult> {
  return client.post("/admin/external-api-configs/test", payload);
}

export function listVideoExternalApiConfigs(): Promise<VideoExternalApiConfig[]> {
  return client.get("/admin/video-external-api-configs");
}

export function createVideoExternalApiConfig(payload: VideoExternalApiConfigPayload): Promise<VideoExternalApiConfig> {
  return client.post("/admin/video-external-api-configs", payload);
}

export function updateVideoExternalApiConfig(configId: number, payload: VideoExternalApiConfigPayload): Promise<VideoExternalApiConfig> {
  return client.put(`/admin/video-external-api-configs/${configId}`, payload);
}

export function updateVideoExternalApiConfigStatus(configId: number, status: ExternalApiConfigStatus): Promise<VideoExternalApiConfig> {
  return client.patch(`/admin/video-external-api-configs/${configId}/status`, { status });
}

export function deleteVideoExternalApiConfig(configId: number): Promise<void> {
  return client.delete(`/admin/video-external-api-configs/${configId}`);
}

export function listVideoExternalApiSceneBindings(): Promise<VideoExternalApiSceneBinding[]> {
  return client.get("/admin/video-external-api-scene-bindings");
}

export function createVideoExternalApiSceneBinding(
  payload: VideoExternalApiSceneBindingCreatePayload,
): Promise<VideoExternalApiSceneBinding> {
  return client.post("/admin/video-external-api-scene-bindings", payload);
}

export function updateVideoExternalApiSceneBindingMeta(
  sceneKey: VideoExternalApiSceneBinding["scene_key"],
  payload: VideoExternalApiSceneBindingMetaPayload,
): Promise<VideoExternalApiSceneBinding> {
  return client.patch(`/admin/video-external-api-scene-bindings/${sceneKey}/meta`, payload);
}

export function updateVideoExternalApiSceneBindingStatus(
  sceneKey: VideoExternalApiSceneBinding["scene_key"],
  status: ExternalApiConfigStatus,
): Promise<VideoExternalApiSceneBinding> {
  return client.patch(`/admin/video-external-api-scene-bindings/${sceneKey}/status`, { status });
}

export function deleteVideoExternalApiSceneBinding(
  sceneKey: VideoExternalApiSceneBinding["scene_key"],
): Promise<void> {
  return client.delete(`/admin/video-external-api-scene-bindings/${sceneKey}`);
}

export function updateVideoExternalApiSceneBinding(
  sceneKey: VideoExternalApiSceneBinding["scene_key"],
  payload: {
    api_config_id: number | null;
    backup_api_config_id: number | null;
    credit_billing_mode: "fixed" | "per_second";
    credit_cost: number;
    per_second_credit_cost: number;
    display_name: string;
    subtitle: string;
    status: ExternalApiConfigStatus;
  },
): Promise<VideoExternalApiSceneBinding> {
  return client.put(`/admin/video-external-api-scene-bindings/${sceneKey}`, payload);
}

export function testVideoExternalApiConfig(payload: VideoExternalApiConfigPayload): Promise<VideoExternalApiConfigTestResult> {
  return client.post("/admin/video-external-api-configs/test", payload);
}

export function listChatExternalApiConfigs(): Promise<ChatExternalApiConfig[]> {
  return client.get("/admin/chat-external-api-configs");
}

export function createChatExternalApiConfig(payload: ChatExternalApiConfigPayload): Promise<ChatExternalApiConfig> {
  return client.post("/admin/chat-external-api-configs", payload);
}

export function updateChatExternalApiConfig(configId: number, payload: ChatExternalApiConfigPayload): Promise<ChatExternalApiConfig> {
  return client.put(`/admin/chat-external-api-configs/${configId}`, payload);
}

export function updateChatExternalApiConfigStatus(configId: number, status: ExternalApiConfigStatus): Promise<ChatExternalApiConfig> {
  return client.patch(`/admin/chat-external-api-configs/${configId}/status`, { status });
}

export function deleteChatExternalApiConfig(configId: number): Promise<void> {
  return client.delete(`/admin/chat-external-api-configs/${configId}`);
}

export function listChatExternalApiSceneBindings(): Promise<ChatExternalApiSceneBinding[]> {
  return client.get("/admin/chat-external-api-scene-bindings");
}

export function createChatExternalApiSceneBinding(
  payload: ChatExternalApiSceneBindingCreatePayload,
): Promise<ChatExternalApiSceneBinding> {
  return client.post("/admin/chat-external-api-scene-bindings", payload);
}

export function updateChatExternalApiSceneBindingMeta(
  sceneKey: ChatExternalApiSceneBinding["scene_key"],
  payload: ChatExternalApiSceneBindingMetaPayload,
): Promise<ChatExternalApiSceneBinding> {
  return client.patch(`/admin/chat-external-api-scene-bindings/${sceneKey}/meta`, payload);
}

export function updateChatExternalApiSceneBindingStatus(
  sceneKey: ChatExternalApiSceneBinding["scene_key"],
  status: ExternalApiConfigStatus,
): Promise<ChatExternalApiSceneBinding> {
  return client.patch(`/admin/chat-external-api-scene-bindings/${sceneKey}/status`, { status });
}

export function deleteChatExternalApiSceneBinding(
  sceneKey: ChatExternalApiSceneBinding["scene_key"],
): Promise<void> {
  return client.delete(`/admin/chat-external-api-scene-bindings/${sceneKey}`);
}

export function updateChatExternalApiSceneBinding(
  sceneKey: ChatExternalApiSceneBinding["scene_key"],
  payload: {
    api_config_id: number | null;
    backup_api_config_id: number | null;
    credit_cost: number;
    display_name: string;
    subtitle: string;
    status: ExternalApiConfigStatus;
  },
): Promise<ChatExternalApiSceneBinding> {
  return client.put(`/admin/chat-external-api-scene-bindings/${sceneKey}`, payload);
}

export function testChatExternalApiConfig(payload: ChatExternalApiConfigPayload): Promise<ChatExternalApiConfigTestResult> {
  return client.post("/admin/chat-external-api-configs/test", payload);
}
