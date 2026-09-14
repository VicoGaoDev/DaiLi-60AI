export interface UserInfo {
  id: string;
  business_id: string;
  username: string;
  email?: string | null;
  phone?: string | null;
  password_set?: boolean;
  role: "user" | "admin" | "superadmin";
  avatar_url?: string;
  credits: number;
  is_whitelisted: boolean;
}

export interface LoginResponse {
  token: string;
  user: UserInfo;
}

export type UserApiKeyStatus = "enabled" | "disabled";

export interface UserApiKey {
  id: number;
  expire_time?: string | null;
  api_key: string;
  key_name: string;
  status: UserApiKeyStatus;
  is_delete: boolean;
  key_prefix: string;
  key_last4: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PromptHistoryItem {
  id: number;
  prompt: string;
  mode: "generate" | "inpaint" | "smart_cutout" | "promptReverse" | "promptOptimize";
  source_image: string;
  created_at: string;
}

export interface ImageResult {
  id: number;
  image_url: string;
  preview_url?: string;
  thumb_url?: string;
  status: "pending" | "success" | "failed";
  error_message?: string;
  image_format?: string;
  image_size_bytes?: number;
  is_deleted?: boolean;
}

export type TaskMode = "generate" | "inpaint" | "smart_cutout" | "promptReverse" | "promptOptimize";
export type TaskType = "text_generate" | "image_edit" | "inpaint" | "smart_cutout" | "promptReverse" | "promptOptimize";
export type TaskSource = "web" | "app" | "api";
export type HistoryItemType = "task" | "prompt_history" | "prompt_optimize_task";

export interface TaskResult {
  id: string;
  canvas_id?: number | null;
  mode: TaskMode;
  model: string;
  source: TaskSource;
  prompt: string;
  num_images: number;
  size: string;
  resolution: string;
  custom_size?: string;
  reference_images?: string[];
  reference_image_thumbs?: string[];
  source_image?: string;
  source_image_thumb?: string;
  mask_image?: string;
  mask_image_thumb?: string;
  credit_cost: number;
  credit_refunded?: boolean;
  failure_refund_remaining_count?: number | null;
  used_fallback_api?: boolean;
  status: "pending" | "queued" | "processing" | "success" | "failed";
  error_message?: string;
  provider_error_message?: string;
  created_at: string;
  enqueued_at?: string | null;
  request_started_at?: string | null;
  request_finished_at?: string | null;
  images: ImageResult[];
  api_attempts?: TaskApiAttempt[];
}

export interface HistoryItem {
  item_type: HistoryItemType;
  task_id?: string | null;
  canvas_id?: number | null;
  canvas_project_id?: string;
  history_id?: number | null;
  style_id?: number | null;
  style_name?: string;
  display_id?: string;
  user_id?: string;
  username?: string;
  avatar_url?: string;
  task_type: TaskType;
  model: string;
  source: TaskSource;
  mode: TaskMode;
  prompt: string;
  reference_images: string[];
  num_images: number;
  size: string;
  resolution: string;
  custom_size?: string;
  credit_cost: number;
  credit_refunded?: boolean;
  used_fallback_api?: boolean;
  status: string;
  error_message?: string;
  provider_error_message?: string;
  task_is_deleted?: boolean;
  is_soft_deleted?: boolean;
  soft_deleted_count?: number;
  created_at: string;
  images: ImageResult[];
  api_attempts?: TaskApiAttempt[];
}

export interface HistoryFilter {
  mode?: TaskType;
  source?: TaskSource;
  model?: string;
  prompt?: string;
  status?: string;
  exclude_failed?: boolean;
  user_id?: string;
  canvas_task_filter?: "all" | "canvas" | "non_canvas";
  include_unsafe_tasks?: boolean;
  start_date?: string;
  end_date?: string;
  used_fallback_api?: boolean;
  respect_pins?: boolean;
  include_prompt_reverse?: boolean;
  board_id?: number;
  board_scope?: "default" | "all";
}

export interface HistoryResponse {
  total: number;
  total_credit_cost: number;
  items: HistoryItem[];
}

export interface TaskApiAttempt {
  id?: number | null;
  image_id?: number | null;
  image_index?: number | null;
  api_config_id?: number | null;
  api_config_name: string;
  attempt_index: number;
  is_fallback: boolean;
  status: "success" | "failed" | string;
  http_status?: number | null;
  error_message?: string;
  duration_ms?: number | null;
  external_http_ms?: number | null;
  result_download_ms?: number | null;
  cos_upload_ms?: number | null;
  response_preview?: string;
  created_at?: string | null;
  request_preview?: {
    request_url: string;
    headers: Record<string, string>;
    payload: unknown;
  } | null;
}

export interface UserHistoryCard {
  history_id?: number | null;
  item_type: HistoryItemType;
  style_id?: number | null;
  style_name?: string;
  display_id?: string;
  task_id?: string | null;
  canvas_id?: number | null;
  canvas_project_id?: string;
  image_id?: number | null;
  user_id?: string;
  username?: string;
  avatar_url?: string;
  is_pinned: boolean;
  pinned_at?: string | null;
  image_url: string;
  preview_url?: string;
  thumb_url?: string;
  status: "pending" | "queued" | "processing" | "success" | "failed";
  image_format?: string;
  image_size_bytes?: number;
  task_is_deleted?: boolean;
  is_soft_deleted?: boolean;
  task_type: TaskType;
  model: string;
  source: TaskSource;
  mode: TaskMode;
  prompt: string;
  reference_images: string[];
  reference_image_thumbs: string[];
  source_image: string;
  source_image_thumb: string;
  mask_image: string;
  mask_image_thumb: string;
  num_images: number;
  size: string;
  resolution: string;
  custom_size?: string;
  credit_cost: number;
  credit_refunded?: boolean;
  used_fallback_api?: boolean;
  created_at: string;
  request_started_at?: string | null;
  request_finished_at?: string | null;
  run_time?: number | null;
  error_message?: string;
  provider_error_message?: string;
  images: ImageResult[];
  api_attempts?: TaskApiAttempt[];
}

export interface UserHistoryResponse {
  total: number;
  items: UserHistoryCard[];
}

export interface HistoryPinTogglePayload {
  item_type: HistoryItemType;
  image_id?: number | null;
  history_id?: number | null;
}

export interface HistoryPinToggleResponse {
  is_pinned: boolean;
  pinned_at?: string | null;
}

export type BoardKey = "default" | `board:${number}`;

export interface UserBoardSummary {
  id: number | null;
  name: string;
  is_default: boolean;
  asset_count: number;
  updated_at?: string | null;
  preview_urls: string[];
}

export interface UserBoardListResponse {
  items: UserBoardSummary[];
}

export interface UserAssetCategory {
  id: number;
  name: string;
  sort_order: number;
  asset_count: number;
  preview_urls: string[];
  updated_at?: string | null;
}

export interface UserAssetCategoryListResponse {
  items: UserAssetCategory[];
  uncategorized_count: number;
}

export interface UserAssetQuota {
  used: number;
  limit: number;
  remaining: number;
}

export interface UserAsset {
  id: number;
  category_id?: number | null;
  category_name: string;
  file_name: string;
  image_url: string;
  thumb_url: string;
  mime_type: string;
  file_size: number;
  width?: number | null;
  height?: number | null;
  status: string;
  created_at?: string | null;
  completed_at?: string | null;
}

export interface UserAssetListResponse {
  items: UserAsset[];
  total: number;
  quota: UserAssetQuota;
}

export interface UserPromptCategory {
  id: number;
  name: string;
  sort_order: number;
  prompt_count: number;
  updated_at?: string | null;
}

export interface UserPromptCategoryListResponse {
  items: UserPromptCategory[];
  uncategorized_count: number;
}

export interface UserPrompt {
  id: number;
  category_id?: number | null;
  category_name: string;
  title: string;
  content: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface UserPromptListResponse {
  items: UserPrompt[];
  total: number;
}

export interface UserCanvasSummary {
  id: number;
  project_id: string;
  name: string;
  node_count: number;
  preview_urls: string[];
  viewport_x: number;
  viewport_y: number;
  zoom: number;
  is_readonly?: boolean;
  is_deleted?: boolean;
  owner_user_id?: string;
  owner_username?: string;
  owner_avatar_url?: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CanvasNode {
  id: number;
  canvas_id: number;
  group_id?: number | null;
  task_id: string;
  video_task_id?: string;
  node_type: "task" | "text" | "image";
  content: string;
  image_url: string;
  asset_is_deleted?: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
  z_index: number;
  created_at?: string | null;
  updated_at?: string | null;
  task?: TaskResult | null;
  video_task?: VideoTaskResult | null;
}

export interface CanvasGroup {
  id: number;
  canvas_id: number;
  name: string;
  color: string;
  x: number;
  y: number;
  width: number;
  height: number;
  z_index: number;
  node_ids: number[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CanvasEdge {
  id: number;
  canvas_id: number;
  source_node_id: number;
  target_node_id: number;
  edge_type: string;
  source_anchor: "auto" | "top" | "right" | "bottom" | "left";
  target_anchor: "auto" | "top" | "right" | "bottom" | "left";
  is_collapsed: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CanvasDetail extends UserCanvasSummary {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  groups: CanvasGroup[];
}

export interface CanvasGroupAssignNodesResponse {
  group: CanvasGroup;
  groups: CanvasGroup[];
  nodes: CanvasNode[];
  deleted_group_ids: number[];
}

export interface CanvasGroupRemoveNodesResponse {
  groups: CanvasGroup[];
  nodes: CanvasNode[];
  deleted_group_ids: number[];
}

export interface UserCanvasListResponse {
  items: UserCanvasSummary[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export type ExampleCanvasStatus = "draft" | "published" | "disabled";

export interface ExampleCanvasProject {
  id: number;
  source_canvas_id: number;
  source_project_id: string;
  source_canvas_name: string;
  title: string;
  subtitle: string;
  cover_url: string;
  status: ExampleCanvasStatus;
  sort_order: number;
  preview_urls: string[];
  created_by: string;
  updated_by: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ExampleCanvasProjectListResponse {
  items: ExampleCanvasProject[];
}

export interface ExampleCanvasProjectCreatePayload {
  project_id: string;
  title?: string;
  subtitle?: string;
  cover_url?: string;
  sort_order?: number;
  status?: ExampleCanvasStatus;
}

export interface ExampleCanvasProjectUpdatePayload {
  project_id?: string;
  title?: string;
  subtitle?: string;
  cover_url?: string;
  sort_order?: number;
  status?: ExampleCanvasStatus;
  refresh_snapshot?: boolean;
}

export interface ExampleCanvasCopyResponse {
  canvas: UserCanvasSummary;
}

export interface CanvasTaskPayload {
  model?: string;
  source?: "web" | "app" | "api";
  prompt: string;
  num_images: number;
  size: string;
  resolution: string;
  custom_size?: string;
  mode?: "generate" | "inpaint" | "smart_cutout";
  reference_images?: string[];
  source_node_ids?: number[];
  source_image?: string;
  mask_image?: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
}

export interface CanvasVideoTaskPayload {
  model: string;
  source?: "web" | "app" | "api";
  prompt: string;
  duration_seconds: number;
  aspect_ratio: string;
  resolution: string;
  reference_images?: string[];
  source_node_ids?: number[];
  x: number;
  y: number;
  width?: number;
  height?: number;
}

export interface CanvasTaskCreateResponse {
  task_id?: string | null;
  task_ids: string[];
  nodes: CanvasNode[];
}

export type FeedbackStatus = "pending" | "processing" | "completed";
export type FeedbackType =
  | "general"
  | "image_task"
  | "video_task"
  | "canvas"
  | "purchase"
  | "feature_request"
  | "bug_report"
  | "optimization";

export interface FeedbackTaskSummary {
  task_id: string;
  model: string;
  mode: TaskMode;
  task_type: TaskType;
  source: TaskSource;
  prompt: string;
  status: string;
  error_message?: string;
  credit_refunded?: boolean;
  created_at?: string | null;
  reference_images: string[];
  reference_image_thumbs: string[];
  images: ImageResult[];
}

export interface FeedbackItem {
  feedback_id: string;
  user_id: string;
  username: string;
  task_id: string;
  feedback_type: FeedbackType;
  attachments: string[];
  status: FeedbackStatus;
  is_read: boolean;
  content: string;
  process_note: string;
  result_note: string;
  handler_id?: string | null;
  handler_name: string;
  handled_at?: string | null;
  last_message_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  task: FeedbackTaskSummary;
}

export interface FeedbackDetail extends FeedbackItem {
  task_user_id: string;
}

export interface FeedbackListResponse {
  total: number;
  items: FeedbackItem[];
}

export interface FeedbackUnresolvedCountResponse {
  count: number;
}

export interface FeedbackReadCountResponse {
  count: number;
}

export interface FeedbackMessage {
  message_id: string;
  feedback_id: string;
  sender_role: "user" | "admin" | "system";
  sender_id?: string | null;
  sender_name: string;
  content: string;
  attachments: string[];
  created_at?: string | null;
}

export interface FeedbackMessageListResponse {
  items: FeedbackMessage[];
}

export interface FeedbackMessageCreatePayload {
  content?: string;
  attachments?: string[];
}

export interface FeedbackListQuery {
  task_id?: string;
  status?: FeedbackStatus;
  feedback_type?: FeedbackType;
}

export interface FeedbackUpdatePayload {
  status?: FeedbackStatus;
  process_note?: string;
  result_note?: string;
}

export interface AdminFeedbackQuery extends FeedbackListQuery {
  user_id?: string;
  feedback_id?: string;
}

export interface FeedbackCreatePayload {
  task_id?: string | null;
  feedback_type?: FeedbackType;
  attachments?: string[];
  content: string;
}

export interface SystemMessageSender {
  user_id: string;
  username: string;
}

export interface SystemMessageRecipient {
  user_id: string;
  username: string;
  email?: string | null;
  is_read: boolean;
  read_at?: string | null;
}

export type SystemMessageRecipientScope = "selected" | "all";

export interface SystemMessageItem {
  message_id: string;
  subject: string;
  content_text: string;
  sender: SystemMessageSender;
  recipient_scope: SystemMessageRecipientScope;
  recipient_count: number;
  is_read: boolean;
  read_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SystemMessageDetail extends SystemMessageItem {
  content_html: string;
  recipients?: SystemMessageRecipient[];
}

export interface SystemMessageListResponse {
  total: number;
  items: SystemMessageItem[];
}

export interface SystemMessageReadCountResponse {
  count: number;
}

export interface SystemMessageCreatePayload {
  subject: string;
  content_html: string;
  recipient_scope: SystemMessageRecipientScope;
  recipient_user_ids: string[];
}

export type UpdateLogTagType = "notice" | "feature" | "optimization" | "bugfix" | "other";

export interface UpdateLogItem {
  log_id: string;
  title: string;
  content: string;
  tag_type: UpdateLogTagType;
  effective_at: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface UpdateLogListResponse {
  total: number;
  items: UpdateLogItem[];
}

export interface UpdateLogPayload {
  title: string;
  content: string;
  tag_type: UpdateLogTagType;
  effective_at?: string | null;
}

export type PromptOptimizeStyleStatus = "enabled" | "disabled";

export interface PromptOptimizeStyle {
  id: number;
  name: string;
  description: string;
  style_prompt: string;
  sort_order: number;
  status: PromptOptimizeStyleStatus;
  is_default: boolean;
  is_deleted?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  usage_count?: number;
}

export interface PromptOptimizeStylePayload {
  name: string;
  description: string;
  style_prompt: string;
  sort_order: number;
  status: PromptOptimizeStyleStatus;
  is_default: boolean;
}

export interface PublicPromptOptimizeStyle {
  id: number;
  name: string;
  description: string;
  style_prompt: string;
  is_default: boolean;
  sort_order: number;
}

export type GenerationSceneCategoryStatus = "enabled" | "disabled";
export type GenerationSceneCategoryType = "generate" | "image_edit";

export interface GenerationSceneCategory {
  id: number;
  name: string;
  description: string;
  scene_type: GenerationSceneCategoryType;
  scene_keys: string[];
  sort_order: number;
  status: GenerationSceneCategoryStatus;
  is_deleted?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GenerationSceneCategoryPayload {
  name: string;
  description: string;
  scene_type: GenerationSceneCategoryType;
  scene_keys: string[];
  sort_order: number;
  status: GenerationSceneCategoryStatus;
}

export interface AdminUser {
  id: string;
  username: string;
  email?: string | null;
  phone?: string | null;
  avatar_url?: string;
  role: string;
  status: string;
  is_whitelisted: boolean;
  credits: number;
  consumed_credits: number;
  created_at: string;
}

export interface AdminUserListResponse {
  items: AdminUser[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  first_admin_id?: string | null;
  whitelisted_total: number;
}

export interface AdminUserPromoDashboard {
  user_id: string;
  username: string;
  summary: PromoCodeSummary;
  promo_codes: PromoCodeItem[];
  referrals: PromoReferralItem[];
  activities: PromoReferralActivityItem[];
}

export interface CreditLog {
  id: number;
  user_id: string;
  username: string;
  amount: number;
  type: "allocate" | "consume";
  mode: TaskType | "manual" | "redeem" | "purchase";
  description: string;
  operator_name: string;
  task_id?: string;
  created_at: string;
}

export interface PaymentPlan {
  key: string;
  title: string;
  amount_fen: number;
  display_amount: string;
  credits: number;
  tag: string;
  purchasable: boolean;
  disabled_reason: string;
}

export interface PaymentOrder {
  order_no: string;
  plan_key: string;
  subject: string;
  amount_fen: number;
  credits: number;
  status: "created" | "pending_pay" | "paid" | "credited" | "closed" | "failed";
  paid_at?: string | null;
  credited_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CreatePaymentOrderResult {
  order_no: string;
  status: "created" | "pending_pay" | "paid" | "credited" | "closed" | "failed";
  amount_fen: number;
  credits: number;
  subject: string;
  pay_url: string;
  result_token: string;
}

export type RedeemKeyStatus = "enabled" | "disabled";

export interface RedeemCreditResult {
  message: string;
  credit_amount: number;
  credits: number;
  redeem_key: string;
  used_at?: string | null;
}

export interface PromoCodeSummary {
  total_referrals: number;
  used_code_count: number;
  rewarded_registrations: number;
  rewarded_invitees?: number;
  reward_grant_count?: number;
  total_reward_amount_fen?: number;
  total_reward_amount_yuan?: number;
  today_reward_amount_fen?: number;
  today_reward_amount_yuan?: number;
  month?: string;
  month_reward_grant_count?: number;
  month_reward_amount_fen?: number;
  month_reward_amount_yuan?: number;
  period_referrals?: number;
  period_rewarded_invitees?: number;
  period_reward_grant_count?: number;
  period_reward_amount_fen?: number;
  period_reward_amount_yuan?: number;
  period_start?: string | null;
  period_end?: string | null;
  first_rate?: number;
  second_rate?: number;
  next_rate?: number;
  first_count?: number;
  max_reward_count?: number;
  start_at?: string | null;
}

export interface PromoCodeItem {
  id: number;
  code: string;
  platform_name: string;
  status: string;
  created_at?: string | null;
  referral_count: number;
  promo_link?: string;
}

export interface PromoCodeListResponse {
  summary: PromoCodeSummary;
  items: PromoCodeItem[];
}

export interface PromoReferralItem {
  user_id: string;
  username: string;
  email_masked: string;
  email?: string | null;
  promo_code: string;
  platform_name: string;
  reward_credits: number;
  reward_count?: number;
  total_reward_amount_yuan?: number;
  last_reward_at?: string | null;
  registered_at?: string | null;
}

export interface PromoReferralListResponse {
  total: number;
  items: PromoReferralItem[];
}

export interface PromoReferralActivityItem {
  user_id: string;
  username: string;
  email_masked: string;
  activity_type: "purchase" | "redeem";
  credits: number;
  amount_fen?: number | null;
  amount_yuan?: number | null;
  reward_rate?: number | null;
  reward_index?: number | null;
  reward_amount_fen?: number | null;
  reward_amount_yuan?: number | null;
  redeem_key: string;
  order_no: string;
  occurred_at?: string | null;
}

export interface PromoReferralActivityListResponse {
  total: number;
  items: PromoReferralActivityItem[];
}

export interface InviteRewardSummary {
  total_referrals: number;
  today_referrals: number;
  rewarded_invitees: number;
  reward_grant_count: number;
  total_reward_credits: number;
  today_reward_credits: number;
}

export interface InviteRewardOverviewResponse {
  invite_code: string;
  invite_link: string;
  reward_rate: number;
  max_reward_count: number;
  summary: InviteRewardSummary;
}

export interface InviteRewardReferralItem {
  user_id: string;
  username: string;
  email_masked: string;
  reward_count: number;
  total_reward_credits: number;
  last_reward_at?: string | null;
  registered_at?: string | null;
}

export interface InviteRewardReferralListResponse {
  total: number;
  items: InviteRewardReferralItem[];
  page: number;
  page_size: number;
}

export interface InviteRewardLogItem {
  id: number;
  invitee_user_id: string;
  invitee_username: string;
  invitee_email_masked: string;
  source_type: "payment" | "redeem" | string;
  source_id: string;
  source_credits: number;
  reward_rate: number;
  reward_credits: number;
  reward_index: number;
  created_at?: string | null;
}

export interface InviteRewardLogListResponse {
  total: number;
  items: InviteRewardLogItem[];
  page: number;
  page_size: number;
}

export interface AdminInviteRewardSummary {
  total_referrals: number;
  rewarded_referrers: number;
  rewarded_invitees: number;
  reward_grant_count: number;
  source_credits: number;
  reward_credits: number;
  payment_reward_count: number;
  redeem_reward_count: number;
}

export interface AdminInviteRewardUserItem {
  user_id: string;
  username: string;
  email: string;
  invite_code: string;
  total_referrals: number;
  rewarded_invitees: number;
  reward_grant_count: number;
  source_credits: number;
  reward_credits: number;
  last_reward_at?: string | null;
  created_at?: string | null;
}

export interface AdminInviteRewardLogItem {
  id: number;
  referrer_user_id: string;
  referrer_username: string;
  invitee_user_id: string;
  invitee_username: string;
  source_type: "payment" | "redeem" | string;
  source_id: string;
  source_credits: number;
  reward_rate: number;
  reward_credits: number;
  reward_index: number;
  created_at?: string | null;
}

export interface AdminInviteRewardDashboard {
  summary: AdminInviteRewardSummary;
  users: AdminInviteRewardUserItem[];
  recent_logs: AdminInviteRewardLogItem[];
}

export interface AdminInviteRewardDetailReferralItem {
  user_id: string;
  username: string;
  email: string;
  reward_count: number;
  reward_credits: number;
  last_reward_at?: string | null;
  registered_at?: string | null;
}

export interface AdminInviteRewardDetailLogItem {
  id: number;
  invitee_user_id: string;
  invitee_username: string;
  invitee_email: string;
  source_type: "payment" | "redeem" | string;
  source_id: string;
  source_credits: number;
  reward_rate: number;
  reward_credits: number;
  reward_index: number;
  created_at?: string | null;
}

export interface AdminInviteRewardUserDetail {
  user: {
    user_id: string;
    username: string;
    email: string;
    invite_code: string;
    created_at?: string | null;
  };
  summary: Pick<AdminInviteRewardSummary, "total_referrals" | "rewarded_invitees" | "reward_grant_count" | "source_credits" | "reward_credits">;
  referrals: AdminInviteRewardDetailReferralItem[];
  reward_logs: AdminInviteRewardDetailLogItem[];
}

export interface AdminPromoStatsSummary {
  total_referrals: number;
  active_promoters: number;
  total_promo_codes: number;
  used_promo_codes: number;
  whitelisted_users: number;
  reward_credits: number;
  purchase_count: number;
  purchase_credits: number;
  redeem_count: number;
  redeem_credits: number;
  reward_grant_count?: number;
  total_reward_amount_yuan?: number;
  month?: string;
  month_reward_grant_count?: number;
  month_reward_amount_yuan?: number;
  start_at?: string | null;
}

export interface AdminPromoStatsUserItem {
  user_id: string;
  username: string;
  email: string;
  is_whitelisted: boolean;
  promo_code_count: number;
  used_code_count: number;
  total_referrals: number;
  reward_credits: number;
  purchase_credits: number;
  redeem_credits: number;
  reward_grant_count?: number;
  total_reward_amount_yuan?: number;
  month_reward_grant_count?: number;
  month_reward_amount_yuan?: number;
  last_referral_at?: string | null;
  created_at?: string | null;
}

export interface AdminPromoStatsReferralItem {
  id: number;
  promoter_user_id: string;
  promoter_username: string;
  invitee_user_id: string;
  invitee_username: string;
  promo_code: string;
  platform_name: string;
  reward_credits: number;
  registered_at?: string | null;
}

export interface AdminPromoStatsDashboard {
  summary: AdminPromoStatsSummary;
  users: AdminPromoStatsUserItem[];
  recent_referrals: AdminPromoStatsReferralItem[];
}

export interface AdminRedeemKey {
  id: number;
  redeem_key: string;
  credit_amount: number;
  batch_no: string;
  status: RedeemKeyStatus;
  is_used: boolean;
  used_at?: string | null;
  used_by_user_id?: string | null;
  used_by_username: string;
  used_by_user_email: string;
  created_by_user_id?: string | null;
  created_by_username: string;
  created_at?: string | null;
}

export interface AdminRedeemKeyBatchResult {
  batch_no: string;
  credit_amount: number;
  count: number;
  items: AdminRedeemKey[];
}

export interface TemplateTag {
  id: number;
  name: string;
  template_count?: number;
}

export interface CreativeTemplate {
  id: number;
  prompt: string;
  model: string;
  reference_images: string[];
  reference_image_thumbs?: string[];
  num_images: number;
  size: string;
  resolution: string;
  custom_size: string;
  result_image: string;
  result_image_thumb?: string;
  sort_order: number;
  tags: TemplateTag[];
  created_at: string;
}

export interface TemplateListResponse {
  total: number;
  items: CreativeTemplate[];
}

export interface AdminStats {
  total_users: number;
  total_tasks: number;
  total_credit_cost: number;
  total_remain_credits: number;
  active_users: number;
}

export type VideoGenerationMode = "text_to_video" | "image_to_video" | "first_last_frame";
export type VideoTaskModeFilter = VideoGenerationMode;
export type VideoSceneAvailabilityMode = "text_to_video" | "image_to_video" | "both";

export interface VideoStats {
  total_users: number;
  total_tasks: number;
  total_credit_cost: number;
  active_users: number;
  success_tasks: number;
  failed_tasks: number;
}

export type ErrorTrendGranularity = "1hour" | "3hour" | "6hour";

export type AdminAnalyticsGranularity = "3hour" | "day" | "week" | "month";

export interface AdminAnalyticsQuery {
  granularity: AdminAnalyticsGranularity;
  start_date?: string;
  end_date?: string;
  user_id?: string;
  source?: TaskSource;
  model?: string;
  mode?: TaskType;
  status?: string;
  canvas_task_filter?: "all" | "canvas" | "non_canvas";
  include_unsafe_tasks?: boolean;
}

export interface VideoAnalyticsQuery {
  granularity: AdminAnalyticsGranularity;
  start_date?: string;
  end_date?: string;
  user_id?: string;
  source?: TaskSource;
  model?: string;
  mode?: VideoTaskModeFilter;
  status?: string;
  include_unsafe_tasks?: boolean;
}

export interface AdminAnalyticsMetric {
  current: number;
  previous: number;
  delta: number;
  delta_pct?: number | null;
}

export interface AdminAnalyticsSummary {
  granularity: AdminAnalyticsGranularity;
  current_range_label: string;
  previous_range_label: string;
  total_users: number;
  tasks_created: AdminAnalyticsMetric;
  success_tasks: AdminAnalyticsMetric;
  failed_tasks: AdminAnalyticsMetric;
  credits_consumed: AdminAnalyticsMetric;
  new_users: AdminAnalyticsMetric;
  active_users: AdminAnalyticsMetric;
  fallback_task_total: number;
  fallback_success_tasks: number;
  fallback_failed_tasks: number;
}

export interface AdminAnalyticsTimeseriesPoint {
  label: string;
  bucket_start?: string | null;
  bucket_end?: string | null;
  tasks_created: number;
  success_tasks: number;
  failed_tasks: number;
  credits_consumed: number;
  new_users: number;
  active_users: number;
}

export interface AdminAnalyticsTimeseries {
  granularity: AdminAnalyticsGranularity;
  current_range_label: string;
  previous_range_label: string;
  current: AdminAnalyticsTimeseriesPoint[];
  previous: AdminAnalyticsTimeseriesPoint[];
}

export interface AdminAnalyticsBreakdownItem {
  name: string;
  count: number;
  credit_cost: number;
}

export interface AdminAnalyticsModelCompareItem {
  name: string;
  count: number;
  success_count: number;
  failed_count: number;
  success_rate: number;
  credit_cost: number;
  avg_credit_cost: number;
  duration_count?: number;
  avg_duration_seconds?: number;
}

export interface AdminAnalyticsApiAttemptPerformanceItem {
  api_config_id?: number | null;
  name: string;
  call_count: number;
  task_duration_count: number;
  avg_task_duration_seconds: number;
  download_count: number;
  avg_result_download_ms: number;
}

export interface AdminDailyReportTestResult {
  sent: boolean;
  report_date: string;
  range_start: string;
  range_end: string;
  revenue_fen: number;
  revenue_yuan: number;
  total_revenue_yuan: number;
  paid_order_count: number;
  offline_order_revenue_fen: number;
  offline_order_revenue_yuan: number;
  offline_order_count: number;
  redeem_revenue_yuan: number;
  redeem_used_count: number;
  task_total_count: number;
  task_success_count: number;
  task_failed_count: number;
  credit_consumed: number;
}

export interface AdminDailyReportRangePayload {
  start_date: string;
  end_date: string;
}

export interface AdminAnalyticsBreakdown {
  range_label: string;
  status_breakdown: AdminAnalyticsBreakdownItem[];
  source_breakdown: AdminAnalyticsBreakdownItem[];
  mode_breakdown: AdminAnalyticsBreakdownItem[];
  canvas_breakdown?: AdminAnalyticsBreakdownItem[];
  model_breakdown: AdminAnalyticsBreakdownItem[];
  model_compare?: AdminAnalyticsModelCompareItem[];
  api_attempt_performance?: AdminAnalyticsApiAttemptPerformanceItem[];
  top_users_by_tasks: AdminAnalyticsBreakdownItem[];
  top_users_by_credit: AdminAnalyticsBreakdownItem[];
}

export interface AdminAnalyticsRedeemRevenueItem {
  credit_amount: number;
  unit_price: number;
  used_count: number;
  total_amount: number;
}

export interface AdminAnalyticsRedeemRevenue {
  range_label: string;
  items: AdminAnalyticsRedeemRevenueItem[];
  total_used_count: number;
  total_amount: number;
}

export interface AdminAnalyticsRevenueTimeseriesPoint {
  label: string;
  bucket_start?: string | null;
  bucket_end?: string | null;
  online_amount: number;
  redeem_amount: number;
  offline_amount: number;
  total_amount: number;
}

export interface AdminAnalyticsRevenueTimeseries {
  granularity: string;
  range_label: string;
  points: AdminAnalyticsRevenueTimeseriesPoint[];
  total_online_amount: number;
  total_redeem_amount: number;
  total_offline_amount: number;
  total_amount: number;
}

export interface AdminErrorAnalyticsItem {
  error_category: string;
  error_message: string;
  count: number;
}

export interface AdminErrorAnalytics {
  range_label: string;
  total_failed_tasks: number;
  fallback_task_total: number;
  fallback_success_tasks: number;
  fallback_failed_tasks: number;
  distinct_error_categories: number;
  distinct_error_messages: number;
  items: AdminErrorAnalyticsItem[];
}

export interface AdminErrorCategoryTimeseriesSeries {
  error_category: string;
  total_count: number;
}

export interface AdminErrorCategoryTimeseriesPoint {
  label: string;
  bucket_start?: string | null;
  bucket_end?: string | null;
  total_failed_tasks: number;
  categories: Record<string, number>;
}

export interface AdminErrorCategoryTimeseries {
  granularity: ErrorTrendGranularity;
  range_label: string;
  series: AdminErrorCategoryTimeseriesSeries[];
  points: AdminErrorCategoryTimeseriesPoint[];
}

export type AdminErrorTaskKind = "image" | "video";

export interface AdminErrorTaskItem {
  task_id: string;
  user_id: string;
  username: string;
  avatar_url: string;
  task_type: TaskType | VideoGenerationMode;
  model: string;
  source: TaskSource;
  mode: TaskMode;
  prompt: string;
  status: string;
  error_message: string;
  credit_cost: number;
  credit_refunded: boolean;
  used_fallback_api?: boolean;
  primary_api_config_name?: string;
  primary_http_status?: number | null;
  fallback_api_config_name?: string;
  fallback_status?: "unused" | "success" | "failed" | "partial";
  fallback_error_message?: string;
  created_at?: string | null;
}

export interface AdminErrorTaskList {
  total: number;
  items: AdminErrorTaskItem[];
}

export interface AdminPaymentOrder {
  id: number;
  order_no: string;
  out_trade_no: string;
  alipay_trade_no: string;
  user_id: string;
  username: string;
  user_email: string;
  plan_key: string;
  subject: string;
  amount_fen: number;
  amount_yuan: number;
  credits: number;
  status: "created" | "pending_pay" | "paid" | "credited" | "closed" | "failed";
  trade_status: string;
  buyer_id: string;
  paid_at?: string | null;
  credited_at?: string | null;
  closed_at?: string | null;
  failed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AdminOfflineOrder {
  id: number;
  business_id: string;
  user_id: string;
  username: string;
  user_email: string;
  order_type: "purchase" | "refund";
  credit_amount: number;
  amount_fen: number;
  amount_yuan: number;
  remark: string;
  created_by: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CreateOfflineOrderPayload {
  user_id: string;
  order_type: "purchase" | "refund";
  credit_amount: number;
  amount_yuan: number;
  remark?: string;
}

export interface AdminConfig {
  id: number;
  contact_qr_image: string;
  announcement_enabled: boolean;
  announcement_content: string;
  announcement_updated_at?: string | null;
  updated_at: string;
}

export interface ExternalApiSecretConfig {
  id: number;
  key: string;
  tongyi_key: string;
  updated_at?: string | null;
}

export interface CosConfig {
  id: number;
  cos_secret_id: string;
  cos_secret_key: string;
  cos_bucket: string;
  cos_region: string;
  cos_upload_domain: string;
  cos_public_base_url: string;
  updated_at?: string | null;
}

export interface AnnouncementConfig {
  announcement_enabled: boolean;
  announcement_content: string;
  announcement_updated_at?: string | null;
}

export type ExternalApiConfigStatus = "enabled" | "disabled";
export type ExternalApiRequestFormat = "json" | "multipart";
export type ExternalApiCallMode = "sync" | "async";
export type ExternalApiPollMethod = "GET" | "POST";
export type ExternalApiSceneType = "generate" | "image_edit" | "prompt_reverse" | "prompt_optimize" | "inpaint" | "smart_cutout";

export interface SceneOptionItem {
  label: string;
  value: string;
}

export interface ExternalApiConfig {
  id: number;
  name: string;
  description: string;
  group_name: string;
  request_url: string;
  request_format: ExternalApiRequestFormat;
  headers_json: string;
  payload_json: string;
  response_json: string;
  result_base64_field: string;
  call_mode: ExternalApiCallMode;
  submit_success_statuses_json: string;
  poll_url: string;
  poll_method: ExternalApiPollMethod;
  poll_headers_json: string;
  poll_payload_json: string;
  task_id_field: string;
  result_status_field: string;
  result_success_values_json: string;
  result_failed_values_json: string;
  result_error_field: string;
  poll_result_base64_field: string;
  poll_result_url_field: string;
  poll_interval_seconds: number;
  poll_timeout_seconds: number;
  status: ExternalApiConfigStatus;
  created_at: string;
  updated_at?: string;
}

export interface ExternalApiConfigPayload {
  name: string;
  description: string;
  group_name: string;
  request_url: string;
  request_format: ExternalApiRequestFormat;
  headers_json: string;
  payload_json: string;
  response_json: string;
  result_base64_field: string;
  call_mode: ExternalApiCallMode;
  submit_success_statuses_json: string;
  poll_url: string;
  poll_method: ExternalApiPollMethod;
  poll_headers_json: string;
  poll_payload_json: string;
  task_id_field: string;
  result_status_field: string;
  result_success_values_json: string;
  result_failed_values_json: string;
  result_error_field: string;
  poll_result_base64_field: string;
  poll_result_url_field: string;
  poll_interval_seconds: number;
  poll_timeout_seconds: number;
  status: ExternalApiConfigStatus;
}

export interface ExternalApiSceneBinding {
  scene_key: string;
  scene_type: ExternalApiSceneType;
  scene_label: string;
  scene_description: string;
  display_name: string;
  subtitle: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_resolution: boolean;
  hide_custom_size: boolean;
  custom_size_min: number;
  custom_size_max: number;
  custom_size_step: number;
  status: ExternalApiConfigStatus;
  is_builtin: boolean;
  api_config_id?: number | null;
  api_config_name: string;
  api_group_name: string;
  api_status?: ExternalApiConfigStatus | null;
  backup_api_config_id?: number | null;
  backup_api_config_name: string;
  backup_api_group_name: string;
  backup_api_status?: ExternalApiConfigStatus | null;
  credit_cost: number;
  resolution_credit_costs_json: string;
  max_reference_images: number;
  aspect_ratio_options_json: string;
  image_size_options_json: string;
  custom_size_options_json: string;
  resolution_mapping_json: string;
}

export interface ExternalApiSceneBindingCreatePayload {
  scene_key: string;
  scene_type: Extract<ExternalApiSceneType, "generate" | "image_edit">;
  scene_label: string;
  scene_description: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_resolution: boolean;
  hide_custom_size: boolean;
  custom_size_min: number;
  custom_size_max: number;
  custom_size_step: number;
  api_config_id: number | null;
  backup_api_config_id: number | null;
  display_name: string;
  subtitle: string;
  credit_cost: number;
  max_reference_images: number;
  aspect_ratio_options_json: string;
  image_size_options_json: string;
  custom_size_options_json: string;
  resolution_mapping_json: string;
  resolution_credit_costs_json: string;
}

export interface ExternalApiSceneBindingMetaPayload {
  scene_key: string;
  scene_label: string;
  scene_description: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_resolution: boolean;
  hide_custom_size: boolean;
  custom_size_min: number;
  custom_size_max: number;
  custom_size_step: number;
  max_reference_images: number;
  aspect_ratio_options_json: string;
  image_size_options_json: string;
  custom_size_options_json: string;
  resolution_mapping_json: string;
  resolution_credit_costs_json: string;
}

export interface ExternalApiConfigTestResult {
  success: boolean;
  request_url: string;
  status_code?: number | null;
  response_preview: string;
}

export interface GenerationModelOption {
  model_key: string;
  model_label: string;
  model_description: string;
  display_name: string;
  subtitle: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_resolution: boolean;
  hide_custom_size: boolean;
  custom_size_min: number;
  custom_size_max: number;
  custom_size_step: number;
  credit_cost: number;
  resolution_credit_costs: Record<string, number>;
  max_reference_images: number;
  aspect_ratio_options: SceneOptionItem[];
  image_size_options: SceneOptionItem[];
  custom_size_options: SceneOptionItem[];
  category_id?: number | null;
  category_name?: string | null;
  category_sort_order?: number | null;
}

export interface TaskSceneConfig {
  scene_key: string;
  scene_type: ExternalApiSceneType;
  scene_label: string;
  scene_description: string;
  display_name: string;
  subtitle: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_resolution: boolean;
  hide_custom_size: boolean;
  custom_size_min: number;
  custom_size_max: number;
  custom_size_step: number;
  credit_cost: number;
  resolution_credit_costs: Record<string, number>;
  max_reference_images: number;
  aspect_ratio_options: SceneOptionItem[];
  image_size_options: SceneOptionItem[];
  custom_size_options: SceneOptionItem[];
  category_id?: number | null;
  category_name?: string | null;
  category_sort_order?: number | null;
}

export interface VideoExternalApiConfig {
  id: number;
  name: string;
  description: string;
  group_name: string;
  request_url: string;
  request_format: ExternalApiRequestFormat;
  headers_json: string;
  payload_json: string;
  response_json: string;
  result_video_url_field: string;
  result_video_base64_field: string;
  result_cover_url_field: string;
  call_mode: "async";
  submit_success_statuses_json: string;
  poll_url: string;
  poll_method: ExternalApiPollMethod;
  poll_headers_json: string;
  poll_payload_json: string;
  task_id_field: string;
  result_status_field: string;
  result_success_values_json: string;
  result_failed_values_json: string;
  result_error_field: string;
  poll_result_video_url_field: string;
  poll_result_video_base64_field: string;
  poll_result_cover_url_field: string;
  poll_interval_seconds: number;
  poll_timeout_seconds: number;
  status: ExternalApiConfigStatus;
  created_at: string;
  updated_at?: string;
}

export interface VideoExternalApiConfigPayload {
  name: string;
  description: string;
  group_name: string;
  request_url: string;
  request_format: ExternalApiRequestFormat;
  headers_json: string;
  payload_json: string;
  response_json: string;
  result_video_url_field: string;
  result_video_base64_field: string;
  result_cover_url_field: string;
  call_mode: "async";
  submit_success_statuses_json: string;
  poll_url: string;
  poll_method: ExternalApiPollMethod;
  poll_headers_json: string;
  poll_payload_json: string;
  task_id_field: string;
  result_status_field: string;
  result_success_values_json: string;
  result_failed_values_json: string;
  result_error_field: string;
  poll_result_video_url_field: string;
  poll_result_video_base64_field: string;
  poll_result_cover_url_field: string;
  poll_interval_seconds: number;
  poll_timeout_seconds: number;
  status: ExternalApiConfigStatus;
}

export interface VideoExternalApiSceneBinding {
  scene_key: string;
  scene_label: string;
  scene_description: string;
  display_name: string;
  subtitle: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_duration: boolean;
  hide_resolution: boolean;
  availability_mode: VideoSceneAvailabilityMode;
  availability_modes: VideoGenerationMode[];
  max_reference_images: number;
  status: ExternalApiConfigStatus;
  is_builtin: boolean;
  api_config_id?: number | null;
  api_config_name: string;
  api_group_name: string;
  api_status?: ExternalApiConfigStatus | null;
  backup_api_config_id?: number | null;
  backup_api_config_name: string;
  backup_api_group_name: string;
  backup_api_status?: ExternalApiConfigStatus | null;
  credit_billing_mode: "fixed" | "per_second";
  credit_cost: number;
  per_second_credit_cost: number;
  aspect_ratio_options_json: string;
  duration_options_json: string;
  resolution_options_json: string;
  resolution_mapping_json: string;
  resolution_credit_costs_json: string;
}

export interface VideoExternalApiSceneBindingCreatePayload {
  scene_key: string;
  scene_label: string;
  scene_description: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_duration: boolean;
  hide_resolution: boolean;
  availability_mode: VideoSceneAvailabilityMode;
  availability_modes: VideoGenerationMode[];
  max_reference_images: number;
  api_config_id: number | null;
  backup_api_config_id: number | null;
  display_name: string;
  subtitle: string;
  credit_billing_mode: "fixed" | "per_second";
  credit_cost: number;
  per_second_credit_cost: number;
  aspect_ratio_options_json: string;
  duration_options_json: string;
  resolution_options_json: string;
  resolution_mapping_json: string;
  resolution_credit_costs_json: string;
  status: ExternalApiConfigStatus;
}

export interface VideoExternalApiSceneBindingMetaPayload {
  scene_key: string;
  scene_label: string;
  scene_description: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_duration: boolean;
  hide_resolution: boolean;
  availability_mode: VideoSceneAvailabilityMode;
  availability_modes: VideoGenerationMode[];
  max_reference_images: number;
  credit_billing_mode: "fixed" | "per_second";
  credit_cost: number;
  per_second_credit_cost: number;
  aspect_ratio_options_json: string;
  duration_options_json: string;
  resolution_options_json: string;
  resolution_mapping_json: string;
  resolution_credit_costs_json: string;
}

export interface VideoExternalApiConfigTestResult {
  success: boolean;
  request_url: string;
  status_code?: number | null;
  response_preview: string;
}

export interface ChatExternalApiConfig {
  id: number;
  name: string;
  description: string;
  group_name: string;
  request_url: string;
  request_format: "json";
  headers_json: string;
  payload_json: string;
  response_json: string;
  result_text_field: string;
  result_error_field: string;
  call_mode: "sync";
  submit_success_statuses_json: string;
  status: ExternalApiConfigStatus;
  created_at: string;
  updated_at?: string;
}

export interface ChatExternalApiConfigPayload {
  name: string;
  description: string;
  group_name: string;
  request_url: string;
  request_format: "json";
  headers_json: string;
  payload_json: string;
  response_json: string;
  result_text_field: string;
  result_error_field: string;
  call_mode: "sync";
  submit_success_statuses_json: string;
  status: ExternalApiConfigStatus;
}

export interface ChatStarterPrompt {
  tag: string;
  text: string;
  image_url?: string;
}

export interface ChatExternalApiSceneBinding {
  scene_key: string;
  scene_label: string;
  scene_description: string;
  display_name: string;
  subtitle: string;
  sort_order: number;
  status: ExternalApiConfigStatus;
  api_config_id?: number | null;
  api_config_name: string;
  api_group_name: string;
  api_status?: ExternalApiConfigStatus | null;
  backup_api_config_id?: number | null;
  backup_api_config_name: string;
  backup_api_group_name: string;
  backup_api_status?: ExternalApiConfigStatus | null;
  credit_cost: number;
  system_prompt: string;
  context_message_limit: number;
  opening_greeting: string;
  starter_prompts: ChatStarterPrompt[];
}

export interface ChatExternalApiSceneBindingCreatePayload {
  scene_key: string;
  scene_label: string;
  scene_description: string;
  sort_order: number;
  api_config_id: number | null;
  backup_api_config_id: number | null;
  display_name: string;
  subtitle: string;
  credit_cost: number;
  system_prompt: string;
  context_message_limit: number;
  opening_greeting: string;
  starter_prompts: ChatStarterPrompt[];
  status: ExternalApiConfigStatus;
}

export interface ChatExternalApiSceneBindingMetaPayload {
  scene_key?: string;
  scene_label: string;
  scene_description: string;
  sort_order: number;
  credit_cost: number;
  system_prompt: string;
  context_message_limit: number;
  opening_greeting: string;
  starter_prompts: ChatStarterPrompt[];
}

export interface ChatExternalApiConfigTestResult {
  success: boolean;
  request_url: string;
  status_code?: number | null;
  response_preview: string;
  extracted_text?: string;
}

export interface ChatGenerationModelOption {
  model_key: string;
  model_label: string;
  model_description: string;
  display_name: string;
  subtitle: string;
  sort_order: number;
  credit_cost: number;
  opening_greeting: string;
  starter_prompts: ChatStarterPrompt[];
  stream?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  model: string;
  last_message_at?: string | null;
  created_at: string;
  updated_at?: string | null;
  user_id?: string;
  username?: string;
  avatar_url?: string;
  credit_cost?: number;
}

export interface ChatSessionListResponse {
  items: ChatSession[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  next_before_session_id?: string | null;
}

export interface ChatImage {
  url: string;
}

export interface ChatGenerateInfo {
  status: "pending_confirm" | "running" | "success" | "failed" | "cancelled" | string;
  prompt: string;
  num_images: number;
  reference_images: string[];
  mode_hint: "generate" | "image_edit" | string;
  model?: string;
  size?: string;
  resolution?: string;
  custom_size?: string;
  task_ids: string[];
  error_message?: string;
}

export interface ChatMessage {
  id: number;
  session_id: string;
  role: "user" | "assistant" | "system" | string;
  content: string;
  images?: ChatImage[];
  generate?: ChatGenerateInfo | null;
  model: string;
  client_message_id?: string | null;
  credit_cost: number;
  status: string;
  error_message: string;
  created_at: string;
}

export interface ChatMessageListResponse {
  items: ChatMessage[];
  has_more: boolean;
  next_before_id?: number | null;
}

export interface ChatSendMessageResponse {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  credit_cost: number;
  balance?: number | null;
  session: ChatSession;
}

export interface VideoGenerationModelOption {
  model_key: string;
  model_label: string;
  model_description: string;
  display_name: string;
  subtitle: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_duration: boolean;
  hide_resolution: boolean;
  availability_mode: VideoSceneAvailabilityMode;
  availability_modes: VideoGenerationMode[];
  max_reference_images: number;
  credit_billing_mode: "fixed" | "per_second";
  credit_cost: number;
  per_second_credit_cost: number;
  aspect_ratio_options: SceneOptionItem[];
  resolution_credit_costs: Record<string, number>;
  duration_options: SceneOptionItem[];
  resolution_options: SceneOptionItem[];
}

export interface VideoTaskSceneConfig {
  scene_key: string;
  scene_label: string;
  scene_description: string;
  display_name: string;
  subtitle: string;
  sort_order: number;
  hide_aspect_ratio: boolean;
  hide_duration: boolean;
  hide_resolution: boolean;
  availability_mode: VideoSceneAvailabilityMode;
  availability_modes: VideoGenerationMode[];
  max_reference_images: number;
  credit_billing_mode: "fixed" | "per_second";
  credit_cost: number;
  per_second_credit_cost: number;
  aspect_ratio_options: SceneOptionItem[];
  resolution_credit_costs: Record<string, number>;
  duration_options: SceneOptionItem[];
  resolution_options: SceneOptionItem[];
}

export interface VideoResult {
  id: number;
  video_url: string;
  cover_url: string;
  video_format?: string;
  video_size_bytes?: number;
  duration_seconds?: number | null;
  status: "pending" | "success" | "failed";
  error_message?: string;
}

export interface VideoTaskApiAttempt {
  id?: number | null;
  api_config_id?: number | null;
  api_config_name: string;
  attempt_index: number;
  is_fallback: boolean;
  status: "success" | "failed" | string;
  http_status?: number | null;
  error_message?: string;
  duration_ms?: number | null;
  created_at?: string | null;
}

export interface VideoTaskResult {
  id: string;
  model: string;
  source: TaskSource;
  generation_mode: VideoGenerationMode;
  prompt: string;
  duration_seconds: number;
  aspect_ratio: string;
  resolution: string;
  reference_images?: string[];
  credit_cost: number;
  credit_refunded?: boolean;
  failure_refund_remaining_count?: number | null;
  used_fallback_api?: boolean;
  task_is_deleted?: boolean;
  status: "pending" | "queued" | "processing" | "success" | "failed";
  error_message?: string;
  created_at: string;
  enqueued_at?: string | null;
  request_started_at?: string | null;
  request_finished_at?: string | null;
  videos: VideoResult[];
  api_attempts?: VideoTaskApiAttempt[];
}

export interface AdminVideoTaskResult extends VideoTaskResult {
  user_id: string;
  username?: string;
  avatar_url?: string;
}

export interface AdminVideoTaskListResponse {
  total: number;
  items: AdminVideoTaskResult[];
}

export type AdminLedgerExpenseType = "server" | "third_party_api" | "other";

export interface AdminLedgerIncome {
  online_revenue_yuan: number;
  redeem_revenue_yuan: number;
  offline_revenue_yuan: number;
  total_income_yuan: number;
}

export interface AdminLedgerExpense {
  id: number;
  business_id: string;
  expense_type: AdminLedgerExpenseType;
  title: string;
  amount_fen: number;
  amount_yuan: number;
  content: string;
  description: string;
  screenshot_urls: string[];
  sort_order: number;
  created_by_username: string;
  updated_by_username: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AdminLedgerLog {
  id: number;
  operator_id: string;
  operator_username: string;
  action: string;
  summary: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  created_at?: string | null;
}

export interface AdminLedger {
  id?: number | null;
  business_id: string;
  month: string;
  title: string;
  content: string;
  description: string;
  screenshot_urls: string[];
  income: AdminLedgerIncome;
  income_snapshot: Record<string, unknown>;
  total_expense_fen: number;
  total_expense_yuan: number;
  net_income_fen: number;
  net_income_yuan: number;
  expenses: AdminLedgerExpense[];
  logs: AdminLedgerLog[];
  exists: boolean;
  created_by_username: string;
  updated_by_username: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AdminLedgerListItem {
  id: number;
  business_id: string;
  month: string;
  title: string;
  total_income_yuan: number;
  total_expense_yuan: number;
  net_income_yuan: number;
  updated_by_username: string;
  updated_at?: string | null;
}

export interface AdminLedgerListResponse {
  total: number;
  items: AdminLedgerListItem[];
}

export interface AdminLedgerExpensePayload {
  id?: number | null;
  expense_type: AdminLedgerExpenseType;
  title: string;
  amount_yuan: number;
  content: string;
  description: string;
  screenshot_urls: string[];
}

export interface AdminLedgerPayload {
  month?: string;
  title: string;
  content: string;
  description: string;
  screenshot_urls: string[];
  expenses: AdminLedgerExpensePayload[];
}

export type UploadPurpose =
  | "ref"
  | "chat"
  | "source"
  | "mask"
  | "reverse"
  | "misc"
  | "contact_qr"
  | "canvas_upload"
  | "user_suggestion"
  | "admin_ledger"
  | "template";

export interface UploadCredential {
  bucket: string;
  region: string;
  key: string;
  upload_domain: string;
  url: string;
  tmp_secret_id: string;
  tmp_secret_key: string;
  session_token: string;
  start_time?: number | null;
  expired_time: number;
}

export interface UserAssetUploadSessionResponse {
  asset: UserAsset;
  quota: UserAssetQuota;
  credential: UploadCredential;
}

export interface UserAssetImportResponse {
  asset: UserAsset;
  quota: UserAssetQuota;
}
