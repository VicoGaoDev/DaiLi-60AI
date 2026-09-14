<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { message } from "ant-design-vue";
import {
  AppstoreOutlined,
  ClearOutlined,
  CloseOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  FontSizeOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  RedoOutlined,
  UndoOutlined,
} from "@ant-design/icons-vue";
import { isSupportedImageUploadFile } from "@/api/upload";
import { uploadUserAssetFile } from "@/api/userAssets";
import { clearSketchBoardDraft, loadSketchBoardDraft, saveSketchBoardDraft } from "@/lib/sketchBoardDraft";

type SketchTool = "pen" | "erase" | "rect" | "circle" | "arrow" | "text" | "image";
type RatioPreset = "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "custom";

interface Point {
  x: number;
  y: number;
}

interface StrokeObject {
  type: "stroke";
  color: string;
  size: number;
  points: Point[];
  erase?: boolean;
}

interface ShapeObject {
  type: "rect" | "circle" | "arrow";
  color: string;
  size: number;
  from: Point;
  to: Point;
}

interface TextObject {
  type: "text";
  color: string;
  size: number;
  text: string;
  x: number;
  y: number;
}

interface ImageObject {
  type: "image";
  src: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

type SketchObject = StrokeObject | ShapeObject | TextObject | ImageObject;

const RATIO_PRESETS: Array<{ value: RatioPreset; label: string; ratio: number }> = [
  { value: "16:9", label: "16:9", ratio: 16 / 9 },
  { value: "4:3", label: "4:3", ratio: 4 / 3 },
  { value: "1:1", label: "1:1", ratio: 1 },
  { value: "3:4", label: "3:4", ratio: 3 / 4 },
  { value: "9:16", label: "9:16", ratio: 9 / 16 },
];

const COLOR_PRESETS = [
  "#111111",
  "#ffffff",
  "#ef4444",
  "#f97316",
  "#eab308",
  "#22c55e",
  "#22d3ee",
  "#3b82f6",
  "#8b5cf6",
  "#ec4899",
];

const EXPORT_LONG_SIDE = 2048;
const CUSTOM_SIZE_MIN = 256;
const CUSTOM_SIZE_MAX = 4096;
const DEFAULT_CUSTOM_WIDTH = 1024;
const DEFAULT_CUSTOM_HEIGHT = 768;

const props = defineProps<{
  open: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [file: File];
}>();

const rootRef = ref<HTMLElement | null>(null);
const boardRef = ref<HTMLElement | null>(null);
const isFullscreen = ref(false);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const imageInputRef = ref<HTMLInputElement | null>(null);
const textInputRef = ref<HTMLInputElement | null>(null);

const MOBILE_QUERY = "(max-width: 768px)";

function readIsMobile() {
  return typeof window !== "undefined" && window.matchMedia(MOBILE_QUERY).matches;
}

const isMobile = ref(readIsMobile());
const mobileToolsOpen = ref(false);
const ratioPreset = ref<RatioPreset>(readIsMobile() ? "9:16" : "16:9");
const customWidth = ref(DEFAULT_CUSTOM_WIDTH);
const customHeight = ref(DEFAULT_CUSTOM_HEIGHT);
const ratioMenuOpen = ref(false);
const customPanelOpen = ref(false);
const customWidthDraft = ref(String(DEFAULT_CUSTOM_WIDTH));
const customHeightDraft = ref(String(DEFAULT_CUSTOM_HEIGHT));

const tool = ref<SketchTool>("pen");
const color = ref("#111111");
const brushSize = ref(3);

const objects = ref<SketchObject[]>([]);
const history = ref<SketchObject[][]>([]);
const future = ref<SketchObject[][]>([]);

const draftStroke = ref<StrokeObject | null>(null);
const draftShape = ref<ShapeObject | null>(null);
const drawing = ref(false);

const textEditorVisible = ref(false);
const textEditorValue = ref("");
const pendingTextPoint = ref<Point | null>(null);
const closeConfirmOpen = ref(false);
const clearConfirmOpen = ref(false);

const ignoreTextBlur = ref(false);
const exporting = ref(false);
const savingAsset = ref(false);
const displaySize = ref({ w: 0, h: 0 });

const imageCache = new Map<string, HTMLImageElement>();
let resizeObserver: ResizeObserver | null = null;
let mobileQuery: MediaQueryList | null = null;
let restoringDraft = true;
let persistTimer: number | null = null;

const aspectRatio = computed(() => {
  if (ratioPreset.value === "custom") {
    return clampCustomSize(customWidth.value) / clampCustomSize(customHeight.value);
  }
  return RATIO_PRESETS.find((item) => item.value === ratioPreset.value)?.ratio || 16 / 9;
});

const ratioLabel = computed(() => {
  if (ratioPreset.value === "custom") return "自定义";
  return ratioPreset.value;
});

const exportFileLabel = computed(() => {
  if (ratioPreset.value === "custom") return "custom";
  return ratioPreset.value.replace(":", "-");
});

const canUndo = computed(() => history.value.length > 0);
const canRedo = computed(() => future.value.length > 0);
const hasContent = computed(() => objects.value.length > 0);
const canvasCursor = computed(() => (tool.value === "text" ? "text" : "crosshair"));
const immersiveLabel = computed(() => (isFullscreen.value ? "退出沉浸" : "沉浸模式"));

function textFontSizePx(size = brushSize.value) {
  return Math.max(14, size * 4.2);
}

function measureInlineTextWidth(text: string, fontSize: number) {
  const sample = text || "字";
  const ctx = canvasRef.value?.getContext("2d");
  if (!ctx) return Math.ceil((sample.length + 1) * fontSize);
  ctx.save();
  ctx.font = `600 ${fontSize}px "PingFang SC", "Microsoft YaHei", sans-serif`;
  const width = ctx.measureText(sample).width;
  ctx.restore();
  return Math.ceil(width + fontSize);
}

const inlineTextStyle = computed(() => {
  const point = pendingTextPoint.value;
  if (!point) return {};
  const fontSize = textFontSizePx();
  return {
    left: `${point.x * displaySize.value.w}px`,
    top: `${point.y * displaySize.value.h}px`,
    color: color.value,
    fontSize: `${fontSize}px`,
    width: `${measureInlineTextWidth(textEditorValue.value, fontSize)}px`,
  };
});

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function clampCustomSize(value: number) {
  return clamp(Math.round(value) || CUSTOM_SIZE_MIN, CUSTOM_SIZE_MIN, CUSTOM_SIZE_MAX);
}

function cloneObjects(list: SketchObject[]): SketchObject[] {
  return JSON.parse(JSON.stringify(list)) as SketchObject[];
}

function normalizeShape(shape: ShapeObject): ShapeObject {
  if (shape.type === "arrow") return shape;
  const minSize = 0.08;
  const width = Math.abs(shape.to.x - shape.from.x);
  const height = Math.abs(shape.to.y - shape.from.y);
  if (width >= 0.01 && height >= 0.01) return shape;
  const size = Math.max(minSize, width, height, 0.08);
  return {
    ...shape,
    from: {
      x: clamp(shape.from.x - size / 2, 0, 1),
      y: clamp(shape.from.y - size / 2, 0, 1),
    },
    to: {
      x: clamp(shape.from.x + size / 2, 0, 1),
      y: clamp(shape.from.y + size / 2, 0, 1),
    },
  };
}

function persistDraft() {
  if (restoringDraft) return;
  if (!objects.value.length) {
    clearSketchBoardDraft();
    return;
  }
  saveSketchBoardDraft({
    ratioPreset: ratioPreset.value,
    customWidth: customWidth.value,
    customHeight: customHeight.value,
    color: color.value,
    brushSize: brushSize.value,
    objects: cloneObjects(objects.value),
  });
}

function schedulePersistDraft() {
  if (restoringDraft) return;
  if (persistTimer !== null) window.clearTimeout(persistTimer);
  persistTimer = window.setTimeout(() => {
    persistTimer = null;
    persistDraft();
  }, 200);
}

function restoreDraft() {
  const draft = loadSketchBoardDraft();
  if (!draft?.objects.length) return;
  const validRatio = RATIO_PRESETS.some((item) => item.value === draft.ratioPreset) || draft.ratioPreset === "custom";
  if (validRatio) ratioPreset.value = draft.ratioPreset as RatioPreset;
  if (Number.isFinite(draft.customWidth)) customWidth.value = clampCustomSize(draft.customWidth);
  if (Number.isFinite(draft.customHeight)) customHeight.value = clampCustomSize(draft.customHeight);
  customWidthDraft.value = String(customWidth.value);
  customHeightDraft.value = String(customHeight.value);
  if (typeof draft.color === "string" && draft.color) color.value = draft.color;
  if (Number.isFinite(draft.brushSize)) brushSize.value = clamp(draft.brushSize, 2, 36);
  objects.value = cloneObjects(draft.objects as SketchObject[]);
}

function requestClearBoard() {
  if (textEditorVisible.value) closeInlineText();
  if (!hasContent.value || clearConfirmOpen.value) return;
  closeFloatingPanels();
  clearConfirmOpen.value = true;
}

function confirmClearBoard() {
  clearConfirmOpen.value = false;
  if (!hasContent.value) return;
  commitObjects([]);
  history.value = [];
  future.value = [];
  clearSketchBoardDraft();
  redraw();
}

function commitObjects(next: SketchObject[]) {
  history.value.push(cloneObjects(objects.value));
  future.value = [];
  objects.value = next;
}

function undo() {
  const prev = history.value.pop();
  if (!prev) return;
  future.value.push(cloneObjects(objects.value));
  objects.value = prev;
  redraw();
}

function redo() {
  const next = future.value.pop();
  if (!next) return;
  history.value.push(cloneObjects(objects.value));
  objects.value = next;
  redraw();
}

function loadImage(src: string): Promise<HTMLImageElement | null> {
  const cached = imageCache.get(src);
  if (cached) return Promise.resolve(cached);
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      imageCache.set(src, image);
      resolve(image);
    };
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

function getCanvasPoint(event: PointerEvent): Point | null {
  const canvas = canvasRef.value;
  if (!canvas) return null;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  return {
    x: clamp((event.clientX - rect.left) / rect.width, 0, 1),
    y: clamp((event.clientY - rect.top) / rect.height, 0, 1),
  };
}

function strokeWidth(size: number, width: number, height: number) {
  return Math.max(1, size * Math.min(width, height));
}

function drawStroke(
  ctx: CanvasRenderingContext2D,
  item: StrokeObject,
  width: number,
  height: number,
) {
  if (!item.points.length) return;
  ctx.save();
  if (item.erase) {
    ctx.globalCompositeOperation = "destination-out";
  }
  ctx.strokeStyle = item.erase ? "#000000" : item.color;
  ctx.fillStyle = item.erase ? "#000000" : item.color;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = strokeWidth(item.size, width, height);
  if (item.points.length === 1) {
    const point = item.points[0];
    ctx.beginPath();
    ctx.arc(point.x * width, point.y * height, ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    return;
  }
  ctx.beginPath();
  ctx.moveTo(item.points[0].x * width, item.points[0].y * height);
  for (let index = 1; index < item.points.length; index += 1) {
    ctx.lineTo(item.points[index].x * width, item.points[index].y * height);
  }
  ctx.stroke();
  ctx.restore();
}

function drawShape(
  ctx: CanvasRenderingContext2D,
  item: ShapeObject,
  width: number,
  height: number,
) {
  const fromX = item.from.x * width;
  const fromY = item.from.y * height;
  const toX = item.to.x * width;
  const toY = item.to.y * height;
  const left = Math.min(fromX, toX);
  const top = Math.min(fromY, toY);
  const shapeWidth = Math.max(1, Math.abs(toX - fromX));
  const shapeHeight = Math.max(1, Math.abs(toY - fromY));
  ctx.save();
  ctx.strokeStyle = item.color;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = strokeWidth(item.size, width, height);
  ctx.beginPath();
  if (item.type === "arrow") {
    const angle = Math.atan2(toY - fromY, toX - fromX);
    const length = Math.hypot(toX - fromX, toY - fromY);
    const headLen = Math.min(Math.max(ctx.lineWidth * 6, 20), Math.max(8, length * 0.42));
    const headHalf = headLen * 0.34;
    const shaftEndX = toX - Math.cos(angle) * headLen * 0.78;
    const shaftEndY = toY - Math.sin(angle) * headLen * 0.78;
    ctx.lineCap = "butt";
    ctx.lineJoin = "miter";
    ctx.beginPath();
    ctx.moveTo(fromX, fromY);
    ctx.lineTo(shaftEndX, shaftEndY);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(toX, toY);
    ctx.lineTo(
      toX - headLen * Math.cos(angle) + headHalf * Math.sin(angle),
      toY - headLen * Math.sin(angle) - headHalf * Math.cos(angle),
    );
    ctx.lineTo(
      toX - headLen * Math.cos(angle) - headHalf * Math.sin(angle),
      toY - headLen * Math.sin(angle) + headHalf * Math.cos(angle),
    );
    ctx.closePath();
    ctx.fillStyle = item.color;
    ctx.fill();
    ctx.restore();
    return;
  }
  if (item.type === "rect") {
    ctx.rect(left, top, shapeWidth, shapeHeight);
  } else {
    ctx.ellipse(
      left + shapeWidth / 2,
      top + shapeHeight / 2,
      Math.max(1, shapeWidth / 2),
      Math.max(1, shapeHeight / 2),
      0,
      0,
      Math.PI * 2,
    );
  }
  ctx.stroke();
  ctx.restore();
}

function drawText(
  ctx: CanvasRenderingContext2D,
  item: TextObject,
  width: number,
  height: number,
) {
  const fontSize = Math.max(14, item.size * Math.min(width, height) * 4.2);
  ctx.save();
  ctx.fillStyle = item.color;
  ctx.font = `600 ${fontSize}px "PingFang SC", "Microsoft YaHei", sans-serif`;
  ctx.textBaseline = "alphabetic";
  ctx.fillText(item.text, item.x * width, item.y * height);
  ctx.restore();
}

function drawImageObject(
  ctx: CanvasRenderingContext2D,
  item: ImageObject,
  width: number,
  height: number,
  image: HTMLImageElement,
) {
  ctx.drawImage(image, item.x * width, item.y * height, item.w * width, item.h * height);
}

function renderScene(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  extras: SketchObject[] = [],
) {
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.restore();

  const scene = [...objects.value, ...extras];
  for (const item of scene) {
    if (item.type === "stroke") {
      drawStroke(ctx, item, width, height);
      continue;
    }
    if (item.type === "rect" || item.type === "circle" || item.type === "arrow") {
      drawShape(ctx, item, width, height);
      continue;
    }
    if (item.type === "text") {
      drawText(ctx, item, width, height);
      continue;
    }
    if (item.type !== "image") continue;
    const image = imageCache.get(item.src);
    if (image) {
      drawImageObject(ctx, item, width, height, image);
    }
  }
}

function collectMissingImages() {
  return objects.value
    .filter((item): item is ImageObject => item.type === "image" && !imageCache.has(item.src))
    .map((item) => item.src);
}

async function ensureImagesLoaded() {
  const missing = collectMissingImages();
  if (!missing.length) return;
  await Promise.all(missing.map((src) => loadImage(src)));
}

function redraw() {
  const canvas = canvasRef.value;
  if (!canvas || !displaySize.value.w || !displaySize.value.h) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const extras: SketchObject[] = [];
  if (draftStroke.value) extras.push(draftStroke.value);
  if (draftShape.value) extras.push(draftShape.value);
  renderScene(ctx, displaySize.value.w, displaySize.value.h, extras);
}

function layoutCanvas() {
  const stage = boardRef.value;
  const canvas = canvasRef.value;
  if (!stage || !canvas) return;
  const rect = stage.getBoundingClientRect();
  const availW = Math.max(1, Math.round(rect.width) || window.innerWidth);
  const availH = Math.max(1, Math.round(rect.height) || Math.max(240, window.innerHeight - 56));
  let width = availW;
  let height = width / aspectRatio.value;
  if (height > availH) {
    height = availH;
    width = height * aspectRatio.value;
  }
  width = Math.max(1, Math.round(width));
  height = Math.max(1, Math.round(height));
  const dpr = window.devicePixelRatio || 1;
  const nextWidth = Math.max(1, Math.round(width * dpr));
  const nextHeight = Math.max(1, Math.round(height * dpr));
  const sameSize =
    displaySize.value.w === width
    && displaySize.value.h === height
    && canvas.width === nextWidth
    && canvas.height === nextHeight;
  displaySize.value = { w: width, h: height };
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  if (!sameSize) {
    canvas.width = nextWidth;
    canvas.height = nextHeight;
  }
  redraw();
}

function scheduleLayout() {
  nextTick(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => layoutCanvas());
    });
  });
}

