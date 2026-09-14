const STORAGE_KEY = "banana.sketch-board.draft";
const DRAFT_VERSION = 1;

export interface SketchBoardDraft {
  version: number;
  ratioPreset: string;
  customWidth: number;
  customHeight: number;
  color: string;
  brushSize: number;
  objects: unknown[];
  updatedAt: number;
}

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function loadSketchBoardDraft(): SketchBoardDraft | null {
  if (!canUseStorage()) return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SketchBoardDraft;
    if (!parsed || parsed.version !== DRAFT_VERSION || !Array.isArray(parsed.objects)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveSketchBoardDraft(draft: Omit<SketchBoardDraft, "version" | "updatedAt">) {
  if (!canUseStorage()) return;
  const payload: SketchBoardDraft = {
    ...draft,
    version: DRAFT_VERSION,
    updatedAt: Date.now(),
  };
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
        ...payload,
        objects: payload.objects.filter((item) => {
          return !item || typeof item !== "object" || (item as { type?: string }).type !== "image";
        }),
      }));
    } catch {
      // Quota exceeded; keep the last successful draft.
    }
  }
}

export function clearSketchBoardDraft() {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(STORAGE_KEY);
}
