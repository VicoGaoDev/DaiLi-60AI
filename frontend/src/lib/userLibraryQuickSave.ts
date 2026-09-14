function getExtensionFromMimeType(mimeType: string) {
  switch ((mimeType || "").toLowerCase()) {
    case "image/jpeg":
      return ".jpg";
    case "image/webp":
      return ".webp";
    case "image/gif":
      return ".gif";
    default:
      return ".png";
  }
}

function normalizeFileName(fileName: string | undefined, mimeType: string, fallbackPrefix: string) {
  const normalized = (fileName || "").trim();
  if (normalized) {
    return /\.[a-z0-9]+$/i.test(normalized) ? normalized : `${normalized}${getExtensionFromMimeType(mimeType)}`;
  }
  return `${fallbackPrefix}-${Date.now()}${getExtensionFromMimeType(mimeType)}`;
}

export async function imageUrlToFile(
  imageUrl: string,
  options?: {
    fileName?: string;
    fallbackPrefix?: string;
  },
) {
  const response = await fetch(imageUrl);
  if (!response.ok) {
    throw new Error("读取图片失败");
  }
  const blob = await response.blob();
  const mimeType = blob.type || "image/png";
  const fileName = normalizeFileName(options?.fileName, mimeType, options?.fallbackPrefix || "reference-image");
  return new File([blob], fileName, { type: mimeType });
}

export function buildQuickSavePromptTitle(content: string, maxLength = 24) {
  const normalized = (content || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "我的提示词";
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, Math.max(1, maxLength - 3)).trim()}...`;
}