async function handlePointerDown(event: PointerEvent) {
  if (exporting.value) return;
  if (event.button !== undefined && event.button !== 0) return;
  closeFloatingPanels();
  const point = getCanvasPoint(event);
  if (!point) return;

  if (textEditorVisible.value) {
    confirmInlineText();
    if (tool.value === "text") {
      event.preventDefault();
      openInlineText(point);
    }
    return;
  }

  if (tool.value === "text") {
    event.preventDefault();
    openInlineText(point);
    return;
  }
  canvasRef.value?.setPointerCapture(event.pointerId);
  if (tool.value === "image") {
    imageInputRef.value?.click();
    return;
  }

  drawing.value = true;
  const size = brushSize.value / Math.min(displaySize.value.w || 1, displaySize.value.h || 1);
  if (tool.value === "pen" || tool.value === "erase") {
    draftStroke.value = {
      type: "stroke",
      color: color.value,
      size,
      points: [point],
      erase: tool.value === "erase",
    };
  } else if (tool.value === "rect" || tool.value === "circle" || tool.value === "arrow") {
    draftShape.value = {
      type: tool.value,
      color: color.value,
      size,
      from: point,
      to: point,
    };
  }
  redraw();
}

function handlePointerMove(event: PointerEvent) {
  if (!drawing.value) return;
  const point = getCanvasPoint(event);
  if (!point) return;
  if (draftStroke.value) {
    const last = draftStroke.value.points[draftStroke.value.points.length - 1];
    if (!last || Math.hypot(point.x - last.x, point.y - last.y) > 0.001) {
      draftStroke.value.points.push(point);
    }
  } else if (draftShape.value) {
    draftShape.value.to = point;
  }
  redraw();
}

