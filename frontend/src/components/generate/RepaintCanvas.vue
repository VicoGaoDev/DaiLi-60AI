<script setup lang="ts">
import { ref, nextTick, watch } from "vue";

const EXPORT_MASK_COLOR = "#fff";
const EXPORT_MASK_BG = "#000";
const PREVIEW_MASK_ALPHA = 0.75;
const PREVIEW_SHAPE_FILL_ALPHA = 0.4;
const PREVIEW_TEXT_ALPHA = 0.92;

const props = withDefaults(defineProps<{
  imageUrl: string;
  maskUrl?: string;
  brushSize?: number;
  tool?: "paint" | "erase" | "rect" | "circle" | "text";
  lineColor?: string;
}>(), {
  maskUrl: "",
  brushSize: 28,
  tool: "paint",
  lineColor: "#c38d36",
});

const emit = defineEmits<{
  (e: "mask-change", value: boolean): void;
}>();

const imageRef = ref<HTMLImageElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const dialogInputRef = ref<HTMLInputElement | null>(null);
const exportCanvas = document.createElement("canvas");
const exportCtx = exportCanvas.getContext("2d");
interface TextOverlay {
  text: string;
  x: number;
  y: number;
  fontSize: number;
}

function cloneTextOverlay(overlay: TextOverlay | null): TextOverlay | null {
  return overlay ? { ...overlay } : null;
}

const historyStack: Array<{
  view: ImageData;
  exported: ImageData;
  text: TextOverlay | null;
}> = [];
const redoStack: Array<{
  view: ImageData;
  exported: ImageData;
  text: TextOverlay | null;
}> = [];

const hasMask = ref(false);
let initializedImageUrl = "";
let drawing = false;
let lastViewPoint: { x: number; y: number } | null = null;
let lastExportPoint: { x: number; y: number } | null = null;
let dragStartViewPoint: { x: number; y: number } | null = null;
let dragStartExportPoint: { x: number; y: number } | null = null;
let draggingText = false;
let textDragOffset: { x: number; y: number } | null = null;
let textOverlay: TextOverlay | null = null;
const textDialogVisible = ref(false);
const textDialogValue = ref("");
const pendingTextPoint = ref<{ x: number; y: number } | null>(null);

function resetExportCanvas(width: number, height: number) {
  if (!exportCtx) return;
  exportCanvas.width = width;
  exportCanvas.height = height;
  exportCtx.fillStyle = EXPORT_MASK_BG;
  exportCtx.fillRect(0, 0, width, height);
}

function setupViewCanvas() {
  const image = imageRef.value;
  const canvas = canvasRef.value;
  if (!image || !canvas) return;

  const rect = image.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
}

