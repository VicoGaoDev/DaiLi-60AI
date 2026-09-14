import generateCamerasData from "@/config/generate-cameras.json";

export type GenerateCameraCategoryId = "body" | "lens" | "focal" | "aperture";

export interface GenerateCameraItem {
  id: string;
  name: string;
  prompt: string;
  thumbnail?: string;
}

export interface GenerateCameraCategory {
  id: GenerateCameraCategoryId;
  name: string;
  items: GenerateCameraItem[];
}

export interface GenerateCameraSelection {
  bodyId: string;
  lensId: string;
  focalId: string;
  apertureId: string;
}

export interface GenerateCameraPreset {
  id: string;
  name: string;
  group?: string;
  thumbnail?: string;
  bodyId: string;
  lensId: string;
  focalId: string;
  apertureId: string;
}

export interface GenerateCameraPresetGroup {
  name: string;
  presets: GenerateCameraPreset[];
}

export const DEFAULT_CAMERA_PRESET_GROUP = "常用预设";

interface GenerateCamerasCatalog {
  version: number;
  categories: GenerateCameraCategory[];
  presets?: GenerateCameraPreset[];
}

const catalog = generateCamerasData as GenerateCamerasCatalog;

export const generateCameraCategories: GenerateCameraCategory[] = catalog.categories || [];

const cameraMap = new Map<string, GenerateCameraItem>();
for (const category of generateCameraCategories) {
  for (const item of category.items) {
    cameraMap.set(item.id, item);
  }
}

function isCompleteCameraPreset(preset: GenerateCameraPreset): boolean {
  return Boolean(
    preset.id
    && preset.name
    && cameraMap.get(preset.bodyId)
    && cameraMap.get(preset.lensId)
    && cameraMap.get(preset.focalId)
    && cameraMap.get(preset.apertureId),
  );
}

export const generateCameraPresets: GenerateCameraPreset[] = (catalog.presets || []).filter(isCompleteCameraPreset);

export const generateCameraPresetGroups: GenerateCameraPresetGroup[] = (() => {
  const groups: GenerateCameraPresetGroup[] = [];
  const index = new Map<string, GenerateCameraPresetGroup>();
  for (const preset of generateCameraPresets) {
    const name = preset.group?.trim() || DEFAULT_CAMERA_PRESET_GROUP;
    let group = index.get(name);
    if (!group) {
      group = { name, presets: [] };
      index.set(name, group);
      groups.push(group);
    }
    group.presets.push(preset);
  }
  return groups;
})();

export const emptyGenerateCameraSelection: GenerateCameraSelection = {
  bodyId: "",
  lensId: "",
  focalId: "",
  apertureId: "",
};

export function getGenerateCameraCategory(categoryId: GenerateCameraCategoryId): GenerateCameraCategory | undefined {
  return generateCameraCategories.find((item) => item.id === categoryId);
}

export function getGenerateCameraById(cameraId?: string | null): GenerateCameraItem | undefined {
  const normalized = (cameraId || "").trim();
  if (!normalized) return undefined;
  return cameraMap.get(normalized);
}

export function hasSelectedGenerateCamera(selection?: GenerateCameraSelection | null): boolean {
  return Boolean(selection?.bodyId || selection?.lensId || selection?.focalId || selection?.apertureId);
}

export function getGenerateCameraSelectionIds(selection?: GenerateCameraSelection | null): string[] {
  if (!selection) return [];
  return [selection.bodyId, selection.lensId, selection.focalId, selection.apertureId].filter(Boolean);
}

export function composeCameraPromptParts(selection?: GenerateCameraSelection | null): string[] {
  if (!selection) return [];
  return [
    getGenerateCameraById(selection.bodyId)?.prompt,
    getGenerateCameraById(selection.lensId)?.prompt,
    getGenerateCameraById(selection.focalId)?.prompt,
    getGenerateCameraById(selection.apertureId)?.prompt,
  ]
    .map((item) => (item || "").trim())
    .filter(Boolean);
}