function finishDrawing(event?: PointerEvent) {
  if (event && canvasRef.value?.hasPointerCapture(event.pointerId)) {
    canvasRef.value.releasePointerCapture(event.pointerId);
  }
  if (!drawing.value) return;
  drawing.value = false;
  if (draftStroke.value?.points.length) {
    commitObjects([...objects.value, draftStroke.value]);
  } else if (draftShape.value) {
    if (draftShape.value.type === "arrow") {
      const { from, to } = draftShape.value;
      if (Math.hypot(to.x - from.x, to.y - from.y) >= 0.004) {
        commitObjects([...objects.value, draftShape.value]);
      }
    } else {
      commitObjects([...objects.value, normalizeShape(draftShape.value)]);
    }
  }
  draftStroke.value = null;
  draftShape.value = null;
  redraw();
}

function openInlineText(point: Point) {
  pendingTextPoint.value = point;
  textEditorValue.value = "";
  textEditorVisible.value = true;
  ignoreTextBlur.value = true;
  void nextTick(() => {
    const input = textInputRef.value;
    if (!input) return;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
    window.setTimeout(() => {
      ignoreTextBlur.value = false;
      input.focus();
    }, 320);
  });
}

function handleTextBlur() {
  if (ignoreTextBlur.value) return;
  confirmInlineText();
}