function normalizeHexColor(color: string) {
  const value = String(color || "").trim();
  if (/^#[0-9a-fA-F]{6}$/.test(value)) return value;
  if (/^#[0-9a-fA-F]{3}$/.test(value)) {
    return `#${value.slice(1).split("").map((char) => `${char}${char}`).join("")}`;
  }
  return "#ffab25";
}

function getPreviewMaskColor(alpha = PREVIEW_MASK_ALPHA) {
  const normalized = normalizeHexColor(props.lineColor);
  const r = Number.parseInt(normalized.slice(1, 3), 16);
  const g = Number.parseInt(normalized.slice(3, 5), 16);
  const b = Number.parseInt(normalized.slice(5, 7), 16);
  return {
    r,
    g,
    b,
    alpha: Math.max(0, Math.min(255, Math.round(alpha * 255))),
    css: `rgba(${r}, ${g}, ${b}, ${alpha})`,
  };
}

function traceShapePath(
  ctx: CanvasRenderingContext2D,
  from: { x: number; y: number },
  to: { x: number; y: number },
  shape: "rect" | "circle",
) {
  const width = to.x - from.x;
  const height = to.y - from.y;
  if (shape === "rect") {
    ctx.rect(from.x, from.y, width, height);
    return;
  }
  ctx.ellipse(
    from.x + width / 2,
    from.y + height / 2,
    Math.abs(width) / 2,
    Math.abs(height) / 2,
    0,
    0,
    Math.PI * 2,
  );
}

function getTextFontSize() {
  return Math.max(18, Math.round(props.brushSize * 1.3));
}

function getTextFont(size: number) {
  return `700 ${size}px "PingFang SC", "Microsoft YaHei", sans-serif`;
}

function measureTextBounds(
  ctx: CanvasRenderingContext2D,
  text: string,
  fontSize: number,
  x: number,
  y: number,
) {
  ctx.save();
  ctx.font = getTextFont(fontSize);
  const metrics = ctx.measureText(text);
  ctx.restore();
  const actualLeft = metrics.actualBoundingBoxLeft || 0;
  const actualRight = metrics.actualBoundingBoxRight || metrics.width;
  const actualAscent = metrics.actualBoundingBoxAscent || fontSize * 0.8;
  const actualDescent = metrics.actualBoundingBoxDescent || fontSize * 0.2;
  return {
    left: x - actualLeft,
    top: y - actualAscent,
    width: actualLeft + actualRight,
    height: actualAscent + actualDescent,
  };
}

function isPointInsideTextOverlay(point: { x: number; y: number }) {
  if (!textOverlay || !exportCtx) return false;
  const bounds = measureTextBounds(exportCtx, textOverlay.text, textOverlay.fontSize, textOverlay.x, textOverlay.y);
  return (
    point.x >= bounds.left
    && point.x <= bounds.left + bounds.width
    && point.y >= bounds.top
    && point.y <= bounds.top + bounds.height
  );
}

function drawTextOverlayOnContext(
  ctx: CanvasRenderingContext2D,
  overlay: TextOverlay,
  color: string,
  scale = 1,
) {
  ctx.save();
  ctx.font = getTextFont(overlay.fontSize * scale);
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = color;
  ctx.fillText(overlay.text, overlay.x * scale, overlay.y * scale);
  ctx.restore();
}

function placeTextAtPoint(
  points: { viewPoint: { x: number; y: number }; exportPoint: { x: number; y: number } },
  text: string,
) {
  pushSnapshot();
  textOverlay = {
    text,
    x: points.exportPoint.x,
    y: points.exportPoint.y,
    fontSize: getTextFontSize(),
  };
  renderPreviewFromExport();
  recomputeMaskState();
}

async function openTextDialog(point: { x: number; y: number }) {
  pendingTextPoint.value = point;
  textDialogValue.value = "";
  textDialogVisible.value = true;
  await nextTick();
  dialogInputRef.value?.focus();
}

function closeTextDialog() {
  textDialogVisible.value = false;
  textDialogValue.value = "";
  pendingTextPoint.value = null;
}

function confirmTextDialog() {
  const point = pendingTextPoint.value;
  const text = textDialogValue.value.trim();
  if (!point || !text) {
    closeTextDialog();
    return;
  }
  pushSnapshot();
  textOverlay = {
    text,
    x: point.x,
    y: point.y,
    fontSize: getTextFontSize(),
  };
  closeTextDialog();
  renderPreviewFromExport();
  recomputeMaskState();
}

function renderPreviewFromExport() {
  const canvas = canvasRef.value;
  if (!canvas || !exportCtx || !exportCanvas.width || !exportCanvas.height) return;
  const viewCtx = canvas.getContext("2d");
  if (!viewCtx) return;
  const previewColor = getPreviewMaskColor();

  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;

  const tempCanvas = document.createElement("canvas");
  tempCanvas.width = Math.max(1, Math.round(rect.width));
  tempCanvas.height = Math.max(1, Math.round(rect.height));
  const tempCtx = tempCanvas.getContext("2d");
  if (!tempCtx) return;

  tempCtx.drawImage(exportCanvas, 0, 0, tempCanvas.width, tempCanvas.height);
  const imageData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    const isMasked = data[i] > 0 || data[i + 1] > 0 || data[i + 2] > 0;
    data[i] = previewColor.r;
    data[i + 1] = previewColor.g;
    data[i + 2] = previewColor.b;
    data[i + 3] = isMasked ? previewColor.alpha : 0;
  }

  tempCtx.putImageData(imageData, 0, 0);
  viewCtx.clearRect(0, 0, rect.width, rect.height);
  viewCtx.drawImage(tempCanvas, 0, 0, rect.width, rect.height);
  if (textOverlay?.text) {
    const scale = rect.width / exportCanvas.width;
    drawTextOverlayOnContext(viewCtx, textOverlay, getPreviewMaskColor(PREVIEW_TEXT_ALPHA).css, scale);
  }
}

