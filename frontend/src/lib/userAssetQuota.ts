import type { UserAssetQuota } from "@/types";

export function isAssetQuotaFull(quota: UserAssetQuota) {
  return quota.remaining <= 0;
}

export function getAssetQuotaFullMessage(quota: UserAssetQuota) {
  return `我的素材已满，最多支持 ${quota.limit} 个素材，请删除后再试`;
}

export function getAssetQuotaTruncatedMessage(acceptedCount: number, remaining: number) {
  return `我的素材剩余 ${remaining} 个额度，本次仅上传前 ${acceptedCount} 个`;
}

export function truncateByAssetQuota<T>(items: T[], remaining: number) {
  const safeRemaining = Math.max(remaining, 0);
  const accepted = items.slice(0, safeRemaining);
  return {
    accepted,
    skipped: Math.max(items.length - accepted.length, 0),
  };
}

export function isAssetQuotaError(detail: unknown): detail is string {
  return typeof detail === "string" && detail.includes("最多可上传");
}

export function resolveAssetQuotaErrorMessage(error: unknown) {
  const detail = (error as any)?.response?.data?.detail;
  return isAssetQuotaError(detail) ? detail : null;
}