function closeInlineText() {
  textEditorVisible.value = false;
  textEditorValue.value = "";
  pendingTextPoint.value = null;
}

function confirmInlineText() {
  const point = pendingTextPoint.value;
  const text = textEditorValue.value.trim();
  if (!point || !text) {
    closeInlineText();
    return;
  }
  commitObjects([
    ...objects.value,
    {
      type: "text",
      color: color.value,
      size: brushSize.value / Math.min(displaySize.value.w || 1, displaySize.value.h || 1),
      text,
      x: point.x,
      y: point.y,
    },
  ]);
  closeInlineText();
  redraw();
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

async function handleInsertImage(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!isSupportedImageUploadFile(file)) {
    message.warning("仅支持上传图片文件");
    return;
  }
  try {
    const src = await readFileAsDataUrl(file);
    const image = await loadImage(src);
    if (!image) {
      message.error("图片读取失败");
      return;
    }
    const canvasW = displaySize.value.w || 1;
    const canvasH = displaySize.value.h || 1;
    const scale = Math.min((canvasW * 0.86) / image.naturalWidth, (canvasH * 0.86) / image.naturalHeight);
    const drawW = image.naturalWidth * scale;
    const drawH = image.naturalHeight * scale;
    commitObjects([
      ...objects.value,
      {
        type: "image",
        src,
        x: (canvasW - drawW) / 2 / canvasW,
        y: (canvasH - drawH) / 2 / canvasH,
        w: drawW / canvasW,
        h: drawH / canvasH,
      },
    ]);
    tool.value = "pen";
    redraw();
  } catch {
    message.error("图片读取失败");
  }
}

function triggerInsertImage() {
  tool.value = "image";
  imageInputRef.value?.click();
}

function selectTool(next: SketchTool) {
  if (textEditorVisible.value) confirmInlineText();
  tool.value = next;
  if (next === "image") {
    imageInputRef.value?.click();
  }
}

function closeFloatingPanels() {
  ratioMenuOpen.value = false;
  customPanelOpen.value = false;
  mobileToolsOpen.value = false;
}

function getFullscreenElement() {
  const doc = document as Document & { webkitFullscreenElement?: Element | null };
  return doc.fullscreenElement || doc.webkitFullscreenElement || null;
}

function requestElementFullscreen(element: HTMLElement) {
  const request = element.requestFullscreen || (element as HTMLElement & { webkitRequestFullscreen?: () => Promise<void> | void }).webkitRequestFullscreen;
  if (!request) return Promise.reject(new Error("fullscreen unsupported"));
  return Promise.resolve(request.call(element));
}

function exitElementFullscreen() {
  const doc = document as Document & { webkitExitFullscreen?: () => Promise<void> | void };
  const exit = doc.exitFullscreen || doc.webkitExitFullscreen;
  if (!exit) return Promise.reject(new Error("fullscreen unsupported"));
  return Promise.resolve(exit.call(doc));
}

function handleFullscreenChange() {
  isFullscreen.value = Boolean(getFullscreenElement());
  scheduleLayout();
}

async function toggleFullscreen() {
  try {
    if (getFullscreenElement()) {
      await exitElementFullscreen();
      return;
    }
    const target = rootRef.value;
    if (!target) return;
    await requestElementFullscreen(target);
  } catch {
    message.warning("当前浏览器不支持全屏");
  }
}

function toggleMobileTools() {
  mobileToolsOpen.value = !mobileToolsOpen.value;
  if (!mobileToolsOpen.value) {
    ratioMenuOpen.value = false;
    customPanelOpen.value = false;
  }
}

function handleMobileQueryChange(event: MediaQueryListEvent) {
  isMobile.value = event.matches;
  if (!event.matches) {
    mobileToolsOpen.value = false;
    ratioMenuOpen.value = false;
    customPanelOpen.value = false;
  }
  nextTick(() => layoutCanvas());
}

