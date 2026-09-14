import { withApiBaseUrl } from "@/lib/assets";

export function triggerDirectDownload(url?: string, filename?: string): boolean {
  const resolvedUrl = withApiBaseUrl(url || "");
  if (!resolvedUrl) return false;

  const anchor = document.createElement("a");
  anchor.href = resolvedUrl;
  if (filename) {
    anchor.download = filename;
  }
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  return true;
}