function stripMatchedPrompt(source: string, stylePrompt: string): string | null {
  const needle = stylePrompt.trim();
  if (!needle) return null;
  const index = source.indexOf(needle);
  if (index < 0) return null;
  const next = `${source.slice(0, index)}\n\n${source.slice(index + needle.length)}`;
  return next.replace(/\n{3,}/g, "\n\n").trim();
}

function pickMatchedCameraId(source: string, categoryId: GenerateCameraCategoryId): { cameraId: string; remaining: string } {
  const items = [...(getGenerateCameraCategory(categoryId)?.items || [])]
    .filter((item) => item.prompt?.trim())
    .sort((left, right) => right.prompt.trim().length - left.prompt.trim().length);
  for (const item of items) {
    const remaining = stripMatchedPrompt(source, item.prompt);
    if (remaining === null) continue;
    return { cameraId: item.id, remaining };
  }
  return { cameraId: "", remaining: source };
}

export function parseCameraPrompt(fullPrompt: string): { userPrompt: string; selection: GenerateCameraSelection } {
  let remaining = (fullPrompt || "").trim();
  const bodyMatch = pickMatchedCameraId(remaining, "body");
  remaining = bodyMatch.remaining;
  const lensMatch = pickMatchedCameraId(remaining, "lens");
  remaining = lensMatch.remaining;
  const focalMatch = pickMatchedCameraId(remaining, "focal");
  remaining = focalMatch.remaining;
  const apertureMatch = pickMatchedCameraId(remaining, "aperture");
  remaining = apertureMatch.remaining;
  return {
    userPrompt: remaining,
    selection: {
      bodyId: bodyMatch.cameraId,
      lensId: lensMatch.cameraId,
      focalId: focalMatch.cameraId,
      apertureId: apertureMatch.cameraId,
    },
  };
}

export function parseApertureFStop(name?: string | null): number | null {
  const matched = (name || "").match(/([\d.]+)/);
  if (!matched) return null;
  const value = Number(matched[1]);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function apertureOpeningRadius(name?: string | null, maxRadius = 22): number {
  const fStop = parseApertureFStop(name) ?? 2.8;
  const t = Math.min(1, Math.max(0, (fStop - 1.2) / (16 - 1.2)));
  return maxRadius * (1 - t * 0.82);
}

export function formatSelectedGenerateCameraLabel(selection?: GenerateCameraSelection | null): string {
  if (!selection) return "";
  return [
    getGenerateCameraById(selection.bodyId)?.name,
    getGenerateCameraById(selection.lensId)?.name,
    getGenerateCameraById(selection.focalId)?.name,
    getGenerateCameraById(selection.apertureId)?.name,
  ].filter(Boolean).join(" · ");
}

export function selectionFromCameraPreset(preset: GenerateCameraPreset): GenerateCameraSelection {
  return {
    bodyId: preset.bodyId,
    lensId: preset.lensId,
    focalId: preset.focalId,
    apertureId: preset.apertureId,
  };
}

export function isSameGenerateCameraSelection(
  left?: GenerateCameraSelection | null,
  right?: GenerateCameraSelection | null,
): boolean {
  return Boolean(
    left
    && right
    && left.bodyId === right.bodyId
    && left.lensId === right.lensId
    && left.focalId === right.focalId
    && left.apertureId === right.apertureId,
  );
}

export function matchGenerateCameraPreset(
  selection?: GenerateCameraSelection | null,
): GenerateCameraPreset | undefined {
  if (!hasSelectedGenerateCamera(selection)) return undefined;
  return generateCameraPresets.find((preset) => (
    isSameGenerateCameraSelection(selectionFromCameraPreset(preset), selection)
  ));
}

export function formatGenerateCameraPresetMeta(preset: GenerateCameraPreset): string {
  return [
    getGenerateCameraById(preset.focalId)?.name,
    getGenerateCameraById(preset.apertureId)?.name,
  ].filter(Boolean).join(" · ");
}
