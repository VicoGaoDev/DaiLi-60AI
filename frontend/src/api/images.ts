import client from "./client";
import type { ImageResult } from "@/types";
import { withApiBaseUrl } from "@/lib/assets";

export const REALTIME_IMAGE_PREVIEW_LIMIT_BYTES = 32 * 1024 * 1024;
export const LARGE_IMAGE_PREVIEW_NOTICE = "原图体积较大，暂不支持实时预览，请下载原图查看完整内容";

export function regenerateImage(imageId: number): Promise<any> {
  return client.post(`/images/${imageId}/regenerate`);
}

export function deleteImage(imageId: number): Promise<void> {
  return client.delete(`/images/${imageId}`);
}

export function resolveImageUrl(imageUrl?: string): string {
  return withApiBaseUrl(imageUrl || "");
}

export function appendImageTransform(url: string, transform: string): string {
  if (!url || url.startsWith("data:") || url.startsWith("blob:")) return url;
  return `${url}${url.includes("?") ? "&" : "?"}${transform}`;
}

export function toOriginalImageUrl(imageUrl?: string): string {
  const resolved = resolveImageUrl(imageUrl || "");
  if (!resolved || resolved.startsWith("data:") || resolved.startsWith("blob:")) return resolved;
  const [withoutHash, hash = ""] = resolved.split("#");
  const [base, query = ""] = withoutHash.split("?");
  const cleanedBase = base.replace(/![^/]*$/, "").replace(/\/Zoom$/i, "");
  const kept = query
    .split("&")
    .map((part) => part.trim())
    .filter((part) => {
      if (!part) return false;
      const key = decodeURIComponent(part.split("=")[0] || "");
      return !key.startsWith("imageMogr2") && !key.startsWith("imageView2");
    });
  const next = kept.length ? `${cleanedBase}?${kept.join("&")}` : cleanedBase;
  return hash ? `${next}#${hash}` : next;
}

export function exceedsRealtimeImagePreviewLimit(imageSizeBytes?: number | null): boolean {
  return typeof imageSizeBytes === "number" && imageSizeBytes >= REALTIME_IMAGE_PREVIEW_LIMIT_BYTES;
}

export function getDisplayImageUrl(image?: Pick<ImageResult, "thumb_url" | "image_url" | "preview_url">): string {
  return getPreviewImageSrc(image?.thumb_url || image?.image_url || image?.preview_url || "");
}

export function getPreviewImageSrc(imageUrl?: string): string {
  return appendImageTransform(resolveImageUrl(imageUrl || ""), "imageMogr2/format/webp");
}

function appendZoomStyle(url: string): string {
  const [withoutHash, hash = ""] = url.split("#");
  const [base, query = ""] = withoutHash.split("?");
  const cleanedBase = base.replace(/\/+$/, "");
  if (!cleanedBase || /\/Zoom$/i.test(cleanedBase)) {
    return url;
  }
  const next = query ? `${cleanedBase}/Zoom?${query}` : `${cleanedBase}/Zoom`;
  return hash ? `${next}#${hash}` : next;
}

export function getAvatarImageSrc(imageUrl?: string): string {
  const raw = (imageUrl || "").trim();
  if (!raw || raw.startsWith("data:") || raw.startsWith("blob:")) return raw;
  if (raw.startsWith("/uploads/") || raw.startsWith("uploads/")) return "";
  const original = toOriginalImageUrl(raw);
  if (!original || original.startsWith("data:") || original.startsWith("blob:")) return original;
  if (!/^https?:\/\//i.test(original)) return "";
  return appendImageTransform(appendZoomStyle(original), "imageMogr2/format/webp");
}

export function getPreviewImageUrl(image?: Pick<ImageResult, "image_url" | "preview_url" | "thumb_url">): string {
  return getPreviewImageSrc(image?.image_url || image?.preview_url || image?.thumb_url || "");
}

function buildDownloadFilename(imageId: number, imageUrl: string): string {
  const cleanPath = imageUrl.split("?")[0] || "";
  const suffix = cleanPath.includes(".") ? cleanPath.slice(cleanPath.lastIndexOf(".")) : ".png";
  return `banana_${imageId}${suffix || ".png"}`;
}

export function getDownloadUrl(imageId: number, imageUrl?: string, previewUrl?: string): string {
  if (imageUrl && /^https?:\/\//.test(imageUrl)) {
    return imageUrl;
  }
  if (!imageUrl && previewUrl) {
    return resolveImageUrl(previewUrl);
  }
  const base = import.meta.env.VITE_API_BASE_URL || "";
  return `${base}/api/images/${imageId}/download`;
}