function selectRatio(preset: RatioPreset) {
  if (preset === "custom") {
    customWidthDraft.value = String(customWidth.value);
    customHeightDraft.value = String(customHeight.value);
    customPanelOpen.value = true;
    ratioMenuOpen.value = false;
    return;
  }
  ratioPreset.value = preset;
  customPanelOpen.value = false;
  ratioMenuOpen.value = false;
  void nextTick(() => layoutCanvas());
}

function applyCustomRatio() {
  const width = Number(customWidthDraft.value);
  const height = Number(customHeightDraft.value);
  if (!Number.isFinite(width) || !Number.isFinite(height)) {
    message.warning("请输入有效的宽高");
    return;
  }
  customWidth.value = clampCustomSize(width);
  customHeight.value = clampCustomSize(height);
  customWidthDraft.value = String(customWidth.value);
  customHeightDraft.value = String(customHeight.value);
  ratioPreset.value = "custom";
  customPanelOpen.value = false;
  nextTick(() => layoutCanvas());
}

function exportSize() {
  const ratio = aspectRatio.value;
  if (ratio >= 1) {
    return {
      width: EXPORT_LONG_SIDE,
      height: Math.max(1, Math.round(EXPORT_LONG_SIDE / ratio)),
    };
  }
  return {
    width: Math.max(1, Math.round(EXPORT_LONG_SIDE * ratio)),
    height: EXPORT_LONG_SIDE,
  };
}

function canvasToFile(source: HTMLCanvasElement, name: string) {
  return new Promise<File>((resolve, reject) => {
    source.toBlob((blob) => {
      if (!blob) {
        reject(new Error("export failed"));
        return;
      }
      resolve(new File([blob], name, { type: "image/png" }));
    }, "image/png");
  });
}

async function exportSketchFile() {
  if (!hasContent.value) {
    message.warning("请先绘制");
    return null;
  }
  await ensureImagesLoaded();
  const { width, height } = exportSize();
  const output = document.createElement("canvas");
  output.width = width;
  output.height = height;
  const ctx = output.getContext("2d");
  if (!ctx) throw new Error("export failed");
  renderScene(ctx, width, height);
  return canvasToFile(output, `sketch-${exportFileLabel.value}.png`);
}

async function handleConfirm() {
  if (textEditorVisible.value) confirmInlineText();
  if (exporting.value || savingAsset.value) return;
  exporting.value = true;
  try {
    const file = await exportSketchFile();
    if (!file) return;
    emit("confirm", file);
    emit("update:open", false);
  } catch {
    message.error("导出失败，请重试");
  } finally {
    exporting.value = false;
  }
}

async function handleSaveAsAsset() {
  if (textEditorVisible.value) confirmInlineText();
  if (exporting.value || savingAsset.value) return;
  savingAsset.value = true;
  try {
    const file = await exportSketchFile();
    if (!file) return;
    await uploadUserAssetFile(file);
    message.success("已保存为我的素材");
  } catch (err: any) {
    message.error(err?.response?.data?.detail || err?.message || "加入我的素材失败");
  } finally {
    savingAsset.value = false;
  }
}

function requestClose() {
  if (exporting.value || savingAsset.value) return;
  if (textEditorVisible.value) confirmInlineText();
  if (closeConfirmOpen.value || clearConfirmOpen.value) {
    closeConfirmOpen.value = false;
    clearConfirmOpen.value = false;
    return;
  }
  if (ratioMenuOpen.value || customPanelOpen.value || mobileToolsOpen.value) {
    closeFloatingPanels();
    return;
  }
  if (!hasContent.value) {
    emit("update:open", false);
    return;
  }
  closeConfirmOpen.value = true;
}

function confirmCloseBoard() {
  closeConfirmOpen.value = false;
  emit("update:open", false);
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.open) return;
  if (event.key === "Escape") {
    event.preventDefault();
    if (textEditorVisible.value) {
      closeInlineText();
      return;
    }
    requestClose();
    return;
  }
  if (textEditorVisible.value || closeConfirmOpen.value || clearConfirmOpen.value) return;
  const key = event.key.toLowerCase();
  if ((event.metaKey || event.ctrlKey) && key === "z") {
    event.preventDefault();
    if (event.shiftKey) redo();
    else undo();
  }
}

function bindWindowListeners() {
  window.addEventListener("keydown", handleKeydown);
  window.addEventListener("resize", layoutCanvas);
  window.addEventListener("pointerup", finishDrawing);
  window.addEventListener("pointercancel", finishDrawing);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
  document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
}

function unbindWindowListeners() {
  window.removeEventListener("keydown", handleKeydown);
  window.removeEventListener("resize", layoutCanvas);
  window.removeEventListener("pointerup", finishDrawing);
  window.removeEventListener("pointercancel", finishDrawing);
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
  document.removeEventListener("webkitfullscreenchange", handleFullscreenChange);
}

watch(aspectRatio, () => {
  nextTick(() => layoutCanvas());
});

watch(objects, () => {
  void ensureImagesLoaded().then(() => redraw());
  schedulePersistDraft();
}, { deep: true });

watch([ratioPreset, customWidth, customHeight, color, brushSize], () => {
  schedulePersistDraft();
});

onMounted(async () => {
  restoreDraft();
  restoringDraft = false;
  document.body.classList.add("sketch-board-open");
  bindWindowListeners();
  if (typeof window !== "undefined") {
    mobileQuery = window.matchMedia(MOBILE_QUERY);
    isMobile.value = mobileQuery.matches;
    mobileQuery.addEventListener("change", handleMobileQueryChange);
  }
  scheduleLayout();
  if (boardRef.value && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => layoutCanvas());
    resizeObserver.observe(boardRef.value);
  }
});

onBeforeUnmount(() => {
  if (persistTimer !== null) {
    window.clearTimeout(persistTimer);
    persistTimer = null;
  }
  persistDraft();
  document.body.classList.remove("sketch-board-open");
  if (getFullscreenElement()) {
    void exitElementFullscreen().catch(() => undefined);
  }
  unbindWindowListeners();
  mobileQuery?.removeEventListener("change", handleMobileQueryChange);
  mobileQuery = null;
  resizeObserver?.disconnect();
  resizeObserver = null;
});
</script>

