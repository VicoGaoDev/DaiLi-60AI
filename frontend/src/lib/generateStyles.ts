import generateStylesData from "@/config/generate-styles.json";
import {
  composeCameraPromptParts,
  parseCameraPrompt,
  type GenerateCameraSelection,
} from "@/lib/generateCameras";

export type GenerateStyleCategoryId = "color" | "lighting";
export type GenerateStylePreviewPattern = "soft" | "rim" | "top" | "bottom" | "silhouette" | "hard" | "blinds";

export interface GenerateStylePreview {
  from: string;
  to: string;
  via?: string;
  pattern?: GenerateStylePreviewPattern;
}

export interface GenerateStyleItem {
  id: string;
  name: string;
  prompt: string;
  thumbnail?: string;
  preview: GenerateStylePreview;
}

export interface GenerateStyleCategory {
  id: GenerateStyleCategoryId;
  name: string;
  items: GenerateStyleItem[];
}

interface GenerateStylesCatalog {
  version: number;
  categories: GenerateStyleCategory[];
}

const catalog = generateStylesData as GenerateStylesCatalog;

export const generateStyleCategories: GenerateStyleCategory[] = catalog.categories || [];

const styleMap = new Map<string, GenerateStyleItem>();
for (const category of generateStyleCategories) {
  for (const item of category.items) {
    styleMap.set(item.id, item);
  }
}

export function getGenerateStyleCategory(categoryId: GenerateStyleCategoryId): GenerateStyleCategory | undefined {
  return generateStyleCategories.find((item) => item.id === categoryId);
}

export function getGenerateStyleById(styleId?: string | null): GenerateStyleItem | undefined {
  const normalized = (styleId || "").trim();
  if (!normalized) return undefined;
  return styleMap.get(normalized);
}

export function composeGeneratePrompt(
  userPrompt: string,
  colorStyleId?: string | null,
  lightingStyleId?: string | null,
  camera?: GenerateCameraSelection | null,
): string {
  const parts = [(userPrompt || "").trim()].filter(Boolean);
  const colorStyle = getGenerateStyleById(colorStyleId);
  const lightingStyle = getGenerateStyleById(lightingStyleId);
  if (colorStyle?.prompt) parts.push(colorStyle.prompt.trim());
  if (lightingStyle?.prompt) parts.push(lightingStyle.prompt.trim());
  parts.push(...composeCameraPromptParts(camera));
  return parts.join("\n\n");
}

export interface ParsedGeneratePrompt {
  userPrompt: string;
  colorStyleId: string;
  lightingStyleId: string;
  camera: GenerateCameraSelection;
}

function stripMatchedStylePrompt(source: string, stylePrompt: string): string | null {
  const needle = stylePrompt.trim();
  if (!needle) return null;
  const index = source.indexOf(needle);
  if (index < 0) return null;
  const next = `${source.slice(0, index)}\n\n${source.slice(index + needle.length)}`;
  return next.replace(/\n{3,}/g, "\n\n").trim();
}

function pickMatchedStyleId(source: string, categoryId: GenerateStyleCategoryId): { styleId: string; remaining: string } {
  const items = [...(getGenerateStyleCategory(categoryId)?.items || [])]
    .filter((item) => item.prompt?.trim())
    .sort((left, right) => right.prompt.trim().length - left.prompt.trim().length);
  for (const item of items) {
    const remaining = stripMatchedStylePrompt(source, item.prompt);
    if (remaining === null) continue;
    return { styleId: item.id, remaining };
  }
  return { styleId: "", remaining: source };
}

export function parseGeneratePrompt(fullPrompt: string): ParsedGeneratePrompt {
  let remaining = (fullPrompt || "").trim();
  const colorMatch = pickMatchedStyleId(remaining, "color");
  remaining = colorMatch.remaining;
  const lightingMatch = pickMatchedStyleId(remaining, "lighting");
  remaining = lightingMatch.remaining;
  const cameraMatch = parseCameraPrompt(remaining);
  return {
    userPrompt: cameraMatch.userPrompt,
    colorStyleId: colorMatch.styleId,
    lightingStyleId: lightingMatch.styleId,
    camera: cameraMatch.selection,
  };
}

export function formatSelectedGenerateStyleLabel(
  colorStyleId?: string | null,
  lightingStyleId?: string | null,
): string {
  const names = [
    getGenerateStyleById(colorStyleId)?.name,
    getGenerateStyleById(lightingStyleId)?.name,
  ].filter(Boolean);
  return names.join(" · ");
}