function loadImage(url: string): Promise<HTMLImageElement | null> {
  const resolvedUrl = (url || "").trim();
  if (!resolvedUrl) return Promise.resolve(null);
  return new Promise((resolve) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = resolvedUrl;
  });
}

async function applyInitialMask() {
  if (!props.maskUrl || !exportCtx) {
    renderPreviewFromExport();
    recomputeMaskState();
    return;
  }
  const maskImage = await loadImage(props.maskUrl);
  if (!maskImage) {
    renderPreviewFromExport();
    recomputeMaskState();
    return;
  }
  exportCtx.drawImage(maskImage, 0, 0, exportCanvas.width, exportCanvas.height);
  renderPreviewFromExport();
  recomputeMaskState();
}

async function initializeCanvas(force = false) {
  const image = imageRef.value;
  const canvas = canvasRef.value;
  if (!image || !image.naturalWidth || !image.naturalHeight || !canvas) return;
  const currentUrl = (props.imageUrl || "").trim();
  if (
    !force
    && currentUrl
    && initializedImageUrl === currentUrl
    && exportCanvas.width === image.naturalWidth
    && exportCanvas.height === image.naturalHeight
  ) {
    setupViewCanvas();
    renderPreviewFromExport();
    recomputeMaskState();
    return;
  }
  setupViewCanvas();
  resetExportCanvas(image.naturalWidth, image.naturalHeight);
  const viewCtx = canvas.getContext("2d");
  if (viewCtx) {
    viewCtx.clearRect(0, 0, canvas.width, canvas.height);
  }
  historyStack.length = 0;
  redoStack.length = 0;
  hasMask.value = false;
  textOverlay = null;
  initializedImageUrl = currentUrl;
  closeTextDialog();
  emit("mask-change", false);
  await applyInitialMask();
}

async function handleImageLoad() {
  await nextTick();
  await initializeCanvas(false);
}

function drawLine(
  ctx: CanvasRenderingContext2D,
  from: { x: number; y: number },
  to: { x: number; y: number },
  width: number,
  color: string,
  mode: "paint" | "erase" = "paint",
) {
  ctx.save();
  ctx.globalCompositeOperation = mode === "erase" ? "destination-out" : "source-over";
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();
  ctx.restore();
}

function drawPreviewShape(
  from: { x: number; y: number },
  to: { x: number; y: number },
  width: number,
  shape: "rect" | "circle",
) {
  const canvas = canvasRef.value;
  const viewCtx = canvas?.getContext("2d");
  if (!canvas || !viewCtx) return;
  const previewColor = getPreviewMaskColor(PREVIEW_SHAPE_FILL_ALPHA);
  viewCtx.save();
  viewCtx.lineWidth = Math.max(2, width);
  viewCtx.strokeStyle = getPreviewMaskColor(0.95).css;
  viewCtx.fillStyle = previewColor.css;
  viewCtx.lineCap = "round";
  viewCtx.lineJoin = "round";
  viewCtx.beginPath();
  traceShapePath(viewCtx, from, to, shape);
  viewCtx.fill();
  viewCtx.stroke();
  viewCtx.restore();
}

function fillShape(
  ctx: CanvasRenderingContext2D,
  from: { x: number; y: number },
  to: { x: number; y: number },
  color: string,
  shape: "rect" | "circle",
) {
  ctx.save();
  ctx.fillStyle = color;
  ctx.beginPath();
  traceShapePath(ctx, from, to, shape);
  ctx.fill();
  ctx.restore();
}