<template>
  <Teleport to="body">
    <div ref="rootRef" class="sketch-root" role="dialog" aria-modal="true" aria-label="画板">
      <div class="sketch-topbar" :class="{ 'sheet-open': mobileToolsOpen }" @pointerdown.stop>
        <button
          v-if="isMobile"
          type="button"
          class="sketch-tools-toggle"
          :class="{ active: mobileToolsOpen }"
          aria-label="工具"
          @click.stop="toggleMobileTools"
        >
          <AppstoreOutlined />
          <span>工具</span>
        </button>
        <span class="sketch-topbar-title">画板</span>
        <div class="sketch-topbar-center">
        <div class="sketch-ratio-wrap">
          <button
            type="button"
            class="sketch-ratio-trigger"
            :aria-expanded="ratioMenuOpen"
            @click.stop="ratioMenuOpen = !ratioMenuOpen; customPanelOpen = false"
          >
            <span class="sketch-ratio-icon" :style="{ aspectRatio: String(aspectRatio) }" />
            <span>{{ ratioLabel }}</span>
            <svg viewBox="0 0 12 12" class="sketch-ratio-caret" aria-hidden="true">
              <path d="M2.4 4.2 6 7.8l3.6-3.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
            </svg>
          </button>
          <div v-if="ratioMenuOpen" class="sketch-ratio-menu" @pointerdown.stop @click.stop>
            <button
              v-for="item in RATIO_PRESETS"
              :key="item.value"
              type="button"
              class="sketch-ratio-option"
              :class="{ active: ratioPreset === item.value }"
              @click="selectRatio(item.value)"
            >
              <span class="sketch-ratio-radio" :class="{ checked: ratioPreset === item.value }" />
              <span>{{ item.label }}</span>
            </button>
            <button
              type="button"
              class="sketch-ratio-option"
              :class="{ active: ratioPreset === 'custom' }"
              @click="selectRatio('custom')"
            >
              <span class="sketch-ratio-radio" :class="{ checked: ratioPreset === 'custom' }" />
              <span>自定义</span>
            </button>
          </div>
          <div v-if="customPanelOpen" class="sketch-custom-panel" @pointerdown.stop @click.stop>
            <div class="sketch-custom-title">自定义画布比例</div>
            <div class="sketch-custom-row">
              <label>
                <span>宽</span>
                <input v-model="customWidthDraft" type="number" min="256" max="4096" />
              </label>
              <label>
                <span>高</span>
                <input v-model="customHeightDraft" type="number" min="256" max="4096" />
              </label>
            </div>
            <div class="sketch-custom-actions">
              <button type="button" @click="customPanelOpen = false">取消</button>
              <button type="button" class="primary" @click="applyCustomRatio">确定</button>
            </div>
          </div>
        </div>
        <div class="sketch-dock">
          <div class="sketch-dock-group sketch-colors">
            <label class="sketch-color-chip sketch-color-custom" title="自定义颜色">
              <input v-model="color" type="color" />
            </label>
            <button
              v-for="item in COLOR_PRESETS"
              :key="item"
              type="button"
              class="sketch-color-chip"
              :class="{ active: color.toLowerCase() === item }"
              :style="{ background: item }"
              :aria-label="`选择颜色 ${item}`"
              @click.stop="color = item"
            />
          </div>
          <div class="sketch-dock-group sketch-brush">
            <span class="sketch-brush-dot sketch-brush-dot-sm" />
            <input
              v-model.number="brushSize"
              class="sketch-brush-slider"
              type="range"
              min="2"
              max="36"
            />
            <span class="sketch-brush-dot sketch-brush-dot-lg" />
          </div>
          <div class="sketch-dock-group sketch-tools">
            <a-tooltip title="清空画板">
              <span class="sketch-tool-tip">
                <button type="button" class="sketch-tool-btn" :disabled="!hasContent" aria-label="清空画板" @click.stop="requestClearBoard">
                  <DeleteOutlined />
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="撤销">
              <span class="sketch-tool-tip">
                <button type="button" class="sketch-tool-btn" :disabled="!canUndo" aria-label="撤销" @click.stop="undo">
                  <UndoOutlined />
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="重做">
              <span class="sketch-tool-tip">
                <button type="button" class="sketch-tool-btn" :disabled="!canRedo" aria-label="重做" @click.stop="redo">
                  <RedoOutlined />
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="画笔">
              <span class="sketch-tool-tip">
                <button
                  type="button"
                  class="sketch-tool-btn"
                  :class="{ active: tool === 'pen' }"
                  aria-label="画笔"
                  @click.stop="selectTool('pen')"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      fill="currentColor"
                      d="M20.2 7.1c.8-.8.8-2 0-2.8l-.5-.5c-.8-.8-2-.8-2.8 0l-1.2 1.2 3.3 3.3 1.2-1.2zM7.4 16.6c.4-.4.9-.7 1.5-.8l7.8-7.8-3.3-3.3-7.8 7.8c-.2.6-.4 1.1-.8 1.5l-2.4 3.7c-.2.3 0 .7.4.8l3.8-1.1c.3-.1.6-.3.8-.8z"
                    />
                    <path
                      fill="currentColor"
                      d="M4.2 19.7c1.5-.2 3.4-1.2 5.2-2.9l-2.2-2.2C5.5 16.3 4.5 18.2 4.2 19.7z"
                    />
                  </svg>
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="橡皮擦">
              <span class="sketch-tool-tip">
                <button
                  type="button"
                  class="sketch-tool-btn"
                  :class="{ active: tool === 'erase' }"
                  aria-label="橡皮擦"
                  @click.stop="selectTool('erase')"
                >
                  <ClearOutlined />
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="箭头">
              <span class="sketch-tool-tip">
                <button
                  type="button"
                  class="sketch-tool-btn"
                  :class="{ active: tool === 'arrow' }"
                  aria-label="箭头"
                  @click.stop="selectTool('arrow')"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4 12h13M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="矩形">
              <span class="sketch-tool-tip">
                <button
                  type="button"
                  class="sketch-tool-btn"
                  :class="{ active: tool === 'rect' }"
                  aria-label="矩形"
                  @click.stop="selectTool('rect')"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <rect x="5" y="6" width="14" height="12" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8" />
                  </svg>
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="圆形">
              <span class="sketch-tool-tip">
                <button
                  type="button"
                  class="sketch-tool-btn"
                  :class="{ active: tool === 'circle' }"
                  aria-label="圆形"
                  @click.stop="selectTool('circle')"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="1.8" />
                  </svg>
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="文字">
              <span class="sketch-tool-tip">
                <button
                  type="button"
                  class="sketch-tool-btn"
                  :class="{ active: tool === 'text' }"
                  aria-label="文字"
                  @click.stop="selectTool('text')"
                >
                  <FontSizeOutlined />
                </button>
              </span>
            </a-tooltip>
            <a-tooltip title="插入图片">
              <span class="sketch-tool-tip">
                <button
                  type="button"
                  class="sketch-tool-btn"
                  :class="{ active: tool === 'image' }"
                  aria-label="插入图片"
                  @click.stop="triggerInsertImage"
                >
                  <FolderOpenOutlined />
                </button>
              </span>
            </a-tooltip>
          </div>
        </div>
          <div v-if="isMobile" class="sketch-sheet-actions">
            <a-button @click="toggleFullscreen">{{ immersiveLabel }}</a-button>
            <a-button :loading="savingAsset" :disabled="exporting" @click="handleSaveAsAsset">保存为我的素材</a-button>
            <a-button type="primary" :loading="exporting" :disabled="savingAsset" @click="handleConfirm">作为参考图</a-button>
          </div>
        </div>
        <div class="sketch-topbar-actions">
          <a-button v-if="!isMobile" @click="toggleFullscreen">{{ immersiveLabel }}</a-button>
          <a-button v-if="!isMobile" :loading="savingAsset" :disabled="exporting" @click="handleSaveAsAsset">保存为我的素材</a-button>
          <a-button v-if="!isMobile" type="primary" :loading="exporting" :disabled="savingAsset" @click="handleConfirm">作为参考图</a-button>
          <button
            v-if="isMobile"
            type="button"
            class="sketch-close-btn"
            :aria-label="isFullscreen ? '退出全屏' : '全屏'"
            @click.stop="toggleFullscreen"
          >
            <FullscreenExitOutlined v-if="isFullscreen" />
            <FullscreenOutlined v-else />
          </button>
          <button type="button" class="sketch-close-btn" aria-label="关闭画板" @click="requestClose">
            <CloseOutlined />
          </button>
        </div>
      </div>

      <div ref="boardRef" class="sketch-board">
        <div
          class="sketch-canvas-host"
          :style="{ width: `${displaySize.w}px`, height: `${displaySize.h}px` }"
        >
          <canvas
            ref="canvasRef"
            class="sketch-canvas"
            :style="{ cursor: canvasCursor }"
            @pointerdown="handlePointerDown"
            @pointermove="handlePointerMove"
            @pointerup="finishDrawing"
            @pointercancel="finishDrawing"
          />
          <input
            v-show="textEditorVisible"
            ref="textInputRef"
            v-model="textEditorValue"
            class="sketch-inline-text"
            :style="inlineTextStyle"
            maxlength="40"
            autocomplete="off"
            spellcheck="false"
            enterkeyhint="done"
            @keydown.enter.prevent.stop="confirmInlineText"
            @keydown.esc.prevent.stop="closeInlineText"
            @blur="handleTextBlur"
            @pointerdown.stop
            @pointerup.stop
          />
        </div>
      </div>
    </div>
  </Teleport>

  <a-modal
    v-model:open="closeConfirmOpen"
    title="关闭画板"
    centered
    ok-text="关闭"
    cancel-text="继续绘制"
    :z-index="1300"
    wrap-class-name="sketch-board-confirm-wrap"
    @ok="confirmCloseBoard"
  >
    画板会自动保存草稿，下次打开可继续编辑。确定关闭吗？
  </a-modal>

  <a-modal
    v-model:open="clearConfirmOpen"
    title="清空画板"
    centered
    ok-text="清空"
    cancel-text="取消"
    :z-index="1300"
    wrap-class-name="sketch-board-confirm-wrap"
    @ok="confirmClearBoard"
  >
    清空后当前绘制和草稿都会删除，确定清空吗？
  </a-modal>

  <input
    ref="imageInputRef"
    class="sketch-hidden-input"
    type="file"
    accept="image/png,image/jpeg,image/webp,image/gif"
    @change="handleInsertImage"
  />
