<script setup lang="ts">
import { computed, h, inject, nextTick, ref, type Ref } from "vue";
import { message } from "ant-design-vue";
import {
  ClearOutlined,
  CloseOutlined,
  CloudUploadOutlined,
  EditOutlined,
  FontSizeOutlined,
  LoadingOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons-vue";
import { getMe } from "@/api/auth";
import { getPreviewImageSrc, resolveImageUrl } from "@/api/images";
import { isSupportedImageUploadFile, MAX_IMAGE_UPLOAD_SIZE_BYTES, MAX_IMAGE_UPLOAD_SIZE_TEXT } from "@/api/upload";
import ImageSourceActionSheet from "@/components/generate/ImageSourceActionSheet.vue";
import AspectRatioPicker from "@/components/generate/AspectRatioPicker.vue";
import OptionGridPicker from "@/components/generate/OptionGridPicker.vue";
import RepaintCanvas from "@/components/generate/RepaintCanvas.vue";
import { useImageSourcePicker } from "@/composables/useImageSourcePicker";
import { useAuthStore } from "@/stores/auth";
import type { SceneOptionItem } from "@/types";

const REPAINT_COLOR_OPTIONS = [
  { label: "金棕", value: "#c38d36" },
  { label: "紫色", value: "#746bff" },
  { label: "青绿", value: "#2fa39b" },
  { label: "玫红", value: "#d95f8d" },
] as const;

const props = withDefaults(defineProps<{
  creditCost?: number;
  submitting?: boolean;
  isSuperAdmin?: boolean;
  queueFull?: boolean;
  sizeOptions?: SceneOptionItem[];
  resolutionOptions?: SceneOptionItem[];
  hideAspectRatio?: boolean;
  hideResolution?: boolean;
  supportsCustomSize?: boolean;
  customSizeEnabled?: boolean;
  customWidth?: number;
  customHeight?: number;
  customWidthError?: string;
  customHeightError?: string;
  customSizeStep?: number;
  parseCustomSizeInput?: (value: string) => string;
  formatCustomSizeInput?: (value: string | number) => string;
}>(), {
  creditCost: 4,
  submitting: false,
  isSuperAdmin: false,
  queueFull: false,
  sizeOptions: () => [],
  resolutionOptions: () => [],
  hideAspectRatio: false,
  hideResolution: false,
  supportsCustomSize: false,
  customSizeEnabled: false,
  customWidth: 1024,
  customHeight: 1024,
  customWidthError: "",
  customHeightError: "",
  customSizeStep: 16,
  parseCustomSizeInput: (value: string) => String(value ?? "").replace(/\D/g, ""),
  formatCustomSizeInput: (value: string | number) => String(value ?? "").replace(/\D/g, ""),
});

const size = defineModel<string>("size", { default: "1:1" });
const resolution = defineModel<string>("resolution", { default: "2K" });

const emit = defineEmits<{
  submit: [payload: { prompt: string; sourceImageUrl: string; maskImageUrl: string }];
  "request-login": [];
  "update:customSizeEnabled": [checked: boolean];
  "update:customWidth": [value: number | string | null];
  "update:customHeight": [value: number | string | null];
}>();

function getBodyPopupContainer() {
  return document.body;
}

function onCustomSizeSwitch(checked: boolean | string | number) {
  emit("update:customSizeEnabled", Boolean(checked));
}

const showCustomSizeToggle = computed(() => props.supportsCustomSize || props.customSizeEnabled);
const showSizeSettings = computed(() => (
  !props.hideAspectRatio
  || !props.hideResolution
  || showCustomSizeToggle.value
));

const auth = useAuthStore();
const loginModalVisible = inject<Ref<boolean> | undefined>("loginModalVisible", undefined);
const accentIndicatorStyle = { fontSize: "20px", color: "var(--theme-icon)" };
const TASK_PROMPT_MAX_LENGTH = 5000;

const inputMode = ref<"prompt" | "smear">("prompt");
const prompt = ref("");
const sourceImageUrl = ref("");
const sourcePreviewUrl = ref("");
const maskOverlayUrl = ref("");
const sourceUploading = ref(false);
const maskUploading = ref(false);
const sourcePickerOpening = ref(false);
const sourceInput = ref<HTMLInputElement | null>(null);
const {
  accept: imageFileAccept,
  sheetOpen: imageSourceSheetOpen,
  requestPick: requestImageSourcePick,
  pickFromCamera,
  pickFromGallery,
  pickFromFiles,
  cancelSheet: cancelImageSourceSheet,
} = useImageSourcePicker();
const brushSize = ref(28);
const repaintTool = ref<"paint" | "erase" | "rect" | "circle" | "text">("paint");
const repaintLineColor = ref("#c38d36");
const hasRepaintMask = ref(false);
const canUndoMask = ref(false);
const canRedoMask = ref(false);
const repaintCanvasRef = ref<{
  clearMask: () => void;
  hasDrawnMask: () => boolean;
  exportMaskBlob: () => Promise<Blob | null>;
  commitPendingMask: () => void;
  undo: () => boolean;
  redo: () => boolean;
  canUndo: () => boolean;
  canRedo: () => boolean;
} | null>(null);

const sourceDisplayUrl = computed(() => getPreviewImageSrc(sourcePreviewUrl.value || sourceImageUrl.value));
const isSmearMode = computed(() => inputMode.value === "smear");
const canSubmit = computed(() => (
  !props.submitting
  && !sourceUploading.value
  && !maskUploading.value
  && !props.queueFull
  && Boolean(sourceImageUrl.value.trim())
  && !(sourcePreviewUrl.value && !sourceImageUrl.value)
));
const submitButtonText = computed(() => {
  if (props.submitting || maskUploading.value) return "提交中...";
  if (sourceUploading.value) return "原图上传中...";
  if (sourcePreviewUrl.value && !sourceImageUrl.value) return "原图未上传完成";
  if (!sourceImageUrl.value.trim()) return "请先上传目标图";
  if (props.queueFull) return "生成队列已满";
  return props.isSuperAdmin ? "开始抠图" : `开始抠图 · ${props.creditCost} 积分`;
});

function requestLogin() {
  if (loginModalVisible) loginModalVisible.value = true;
  emit("request-login");
}

function revokeObjectUrl(url?: string) {
  if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
}

function hexToRgba(color: string, alpha: number) {
  const value = color.trim();
  const normalized = /^#[0-9a-fA-F]{3}$/.test(value)
    ? `#${value.slice(1).split("").map((char) => `${char}${char}`).join("")}`
    : value;
  const r = Number.parseInt(normalized.slice(1, 3), 16);
  const g = Number.parseInt(normalized.slice(3, 5), 16);
  const b = Number.parseInt(normalized.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function getRepaintBrushPreviewStyle() {
  const size = Math.max(10, Math.min(brushSize.value, 34));
  return {
    width: `${size}px`,
    height: `${size}px`,
    background: hexToRgba(repaintLineColor.value, 0.75),
    borderColor: hexToRgba(repaintLineColor.value, 0.9),
    boxShadow: `0 0 0 6px ${hexToRgba(repaintLineColor.value, 0.12)}, 0 4px 10px rgba(0, 0, 0, 0.16)`,
  };
}

function syncMaskHistory() {
  canUndoMask.value = repaintCanvasRef.value?.canUndo() ?? false;
  canRedoMask.value = repaintCanvasRef.value?.canRedo() ?? false;
}

function resetMaskState() {
  hasRepaintMask.value = false;
  canUndoMask.value = false;
  canRedoMask.value = false;
}

function isReferenceImageFile(file: File) {
  return isSupportedImageUploadFile(file);
}

function triggerSourceUpload() {
  if (!auth.isLoggedIn) {
    requestLogin();
    return;
  }
  getMe().then((user) => auth.updateUser(user)).catch(() => {
    sourcePickerOpening.value = false;
    requestLogin();
  });
  requestImageSourcePick(sourceInput.value, {
    onOpen: () => {
      sourcePickerOpening.value = true;
    },
    onCancel: () => {
      sourcePickerOpening.value = false;
    },
  });
}

async function handleSourceFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  sourcePickerOpening.value = false;
  if (!file) return;

  if (!isReferenceImageFile(file)) {
    message.warning("仅支持上传图片文件");
    input.value = "";
    return;
  }

  if (file.size > MAX_IMAGE_UPLOAD_SIZE_BYTES) {
    message.warning(`图片大小不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
    input.value = "";
    return;
  }

  revokeObjectUrl(sourcePreviewUrl.value);
  sourcePreviewUrl.value = URL.createObjectURL(file);
  sourceImageUrl.value = "";
  maskOverlayUrl.value = "";
  resetMaskState();
  sourceUploading.value = true;
  try {
    const { uploadReferenceImage } = await import("@/api/upload");
    const res = await uploadReferenceImage(file, "source");
    sourceImageUrl.value = res.url;
    repaintCanvasRef.value?.clearMask();
    message.success("原图上传成功");
  } catch {
    message.error("原图上传失败，请重试");
  } finally {
    sourceUploading.value = false;
    input.value = "";
  }
}

function removeSourceImage() {
  revokeObjectUrl(sourcePreviewUrl.value);
  sourcePreviewUrl.value = "";
  sourceImageUrl.value = "";
  maskOverlayUrl.value = "";
  resetMaskState();
}

function clearRepaintMask() {
  maskOverlayUrl.value = "";
  repaintCanvasRef.value?.clearMask();
  resetMaskState();
}

function undoRepaintMask() {
  if (!repaintCanvasRef.value?.undo()) return;
  hasRepaintMask.value = repaintCanvasRef.value.hasDrawnMask();
  syncMaskHistory();
}

function redoRepaintMask() {
  if (!repaintCanvasRef.value?.redo()) return;
  hasRepaintMask.value = repaintCanvasRef.value.hasDrawnMask();
  syncMaskHistory();
}

function handleMaskChange(value: boolean) {
  hasRepaintMask.value = value;
  syncMaskHistory();
}

function applySource(sourceUrl: string, maskUrl = "", promptText = "") {
  revokeObjectUrl(sourcePreviewUrl.value);
  sourcePreviewUrl.value = "";
  sourceImageUrl.value = sourceUrl;
  maskOverlayUrl.value = maskUrl;
  const nextPrompt = (promptText || "").trim();
  prompt.value = nextPrompt === "智能抠图" ? "" : nextPrompt;
  if (maskUrl) {
    inputMode.value = "smear";
  }
  resetMaskState();
  void nextTick(() => {
    if (!maskUrl) {
      repaintCanvasRef.value?.clearMask();
    }
  });
}

function clear() {
  prompt.value = "";
  inputMode.value = "prompt";
  removeSourceImage();
  clearRepaintMask();
}

async function handleSubmit() {
  if (!auth.isLoggedIn) {
    requestLogin();
    return;
  }
  if (sourceUploading.value || (sourcePreviewUrl.value && !sourceImageUrl.value.trim())) {
    message.warning(sourceUploading.value ? "原图上传中，请稍候再试" : "原图未上传完成，请重新上传后再试");
    return;
  }
  if (!sourceImageUrl.value.trim()) {
    message.warning("请先上传目标图");
    return;
  }

  const sourceUrl = sourceImageUrl.value.trim();
  let maskUrl = "";
  repaintCanvasRef.value?.commitPendingMask();
  const paintedMask = hasRepaintMask.value || Boolean(repaintCanvasRef.value?.hasDrawnMask());
  if (paintedMask) {
    if (!sourceUrl) {
      message.warning("请先上传原图后再涂抹");
      return;
    }
    const maskBlob = await repaintCanvasRef.value?.exportMaskBlob();
    if (!maskBlob) {
      message.warning("蒙版生成失败，请重新涂抹后再试");
      return;
    }
    maskUploading.value = true;
    try {
      const { uploadReferenceImage } = await import("@/api/upload");
      const maskFile = new File([maskBlob], `mask-${Date.now()}.png`, { type: "image/png" });
      const uploaded = await uploadReferenceImage(maskFile, "mask");
      maskUrl = uploaded.url;
      if (!maskUrl) {
        message.error("蒙版上传失败，请重试");
        return;
      }
    } catch {
      message.error("蒙版上传失败，请重试");
      return;
    } finally {
      maskUploading.value = false;
    }
  }

  emit("submit", {
    prompt: isSmearMode.value ? "" : prompt.value.trim(),
    sourceImageUrl: sourceUrl,
    maskImageUrl: maskUrl,
  });
}

defineExpose({
  applySource,
  clear,
});
</script>

<template>
  <section class="smart-cutout-panel">
    <div class="settings-scroll">
      <div class="cutout-mode-switch">
        <button
          type="button"
          class="cutout-mode-btn"
          :class="{ active: inputMode === 'prompt' }"
          @click="inputMode = 'prompt'"
        >
          提示词
        </button>
        <button
          type="button"
          class="cutout-mode-btn"
          :class="{ active: inputMode === 'smear' }"
          @click="inputMode = 'smear'"
        >
          涂抹
        </button>
      </div>

      <div v-if="!isSmearMode" class="field-block">
        <div class="panel-head">
          <h3>提示词</h3>
          <span class="panel-hint">(可选)</span>
        </div>
        <a-textarea
          v-model:value="prompt"
          :rows="5"
          placeholder="描述要抠出的主体或效果。不填写时，将按整张图去背景抠图"
          class="prompt-input"
          :maxlength="TASK_PROMPT_MAX_LENGTH"
          allow-clear
          show-count
        />
      </div>

      <div class="field-block">
        <div class="panel-head">
          <h3>{{ isSmearMode ? "涂抹抠图区域" : "目标图" }}</h3>
          <span class="panel-hint">{{ isSmearMode ? "(可选，涂抹后仅抠出选区)" : "(必填)" }}</span>
        </div>

        <input
          ref="sourceInput"
          class="native-file-input"
          type="file"
          :accept="imageFileAccept"
          @change="handleSourceFileChange"
        />

        <div
          v-if="!sourceDisplayUrl"
          class="source-upload-empty"
          @click="triggerSourceUpload"
        >
          <a-spin
            v-if="sourceUploading || sourcePickerOpening"
            :indicator="h(LoadingOutlined, { style: accentIndicatorStyle })"
          />
          <template v-else>
            <CloudUploadOutlined class="source-upload-icon" />
            <div class="source-upload-title">点击上传目标图</div>
            <div class="source-upload-desc">
              {{ isSmearMode ? "请先上传目标图，上传后可涂抹需要抠出的区域" : "请上传需要抠图的目标图" }}
            </div>
          </template>
        </div>

        <template v-else>
          <div v-if="isSmearMode" class="repaint-status-card" :class="{ ready: hasRepaintMask }">
            <div class="repaint-status-title">
              {{ hasRepaintMask ? "已选择抠图区域" : "可涂抹需要抠出的区域" }}
            </div>
            <div class="repaint-status-desc">
              {{ hasRepaintMask
                ? "提交后只会抠出已涂抹部分，未涂抹区域将作为背景去掉。"
                : "不涂抹则只使用原图作为参考，不会上传蒙版。" }}
            </div>
            <div v-if="sourceUploading || (!sourceImageUrl && sourcePreviewUrl)" class="repaint-status-uploading">
              {{ sourceUploading ? "原图上传中，完成后可提交任务" : "原图上传未完成，请重新上传后再试" }}
            </div>
          </div>

          <div class="repaint-canvas-shell" :class="{ preview: !isSmearMode }">
            <button type="button" class="canvas-remove-btn" @click.stop="removeSourceImage">
              <CloseOutlined />
            </button>
            <RepaintCanvas
              ref="repaintCanvasRef"
              :image-url="sourceDisplayUrl"
              :mask-url="resolveImageUrl(maskOverlayUrl)"
              :brush-size="brushSize"
              :tool="repaintTool"
              :line-color="repaintLineColor"
              @mask-change="handleMaskChange"
            />
          </div>

          <template v-if="isSmearMode">

          <div class="repaint-toolbar">
            <a-tooltip title="画笔">
              <button
                type="button"
                class="tool-btn"
                :class="{ active: repaintTool === 'paint' }"
                @click="repaintTool = 'paint'"
              >
                <EditOutlined />
              </button>
            </a-tooltip>
            <a-tooltip title="擦除">
              <button
                type="button"
                class="tool-btn"
                :class="{ active: repaintTool === 'erase' }"
                @click="repaintTool = 'erase'"
              >
                <ClearOutlined />
              </button>
            </a-tooltip>
            <a-tooltip title="矩形">
              <button
                type="button"
                class="tool-btn"
                :class="{ active: repaintTool === 'rect' }"
                @click="repaintTool = 'rect'"
              >
                <svg viewBox="0 0 24 24" class="shape-tool-icon" aria-hidden="true">
                  <rect x="5" y="6" width="14" height="12" rx="2.5" />
                </svg>
              </button>
            </a-tooltip>
            <a-tooltip title="圆形">
              <button
                type="button"
                class="tool-btn"
                :class="{ active: repaintTool === 'circle' }"
                @click="repaintTool = 'circle'"
              >
                <svg viewBox="0 0 24 24" class="shape-tool-icon" aria-hidden="true">
                  <circle cx="12" cy="12" r="6.5" />
                </svg>
              </button>
            </a-tooltip>
            <a-tooltip title="文字">
              <button
                type="button"
                class="tool-btn"
                :class="{ active: repaintTool === 'text' }"
                @click="repaintTool = 'text'"
              >
                <FontSizeOutlined />
              </button>
            </a-tooltip>
            <div class="toolbar-divider" />
            <div class="toolbar-slider">
              <a-slider v-model:value="brushSize" :min="12" :max="60" class="brush-slider" />
            </div>
            <div class="brush-preview" :style="getRepaintBrushPreviewStyle()" />
            <div class="repaint-color-group">
              <a-tooltip v-for="color in REPAINT_COLOR_OPTIONS" :key="color.value" :title="color.label">
                <button
                  type="button"
                  class="repaint-color-chip"
                  :class="{ active: repaintLineColor === color.value }"
                  :style="{ '--repaint-color': color.value }"
                  @click="repaintLineColor = color.value"
                >
                  <span class="repaint-color-chip-swatch" />
                </button>
              </a-tooltip>
            </div>
            <div class="toolbar-divider" />
            <a-tooltip title="清空选区">
              <button type="button" class="tool-btn" @click="clearRepaintMask">
                <ReloadOutlined />
              </button>
            </a-tooltip>
            <a-tooltip title="后退">
              <button
                type="button"
                class="tool-btn"
                :disabled="!canUndoMask"
                @click="undoRepaintMask"
              >
                <svg viewBox="0 0 24 24" class="tool-btn-icon" aria-hidden="true">
                  <path d="M10 7 5 12l5 5" />
                  <path d="M6 12h7a6 6 0 0 1 6 6" />
                </svg>
              </button>
            </a-tooltip>
            <a-tooltip title="前进">
              <button
                type="button"
                class="tool-btn"
                :disabled="!canRedoMask"
                @click="redoRepaintMask"
              >
                <svg viewBox="0 0 24 24" class="tool-btn-icon" aria-hidden="true">
                  <path d="m14 7 5 5-5 5" />
                  <path d="M18 12h-7a6 6 0 0 0-6 6" />
                </svg>
              </button>
            </a-tooltip>
          </div>
          <div class="mask-tip">
            支持画笔、擦除、矩形、圆形和文字选区，可切换圈选线条颜色；选择文字工具后点击图片即可原地输入。
          </div>
          </template>
        </template>
      </div>
    </div>

    <div v-if="showSizeSettings" class="settings-size">
      <div class="settings-row settings-row-inline">
        <div v-if="!hideAspectRatio && !customSizeEnabled" class="setting-item setting-item-inline">
          <label>宽高比</label>
          <AspectRatioPicker v-model="size" :options="sizeOptions" />
        </div>
        <div v-else-if="customSizeEnabled" class="setting-item setting-item-inline">
          <label>宽度</label>
          <div class="custom-size-input-wrap">
            <a-input-number
              :value="customWidth"
              class="warm-input-number custom-size-input"
              :class="{ 'is-invalid': !!customWidthError }"
              :step="customSizeStep"
              :precision="0"
              :parser="parseCustomSizeInput"
              :formatter="formatCustomSizeInput"
              :status="customWidthError ? 'error' : undefined"
              @update:value="emit('update:customWidth', $event)"
            />
            <span class="custom-size-unit">px</span>
          </div>
          <div v-if="customWidthError" class="custom-size-error">{{ customWidthError }}</div>
        </div>
        <div v-if="!hideResolution && !customSizeEnabled" class="setting-item setting-item-inline">
          <label>分辨率</label>
          <OptionGridPicker
            v-model="resolution"
            :options="resolutionOptions"
            panel-title="选择分辨率"
            placeholder="选择分辨率"
          />
        </div>
        <div v-else-if="customSizeEnabled" class="setting-item setting-item-inline custom-size-height-col">
          <span class="custom-size-x" aria-hidden="true">×</span>
          <label>高度</label>
          <div class="custom-size-input-wrap">
            <a-input-number
              :value="customHeight"
              class="warm-input-number custom-size-input"
              :class="{ 'is-invalid': !!customHeightError }"
              :step="customSizeStep"
              :precision="0"
              :parser="parseCustomSizeInput"
              :formatter="formatCustomSizeInput"
              :status="customHeightError ? 'error' : undefined"
              @update:value="emit('update:customHeight', $event)"
            />
            <span class="custom-size-unit">px</span>
          </div>
          <div v-if="customHeightError" class="custom-size-error">{{ customHeightError }}</div>
        </div>
        <div
          v-if="showCustomSizeToggle"
          class="setting-item setting-item-inline custom-size-toggle-col"
        >
          <label class="custom-size-toggle-spacer" aria-hidden="true">&nbsp;</label>
          <div class="aspect-ratio-auto-row custom-size-toggle-row">
            <a-switch
              :checked="customSizeEnabled"
              size="small"
              class="aspect-ratio-auto-switch"
              @change="onCustomSizeSwitch"
            />
            <div class="aspect-ratio-auto-text">
              <span class="aspect-ratio-auto-label">自定义分辨率</span>
              <a-tooltip
                overlay-class-name="custom-size-help-tooltip"
                placement="top"
                :get-popup-container="getBodyPopupContainer"
              >
                <template #title>
                  <div class="custom-size-help-tip">
                    <div>开启后可手动输入宽高像素值：</div>
                    <ul>
                      <li>宽高须为 16 的倍数</li>
                      <li>长短边比例不超过 3:1</li>
                      <li>最大边长不超过 3840px</li>
                      <li>总像素数不得低于 655360px</li>
                    </ul>
                  </div>
                </template>
                <button type="button" class="aspect-ratio-auto-help" aria-label="自定义分辨率说明">
                  <QuestionCircleOutlined />
                </button>
              </a-tooltip>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="settings-footer">
      <a-button
        type="primary"
        block
        size="large"
        :loading="sourceUploading || maskUploading || submitting"
        :disabled="!canSubmit"
        class="generate-btn"
        @click="handleSubmit"
      >
        <template #icon><ThunderboltOutlined /></template>
        {{ submitButtonText }}
      </a-button>
    </div>
    <ImageSourceActionSheet
      v-if="imageSourceSheetOpen"
      @camera="pickFromCamera"
      @gallery="pickFromGallery"
      @files="pickFromFiles"
      @cancel="cancelImageSourceSheet"
    />
  </section>
</template>

<style scoped lang="scss">
.smart-cutout-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.settings-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 10px 0 4px;
}

.settings-size {
  position: relative;
  z-index: 3;
  flex-shrink: 0;
  padding: 12px 10px 0 4px;
  background: transparent;
}

.settings-footer {
  position: relative;
  z-index: 3;
  flex-shrink: 0;
  margin-top: 0;
  padding-top: 8px;
  background: transparent;
}

.native-file-input {
  position: fixed;
  left: -9999px;
  top: 0;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: var(--config-title-gap);

  h3 {
    font-size: 14px;
    line-height: 1.35;
    color: var(--config-title-color);
    margin: 0;
    font-weight: 700;
  }
}

.panel-hint {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  line-height: 1.5;
}

.cutout-mode-switch {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.cutout-mode-btn {
  flex: 1;
  height: 36px;
  border: 1px solid var(--theme-panel-border-strong);
  border-radius: 999px;
  background: var(--theme-panel-bg-soft);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft);

  &.active {
    background: var(--theme-accent);
    border-color: transparent;
    color: var(--theme-accent-contrast);
  }
}

.field-block + .field-block,
.field-block + .settings-row {
  margin-top: 16px;
}

.settings-row {
  display: flex;
  gap: 16px;
}

.settings-row-inline {
  align-items: stretch;
}

.setting-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--config-title-gap);

  label {
    color: var(--config-title-color);
    font-size: 15px;
    font-weight: 700;
    line-height: 1.4;
  }
}

.setting-item-inline {
  flex: 1 1 0;
  align-items: stretch;
  gap: 10px;

  label {
    margin: 0;
    white-space: normal;
  }

  :deep(.option-grid-picker) {
    display: flex;
    width: 100%;
  }

  :deep(.option-grid-trigger) {
    width: 100%;
    justify-content: space-between;
  }
}

.custom-size-toggle-col {
  flex: 0 0 auto;
  justify-content: flex-start;
}

.custom-size-toggle-spacer {
  visibility: hidden;
  user-select: none;
}

.custom-size-toggle-col .custom-size-toggle-row {
  min-height: 40px;
}

.custom-size-height-col {
  position: relative;
}

.custom-size-x {
  position: absolute;
  top: calc(1.4em + 10px);
  left: 0;
  display: flex;
  align-items: center;
  height: 40px;
  transform: translateX(calc(-50% - 8px));
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
  pointer-events: none;
}

.custom-size-error {
  color: #d4380d;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
}

.setting-item-inline :deep(.custom-size-input.is-invalid.ant-input-number),
.setting-item-inline :deep(.custom-size-input.ant-input-number-status-error) {
  border-color: #d4380d !important;
}

.custom-size-input-wrap {
  position: relative;
  width: 100%;
}

.custom-size-unit {
  position: absolute;
  top: 0;
  right: 28px;
  bottom: 0;
  display: flex;
  align-items: center;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  pointer-events: none;
}

.setting-item-inline :deep(.custom-size-input.ant-input-number) {
  display: flex;
  align-items: center;
  width: 100%;
  height: 40px;
  min-height: 40px;
  border: 1px solid var(--theme-control-border-strong) !important;
  border-radius: 16px !important;
  background: var(--theme-field-bg, var(--theme-control-bg)) !important;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 10px 22px var(--theme-shadow-soft) !important;
}

.setting-item-inline :deep(.custom-size-input.ant-input-number:hover),
.setting-item-inline :deep(.custom-size-input.ant-input-number-focused) {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-field-hover-bg, var(--theme-control-hover-bg)) !important;
}

.setting-item-inline :deep(.custom-size-input.ant-input-number .ant-input-number-input) {
  height: 40px;
  padding: 0 44px 0 12px;
  font-size: 14px;
  font-weight: 600;
  line-height: 40px;
  ime-mode: disabled;
  background: transparent !important;
}

.aspect-ratio-auto-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
}

.aspect-ratio-auto-row :deep(.aspect-ratio-auto-switch.ant-switch) {
  background: var(--theme-control-bg) !important;
  border: none !important;
  box-shadow: inset 0 0 0 1px var(--theme-control-border) !important;
}

.aspect-ratio-auto-row :deep(.aspect-ratio-auto-switch.ant-switch.ant-switch-small .ant-switch-handle) {
  top: 2px;
}

.aspect-ratio-auto-row :deep(.aspect-ratio-auto-switch.ant-switch.ant-switch-small .ant-switch-handle::before) {
  background: var(--theme-accent) !important;
  box-shadow: none !important;
}

.aspect-ratio-auto-row :deep(.aspect-ratio-auto-switch.ant-switch:hover:not(.ant-switch-disabled)) {
  background: var(--theme-control-hover-bg) !important;
  box-shadow: inset 0 0 0 1px var(--theme-border-strong) !important;
}

.aspect-ratio-auto-row :deep(.aspect-ratio-auto-switch.ant-switch.ant-switch-checked) {
  background: var(--theme-control-active) !important;
  box-shadow: none !important;
}

.aspect-ratio-auto-row :deep(.aspect-ratio-auto-switch.ant-switch.ant-switch-checked .ant-switch-handle::before) {
  background: #ffffff !important;
}

.aspect-ratio-auto-row :deep(.aspect-ratio-auto-switch.ant-switch.ant-switch-checked:hover:not(.ant-switch-disabled)) {
  background: var(--theme-control-active) !important;
  box-shadow: none !important;
}

.aspect-ratio-auto-text {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.aspect-ratio-auto-label {
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}

.aspect-ratio-auto-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition:
    color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.aspect-ratio-auto-help:hover,
.aspect-ratio-auto-help:focus-visible {
  color: var(--theme-accent);
  background: rgba(var(--theme-accent-rgb), 0.08);
}

.prompt-input {
  border-radius: 16px;
}

.source-preview-shell {
  position: relative;
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
}

.source-preview-image {
  width: 100%;
  display: block;
  max-height: 420px;
  object-fit: contain;
}

.source-preview-shell:hover .canvas-remove-btn,
.source-preview-shell:focus-within .canvas-remove-btn {
  opacity: 1;
  transform: scale(1);
}

.source-upload-empty {
  min-height: 280px;
  padding: 26px 20px;
  border-radius: 20px;
  border: 2px dashed var(--theme-panel-border-strong);
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  cursor: pointer;
  transition: border-color var(--motion-duration-fast) var(--motion-ease-soft), transform var(--motion-duration-fast) var(--motion-ease-soft), box-shadow var(--motion-duration-base) var(--motion-ease-soft);

  &:hover {
    border-color: var(--theme-border-strong);
    transform: translateY(-2px);
    box-shadow: 0 16px 28px var(--theme-shadow-soft);
  }

  &:active {
    transform: scale(0.99);
  }
}

.source-upload-icon {
  font-size: 30px;
  color: var(--theme-accent);
}

.source-upload-title {
  margin-top: 12px;
  font-size: 16px;
  font-weight: 700;
  color: var(--theme-title);
}

.source-upload-desc {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.repaint-status-card {
  margin-bottom: 14px;
  padding: 14px 16px;
  border-radius: 16px;
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
  border: 1px solid var(--theme-panel-border);
  transition: transform var(--motion-duration-base) var(--motion-ease-soft), box-shadow var(--motion-duration-base) var(--motion-ease-soft), border-color var(--motion-duration-base) var(--motion-ease-soft);

  &.ready {
    background: linear-gradient(180deg, var(--theme-panel-bg-strong), var(--theme-panel-bg-soft));
    border-color: var(--theme-border-strong);
  }
}

.repaint-status-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 24px var(--theme-shadow-soft);
}

.repaint-status-title {
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 700;
}

.repaint-status-desc {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.7;
}

.repaint-status-uploading {
  margin-top: 8px;
  color: var(--theme-accent-text);
  font-size: 12px;
  font-weight: 700;
}

.repaint-canvas-shell {
  position: relative;
  border-radius: 18px;
}

.repaint-canvas-shell.preview :deep(.mask-canvas) {
  pointer-events: none;
  cursor: default;
}

.canvas-remove-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  width: 40px;
  height: 40px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 14px;
  background: rgba(38, 38, 42, 0.84);
  color: rgba(255, 255, 255, 0.92);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(8px);
  opacity: 0;
  transform: scale(0.92);
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    background: rgba(48, 48, 54, 0.94);
    border-color: rgba(255, 255, 255, 0.24);
    transform: translateY(-1px) scale(1.03);
  }

  &:active {
    transform: scale(0.94);
  }
}

.repaint-canvas-shell:hover .canvas-remove-btn,
.repaint-canvas-shell:focus-within .canvas-remove-btn {
  opacity: 1;
  transform: scale(1);
}

.repaint-toolbar {
  margin-top: 14px;
  padding: 9px 12px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(46, 46, 52, 0.96), rgba(34, 34, 38, 0.96));
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.18);
}

.tool-btn {
  width: 38px;
  height: 38px;
  border: 1px solid transparent;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.9);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  cursor: pointer;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.12);
    transform: translateY(-2px);
  }

  &.active {
    background: linear-gradient(180deg, rgba(116, 107, 255, 0.9), rgba(95, 91, 240, 0.9));
    color: #fff;
    border-color: rgba(170, 167, 255, 0.38);
    box-shadow: 0 10px 18px rgba(90, 87, 230, 0.24);
  }

  &:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  &:active:not(:disabled) {
    transform: scale(0.95);
  }
}

.tool-btn-icon,
.shape-tool-icon {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  stroke-width: 1.9;
  stroke-linecap: round;
  stroke-linejoin: round;
  fill: none;
  flex-shrink: 0;
}

.toolbar-divider {
  width: 1px;
  height: 30px;
  background: rgba(255, 255, 255, 0.12);
}

.toolbar-slider {
  flex: 1;
  min-width: 120px;
  max-width: 180px;
}

.brush-preview {
  flex: 0 0 auto;
  min-width: 10px;
  min-height: 10px;
  max-width: 34px;
  max-height: 34px;
  border-radius: 50%;
  background: rgba(255, 171, 37, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.56);
  box-shadow:
    0 0 0 6px rgba(255, 255, 255, 0.06),
    0 4px 10px rgba(0, 0, 0, 0.16);
}

.repaint-color-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.repaint-color-chip {
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-visible {
    transform: translateY(-1px);
    border-color: rgba(255, 255, 255, 0.24);
    background: rgba(255, 255, 255, 0.12);
  }

  &.active {
    border-color: rgba(255, 255, 255, 0.38);
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.14);
  }
}

.repaint-color-chip-swatch {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--repaint-color);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.2),
    0 4px 10px rgba(0, 0, 0, 0.18);
}

.brush-slider {
  margin: 0 4px;

  :deep(.ant-slider-rail) {
    height: 8px;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 999px;
  }

  :deep(.ant-slider-track) {
    height: 8px;
    background: #6d6cff;
    border-radius: 999px;
  }

  :deep(.ant-slider-handle) {
    width: 24px;
    height: 24px;
    margin-top: -8px;
    border: none;
    background: transparent;
    box-shadow: none;

    &::after {
      width: 24px;
      height: 24px;
      border-color: #6d6cff;
      background: #fff;
      box-shadow: 0 4px 12px rgba(57, 56, 138, 0.32);
    }
  }
}

.mask-tip {
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.generate-btn {
  margin-top: 10px;
  height: 48px;
  border-radius: 16px;
  font-size: 15px;
  font-weight: 700;
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  border: none !important;
  box-shadow: 0 18px 32px var(--theme-shadow-strong) !important;

  &:hover,
  &:focus {
    background: var(--primary-dark) !important;
    box-shadow: 0 20px 34px var(--theme-shadow-strong) !important;
    transform: translateY(-2px);
  }

  &:disabled {
    background: var(--theme-control-hover-bg) !important;
    color: var(--text-muted) !important;
    box-shadow: none !important;
  }

  &:active {
    transform: scale(0.97);
  }
}

@media (max-width: 960px) {
  .settings-scroll {
    overflow-y: visible;
    padding: 0;
  }

  .settings-size {
    padding: 12px 0 0;
  }

  .settings-row {
    flex-direction: column;
  }

  .settings-row-inline {
    flex-direction: row;
  }
}

@media (prefers-reduced-motion: reduce) {
  .source-upload-empty,
  .repaint-status-card,
  .canvas-remove-btn,
  .tool-btn,
  .generate-btn {
    transition: none !important;
  }
}
</style>

<style>
.custom-size-help-tooltip .custom-size-help-tip {
  text-align: left;
  line-height: 1.6;
}

.custom-size-help-tooltip .custom-size-help-tip ul {
  margin: 6px 0 0;
  padding-left: 1.15em;
}

.custom-size-help-tooltip .custom-size-help-tip li {
  list-style: disc;
}
</style>
