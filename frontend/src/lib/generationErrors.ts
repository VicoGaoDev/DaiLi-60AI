import type { ImageResult, TaskApiAttempt } from "@/types";

export const IMAGE_SAFETY_ERROR_MESSAGE = "生成的图片存在安全风险（色情、暴力、版权、政治敏感等），请尝试修改提示词或参考图，或换个模型尝试（不同模型审查尺度不同）！";
export const PROMPT_MODERATION_ERROR_MESSAGE = "提示词或参考图审核未通过";
export const GENERATION_TASK_FAILURE_MESSAGE = "生图失败，请反馈给我们处理";
export const INVALID_REFERENCE_IMAGE_MESSAGE = "参考图被模型拒绝，请更换正常格式的参考图后重试；或换个模型尝试（不同模型审查尺度不同）！";
export const INVALID_ASPECT_RATIO_MESSAGE = "当前宽高比不受支持，请更换其他宽高比后重试";
export const CREDIT_REFUNDED_SUFFIX = "（积分已返还）";

const PROMPT_MODERATION_ERROR_PATTERN =
  /\b(?:safety|prompt|moderation)\b|提示词|审核/i;
const IMAGE_SAFETY_ERROR_PATTERN = /unsafe|image_unsafe|content blocked/i;
const INVALID_ASPECT_RATIO_PATTERN = /n?put\.aspect_ratio is invalid|aspect_ratio is invalid/i;
const INVALID_REFERENCE_IMAGE_PATTERN =
  /invalid image file or mode|provider_request_invalid|bad request to openai|poll rejected: 400|image \d+/i;
const INVALID_REFERENCE_IMAGE_INDEX_PATTERN = /for image (\d+)/i;

export function extractInvalidReferenceImageIndex(rawMessage?: string) {
  const match = String(rawMessage || "").match(INVALID_REFERENCE_IMAGE_INDEX_PATTERN);
  if (!match) return null;
  const index = Number(match[1]);
  return Number.isFinite(index) && index > 0 ? index : null;
}

export function formatInvalidReferenceImageMessage(rawMessage?: string) {
  const index = extractInvalidReferenceImageIndex(rawMessage);
  if (!index) {
    return INVALID_REFERENCE_IMAGE_MESSAGE;
  }
  return `第 ${index} 张参考图被模型拒绝，请更换正常格式的参考图后重试；或换个模型尝试（不同模型审查尺度不同）！`;
}

export function isImageSafetyError(rawMessage?: string) {
  return IMAGE_SAFETY_ERROR_PATTERN.test(String(rawMessage || "").trim());
}

export function isPromptModerationError(rawMessage?: string) {
  return PROMPT_MODERATION_ERROR_PATTERN.test(String(rawMessage || "").trim());
}

export function isInvalidReferenceImageError(rawMessage?: string) {
  return INVALID_REFERENCE_IMAGE_PATTERN.test(String(rawMessage || "").trim());
}

export function isInvalidAspectRatioError(rawMessage?: string) {
  return INVALID_ASPECT_RATIO_PATTERN.test(String(rawMessage || "").trim());
}

export function extractApiErrorDetail(err: any): string {
  const detail = err?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.detail || (typeof item === "string" ? item : ""))
      .filter(Boolean)
      .join("；");
  }
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (detail && typeof detail === "object") {
    return String(detail.msg || detail.message || "").trim();
  }
  if (err?.code === "ECONNABORTED") return "请求超时，请稍后重试";
  return String(err?.message || "").trim();
}

export function formatGenerationErrorMessage(rawMessage?: string, fallback = "生成失败，请重试") {
  const detail = String(rawMessage || "").trim();
  if (!detail) return fallback;
  if (isPromptModerationError(detail)) {
    return PROMPT_MODERATION_ERROR_MESSAGE;
  }
  if (isImageSafetyError(detail)) {
    return IMAGE_SAFETY_ERROR_MESSAGE;
  }
  if (isInvalidAspectRatioError(detail)) {
    return INVALID_ASPECT_RATIO_MESSAGE;
  }
  if (isInvalidReferenceImageError(detail)) {
    return formatInvalidReferenceImageMessage(detail);
  }
  return detail;
}

function withCreditRefundedSuffix(message: string) {
  return message.endsWith(CREDIT_REFUNDED_SUFFIX) ? message : `${message}${CREDIT_REFUNDED_SUFFIX}`;
}

function formatMaybeRefundedMessage(message: string, creditRefunded: boolean) {
  return creditRefunded ? withCreditRefundedSuffix(message) : message;
}

function formatPublicGenerationFailureMessage(message: string, creditRefunded: boolean) {
  return formatGenerationTaskFailureMessage(message, creditRefunded);
}

function getFailedFallbackAttemptError(apiAttempts?: TaskApiAttempt[]) {
  const attempts = Array.isArray(apiAttempts) ? apiAttempts : [];
  const failedFallbackAttempts = attempts
    .filter((attempt) => attempt.is_fallback && attempt.status === "failed" && String(attempt.error_message || "").trim())
    .sort((left, right) => {
      const leftIndex = Number(left.attempt_index || 0);
      const rightIndex = Number(right.attempt_index || 0);
      if (leftIndex !== rightIndex) return rightIndex - leftIndex;
      return Number(right.id || 0) - Number(left.id || 0);
    });
  return String(failedFallbackAttempts[0]?.error_message || "").trim();
}

export function formatGenerationTaskFailureMessage(rawMessage?: string, creditRefunded = false) {
  const detail = String(rawMessage || "").trim();
  const message = isPromptModerationError(detail)
    ? PROMPT_MODERATION_ERROR_MESSAGE
    : isImageSafetyError(detail)
    ? IMAGE_SAFETY_ERROR_MESSAGE
    : isInvalidAspectRatioError(detail)
      ? INVALID_ASPECT_RATIO_MESSAGE
      : isInvalidReferenceImageError(detail)
        ? formatInvalidReferenceImageMessage(detail)
        : GENERATION_TASK_FAILURE_MESSAGE;
  return formatMaybeRefundedMessage(message, creditRefunded);
}

export function getPreferredGenerationErrorMessage(
  taskError?: string,
  imageError?: string,
  creditRefunded = false,
  _fallback = "生成失败，请重试",
  usedFallbackApi = false,
  apiAttempts?: TaskApiAttempt[],
  providerError?: string,
) {
  const failedFallbackError = usedFallbackApi ? getFailedFallbackAttemptError(apiAttempts) : "";
  if (failedFallbackError) {
    return formatPublicGenerationFailureMessage(failedFallbackError, creditRefunded);
  }
  const fallbackFinalError = usedFallbackApi ? String(providerError || imageError || taskError || "").trim() : "";
  if (fallbackFinalError) {
    return formatPublicGenerationFailureMessage(fallbackFinalError, creditRefunded);
  }
  return formatGenerationTaskFailureMessage(imageError || taskError, creditRefunded);
}

export function getTaskImageFailureMessage(
  task: {
    error_message?: string;
    provider_error_message?: string;
    credit_refunded?: boolean;
    used_fallback_api?: boolean;
    api_attempts?: TaskApiAttempt[];
  } | null | undefined,
  image: Pick<ImageResult, "error_message"> | null | undefined,
  fallback = "生成失败，请重试"
) {
  return getPreferredGenerationErrorMessage(
    task?.error_message,
    image?.error_message,
    Boolean(task?.credit_refunded),
    fallback,
    Boolean(task?.used_fallback_api),
    task?.api_attempts,
    task?.provider_error_message,
  );
}