</template>

<style scoped lang="scss">
.sketch-root {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  flex-direction: column;
  background: var(--theme-page-bg, #f6f4ef);
}

.sketch-topbar {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  flex: 0 0 auto;
  width: 100%;
  min-height: 52px;
  min-width: 0;
  padding: 8px;
  gap: 12px;
  background: var(--theme-modal-header-bg, #fff8ec);
}

.sketch-tools-toggle {
  appearance: none;
  display: none;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 6px;
  background: var(--theme-control-bg);
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;

  &.active,
  &:hover {
    background: var(--theme-control-hover-bg);
  }
}

.sketch-topbar-title {
  flex: 0 0 auto;
  font-weight: 700;
}

.sketch-topbar-center {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1 1 auto;
  gap: 14px;
  min-width: 0;
}

.sketch-topbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex: 0 0 auto;
  gap: 8px;
}

.sketch-close-btn {
  appearance: none;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--theme-title);
  cursor: pointer;

  &:hover {
    background: var(--theme-control-hover-bg);
  }
}

.sketch-board {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1 1 auto;
  width: 100%;
  min-height: 0;
  background: var(--theme-page-bg, #f6f4ef);
  user-select: none;
}

.sketch-canvas-host {
  position: relative;
  flex: 0 0 auto;
  background: #ffffff;
}

.sketch-ratio-wrap {
  position: relative;
}

.sketch-ratio-trigger {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 6px;
  background: var(--theme-control-bg);
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.sketch-ratio-icon {
  width: 16px;
  max-height: 14px;
  border: 1.5px solid currentColor;
}

.sketch-ratio-caret {
  width: 10px;
  height: 10px;
}

.sketch-ratio-menu,
.sketch-custom-panel {
  position: absolute;
  top: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 6;
  border: 1px solid var(--theme-panel-border);
  border-radius: 8px;
  background: var(--theme-modal-bg);
  box-shadow: 0 8px 24px var(--theme-shadow-medium);
}

.sketch-ratio-menu {
  min-width: 148px;
  padding: 6px;
}

.sketch-ratio-option {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--theme-title);
  cursor: pointer;
  text-align: left;

  &:hover,
  &.active {
    background: var(--theme-control-hover-bg);
  }
}

.sketch-ratio-radio {
  width: 14px;
  height: 14px;
  border: 1.5px solid var(--theme-control-border-strong);
  border-radius: 999px;

  &.checked {
    border-color: var(--theme-action);
    box-shadow: inset 0 0 0 3.5px var(--theme-action);
  }
}

.sketch-custom-panel {
  width: 240px;
  padding: 12px;
  color: var(--theme-title);
}

.sketch-custom-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
}