function recomputeMaskState() {
  if (!exportCtx || !exportCanvas.width || !exportCanvas.height) {
    hasMask.value = false;
    emit("mask-change", false);
    return;
  }
  if (textOverlay?.text) {
    hasMask.value = true;
    emit("mask-change", true);
    return;
  }
  const data = exportCtx.getImageData(0, 0, exportCanvas.width, exportCanvas.height).data;
  let filled = false;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i] > 0 || data[i + 1] > 0 || data[i + 2] > 0) {
      filled = true;
      break;
    }
  }
  hasMask.value = filled;
  emit("mask-change", filled);
}

function pushSnapshot() {
  const canvas = canvasRef.value;
  const viewCtx = canvas?.getContext("2d");
  if (!canvas || !viewCtx || !exportCtx) return;
  historyStack.push({
    view: viewCtx.getImageData(0, 0, canvas.width, canvas.height),
    exported: exportCtx.getImageData(0, 0, exportCanvas.width, exportCanvas.height),
    text: cloneTextOverlay(textOverlay),
  });
  if (historyStack.length > 20) historyStack.shift();
  redoStack.length = 0;
}

function getPoints(event: PointerEvent) {
  const image = imageRef.value;
  const canvas = canvasRef.value;
  if (!image || !canvas) return null;

  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;

  const viewPoint = {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
  const scale = image.naturalWidth / rect.width;
  const exportPoint = {
    x: viewPoint.x * scale,
    y: viewPoint.y * scale,
  };

  return { viewPoint, exportPoint, scale };
}

function handlePointerDown(event: PointerEvent) {
  const points = getPoints(event);
  const canvas = canvasRef.value;
  if (!points || !canvas || !exportCtx) return;

  if (props.tool === "text") {
    if (textOverlay?.text && isPointInsideTextOverlay(points.exportPoint)) {
      drawing = true;
      draggingText = true;
      canvas.setPointerCapture(event.pointerId);
      pushSnapshot();
      textDragOffset = {
        x: points.exportPoint.x - textOverlay.x,
        y: points.exportPoint.y - textOverlay.y,
      };
      return;
    }
    void openTextDialog(points.exportPoint);
    return;
  }

  drawing = true;
  draggingText = false;
  textDragOffset = null;
  canvas.setPointerCapture(event.pointerId);
  pushSnapshot();
  dragStartViewPoint = points.viewPoint;
  dragStartExportPoint = points.exportPoint;
  lastViewPoint = points.viewPoint;
  lastExportPoint = points.exportPoint;

  if (props.tool === "rect" || props.tool === "circle") {
    renderPreviewFromExport();
    drawPreviewShape(points.viewPoint, points.viewPoint, props.brushSize, props.tool);
    return;
  }

  drawLine(
    exportCtx,
    points.exportPoint,
    points.exportPoint,
    props.brushSize * points.scale,
    props.tool === "erase" ? EXPORT_MASK_BG : EXPORT_MASK_COLOR,
    props.tool
  );

  renderPreviewFromExport();
  recomputeMaskState();
}

function handlePointerMove(event: PointerEvent) {
  if (!drawing) return;
  const points = getPoints(event);
  if (!points || !exportCtx) return;
  if (props.tool === "text") {
    if (!textOverlay) return;
    const offset = textDragOffset || { x: 0, y: 0 };
    textOverlay = {
      ...textOverlay,
      fontSize: getTextFontSize(),
      x: draggingText ? points.exportPoint.x - offset.x : points.exportPoint.x,
      y: draggingText ? points.exportPoint.y - offset.y : points.exportPoint.y,
    };
    renderPreviewFromExport();
    recomputeMaskState();
    return;
  }
  if (!lastViewPoint || !lastExportPoint) return;
  if (props.tool === "rect" || props.tool === "circle") {
    lastViewPoint = points.viewPoint;
    lastExportPoint = points.exportPoint;
    if (!dragStartViewPoint) return;
    renderPreviewFromExport();
    drawPreviewShape(dragStartViewPoint, points.viewPoint, props.brushSize, props.tool);
    return;
  }
  drawLine(
    exportCtx,
    lastExportPoint,
    points.exportPoint,
    props.brushSize * points.scale,
    props.tool === "erase" ? EXPORT_MASK_BG : EXPORT_MASK_COLOR,
    props.tool
  );

  lastViewPoint = points.viewPoint;
  lastExportPoint = points.exportPoint;
  renderPreviewFromExport();
  recomputeMaskState();
}

function stopDrawing(event?: PointerEvent) {
  const shouldCommitShape = drawing && (props.tool === "rect" || props.tool === "circle");
  if (shouldCommitShape && exportCtx && dragStartExportPoint && lastExportPoint) {
    fillShape(
      exportCtx,
      dragStartExportPoint,
      lastExportPoint,
      EXPORT_MASK_COLOR,
      props.tool,
    );
    renderPreviewFromExport();
    recomputeMaskState();
  }
  if (event && canvasRef.value?.hasPointerCapture(event.pointerId)) {
    canvasRef.value.releasePointerCapture(event.pointerId);
  }
  drawing = false;
  draggingText = false;
  textDragOffset = null;
  lastViewPoint = null;
  lastExportPoint = null;
  dragStartViewPoint = null;
  dragStartExportPoint = null;
}

function clearMask() {
  initializedImageUrl = "";
  void initializeCanvas(true);
}

function undo() {
  const canvas = canvasRef.value;
  const viewCtx = canvas?.getContext("2d");
  const snapshot = historyStack.pop();
  if (!canvas || !viewCtx || !exportCtx || !snapshot) return false;
  redoStack.push({
    view: viewCtx.getImageData(0, 0, canvas.width, canvas.height),
    exported: exportCtx.getImageData(0, 0, exportCanvas.width, exportCanvas.height),
    text: cloneTextOverlay(textOverlay),
  });
  viewCtx.putImageData(snapshot.view, 0, 0);
  exportCtx.putImageData(snapshot.exported, 0, 0);
  textOverlay = cloneTextOverlay(snapshot.text);
  recomputeMaskState();
  renderPreviewFromExport();
  return true;
}

function canUndo() {
  return historyStack.length > 0;
}

function redo() {
  const canvas = canvasRef.value;
  const viewCtx = canvas?.getContext("2d");
  const snapshot = redoStack.pop();
  if (!canvas || !viewCtx || !exportCtx || !snapshot) return false;
  historyStack.push({
    view: viewCtx.getImageData(0, 0, canvas.width, canvas.height),
    exported: exportCtx.getImageData(0, 0, exportCanvas.width, exportCanvas.height),
    text: cloneTextOverlay(textOverlay),
  });
  viewCtx.putImageData(snapshot.view, 0, 0);
  exportCtx.putImageData(snapshot.exported, 0, 0);
  textOverlay = cloneTextOverlay(snapshot.text);
  recomputeMaskState();
  renderPreviewFromExport();
  return true;
}

function canRedo() {
  return redoStack.length > 0;
}

function hasDrawnMask() {
  return hasMask.value;
}

function exportMaskBlob(): Promise<Blob | null> {
  if (!hasMask.value) return Promise.resolve(null);
  return new Promise((resolve) => {
    const outputCanvas = document.createElement("canvas");
    outputCanvas.width = exportCanvas.width;
    outputCanvas.height = exportCanvas.height;
    const outputCtx = outputCanvas.getContext("2d");
    if (!outputCtx) {
      resolve(null);
      return;
    }
    outputCtx.drawImage(exportCanvas, 0, 0);
    if (textOverlay?.text) {
      drawTextOverlayOnContext(outputCtx, textOverlay, EXPORT_MASK_COLOR);
    }
    outputCanvas.toBlob((blob) => resolve(blob), "image/png");
  });
}

defineExpose({
  clearMask,
  hasDrawnMask,
  exportMaskBlob,
  commitPendingMask: stopDrawing,
  undo,
  canUndo,
  redo,
  canRedo,
});

watch(() => props.imageUrl, async (nextUrl, prevUrl) => {
  if ((nextUrl || "").trim() === (prevUrl || "").trim()) return;
  initializedImageUrl = "";
  await nextTick();
  await initializeCanvas(true);
});

watch(() => props.maskUrl, async (nextUrl, prevUrl) => {
  if ((nextUrl || "").trim() === (prevUrl || "").trim()) return;
  initializedImageUrl = "";
  await nextTick();
  await initializeCanvas(true);
});

watch(() => props.lineColor, () => {
  renderPreviewFromExport();
});

watch(() => props.tool, (tool) => {
  if (tool !== "text") closeTextDialog();
});

watch(textDialogVisible, async (visible) => {
  if (!visible) return;
  await nextTick();
  dialogInputRef.value?.focus();
});

watch(() => props.brushSize, () => {
  if (props.tool === "text" && textOverlay) {
    textOverlay = {
      ...textOverlay,
      fontSize: getTextFontSize(),
    };
    renderPreviewFromExport();
  }
});
</script>

<template>
  <div class="repaint-canvas">
    <img
      ref="imageRef"
      :src="imageUrl"
      alt="局部重绘原图"
      class="repaint-image"
      @load="handleImageLoad"
    />
    <canvas
      ref="canvasRef"
      class="mask-canvas"
      :class="{ 'mask-canvas-text': props.tool === 'text' }"
      @pointerdown="handlePointerDown"
      @pointermove="handlePointerMove"
      @pointerup="stopDrawing"
      @pointerleave="stopDrawing"
      @pointercancel="stopDrawing"
    />
    <Teleport to="body">
      <div v-if="textDialogVisible" class="text-dialog-backdrop" @click="closeTextDialog">
        <div class="text-dialog-card" @click.stop>
          <div class="text-dialog-title">输入要添加的文字</div>
          <div class="text-dialog-subtitle">确认后会放到刚才点击的图片位置</div>
          <input
            ref="dialogInputRef"
            v-model="textDialogValue"
            type="text"
            maxlength="40"
            class="text-dialog-input"
            placeholder="请输入文字内容"
            @keydown.enter.prevent="confirmTextDialog"
            @keydown.esc.prevent="closeTextDialog"
          />
          <div class="text-dialog-actions">
            <button type="button" class="text-dialog-btn text-dialog-btn-secondary" @click="closeTextDialog">
              取消
            </button>
            <button type="button" class="text-dialog-btn text-dialog-btn-primary" @click="confirmTextDialog">
              确定
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
.repaint-canvas {
  position: relative;
  width: 100%;
  border-radius: 18px;
  overflow: hidden;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
}

.repaint-image {
  width: 100%;
  display: block;
}

.mask-canvas {
  position: absolute;
  inset: 0;
  cursor: crosshair;
  touch-action: none;
}

.mask-canvas-text {
  cursor: text;
}

.text-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(8, 11, 20, 0.68);
}

