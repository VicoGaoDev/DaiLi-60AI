export const VIDEO_GENERATE_DRAFT_KEY = "videoGenerateDraft";

export interface VideoGenerateDraftPayload {
  mode: "textGenerate" | "imageToVideo" | "firstLastFrame";
  prompt?: string;
  reference_images: string[];
  model?: string;
  aspect_ratio?: string;
  duration_seconds?: number;
  resolution?: string;
}

export function saveVideoGenerateDraft(payload: {
  mode?: "textGenerate" | "imageToVideo" | "firstLastFrame";
  prompt?: string;
  reference_images?: string[];
  model?: string;
  aspect_ratio?: string;
  duration_seconds?: number | null;
  resolution?: string;
}) {
  const referenceImages = Array.isArray(payload.reference_images)
    ? payload.reference_images.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const explicitMode = payload.mode === "textGenerate" || payload.mode === "firstLastFrame" ? payload.mode : "imageToVideo";
  const mode = explicitMode === "firstLastFrame" && referenceImages.length >= 2
    ? "firstLastFrame"
    : (referenceImages.length ? "imageToVideo" : explicitMode);
  const durationSeconds = Number(payload.duration_seconds || 0);
  const draft: VideoGenerateDraftPayload = {
    mode,
    prompt: String(payload.prompt || "").trim(),
    reference_images: mode === "firstLastFrame"
      ? referenceImages.slice(0, 2)
      : (mode === "imageToVideo" ? referenceImages.slice(0, 1) : []),
    model: String(payload.model || "").trim(),
    aspect_ratio: String(payload.aspect_ratio || "").trim(),
    duration_seconds: Number.isFinite(durationSeconds) && durationSeconds > 0 ? durationSeconds : undefined,
    resolution: String(payload.resolution || "").trim(),
  };
  localStorage.setItem(VIDEO_GENERATE_DRAFT_KEY, JSON.stringify(draft));
  return true;
}

export function saveImageToVideoDraft(payload: {
  referenceImage: string;
  prompt?: string;
}) {
  const referenceImage = String(payload.referenceImage || "").trim();
  if (!referenceImage) return false;
  return saveVideoGenerateDraft({
    mode: "imageToVideo",
    prompt: payload.prompt,
    reference_images: [referenceImage],
  });
}

export function consumeVideoGenerateDraft(): VideoGenerateDraftPayload | null {
  const raw = localStorage.getItem(VIDEO_GENERATE_DRAFT_KEY);
  if (!raw) return null;
  try {
    const draft = JSON.parse(raw) as VideoGenerateDraftPayload;
    const referenceImages = Array.isArray(draft.reference_images)
      ? draft.reference_images.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    const mode = draft.mode === "textGenerate" || draft.mode === "firstLastFrame" ? draft.mode : "imageToVideo";
    if ((mode === "imageToVideo" && !referenceImages.length) || (mode === "firstLastFrame" && referenceImages.length < 2)) {
      localStorage.removeItem(VIDEO_GENERATE_DRAFT_KEY);
      return null;
    }
    const durationSeconds = Number(draft.duration_seconds || 0);
    localStorage.removeItem(VIDEO_GENERATE_DRAFT_KEY);
    return {
      mode,
      prompt: String(draft.prompt || "").trim(),
      reference_images: mode === "firstLastFrame"
        ? referenceImages.slice(0, 2)
        : (mode === "imageToVideo" ? referenceImages.slice(0, 1) : []),
      model: String(draft.model || "").trim(),
      aspect_ratio: String(draft.aspect_ratio || "").trim(),
      duration_seconds: Number.isFinite(durationSeconds) && durationSeconds > 0 ? durationSeconds : undefined,
      resolution: String(draft.resolution || "").trim(),
    };
  } catch {
    localStorage.removeItem(VIDEO_GENERATE_DRAFT_KEY);
    return null;
  }
}