.sketch-custom-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;

  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 12px;
    color: var(--theme-text-secondary);
  }

  input {
    width: 100%;
    height: 34px;
    padding: 0 8px;
    border: 1px solid var(--theme-control-border-strong);
    border-radius: 6px;
    background: var(--theme-control-bg);
    color: var(--theme-title);
  }
}

.sketch-custom-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;

  button {
    height: 32px;
    padding: 0 12px;
    border: 1px solid var(--theme-control-border-strong);
    border-radius: 6px;
    background: var(--theme-control-bg);
    color: var(--theme-title);
    cursor: pointer;
  }

  .primary {
    border-color: transparent;
    background: var(--theme-action);
    color: var(--theme-action-contrast);
    font-weight: 600;
  }
}

.sketch-canvas {
  display: block;
  width: 100%;
  height: 100%;
  background: #ffffff;
  touch-action: none;
}

.sketch-inline-text {
  position: absolute;
  z-index: 5;
  min-width: 2em;
  overflow: hidden;
  min-height: 1.2em;
  margin: 0;
  padding: 0 2px;
  border: 0;
  border-bottom: 1px dashed currentColor;
  outline: none;
  background: transparent;
  box-shadow: none;
  transform: translateY(-0.85em);
  font-weight: 600;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  line-height: 1.2;
  caret-color: currentColor;
  pointer-events: auto;
  user-select: text;
  -webkit-user-select: text;
}

.sketch-dock {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 14px;
  min-width: 0;
}

.sketch-dock-group {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
}

.sketch-color-chip {
  width: 18px;
  height: 18px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 999px;
  cursor: pointer;

  &.active {
    border-color: var(--theme-title);
  }
}

.sketch-color-custom {
  position: relative;
  overflow: hidden;
  background: conic-gradient(#ef4444, #eab308, #22c55e, #3b82f6, #8b5cf6, #ef4444);

  input {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }
}

.sketch-brush-slider {
  width: 88px;
  accent-color: var(--theme-action);
}

.sketch-brush-dot {
  border-radius: 999px;
  background: var(--theme-muted-text);
}

.sketch-brush-dot-sm {
  width: 6px;
  height: 6px;
}

.sketch-brush-dot-lg {
  width: 12px;
  height: 12px;
}

.sketch-tool-tip {
  display: inline-flex;
}

.sketch-tool-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--theme-title);
  cursor: pointer;

  svg {
    width: 16px;
    height: 16px;
  }

  &.active,
  &:hover:not(:disabled) {
    background: var(--theme-control-hover-bg);
  }

  &:disabled {
    opacity: 0.35;
    cursor: default;
  }
}

.sketch-hidden-input {
  display: none;
}

@media (max-width: 1100px) {
  .sketch-topbar-title {
    display: none;
  }

  .sketch-dock {
    gap: 8px;
  }
}

@media (max-width: 768px) {
  .sketch-tools-toggle {
    display: inline-flex;
  }

  .sketch-topbar-center {
    display: none;
    position: absolute;
    top: calc(100% + 8px);
    left: 0;
    right: 0;
    z-index: 8;
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    max-height: min(70vh, 520px);
    padding: 12px;
    overflow: auto;
    border: 1px solid var(--theme-panel-border);
    border-radius: 12px;
    background: var(--theme-modal-bg);
    box-shadow: 0 8px 24px var(--theme-shadow-medium);
  }

  .sketch-topbar.sheet-open .sketch-topbar-center {
    display: flex;
  }

  .sketch-ratio-trigger {
    width: 100%;
    justify-content: space-between;
  }

  .sketch-ratio-menu,
  .sketch-custom-panel {
    left: 0;
    right: 0;
    width: 100%;
    transform: none;
  }

  .sketch-dock,
  .sketch-dock-group {
    flex-wrap: wrap;
    width: 100%;
  }

  .sketch-brush-slider {
    flex: 1 1 120px;
    width: auto;
  }

  .sketch-sheet-actions {
    display: flex;
    flex-direction: column;
    gap: 8px;

    :deep(.ant-btn) {
      width: 100%;
    }
  }
}
</style>

<style lang="scss">
.sketch-board-confirm-wrap {
  z-index: 1300 !important;
}

body.sketch-board-open {
  overflow: hidden;
}

body.sketch-board-open .canvas-side-nav {
  display: none !important;
}

body.sketch-board-open .ant-message,
body.sketch-board-open .ant-tooltip {
  z-index: 1400 !important;
}
</style>