.text-dialog-card {
  width: min(420px, 100%);
  padding: 18px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(46, 46, 52, 0.96), rgba(34, 34, 38, 0.98));
  box-shadow:
    0 24px 60px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.text-dialog-title {
  color: #fff;
  font-size: 16px;
  font-weight: 700;
}

.text-dialog-subtitle {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 13px;
  line-height: 1.6;
}

.text-dialog-input {
  width: 100%;
  margin-top: 14px;
  padding: 11px 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  font-size: 14px;
  outline: none;
  transition:
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);
}

.text-dialog-input:hover,
.text-dialog-input:focus {
  border-color: rgba(120, 112, 255, 0.55);
  background: rgba(255, 255, 255, 0.09);
  box-shadow: 0 0 0 3px rgba(120, 112, 255, 0.14);
}

.text-dialog-input::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

.text-dialog-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.text-dialog-btn {
  min-width: 88px;
  height: 38px;
  padding: 0 16px;
  border-radius: 999px;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft);
}

.text-dialog-btn:hover {
  transform: translateY(-1px);
}

.text-dialog-btn-secondary {
  border-color: var(--theme-panel-border);
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
  color: var(--text-primary);
}

.text-dialog-btn-primary {
  border-color: color-mix(in srgb, var(--theme-accent) 34%, transparent);
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  box-shadow: 0 12px 24px rgba(var(--theme-accent-rgb), 0.24);
}

.text-dialog-btn-secondary:hover {
  border-color: var(--theme-panel-border-strong);
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-strong));
}

.text-dialog-btn-primary:hover {
  background: color-mix(in srgb, var(--theme-accent) 90%, white 10%);
}
</style>
