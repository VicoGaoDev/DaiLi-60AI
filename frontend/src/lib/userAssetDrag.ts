import type { UserAsset } from "@/types";

export const USER_ASSET_DRAG_MIME = "application/x-banana-user-asset";

export function encodeDraggedUserAsset(asset: UserAsset) {
  return JSON.stringify(asset);
}

export function decodeDraggedUserAsset(raw: string | null | undefined): UserAsset | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || typeof parsed.id !== "number") {
      return null;
    }
    return parsed as UserAsset;
  } catch {
    return null;
  }
}
