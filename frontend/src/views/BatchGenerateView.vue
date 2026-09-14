<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";
import { useRouter } from "vue-router";
import { message, Modal } from "ant-design-vue";
import {
  CheckCircleFilled,
  CloseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  EyeOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  CopyOutlined,
  UploadOutlined,
} from "@ant-design/icons-vue";
import { getMe } from "@/api/auth";
import { getTaskScenes } from "@/api/config";
import { deleteHistoryTask, fetchHistory } from "@/api/history";
import { getDisplayImageUrl, getDownloadUrl, getPreviewImageUrl, resolveImageUrl } from "@/api/images";
import { createTask, getTasks } from "@/api/tasks";
import {
  isImageUploadTooLarge,
  MAX_IMAGE_UPLOAD_SIZE_TEXT,
  uploadReferenceImage,
} from "@/api/upload";
import AspectRatioPicker from "@/components/generate/AspectRatioPicker.vue";
import ModelCategorySelect from "@/components/generate/ModelCategorySelect.vue";
import OptionGridPicker from "@/components/generate/OptionGridPicker.vue";
import FeedbackDialog from "@/components/feedback/FeedbackDialog.vue";
import HistoryDetailDialog from "@/components/history/HistoryDetailDialog.vue";
import {
  formatGenerationErrorMessage,
  getPreferredGenerationErrorMessage,
} from "@/lib/generationErrors";
import { withBaseUrl } from "@/lib/assets";
import {
  CUSTOM_SIZE_DEFAULT_SIDE,
  CUSTOM_SIZE_PIXEL_MULTIPLE,
  applyCustomDimensionChange,
  createDigitsOnlyDirective,
  formatCustomSizeInput,
  formatCustomSizeValue,
  getCustomDimensionError,
  getCustomSizeBounds,
  parseCustomSizeInput,
  parseCustomSizeValue,
  type CustomSizeBounds,
} from "@/lib/customSize";
import { useAuthStore } from "@/stores/auth";
import type { GenerationModelOption, ImageResult, SceneOptionItem, TaskResult, TaskSceneConfig, UserHistoryCard } from "@/types";

type BatchCardStatus = "idle" | "queued_local" | "submitting" | TaskResult["status"];
type UploadItemStatus = "uploading" | "success" | "failed";
type BatchSceneMode = "generate" | "image_edit";
type PasteApplyScope = "global" | "all_cards" | "single_card";

interface UploadPreviewItem {
  id: string;
  localUrl: string;
  remoteUrl: string;
  status: UploadItemStatus;
  objectUrl?: string;
}

interface BatchGenerateCard {
  id: string;
  sceneType: BatchSceneMode;
  prompt: string;
  model: string;
  size: string;
  resolution: string;
  customSize: string;
  customSizeEnabled: boolean;
  customWidth: number;
  customHeight: number;
  numImages: number;
  referenceItems: UploadPreviewItem[];
  status: BatchCardStatus;
  taskId: string | null;
  taskIds: string[];
  images: ImageResult[];
  errorMessage: string;
  creditRefunded: boolean;
  netCreditCost: number | null;
  createdAt: string | null;
  dragActive: boolean;
  dragCounter: number;
  highlighted: boolean;
  cancelRequested: boolean;
}

interface GlobalBatchSettings {
  sceneType: BatchSceneMode;
  model: string;
  prompt: string;
  size: string;
  resolution: string;
  customSize: string;
  customSizeEnabled: boolean;
  customWidth: number;
  customHeight: number;
  numImages: number;
}

interface BatchGenerateDraftCard {
  sceneType: BatchSceneMode;
  prompt: string;
  model: string;
  size: string;
  resolution: string;
  customSize: string;
  customSizeEnabled?: boolean;
  customWidth?: number;
  customHeight?: number;
  numImages: number;
  referenceImages: string[];
  status: BatchCardStatus;
  taskId: string | null;
  taskIds: string[];
  images: ImageResult[];
  errorMessage: string;
  creditRefunded: boolean;
  netCreditCost: number | null;
  createdAt: string | null;
}

interface BatchGenerateDraftState {
  globalSettings: GlobalBatchSettings;
  globalReferenceImages: string[];
  cards: BatchGenerateDraftCard[];
}

const auth = useAuthStore();
const router = useRouter();
const loginModalVisible = inject<Ref<boolean>>("loginModalVisible")!;
const openPurchaseEntry = inject<() => void>("openPurchaseEntry");

const MAX_BATCH_CARDS = 12;
const DEFAULT_BATCH_CARDS = 3;
const MAX_IMAGES_PER_CARD = 8;
const BATCH_IMAGE_COUNT_OPTIONS: SceneOptionItem[] = Array.from(
  { length: MAX_IMAGES_PER_CARD },
  (_, index) => {
    const value = String(index + 1);
    return { label: value, value };
  },
);
const POLL_INTERVAL_MS = 5000;
const SUBMISSION_RETRY_DELAY_MS = 5200;
const DEFAULT_IMAGE_SIZE_OPTIONS: SceneOptionItem[] = [
  { label: "1K", value: "1K" },
  { label: "2K", value: "2K" },
  { label: "4K", value: "4K" },
];
const DEFAULT_ASPECT_RATIO_OPTIONS: SceneOptionItem[] = [
  { label: "■  1:1", value: "1:1" },
  { label: "▮  2:3", value: "2:3" },
  { label: "▬  3:2", value: "3:2" },
  { label: "▮  3:4", value: "3:4" },
  { label: "▬  4:3", value: "4:3" },
  { label: "▮  9:16", value: "9:16" },
  { label: "▬  16:9", value: "16:9" },
];
const ACTIVE_BATCH_HISTORY_PAGE_SIZE = 20;
const failedResultAsset = withBaseUrl("failed-result.svg");
const BATCH_GENERATE_DRAFT_KEY = "batchGenerateDraft";
const ASPECT_RATIO_AUTO_DETECT_STORAGE_KEY = "generateAspectRatioAutoDetectEnabled";

const sceneConfigLoading = ref(true);
const sceneConfigLoaded = ref(false);
const taskScenes = ref<TaskSceneConfig[]>([]);
const cards = ref<BatchGenerateCard[]>([]);
const globalSettings = ref<GlobalBatchSettings>({
  sceneType: "image_edit",
  model: "",
  prompt: "",
  size: "",
  resolution: "",
  customSize: "",
  customSizeEnabled: false,
  customWidth: CUSTOM_SIZE_DEFAULT_SIDE,
  customHeight: CUSTOM_SIZE_DEFAULT_SIDE,
  numImages: 1,
});
const aspectRatioAutoDetectEnabled = ref(readStoredAspectRatioAutoDetectEnabled());
const vDigitsOnly = createDigitsOnlyDirective();
const globalReferenceItems = ref<UploadPreviewItem[]>([]);
const taskPollingInFlight = ref(false);
const previewVisible = ref(false);
const previewCurrent = ref("");
const detailOpen = ref(false);
const detailItem = ref<UserHistoryCard | null>(null);
const detailCardId = ref("");
const detailImageIndex = ref(0);
const feedbackDialogOpen = ref(false);
const feedbackTarget = ref<{
  taskId: string;
  model?: string;
  prompt: string;
  createdAt: string;
} | null>(null);

const globalFileInput = ref<HTMLInputElement | null>(null);
const cardFileInputs = new Map<string, HTMLInputElement>();
const cardReferenceUploadBlockRefs = new Map<string, HTMLElement>();
const globalReferenceDragActive = ref(false);
const globalReferenceDragCounter = ref(0);
const draftHydrationReady = ref(false);
const pasteDialogVisible = ref(false);
const pasteDialogSubmitting = ref(false);
const pasteDialogScope = ref<PasteApplyScope>("global");
const pasteDialogTargetCardIds = ref<string[]>([]);
const pendingPasteFiles = ref<File[]>([]);
const pendingPastePreviewUrls = ref<string[]>([]);

let pollTimer: ReturnType<typeof setInterval> | null = null;
let queueTimer: ReturnType<typeof setTimeout> | null = null;
let submissionInFlightCount = 0;
let unbindGlobalReferenceDragHandlers: (() => void) | null = null;
const unbindCardReferenceDragHandlers = new Map<string, () => void>();

function makeId(prefix = "batch") {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function revokeObjectUrl(url?: string) {
  if (url?.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}

function createPendingImages(count = 1): ImageResult[] {
  return Array.from({ length: Math.max(0, count) }, (_, index) => ({
    id: -(Date.now() + index),
    image_url: "",
    status: "pending",
  }));
}

function createFailedImages(count = 1, errorMessage = ""): ImageResult[] {
  return Array.from({ length: Math.max(0, count) }, (_, index) => ({
    id: -(Date.now() + index),
    image_url: "",
    status: "failed",
    error_message: errorMessage,
  }));
}

function normalizeFailedCardImages(card: BatchGenerateCard) {
  if (card.status !== "failed") return;
  const count = Math.max(getCardRequestedImageCount(card), card.images.length, 1);
  if (!card.images.length) {
    card.images = createFailedImages(count, card.errorMessage);
    return;
  }
  card.images = card.images.map((image) => {
    if (image.status !== "pending") return image;
    return {
      ...image,
      status: "failed",
      error_message: image.error_message || card.errorMessage || "生成失败",
    };
  });
}

function normalizeNumImages(value: unknown, fallback = 1) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(MAX_IMAGES_PER_CARD, Math.max(1, Math.round(parsed)));
}

function getCardTaskIds(card: Pick<BatchGenerateCard, "taskId" | "taskIds">) {
  const ids = Array.isArray(card.taskIds)
    ? card.taskIds.map((id) => String(id || "").trim()).filter(Boolean)
    : [];
  if (ids.length) return Array.from(new Set(ids));
  const fallback = String(card.taskId || "").trim();
  return fallback ? [fallback] : [];
}

function syncCardTaskIds(card: BatchGenerateCard, taskIds: string[]) {
  const normalized = Array.from(new Set(taskIds.map((id) => String(id || "").trim()).filter(Boolean)));
  card.taskIds = normalized;
  card.taskId = normalized[0] || null;
}

function getCardRequestedImageCount(card: BatchGenerateCard) {
  return normalizeNumImages(card.numImages);
}

function isRemoteActiveCard(card: BatchGenerateCard) {
  if (card.status === "failed" || card.status === "idle" || card.status === "queued_local") return false;
  return ["submitting", "pending", "queued", "processing"].includes(card.status)
    || card.images.some((image) => image.status === "pending");
}

function getCardActiveImageCount(card: BatchGenerateCard) {
  if (!isRemoteActiveCard(card)) return 0;
  const pendingCount = card.images.filter((image) => image.status === "pending").length;
  if (pendingCount > 0) return pendingCount;
  const taskIds = getCardTaskIds(card);
  if (taskIds.length) return taskIds.length;
  return getCardRequestedImageCount(card);
}

function getSuccessImages(card: BatchGenerateCard) {
  return card.images.filter((image) => (
    image.status === "success" && Boolean(image.image_url || image.preview_url)
  ));
}

function getSlotTaskId(card: BatchGenerateCard, index: number) {
  return getCardTaskIds(card)[index] || "";
}

function ensureCardImageSlots(card: BatchGenerateCard, count: number) {
  const nextCount = Math.max(0, count);
  if (card.images.length === nextCount) return;
  if (card.images.length > nextCount) {
    card.images = card.images.slice(0, nextCount);
    return;
  }
  card.images = [...card.images, ...createPendingImages(nextCount - card.images.length)];
}

function hasIncompleteCardSlots(card: BatchGenerateCard) {
  if (card.status === "failed" || card.status === "idle" || card.status === "queued_local") return false;
  if (!getCardTaskIds(card).length) return false;
  if (["submitting", "pending", "queued", "processing"].includes(card.status)) return true;
  if (card.images.some((image) => image.status === "pending")) return true;
  return card.status === "success" && !getSuccessImages(card).length;
}

function refreshCardAggregateStatus(card: BatchGenerateCard) {
  if (["idle", "queued_local"].includes(card.status) && !getCardTaskIds(card).length) return;

  const images = card.images;
  if (!images.length) return;

  const hasPending = images.some((image) => image.status === "pending");
  const successCount = images.filter((image) => image.status === "success").length;
  const failedCount = images.filter((image) => image.status === "failed").length;

  if (hasPending) {
    if (!["submitting", "pending", "queued", "processing"].includes(card.status)) {
      card.status = "processing";
    }
    return;
  }

  if (failedCount === images.length) {
    card.status = "failed";
    return;
  }

  if (successCount > 0) {
    card.status = "success";
    if (failedCount === 0) card.errorMessage = "";
  }
}

function createReferenceItemFromRemote(url: string): UploadPreviewItem {
  return {
    id: makeId("ref"),
    localUrl: url,
    remoteUrl: url,
    status: "success",
  };
}

function createReferenceItemsFromRemoteUrls(urls: string[]) {
  return urls
    .map((url) => String(url || "").trim())
    .filter(Boolean)
    .map((url) => createReferenceItemFromRemote(url));
}

function readStoredAspectRatioAutoDetectEnabled() {
  if (typeof window === "undefined") return false;
  const storedValue = localStorage.getItem(ASPECT_RATIO_AUTO_DETECT_STORAGE_KEY);
  if (storedValue == null) return true;
  return storedValue === "1";
}

function writeStoredAspectRatioAutoDetectEnabled(enabled: boolean) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ASPECT_RATIO_AUTO_DETECT_STORAGE_KEY, enabled ? "1" : "0");
}

function parseAspectRatioPair(value?: string) {
  if (!value) return null;
  const normalized = value.trim();
  const ratioMatch = normalized.match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
  if (ratioMatch) {
    const width = Number(ratioMatch[1]);
    const height = Number(ratioMatch[2]);
    if (width > 0 && height > 0) return { width, height };
  }

  const sizeMatch = normalized.match(/^(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)$/);
  if (sizeMatch) {
    const width = Number(sizeMatch[1]);
    const height = Number(sizeMatch[2]);
    if (width > 0 && height > 0) return { width, height };
  }

  return null;
}

function loadImageDimensions(src: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.decoding = "async";
    image.onload = () => {
      if (image.naturalWidth > 0 && image.naturalHeight > 0) {
        resolve({ width: image.naturalWidth, height: image.naturalHeight });
        return;
      }
      reject(new Error("无法读取图片尺寸"));
    };
    image.onerror = () => reject(new Error("图片加载失败"));
    image.src = src;
  });
}

async function readImageDimensionsFromFile(file: File) {
  const objectUrl = URL.createObjectURL(file);
  try {
    return await loadImageDimensions(objectUrl);
  } finally {
    revokeObjectUrl(objectUrl);
  }
}

function cloneSuccessReferenceItems(items: UploadPreviewItem[]) {
  return items
    .filter((item) => item.status === "success" && item.remoteUrl)
    .map((item) => createReferenceItemFromRemote(item.remoteUrl));
}

function serializeCard(card: BatchGenerateCard): BatchGenerateDraftCard {
  const taskIds = getCardTaskIds(card);
  return {
    sceneType: card.sceneType,
    prompt: card.prompt,
    model: card.model,
    size: card.size,
    resolution: card.resolution,
    customSize: card.customSize,
    customSizeEnabled: card.customSizeEnabled,
    customWidth: card.customWidth,
    customHeight: card.customHeight,
    numImages: getCardRequestedImageCount(card),
    referenceImages: card.referenceItems
      .filter((item) => item.status === "success" && item.remoteUrl)
      .map((item) => item.remoteUrl),
    status: card.status,
    taskId: taskIds[0] || null,
    taskIds,
    images: card.images,
    errorMessage: card.errorMessage,
    creditRefunded: card.creditRefunded,
    netCreditCost: card.netCreditCost,
    createdAt: card.createdAt,
  };
}

function hydrateCardFromDraft(draft: BatchGenerateDraftCard): BatchGenerateCard {
  const taskIds = Array.isArray(draft.taskIds) && draft.taskIds.length
    ? Array.from(new Set(draft.taskIds.map((id) => String(id || "").trim()).filter(Boolean)))
    : (draft.taskId ? [String(draft.taskId)] : []);
  const numImages = normalizeNumImages(draft.numImages, Math.max(taskIds.length, draft.images?.length || 1, 1));
  const slotCount = Math.max(taskIds.length, Array.isArray(draft.images) ? draft.images.length : 0, draft.status === "idle" ? 0 : numImages);
  const card: BatchGenerateCard = {
    id: makeId("draft-card"),
    sceneType: draft.sceneType,
    prompt: draft.prompt || "",
    model: draft.model || getDefaultModelKey(draft.sceneType),
    size: draft.size || "",
    resolution: draft.resolution || "",
    customSize: draft.customSize || "",
    customSizeEnabled: Boolean(draft.customSizeEnabled),
    customWidth: Number(draft.customWidth || CUSTOM_SIZE_DEFAULT_SIDE),
    customHeight: Number(draft.customHeight || CUSTOM_SIZE_DEFAULT_SIDE),
    numImages,
    referenceItems: Array.isArray(draft.referenceImages)
      ? draft.referenceImages.map((url) => createReferenceItemFromRemote(url))
      : [],
    status: draft.status,
    taskId: taskIds[0] || null,
    taskIds,
    images: Array.isArray(draft.images) && draft.images.length
      ? draft.images
      : (draft.status === "failed"
        ? createFailedImages(slotCount || numImages, draft.errorMessage || "")
        : (draft.status === "success" || draft.status === "idle" ? [] : createPendingImages(slotCount || 1))),
    errorMessage: draft.errorMessage || "",
    creditRefunded: Boolean(draft.creditRefunded),
    netCreditCost: typeof draft.netCreditCost === "number" ? draft.netCreditCost : null,
    createdAt: draft.createdAt || null,
    dragActive: false,
    dragCounter: 0,
    highlighted: false,
    cancelRequested: false,
  };
  normalizeFailedCardImages(card);
  normalizeCardSelections(card);
  return card;
}

function highlightCard(card: BatchGenerateCard) {
  card.highlighted = false;
  window.setTimeout(() => {
    card.highlighted = true;
    window.setTimeout(() => {
      card.highlighted = false;
    }, 2400);
  }, 0);
}

function isCardMeaningfulForDraft(card: BatchGenerateCard) {
  return Boolean(
    card.prompt.trim()
    || card.referenceItems.some((item) => item.status === "success" && item.remoteUrl)
    || getCardTaskIds(card).length
    || card.images.length
    || card.errorMessage
    || card.status !== "idle",
  );
}

function shouldPersistBatchGenerateDraft() {
  const hasMeaningfulGlobalSettings = Boolean(
    globalSettings.value.prompt.trim()
    || globalReferenceItems.value.some((item) => item.status === "success" && item.remoteUrl),
  );

  return hasMeaningfulGlobalSettings || cards.value.some(isCardMeaningfulForDraft);
}

function getBatchGenerateDraftStorageKey() {
  const currentUserId = String(auth.user?.id || "").trim();
  return currentUserId ? `${BATCH_GENERATE_DRAFT_KEY}:${currentUserId}` : BATCH_GENERATE_DRAFT_KEY;
}

function persistBatchGenerateDraft() {
  try {
    const storageKey = getBatchGenerateDraftStorageKey();
    if (!shouldPersistBatchGenerateDraft()) {
      localStorage.removeItem(storageKey);
      return;
    }

    const payload: BatchGenerateDraftState = {
      globalSettings: { ...globalSettings.value },
      globalReferenceImages: globalReferenceItems.value
        .filter((item) => item.status === "success" && item.remoteUrl)
        .map((item) => item.remoteUrl),
      cards: cards.value.filter(isCardMeaningfulForDraft).map(serializeCard),
    };
    localStorage.setItem(storageKey, JSON.stringify(payload));
  } catch {
    // ignore storage errors
  }
}

function restoreBatchGenerateDraft() {
  try {
    const storageKey = getBatchGenerateDraftStorageKey();
    const raw = localStorage.getItem(storageKey);
    if (!raw) return false;
    const draft = JSON.parse(raw) as Partial<BatchGenerateDraftState>;
    if (draft.globalSettings) {
      globalSettings.value = {
        sceneType: draft.globalSettings.sceneType || "image_edit",
        model: draft.globalSettings.model || "",
        prompt: draft.globalSettings.prompt || "",
        size: draft.globalSettings.size || "",
        resolution: draft.globalSettings.resolution || "",
        customSize: draft.globalSettings.customSize || "",
        customSizeEnabled: Boolean(draft.globalSettings.customSizeEnabled),
        customWidth: Number(draft.globalSettings.customWidth || CUSTOM_SIZE_DEFAULT_SIDE),
        customHeight: Number(draft.globalSettings.customHeight || CUSTOM_SIZE_DEFAULT_SIDE),
        numImages: normalizeNumImages(draft.globalSettings.numImages, 1),
      };
    }
    globalReferenceItems.value = Array.isArray(draft.globalReferenceImages)
      ? draft.globalReferenceImages.map((url) => createReferenceItemFromRemote(url))
      : [];
    cards.value = Array.isArray(draft.cards)
      ? draft.cards.slice(0, MAX_BATCH_CARDS).map(hydrateCardFromDraft)
      : [];
    if (!shouldPersistBatchGenerateDraft()) {
      localStorage.removeItem(storageKey);
      cards.value = [];
      globalReferenceItems.value = [];
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

function toGenerationModelOption(scene: TaskSceneConfig): GenerationModelOption {
  return {
    model_key: scene.scene_key,
    model_label: scene.scene_label,
    model_description: scene.scene_description,
    display_name: scene.display_name,
    subtitle: scene.subtitle,
    sort_order: scene.sort_order,
    hide_aspect_ratio: scene.hide_aspect_ratio,
    hide_resolution: scene.hide_resolution,
    hide_custom_size: scene.hide_custom_size,
    custom_size_min: scene.custom_size_min,
    custom_size_max: scene.custom_size_max,
    custom_size_step: scene.custom_size_step,
    credit_cost: scene.credit_cost,
    resolution_credit_costs: scene.resolution_credit_costs || {},
    max_reference_images: scene.max_reference_images,
    aspect_ratio_options: scene.aspect_ratio_options,
    image_size_options: scene.image_size_options,
    custom_size_options: scene.custom_size_options,
    category_id: scene.category_id ?? null,
    category_name: scene.category_name ?? null,
    category_sort_order: scene.category_sort_order ?? null,
  };
}

const generationModels = computed(() => (
  taskScenes.value
    .filter((item) => item.scene_type === "generate" || item.scene_type === "image_edit")
    .filter((item) => item.scene_key !== "prompt_reverse" && item.scene_key !== "inpaint" && item.scene_key !== "smart_cutout")
    .map(toGenerationModelOption)
    .sort((a, b) => a.sort_order - b.sort_order)
));

const sceneTypeOptions = [
  { label: "文生图", value: "generate" },
  { label: "图编辑", value: "image_edit" },
] as const;

function getSceneTypeLabel(sceneType: BatchSceneMode) {
  return sceneType === "image_edit" ? "图编辑" : "文生图";
}

function getModelsBySceneType(sceneType: BatchSceneMode) {
  return generationModels.value
    .filter((item) => (
      taskScenes.value.find((scene) => scene.scene_key === item.model_key)?.scene_type === sceneType
    ))
    .sort((a, b) => a.sort_order - b.sort_order);
}

function getModelDisplayName(model: GenerationModelOption) {
  return model.display_name || model.model_label || model.model_key;
}

function getModelCreditSubtitle(modelKey: string, targetResolution = "") {
  return `消耗 ${resolveSceneCreditCost(modelKey, targetResolution)} 积分`;
}

function getModelSelectOptions(sceneType: BatchSceneMode, targetResolution = "") {
  return getModelsBySceneType(sceneType).map((model) => ({
    value: model.model_key,
    label: getModelDisplayName(model),
    description: getModelCreditSubtitle(model.model_key, targetResolution),
    sortOrder: model.sort_order,
    categoryId: model.category_id,
    categoryName: model.category_name,
    categorySortOrder: model.category_sort_order,
  }));
}

function getDefaultModelKey(sceneType: BatchSceneMode) {
  return getModelsBySceneType(sceneType)[0]?.model_key || generationModels.value[0]?.model_key || "";
}

const userCredits = computed(() => Number(auth.user?.credits || 0));
const activeRemoteImageCount = computed(() => cards.value.reduce((total, card) => (
  total + getCardActiveImageCount(card)
), 0));
const remainingSlots = computed(() => Math.max(MAX_BATCH_CARDS - activeRemoteImageCount.value, 0));
const remainingSubmissionSlots = computed(() => Math.max(MAX_BATCH_CARDS - submissionInFlightCount, 0));
const canAddMoreCards = computed(() => cards.value.length < MAX_BATCH_CARDS);
const hasFinishedCards = computed(() => cards.value.some((card) => ["success", "failed"].includes(card.status)));
const globalUploading = computed(() => globalReferenceItems.value.some((item) => item.status === "uploading"));
const pasteEligibleCards = computed(() => cards.value.filter((card) => card.sceneType === "image_edit" && !isCardLocked(card)));
const downloadableImages = computed(() => cards.value.flatMap((card) => getSuccessImages(card)));
const estimatedCreditTotal = computed(() => cards.value.reduce((total, card) => {
  if (!card.model) return total;
  return total + resolveSceneCreditCost(card.model, card.customSizeEnabled ? "" : card.resolution) * getCardRequestedImageCount(card);
}, 0));
const detailModelOptions = computed(() => (
  taskScenes.value.map((scene) => ({
    label: scene.scene_label,
    value: scene.scene_key,
  }))
));
const detailableCards = computed(() => cards.value.filter((card) => (
  card.images.length > 0 || card.status !== "idle"
)));
const detailCardIndex = computed(() => (
  detailableCards.value.findIndex((card) => card.id === detailCardId.value)
));
const hasDetailPrev = computed(() => detailCardIndex.value > 0);
const hasDetailNext = computed(() => (
  detailCardIndex.value >= 0 && detailCardIndex.value < detailableCards.value.length - 1
));

function getModelOption(modelKey: string) {
  return generationModels.value.find((item) => item.model_key === modelKey) || null;
}

function isImageEditModel(modelKey: string) {
  return taskScenes.value.find((item) => item.scene_key === modelKey)?.scene_type === "image_edit";
}

function getAspectRatioOptions(modelKey: string) {
  return getModelOption(modelKey)?.aspect_ratio_options?.length
    ? getModelOption(modelKey)!.aspect_ratio_options
    : DEFAULT_ASPECT_RATIO_OPTIONS;
}

function getResolutionOptions(modelKey: string) {
  return getModelOption(modelKey)?.image_size_options?.length
    ? getModelOption(modelKey)!.image_size_options
    : DEFAULT_IMAGE_SIZE_OPTIONS;
}

function hideAspectRatio(modelKey: string) {
  return Boolean(getModelOption(modelKey)?.hide_aspect_ratio);
}

function hideResolution(modelKey: string) {
  return Boolean(getModelOption(modelKey)?.hide_resolution);
}

function supportsCustomSize(modelKey: string) {
  return getModelOption(modelKey)?.hide_custom_size === false;
}

function getModelCustomSizeBounds(modelKey: string): CustomSizeBounds {
  const model = getModelOption(modelKey);
  return getCustomSizeBounds(model?.custom_size_min, model?.custom_size_max);
}

function syncCustomSizeValue(target: { customSize: string; customWidth: number; customHeight: number }) {
  target.customSize = formatCustomSizeValue(Number(target.customWidth), Number(target.customHeight));
}

function applyCustomSizeState(
  target: { customSize: string; customSizeEnabled: boolean; customWidth: number; customHeight: number },
  value?: string | null,
  enabled = Boolean(value),
) {
  const parsed = parseCustomSizeValue(value);
  if (!enabled || !parsed) {
    target.customSizeEnabled = false;
    target.customWidth = CUSTOM_SIZE_DEFAULT_SIDE;
    target.customHeight = CUSTOM_SIZE_DEFAULT_SIDE;
    target.customSize = "";
    return;
  }
  target.customSizeEnabled = true;
  target.customWidth = parsed.width;
  target.customHeight = parsed.height;
  target.customSize = formatCustomSizeValue(parsed.width, parsed.height);
}

function toggleCustomSize(
  target: { customSize: string; customSizeEnabled: boolean; customWidth: number; customHeight: number },
  enabled: boolean,
  modelKey: string,
) {
  if (!supportsCustomSize(modelKey)) {
    applyCustomSizeState(target, "", false);
    return;
  }
  target.customSizeEnabled = enabled;
  if (!enabled) {
    target.customSize = "";
    return;
  }
  const bounds = getModelCustomSizeBounds(modelKey);
  target.customWidth = applyCustomDimensionChange(target.customWidth, target.customWidth || CUSTOM_SIZE_DEFAULT_SIDE, bounds);
  target.customHeight = applyCustomDimensionChange(target.customHeight, target.customHeight || CUSTOM_SIZE_DEFAULT_SIDE, bounds);
  syncCustomSizeValue(target);
}

function getTargetCustomDimensionError(
  target: { customWidth: number; customHeight: number },
  modelKey: string,
  axis: "width" | "height",
) {
  const bounds = getModelCustomSizeBounds(modelKey);
  return axis === "width"
    ? getCustomDimensionError(Number(target.customWidth), Number(target.customHeight), bounds)
    : getCustomDimensionError(Number(target.customHeight), Number(target.customWidth), bounds);
}

function handleCustomWidthChange(
  target: { customSize: string; customWidth: number; customHeight: number },
  modelKey: string,
  value: number | string | null,
) {
  const bounds = getModelCustomSizeBounds(modelKey);
  target.customWidth = applyCustomDimensionChange(Number(target.customWidth), value, bounds);
  syncCustomSizeValue(target);
}

function handleCustomHeightChange(
  target: { customSize: string; customWidth: number; customHeight: number },
  modelKey: string,
  value: number | string | null,
) {
  const bounds = getModelCustomSizeBounds(modelKey);
  target.customHeight = applyCustomDimensionChange(Number(target.customHeight), value, bounds);
  syncCustomSizeValue(target);
}

function onGlobalCustomSizeToggle(checked: boolean | string | number) {
  toggleCustomSize(globalSettings.value, Boolean(checked), globalSettings.value.model);
}

function onCardCustomSizeToggle(card: BatchGenerateCard, checked: boolean) {
  if (isCardLocked(card)) return;
  toggleCustomSize(card, checked, card.model);
}

function getMaxReferenceImages(modelKey: string) {
  const configured = Number(getModelOption(modelKey)?.max_reference_images || 0);
  return configured > 0 ? configured : 6;
}

function getClosestAspectRatioValue(width: number, height: number, options: SceneOptionItem[]) {
  if (width <= 0 || height <= 0 || !options.length) return "";
  const targetRatio = width / height;
  let matchedValue = "";
  let bestDiff = Number.POSITIVE_INFINITY;
  options.forEach((item) => {
    const parsed = parseAspectRatioPair(item.value);
    if (!parsed) return;
    const candidateRatio = parsed.width / parsed.height;
    const diff = Math.abs(Math.log(targetRatio / candidateRatio));
    if (diff < bestDiff) {
      bestDiff = diff;
      matchedValue = item.value;
    }
  });
  return matchedValue;
}

async function maybeAutoDetectAspectRatioForGlobal(source: File | string) {
  if (!aspectRatioAutoDetectEnabled.value) return;
  if (globalSettings.value.customSizeEnabled) return;
  if (globalSettings.value.sceneType !== "image_edit") return;
  if (hideAspectRatio(globalSettings.value.model)) return;
  if (globalReferenceItems.value.length > 0) return;
  const options = getAspectRatioOptions(globalSettings.value.model);
  if (!options.length) return;
  try {
    const dimensions = typeof source === "string"
      ? await loadImageDimensions(resolveImageUrl(source))
      : await readImageDimensionsFromFile(source);
    const matchedValue = getClosestAspectRatioValue(dimensions.width, dimensions.height, options);
    if (matchedValue && options.some((item) => item.value === matchedValue)) {
      globalSettings.value.size = matchedValue;
    }
  } catch {
    // Ignore failures and keep current aspect ratio.
  }
}

async function maybeAutoDetectAspectRatioForCard(card: BatchGenerateCard, source: File | string) {
  if (!aspectRatioAutoDetectEnabled.value) return;
  if (card.customSizeEnabled) return;
  if (card.sceneType !== "image_edit") return;
  if (hideAspectRatio(card.model)) return;
  if (card.referenceItems.length > 0) return;
  const options = getAspectRatioOptions(card.model);
  if (!options.length) return;
  try {
    const dimensions = typeof source === "string"
      ? await loadImageDimensions(resolveImageUrl(source))
      : await readImageDimensionsFromFile(source);
    const matchedValue = getClosestAspectRatioValue(dimensions.width, dimensions.height, options);
    if (matchedValue && options.some((item) => item.value === matchedValue)) {
      card.size = matchedValue;
    }
  } catch {
    // Ignore failures and keep current aspect ratio.
  }
}

function resolveSceneCreditCost(sceneKey: string, targetResolution = "") {
  const scene = getModelOption(sceneKey) || taskScenes.value.find((item) => item.scene_key === sceneKey);
  const resolutionKey = String(targetResolution || "").trim();
  const resolutionCosts = scene?.resolution_credit_costs || {};
  if (resolutionKey && Object.prototype.hasOwnProperty.call(resolutionCosts, resolutionKey)) {
    return Number(resolutionCosts[resolutionKey] || 0);
  }
  return Number(scene?.credit_cost || 0);
}

function getBatchCardBaseCreditCost(card: BatchGenerateCard) {
  return resolveSceneCreditCost(card.model, card.customSizeEnabled ? "" : card.resolution) * getCardRequestedImageCount(card);
}

function getBatchCardNetCreditCost(card: BatchGenerateCard) {
  if (typeof card.netCreditCost === "number" && Number.isFinite(card.netCreditCost)) {
    return Math.max(0, card.netCreditCost);
  }
  return getBatchCardBaseCreditCost(card);
}

function createEmptyCard(): BatchGenerateCard {
  const card: BatchGenerateCard = {
    id: makeId("card"),
    sceneType: globalSettings.value.sceneType,
    prompt: "",
    model: globalSettings.value.model || getDefaultModelKey(globalSettings.value.sceneType),
    size: globalSettings.value.size,
    resolution: globalSettings.value.resolution,
    customSize: globalSettings.value.customSize,
    customSizeEnabled: globalSettings.value.customSizeEnabled,
    customWidth: globalSettings.value.customWidth,
    customHeight: globalSettings.value.customHeight,
    numImages: normalizeNumImages(globalSettings.value.numImages, 1),
    referenceItems: cloneSuccessReferenceItems(globalReferenceItems.value),
    status: "idle",
    taskId: null,
    taskIds: [],
    images: [],
    errorMessage: "",
    creditRefunded: false,
    netCreditCost: null,
    createdAt: null,
    dragActive: false,
    dragCounter: 0,
    highlighted: false,
    cancelRequested: false,
  };
  if (globalSettings.value.prompt.trim()) {
    card.prompt = globalSettings.value.prompt;
  }
  normalizeCardSelections(card);
  return card;
}

function createCardFromHistoryItem(item: UserHistoryCard): BatchGenerateCard {
  const hasReferenceImages = Array.isArray(item.reference_images) && item.reference_images.length > 0;
  const matchedScene = item.model
    ? taskScenes.value.find((scene) => scene.scene_key === item.model)
    : null;
  const sceneType: BatchSceneMode = (
    item.task_type === "image_edit"
    || matchedScene?.scene_type === "image_edit"
    || hasReferenceImages
  )
    ? "image_edit"
    : "generate";
  const taskIds = item.task_id ? [item.task_id] : [];

  const card: BatchGenerateCard = {
    id: makeId("history-card"),
    sceneType,
    prompt: item.prompt || "",
    model: item.model || getDefaultModelKey(sceneType),
    size: item.size || "",
    resolution: item.resolution || "",
    customSize: item.custom_size || "",
    customSizeEnabled: Boolean(parseCustomSizeValue(item.custom_size)),
    customWidth: parseCustomSizeValue(item.custom_size)?.width || CUSTOM_SIZE_DEFAULT_SIDE,
    customHeight: parseCustomSizeValue(item.custom_size)?.height || CUSTOM_SIZE_DEFAULT_SIDE,
    numImages: 1,
    referenceItems: hasReferenceImages
      ? item.reference_images.map((url) => createReferenceItemFromRemote(url))
      : [],
    status: item.status,
    taskId: taskIds[0] || null,
    taskIds,
    images: item.images.length ? item.images : createPendingImages(1),
    errorMessage: item.error_message || item.images.find((image) => image.status === "failed" && image.error_message)?.error_message || "",
    creditRefunded: Boolean(item.credit_refunded),
    netCreditCost: Boolean(item.credit_refunded) ? 0 : Number(item.credit_cost || 0),
    createdAt: item.created_at || null,
    dragActive: false,
    dragCounter: 0,
    highlighted: false,
    cancelRequested: false,
  };

  normalizeCardSelections(card);
  return card;
}

function normalizeSelectedValue(currentValue: string, options: SceneOptionItem[]) {
  if (!options.length) return "";
  if (currentValue && options.some((item) => item.value === currentValue)) return currentValue;
  return options[0]?.value || "";
}

function normalizeReferenceLimit(items: UploadPreviewItem[], modelKey: string) {
  const limit = getMaxReferenceImages(modelKey);
  if (items.length <= limit) return items;
  items.slice(limit).forEach((item) => revokeObjectUrl(item.objectUrl));
  return items.slice(0, limit);
}

function normalizeCardSelections(card: BatchGenerateCard) {
  if (!generationModels.value.length) return;
  if (!card.model || !getModelOption(card.model) || !getModelsBySceneType(card.sceneType).some((item) => item.model_key === card.model)) {
    card.model = getDefaultModelKey(card.sceneType);
  }

  const sizeOptions = getAspectRatioOptions(card.model);
  const resolutionOptions = getResolutionOptions(card.model);

  if (!supportsCustomSize(card.model)) {
    applyCustomSizeState(card, "", false);
  } else if (card.customSizeEnabled) {
    applyCustomSizeState(card, card.customSize || formatCustomSizeValue(card.customWidth, card.customHeight), true);
  } else {
    card.customSizeEnabled = false;
    card.customSize = "";
  }
  if (!card.customSizeEnabled) {
    card.size = hideAspectRatio(card.model) ? "" : normalizeSelectedValue(card.size, sizeOptions);
    card.resolution = hideResolution(card.model) ? "" : normalizeSelectedValue(card.resolution, resolutionOptions);
  }
  card.numImages = normalizeNumImages(card.numImages, 1);
  card.taskIds = getCardTaskIds(card);
  card.taskId = card.taskIds[0] || null;
  card.referenceItems = normalizeReferenceLimit(card.referenceItems, card.model);
}

function normalizeGlobalSelections() {
  if (!generationModels.value.length) return;
  if (
    !globalSettings.value.model
    || !getModelOption(globalSettings.value.model)
    || !getModelsBySceneType(globalSettings.value.sceneType).some((item) => item.model_key === globalSettings.value.model)
  ) {
    globalSettings.value.model = getDefaultModelKey(globalSettings.value.sceneType);
  }

  const sizeOptions = getAspectRatioOptions(globalSettings.value.model);
  const resolutionOptions = getResolutionOptions(globalSettings.value.model);

  if (!supportsCustomSize(globalSettings.value.model)) {
    applyCustomSizeState(globalSettings.value, "", false);
  } else if (globalSettings.value.customSizeEnabled) {
    applyCustomSizeState(
      globalSettings.value,
      globalSettings.value.customSize || formatCustomSizeValue(globalSettings.value.customWidth, globalSettings.value.customHeight),
      true,
    );
  } else {
    globalSettings.value.customSizeEnabled = false;
    globalSettings.value.customSize = "";
  }
  if (!globalSettings.value.customSizeEnabled) {
    globalSettings.value.size = hideAspectRatio(globalSettings.value.model)
      ? ""
      : normalizeSelectedValue(globalSettings.value.size, sizeOptions);
    globalSettings.value.resolution = hideResolution(globalSettings.value.model)
      ? ""
      : normalizeSelectedValue(globalSettings.value.resolution, resolutionOptions);
  }
  globalSettings.value.numImages = normalizeNumImages(globalSettings.value.numImages, 1);
  globalReferenceItems.value = normalizeReferenceLimit(globalReferenceItems.value, globalSettings.value.model);
}

function createInitialCards(count = DEFAULT_BATCH_CARDS) {
  if (!generationModels.value.length) return;
  const safeCount = Math.min(Math.max(count, 1), MAX_BATCH_CARDS);
  cards.value = Array.from({ length: safeCount }, () => createEmptyCard());
}

function ensureInitialCard() {
  if (!cards.value.length && generationModels.value.length) {
    createInitialCards();
  }
}

async function loadActiveHistoryCards() {
  if (!auth.isLoggedIn || !generationModels.value.length) return;

  try {
    const currentUserId = String(auth.user?.id || "").trim();
    const seenTaskIds = new Set<string>();
    const activeHistoryItems: UserHistoryCard[] = [];
    let page = 1;
    let total = Infinity;
    const maxHistoryItems = MAX_BATCH_CARDS * MAX_IMAGES_PER_CARD;

    while (activeHistoryItems.length < maxHistoryItems && activeHistoryItems.length < total) {
      const res = await fetchHistory(page, ACTIVE_BATCH_HISTORY_PAGE_SIZE, {
        respect_pins: false,
        include_prompt_reverse: false,
      });
      total = res.total;
      if (!res.items.length) break;

      res.items.forEach((item) => {
        if (activeHistoryItems.length >= maxHistoryItems) return;
        if (currentUserId && String(item.user_id || "").trim() && String(item.user_id || "").trim() !== currentUserId) return;
        if (item.mode === "promptReverse" || !item.task_id || seenTaskIds.has(item.task_id)) return;
        if (!["pending", "queued", "processing"].includes(item.status)) return;
        seenTaskIds.add(item.task_id);
        activeHistoryItems.push(item);
      });

      page += 1;
    }

    if (!activeHistoryItems.length) return;

    const existingCardsByTaskId = new Map<string, BatchGenerateCard>();
    cards.value.forEach((card) => {
      getCardTaskIds(card).forEach((taskId) => {
        existingCardsByTaskId.set(taskId, card);
      });
    });

    activeHistoryItems.forEach((item) => {
      const taskId = String(item.task_id || "").trim();
      if (!taskId) return;

      const existingCard = existingCardsByTaskId.get(taskId);
      if (existingCard) {
        const slotIndex = getCardTaskIds(existingCard).indexOf(taskId);
        if (slotIndex >= 0) {
          ensureCardImageSlots(existingCard, getCardTaskIds(existingCard).length);
          if (item.images.length) {
            existingCard.images[slotIndex] = item.images[0];
          }
          existingCard.creditRefunded = existingCard.creditRefunded || Boolean(item.credit_refunded);
          if (!existingCard.createdAt && item.created_at) {
            existingCard.createdAt = item.created_at;
          }
          refreshCardAggregateStatus(existingCard);
        }
        return;
      }

      if (cards.value.length >= MAX_BATCH_CARDS) return;
      const historyCard = createCardFromHistoryItem(item);
      cards.value.push(historyCard);
      getCardTaskIds(historyCard).forEach((id) => existingCardsByTaskId.set(id, historyCard));
    });
    ensurePolling();

    try {
      await pollTaskResults();
    } catch {
      // keep history snapshot cards and continue polling
    }
  } catch {
    // ignore history hydration failure and fall back to empty card
  }
}

watch(generationModels, () => {
  normalizeGlobalSelections();
  cards.value.forEach((card) => normalizeCardSelections(card));
  ensureInitialCard();
});

watch(aspectRatioAutoDetectEnabled, (enabled) => {
  writeStoredAspectRatioAutoDetectEnabled(enabled);
});

watch(
  [globalSettings, globalReferenceItems, cards],
  () => {
    if (!draftHydrationReady.value) return;
    persistBatchGenerateDraft();
  },
  { deep: true },
);

watch(cards, () => {
  if (!detailOpen.value || !detailCardId.value) return;
  const card = cards.value.find((item) => item.id === detailCardId.value);
  if (!card) {
    detailOpen.value = false;
    detailItem.value = null;
    return;
  }
  detailItem.value = convertBatchCardToHistoryCard(card, detailImageIndex.value);
}, { deep: true });

function setGlobalReferenceUploadBlockRef(el: unknown) {
  unbindGlobalReferenceDragHandlers?.();
  unbindGlobalReferenceDragHandlers = null;

  if (el instanceof HTMLElement) {
    unbindGlobalReferenceDragHandlers = bindReferenceDragHandlers(el, {
      setActive(active) {
        globalReferenceDragActive.value = active;
      },
      increaseCounter() {
        globalReferenceDragCounter.value += 1;
      },
      decreaseCounter() {
        globalReferenceDragCounter.value = Math.max(0, globalReferenceDragCounter.value - 1);
        if (globalReferenceDragCounter.value === 0) {
          globalReferenceDragActive.value = false;
        }
      },
      resetCounter() {
        globalReferenceDragCounter.value = 0;
        globalReferenceDragActive.value = false;
      },
      onDrop(files) {
        void uploadReferenceFilesToTarget(files, "global");
      },
    });
    return;
  }
}

function setCardFileInput(cardId: string, el: unknown) {
  if (el instanceof HTMLInputElement) {
    cardFileInputs.set(cardId, el);
  } else {
    cardFileInputs.delete(cardId);
  }
}

function setCardReferenceUploadBlockRef(cardId: string, el: unknown) {
  const previousUnbind = unbindCardReferenceDragHandlers.get(cardId);
  previousUnbind?.();
  unbindCardReferenceDragHandlers.delete(cardId);

  if (el instanceof HTMLElement) {
    cardReferenceUploadBlockRefs.set(cardId, el);
    const unbind = bindReferenceDragHandlers(el, {
      setActive(active) {
        const card = cards.value.find((item) => item.id === cardId);
        if (!card) return;
        card.dragActive = active;
      },
      increaseCounter() {
        const card = cards.value.find((item) => item.id === cardId);
        if (!card) return;
        card.dragCounter += 1;
      },
      decreaseCounter() {
        const card = cards.value.find((item) => item.id === cardId);
        if (!card) return;
        card.dragCounter = Math.max(0, card.dragCounter - 1);
        if (card.dragCounter === 0) {
          card.dragActive = false;
        }
      },
      resetCounter() {
        const card = cards.value.find((item) => item.id === cardId);
        if (!card) return;
        card.dragCounter = 0;
        card.dragActive = false;
      },
      onDrop(files) {
        const card = cards.value.find((item) => item.id === cardId);
        if (!card) return;
        void uploadReferenceFilesToTarget(files, card);
      },
    });
    unbindCardReferenceDragHandlers.set(cardId, unbind);
    return;
  }

  cardReferenceUploadBlockRefs.delete(cardId);
}

async function ensureAuthenticated() {
  if (!auth.isLoggedIn) {
    loginModalVisible.value = true;
    return false;
  }
  try {
    auth.updateUser(await getMe());
    return true;
  } catch {
    loginModalVisible.value = true;
    return false;
  }
}

function isInsufficientCreditsError(err: any) {
  const detail = String(err?.response?.data?.detail || err?.message || "");
  return detail.includes("积分不足");
}

function isSubmissionLimitError(err: any) {
  const detail = String(err?.response?.data?.detail || err?.message || "");
  return err?.response?.status === 429 || detail.includes("当前提交任务较多");
}

function showInsufficientCreditsPurchase(detail?: string) {
  if (detail) {
    message.warning(detail);
  }
  openPurchaseEntry?.();
}

function getReferencePreviewUrl(item: UploadPreviewItem) {
  return resolveImageUrl(item.localUrl || item.remoteUrl);
}

function isReferenceImageFile(file: File) {
  if (file.type.startsWith("image/")) return true;
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(file.name);
}

function isReferenceFileDragEvent(event: DragEvent) {
  const types = Array.from(event.dataTransfer?.types || []);
  return types.includes("Files");
}

function bindReferenceDragHandlers(
  element: HTMLElement,
  handlers: {
    setActive: (active: boolean) => void;
    increaseCounter: () => void;
    decreaseCounter: () => void;
    resetCounter: () => void;
    onDrop: (files: File[]) => void;
  }
) {
  const handleDragEnter = (event: DragEvent) => {
    if (!isReferenceFileDragEvent(event)) return;
    event.preventDefault();
    event.stopPropagation();
    handlers.increaseCounter();
    handlers.setActive(true);
  };

  const handleDragOver = (event: DragEvent) => {
    if (!isReferenceFileDragEvent(event)) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
  };

  const handleDragLeave = (event: DragEvent) => {
    if (!isReferenceFileDragEvent(event)) return;
    event.preventDefault();
    event.stopPropagation();
    handlers.decreaseCounter();
  };

  const handleDrop = (event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    handlers.resetCounter();

    const files = Array.from(event.dataTransfer?.files || []);
    if (!files.length) return;
    handlers.onDrop(files);
  };

  element.addEventListener("dragenter", handleDragEnter);
  element.addEventListener("dragover", handleDragOver);
  element.addEventListener("dragleave", handleDragLeave);
  element.addEventListener("drop", handleDrop);

  return () => {
    element.removeEventListener("dragenter", handleDragEnter);
    element.removeEventListener("dragover", handleDragOver);
    element.removeEventListener("dragleave", handleDragLeave);
    element.removeEventListener("drop", handleDrop);
  };
}

function updateCard(cardId: string, updater: (card: BatchGenerateCard) => void) {
  const card = cards.value.find((item) => item.id === cardId);
  if (!card) return;
  updater(card);
}

function hasUploadingReferences(items: UploadPreviewItem[]) {
  return items.some((item) => item.status === "uploading");
}

function hasFailedReferences(items: UploadPreviewItem[]) {
  return items.some((item) => item.status === "failed");
}

function isCardLocked(card: BatchGenerateCard) {
  return ["queued_local", "submitting", "pending", "queued", "processing"].includes(card.status);
}

function canRemoveCard(card: BatchGenerateCard) {
  if (!isCardLocked(card)) return true;
  return card.status === "queued_local" || (card.status === "submitting" && !getCardTaskIds(card).length);
}

function buildReferenceUrls(items: UploadPreviewItem[]) {
  return items
    .filter((item) => item.status === "success" && item.remoteUrl)
    .map((item) => item.remoteUrl);
}

function updateReferenceItem(
  items: UploadPreviewItem[],
  id: string,
  patch: Partial<UploadPreviewItem>,
) {
  const index = items.findIndex((item) => item.id === id);
  if (index === -1) return items;
  const nextItems = [...items];
  nextItems[index] = {
    ...nextItems[index],
    ...patch,
  };
  return nextItems;
}

function commitReferenceItems(
  items: UploadPreviewItem[],
  target: "global" | BatchGenerateCard,
) {
  if (target === "global") {
    globalReferenceItems.value = items;
    return;
  }

  const cardIndex = cards.value.findIndex((card) => card.id === target.id);
  if (cardIndex === -1) {
    target.referenceItems = items;
    return;
  }

  cards.value[cardIndex] = {
    ...cards.value[cardIndex],
    referenceItems: items,
  };
}

async function uploadReferenceFilesToTarget(
  files: File[],
  target: "global" | BatchGenerateCard,
) {
  if (!(await ensureAuthenticated())) return;

  const imageFiles = files.filter((file) => isReferenceImageFile(file));
  if (!imageFiles.length) {
    if (files.length) {
      message.warning("仅支持上传图片文件");
    }
    return;
  }

  const items = target === "global" ? [...globalReferenceItems.value] : [...target.referenceItems];
  const modelKey = target === "global" ? globalSettings.value.model : target.model;
  const limit = getMaxReferenceImages(modelKey);
  const remainingSlots = Math.max(0, limit - items.length);
  if (!remainingSlots) {
    message.warning(`当前模型最多上传 ${limit} 张参考图`);
    return;
  }

  const acceptedFiles = imageFiles.slice(0, remainingSlots);
  if (imageFiles.length > acceptedFiles.length) {
    message.warning(`当前模型最多支持 ${limit} 张参考图，本次仅上传前 ${acceptedFiles.length} 张`);
  }

  if (acceptedFiles.length && items.length === 0) {
    if (target === "global") {
      await maybeAutoDetectAspectRatioForGlobal(acceptedFiles[0]);
    } else {
      await maybeAutoDetectAspectRatioForCard(target, acceptedFiles[0]);
    }
  }

  let uploadedCount = 0;
  let failedCount = 0;
  let oversizedCount = 0;
  let workingItems = items;

  for (const file of acceptedFiles) {
    if (isImageUploadTooLarge(file)) {
      oversizedCount += 1;
      continue;
    }

    const objectUrl = URL.createObjectURL(file);
    const item: UploadPreviewItem = {
      id: makeId("upload"),
      localUrl: objectUrl,
      remoteUrl: "",
      status: "uploading",
      objectUrl,
    };
    workingItems = [...workingItems, item];
    commitReferenceItems(workingItems, target);

    try {
      const res = await uploadReferenceImage(file, "ref");
      revokeObjectUrl(objectUrl);
      workingItems = updateReferenceItem(workingItems, item.id, {
        objectUrl: undefined,
        localUrl: res.url,
        remoteUrl: res.url,
        status: "success",
      });
      uploadedCount += 1;
    } catch {
      workingItems = updateReferenceItem(workingItems, item.id, {
        status: "failed",
      });
      failedCount += 1;
    }

    commitReferenceItems(workingItems, target);
  }

  if (target !== "global") {
    const latestCard = cards.value.find((item) => item.id === target.id);
    if (latestCard) {
      normalizeCardSelections(latestCard);
    }
  } else {
    normalizeGlobalSelections();
  }

  if (uploadedCount > 0) {
    message.success(`成功上传 ${uploadedCount} 张参考图`);
  }
  if (oversizedCount > 0) {
    message.warning(`${oversizedCount} 张图片超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}，已跳过`);
  }
  if (failedCount > 0) {
    message.error(`${failedCount} 张参考图上传失败，请重试`);
  }
}

function getClipboardImageFiles(event: ClipboardEvent) {
  return Array.from(event.clipboardData?.items || [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));
}

function getAvailableReferenceSlots(items: UploadPreviewItem[], modelKey: string) {
  return Math.max(0, getMaxReferenceImages(modelKey) - items.length);
}

function getPasteTargetCards(cardIds: string[]) {
  const idSet = new Set(cardIds.filter(Boolean));
  return pasteEligibleCards.value.filter((card) => idSet.has(card.id));
}

function getPasteScopeUploadLimit(scope: PasteApplyScope, targetCardIds: string[]) {
  if (scope === "global") {
    if (globalSettings.value.sceneType !== "image_edit") return 0;
    return getAvailableReferenceSlots(globalReferenceItems.value, globalSettings.value.model);
  }
  if (scope === "single_card") {
    const targetCards = getPasteTargetCards(targetCardIds);
    if (!targetCards.length) return 0;
    return targetCards.reduce((maxSlots, card) => (
      Math.max(maxSlots, getAvailableReferenceSlots(card.referenceItems, card.model))
    ), 0);
  }
  const imageEditCards = pasteEligibleCards.value;
  if (!imageEditCards.length) return 0;
  return imageEditCards.reduce((maxSlots, card) => (
    Math.max(maxSlots, getAvailableReferenceSlots(card.referenceItems, card.model))
  ), 0);
}

function appendRemoteReferences(
  items: UploadPreviewItem[],
  modelKey: string,
  remoteUrls: string[],
) {
  const remainingSlots = getAvailableReferenceSlots(items, modelKey);
  const acceptedUrls = remoteUrls.slice(0, remainingSlots);
  return {
    nextItems: [...items, ...createReferenceItemsFromRemoteUrls(acceptedUrls)],
    appliedCount: acceptedUrls.length,
    skippedCount: Math.max(0, remoteUrls.length - acceptedUrls.length),
  };
}

async function uploadReferenceFilesOnce(
  files: File[],
  maxUploads = 0,
) {
  const imageFiles = files.filter((file) => isReferenceImageFile(file));
  if (!imageFiles.length) {
    if (files.length) {
      message.warning("仅支持上传图片文件");
    }
    return { uploadedUrls: [] as string[], uploadedCount: 0, failedCount: 0, oversizedCount: 0 };
  }

  const acceptedFiles = maxUploads > 0 ? imageFiles.slice(0, maxUploads) : [];
  if (!acceptedFiles.length) {
    return { uploadedUrls: [] as string[], uploadedCount: 0, failedCount: 0, oversizedCount: 0 };
  }
  if (imageFiles.length > acceptedFiles.length) {
    message.warning(`本次仅处理前 ${acceptedFiles.length} 张粘贴图片`);
  }

  const uploadedUrls: string[] = [];
  let uploadedCount = 0;
  let failedCount = 0;
  let oversizedCount = 0;

  for (const file of acceptedFiles) {
    if (isImageUploadTooLarge(file)) {
      oversizedCount += 1;
      continue;
    }
    try {
      const res = await uploadReferenceImage(file, "ref");
      uploadedUrls.push(res.url);
      uploadedCount += 1;
    } catch {
      failedCount += 1;
    }
  }

  return { uploadedUrls, uploadedCount, failedCount, oversizedCount };
}

function resetPasteDialogState() {
  pendingPastePreviewUrls.value.forEach((url) => revokeObjectUrl(url));
  pendingPastePreviewUrls.value = [];
  pasteDialogVisible.value = false;
  pasteDialogSubmitting.value = false;
  pasteDialogScope.value = "global";
  pasteDialogTargetCardIds.value = [];
  pendingPasteFiles.value = [];
}

function openPasteDialog(files: File[]) {
  const hasGlobalTarget = globalSettings.value.sceneType === "image_edit";
  const eligibleCards = pasteEligibleCards.value;
  if (!hasGlobalTarget && !eligibleCards.length) {
    message.warning("当前没有可接收参考图的图编辑配置，请先添加或切换到图编辑卡片");
    return;
  }
  pendingPasteFiles.value = files;
  pendingPastePreviewUrls.value.forEach((url) => revokeObjectUrl(url));
  pendingPastePreviewUrls.value = files.map((file) => URL.createObjectURL(file));
  pasteDialogScope.value = hasGlobalTarget ? "global" : (eligibleCards.length > 1 ? "all_cards" : "single_card");
  pasteDialogTargetCardIds.value = eligibleCards[0]?.id ? [eligibleCards[0].id] : [];
  pasteDialogVisible.value = true;
}

function togglePasteTargetCard(cardId: string) {
  if (!cardId) return;
  if (pasteDialogTargetCardIds.value.includes(cardId)) {
    pasteDialogTargetCardIds.value = pasteDialogTargetCardIds.value.filter((id) => id !== cardId);
    return;
  }
  pasteDialogTargetCardIds.value = [...pasteDialogTargetCardIds.value, cardId];
}

async function confirmPasteDialog() {
  if (!(await ensureAuthenticated())) return;
  const files = pendingPasteFiles.value.slice();
  const scope = pasteDialogScope.value;
  const targetCardIds = pasteDialogTargetCardIds.value.slice();
  const maxUploads = getPasteScopeUploadLimit(scope, targetCardIds);
  if (!maxUploads) {
    message.warning("所选目标已没有可用参考图位置");
    return;
  }

  pasteDialogSubmitting.value = true;
  try {
    const { uploadedUrls, uploadedCount, failedCount, oversizedCount } = await uploadReferenceFilesOnce(files, maxUploads);
    if (!uploadedUrls.length) {
      if (oversizedCount > 0) {
        message.warning(`${oversizedCount} 张图片超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}，已跳过`);
      }
      if (failedCount > 0) {
        message.error(`${failedCount} 张参考图上传失败，请重试`);
      }
      if (!failedCount && !oversizedCount) {
        message.warning("没有可应用的参考图");
      }
      return;
    }

    if (scope === "global") {
      await maybeAutoDetectAspectRatioForGlobal(uploadedUrls[0]);
      const { nextItems, appliedCount } = appendRemoteReferences(globalReferenceItems.value, globalSettings.value.model, uploadedUrls);
      globalReferenceItems.value = nextItems;
      normalizeGlobalSelections();
      message.success(`已上传 ${uploadedCount} 张参考图，并加入全局设置`);
      if (appliedCount < uploadedUrls.length) {
        message.warning("部分参考图因达到全局上限未加入");
      }
    } else if (scope === "single_card") {
      const targetCards = getPasteTargetCards(targetCardIds);
      if (!targetCards.length) {
        message.warning("目标任务卡片不存在或不支持参考图");
        return;
      }
      await Promise.all(
        targetCards
          .filter((card) => !card.referenceItems.length)
          .map((card) => maybeAutoDetectAspectRatioForCard(card, uploadedUrls[0])),
      );
      let appliedCardCount = 0;
      let limitedCardCount = 0;
      targetCards.forEach((card) => {
        const { nextItems, appliedCount } = appendRemoteReferences(card.referenceItems, card.model, uploadedUrls);
        if (appliedCount > 0) {
          commitReferenceItems(nextItems, card);
          normalizeCardSelections(card);
          appliedCardCount += 1;
        }
        if (appliedCount < uploadedUrls.length) {
          limitedCardCount += 1;
        }
      });
      if (!appliedCardCount) {
        message.warning("所选任务卡片都已达到参考图上限");
        return;
      }
      message.success(`已上传 ${uploadedCount} 张参考图，并作用到 ${appliedCardCount} 张任务卡片`);
      if (limitedCardCount > 0) {
        message.warning("部分卡片因达到参考图上限，未能加入全部粘贴图片");
      }
    } else {
      const targets = pasteEligibleCards.value;
      await Promise.all(
        targets
          .filter((card) => !card.referenceItems.length)
          .map((card) => maybeAutoDetectAspectRatioForCard(card, uploadedUrls[0])),
      );
      let appliedCardCount = 0;
      targets.forEach((card) => {
        const { nextItems, appliedCount } = appendRemoteReferences(card.referenceItems, card.model, uploadedUrls);
        if (appliedCount > 0) {
          commitReferenceItems(nextItems, card);
          normalizeCardSelections(card);
          appliedCardCount += 1;
        }
      });
      if (!appliedCardCount) {
        message.warning("所有图编辑卡片都已达到参考图上限");
        return;
      }
      message.success(`已上传 ${uploadedCount} 张参考图，并作用到 ${appliedCardCount} 张任务卡片`);
    }

    if (oversizedCount > 0) {
      message.warning(`${oversizedCount} 张图片超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}，已跳过`);
    }
    if (failedCount > 0) {
      message.error(`${failedCount} 张参考图上传失败，请重试`);
    }
    resetPasteDialogState();
  } finally {
    pasteDialogSubmitting.value = false;
  }
}

function handleBatchReferencePaste(event: ClipboardEvent) {
  const files = getClipboardImageFiles(event);
  if (!files.length) return;
  event.preventDefault();
  openPasteDialog(files);
}

function removeReferenceItem(items: UploadPreviewItem[], index: number) {
  const item = items[index];
  if (item) {
    revokeObjectUrl(item.objectUrl);
  }
  items.splice(index, 1);
}

function triggerGlobalReferenceUpload() {
  void ensureAuthenticated().then((passed) => {
    if (!passed) return;
    globalFileInput.value?.click();
  });
}

function triggerCardReferenceUpload(cardId: string) {
  const card = cards.value.find((item) => item.id === cardId);
  if (!card || isCardLocked(card)) return;
  void ensureAuthenticated().then((passed) => {
    if (!passed) return;
    cardFileInputs.get(cardId)?.click();
  });
}

async function handleGlobalReferenceChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  try {
    await uploadReferenceFilesToTarget(files, "global");
  } finally {
    input.value = "";
  }
}

async function handleCardReferenceChange(cardId: string, event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  const card = cards.value.find((item) => item.id === cardId);
  if (!card) return;
  try {
    if (isCardLocked(card)) return;
    await uploadReferenceFilesToTarget(files, card);
  } finally {
    input.value = "";
  }
}

function handleGlobalModelChange(modelKey: string) {
  globalSettings.value.model = modelKey;
  globalSettings.value.sceneType = isImageEditModel(modelKey) ? "image_edit" : "generate";
  normalizeGlobalSelections();
}

function handleGlobalSceneTypeChange(sceneType: BatchSceneMode) {
  globalSettings.value.sceneType = sceneType;
  globalSettings.value.model = getDefaultModelKey(sceneType);
  normalizeGlobalSelections();
}

function handleCardModelChange(card: BatchGenerateCard, modelKey: string) {
  if (isCardLocked(card)) return;
  card.model = modelKey;
  card.sceneType = isImageEditModel(modelKey) ? "image_edit" : "generate";
  normalizeCardSelections(card);
}

function handleCardSceneTypeChange(card: BatchGenerateCard, sceneType: BatchSceneMode) {
  if (isCardLocked(card)) return;
  card.sceneType = sceneType;
  card.model = getDefaultModelKey(sceneType);
  normalizeCardSelections(card);
}

function addCard() {
  if (!canAddMoreCards.value) {
    message.warning(`最多添加 ${MAX_BATCH_CARDS} 张配置卡片`);
    return;
  }
  cards.value.push(createEmptyCard());
}

function removeCard(card: BatchGenerateCard) {
  if (!canRemoveCard(card)) return;
  card.cancelRequested = true;
  const doRemove = () => {
    card.referenceItems.forEach((item) => revokeObjectUrl(item.objectUrl));
    cards.value = cards.value.filter((item) => item.id !== card.id);
    if (!cards.value.length) {
      createInitialCards();
    }
  };

  doRemove();
}

function clearFinishedCards() {
  cards.value.forEach((card) => {
    if (["success", "failed"].includes(card.status)) {
      card.referenceItems.forEach((item) => revokeObjectUrl(item.objectUrl));
    }
  });
  cards.value = cards.value.filter((card) => !["success", "failed"].includes(card.status));
  if (!cards.value.length) {
    createInitialCards();
  }
}

function applyGlobalSettingsToAll() {
  const successReferences = cloneSuccessReferenceItems(globalReferenceItems.value);
  let appliedFieldCount = 0;

  cards.value.forEach((card) => {
    if (globalSettings.value.model) {
      card.sceneType = globalSettings.value.sceneType;
      card.model = globalSettings.value.model;
      appliedFieldCount += 1;
    }
    if (globalSettings.value.prompt.trim()) {
      card.prompt = globalSettings.value.prompt;
      appliedFieldCount += 1;
    }
    if (globalSettings.value.customSizeEnabled && supportsCustomSize(card.model)) {
      applyCustomSizeState(
        card,
        globalSettings.value.customSize || formatCustomSizeValue(globalSettings.value.customWidth, globalSettings.value.customHeight),
        true,
      );
      appliedFieldCount += 1;
    } else {
      if (card.customSizeEnabled) {
        applyCustomSizeState(card, "", false);
        appliedFieldCount += 1;
      }
      if (globalSettings.value.size) {
        card.size = globalSettings.value.size;
        appliedFieldCount += 1;
      }
      if (globalSettings.value.resolution) {
        card.resolution = globalSettings.value.resolution;
        appliedFieldCount += 1;
      }
    }
    if (globalSettings.value.numImages) {
      card.numImages = normalizeNumImages(globalSettings.value.numImages, 1);
      appliedFieldCount += 1;
    }
    if (successReferences.length) {
      card.referenceItems.forEach((item) => revokeObjectUrl(item.objectUrl));
      card.referenceItems = cloneSuccessReferenceItems(successReferences);
      appliedFieldCount += 1;
    }
    normalizeCardSelections(card);
  });

  if (!appliedFieldCount) {
    message.warning("全局设置中还没有可应用的内容");
    return;
  }
  message.success(`已将全局设置应用到 ${cards.value.length} 张卡片`);
}

function getCardBlockingReason(card: BatchGenerateCard) {
  if (!card.model) return "请选择模型";
  if (card.customSizeEnabled) {
    const widthError = getTargetCustomDimensionError(card, card.model, "width");
    const heightError = getTargetCustomDimensionError(card, card.model, "height");
    if (widthError || heightError) {
      return [
        widthError ? `宽度${widthError}` : "",
        heightError ? `高度${heightError}` : "",
      ].filter(Boolean).join("；") || "请检查自定义分辨率";
    }
    syncCustomSizeValue(card);
  }
  if (!card.prompt.trim()) return "提示词不能为空";
  if (card.sceneType === "image_edit" && !buildReferenceUrls(card.referenceItems).length) {
    return "参考图不能为空";
  }
  if (hasUploadingReferences(card.referenceItems)) return "参考图仍在上传，请稍后再试";
  if (hasFailedReferences(card.referenceItems)) return "存在上传失败的参考图，请删除或重传";
  return "";
}

function getSingleSubmitButtonLabel(card: BatchGenerateCard) {
  return card.status === "idle" ? "开始生成" : "重新生成";
}

function getStatusLabel(status: BatchCardStatus) {
  if (status === "idle") return "待开始";
  if (status === "queued_local") return "等待提交";
  if (status === "submitting") return "提交中";
  if (status === "pending") return "待处理";
  if (status === "queued") return "排队中";
  if (status === "processing") return "生成中";
  if (status === "success") return "已完成";
  return "失败";
}

function getCardCloseButtonTitle(card: BatchGenerateCard) {
  if (card.status === "queued_local" || (card.status === "submitting" && !getCardTaskIds(card).length)) {
    return "取消提交";
  }
  return "删除卡片";
}

function getStatusColor(status: BatchCardStatus) {
  if (status === "success") return "success";
  if (status === "failed") return "error";
  if (status === "idle") return "default";
  return "processing";
}

function openPreview(image?: ImageResult) {
  const url = getPreviewImageUrl(image);
  if (!url) return;
  previewCurrent.value = url;
  previewVisible.value = true;
}

function toHistoryCardStatus(status: BatchCardStatus): UserHistoryCard["status"] {
  if (status === "queued_local" || status === "submitting" || status === "idle") return "pending";
  return status;
}

function convertBatchCardToHistoryCard(card: BatchGenerateCard, imageIndex = 0): UserHistoryCard {
  const focusedImage = card.images[imageIndex] || card.images.find((image) => image.status === "success") || card.images[0];
  const referenceUrls = buildReferenceUrls(card.referenceItems);
  const taskId = getSlotTaskId(card, imageIndex) || getCardTaskIds(card)[0] || null;

  return {
    item_type: "task",
    display_id: taskId || card.id,
    task_id: taskId,
    image_id: typeof focusedImage?.id === "number" && focusedImage.id > 0 ? focusedImage.id : null,
    is_pinned: false,
    image_url: focusedImage?.image_url || "",
    preview_url: focusedImage?.preview_url,
    thumb_url: focusedImage?.thumb_url,
    status: toHistoryCardStatus(card.status),
    image_format: focusedImage?.image_format,
    image_size_bytes: focusedImage?.image_size_bytes,
    task_type: card.sceneType === "image_edit" ? "image_edit" : "text_generate",
    model: card.model || "",
    source: "web",
    mode: "generate",
    prompt: card.prompt || "",
    reference_images: [...referenceUrls],
    reference_image_thumbs: [...referenceUrls],
    source_image: "",
    source_image_thumb: "",
    mask_image: "",
    mask_image_thumb: "",
    num_images: Math.max(getCardRequestedImageCount(card), card.images.length, 1),
    size: card.size || "",
    resolution: card.resolution || "",
    custom_size: card.customSize || "",
    credit_cost: getBatchCardNetCreditCost(card),
    credit_refunded: Boolean(card.creditRefunded),
    created_at: card.createdAt || new Date().toISOString(),
    error_message: card.errorMessage || "",
    images: card.images.length ? [...card.images] : [],
  };
}

function openBatchTaskDetail(card: BatchGenerateCard, imageIndex = 0) {
  const focusedIndex = Math.max(0, Math.min(imageIndex, Math.max(card.images.length - 1, 0)));
  detailCardId.value = card.id;
  detailImageIndex.value = focusedIndex;
  detailItem.value = convertBatchCardToHistoryCard(card, focusedIndex);
  detailOpen.value = true;
}

function navigateBatchTaskDetail(delta: -1 | 1) {
  const nextCard = detailableCards.value[detailCardIndex.value + delta];
  if (!nextCard) return;
  openBatchTaskDetail(nextCard, 0);
}

function handleDetailReedit(item: UserHistoryCard) {
  const card = cards.value.find((entry) => entry.id === detailCardId.value);
  detailOpen.value = false;
  if (!card) return;
  const focusedImage = typeof item.image_id === "number"
    ? card.images.find((image) => image.id === item.image_id)
    : card.images[detailImageIndex.value];
  if (focusedImage && canEditBatchGeneratedImage(card, focusedImage)) {
    handleEditBatchGeneratedImage(card, focusedImage);
    return;
  }
  highlightCard(card);
}

async function handleDetailDownload(item: UserHistoryCard) {
  if (typeof item.image_id !== "number" || !item.image_url) return;
  try {
    await downloadBlob(item.image_id, item.image_url, item.preview_url);
  } catch {
    message.error("下载失败，请重试");
  }
}

function refreshCurrentUser() {
  return getMe().then((user) => auth.updateUser(user)).catch(() => {});
}

function canEditBatchGeneratedImage(card: BatchGenerateCard, image: ImageResult) {
  return image.status === "success" && !!(image.image_url || image.preview_url);
}

function handleEditBatchGeneratedImage(card: BatchGenerateCard, image: ImageResult) {
  const referenceImage = image.image_url || image.preview_url || "";
  if (!referenceImage) {
    message.warning("当前结果图暂不可用于图编辑");
    return;
  }

  card.sceneType = "image_edit";
  if (!isImageEditModel(card.model)) {
    card.model = getDefaultModelKey("image_edit");
  }
  card.referenceItems.forEach((item) => revokeObjectUrl(item.objectUrl));
  card.referenceItems = [createReferenceItemFromRemote(referenceImage)];
  syncCardTaskIds(card, []);
  card.status = "idle";
  card.images = [];
  card.errorMessage = "";
  card.creditRefunded = false;
  card.netCreditCost = null;
  normalizeCardSelections(card);
  highlightCard(card);
  message.success("结果图已加载到当前任务卡片，可继续图编辑");
}

function openFeedbackDialogForBatchCard(card: BatchGenerateCard, imageIndex = 0) {
  const taskId = getSlotTaskId(card, imageIndex) || getCardTaskIds(card)[0];
  const image = card.images[imageIndex];
  if (!taskId || (image && image.status === "pending")) {
    message.warning("当前任务尚未生成完成，暂时无法提交反馈");
    return;
  }

  feedbackTarget.value = {
    taskId,
    model: card.model,
    prompt: card.prompt,
    createdAt: card.createdAt || new Date().toISOString(),
  };
  feedbackDialogOpen.value = true;
}

function canDeleteBatchCardTask(card: BatchGenerateCard) {
  return Boolean(getCardTaskIds(card).length && (card.status === "success" || card.status === "failed"));
}

async function deleteCardTasks(card: BatchGenerateCard) {
  const taskIds = getCardTaskIds(card);
  if (!taskIds.length) return;
  await Promise.allSettled(taskIds.map((taskId) => deleteHistoryTask(taskId)));
}

async function removeBatchCardTask(card: BatchGenerateCard) {
  if (!canDeleteBatchCardTask(card) || !getCardTaskIds(card).length) {
    message.warning("当前任务暂不支持删除");
    return;
  }

  try {
    await deleteCardTasks(card);
    card.images = [];
    card.status = "idle";
    card.errorMessage = "";
    syncCardTaskIds(card, []);
    card.createdAt = null;
    card.creditRefunded = false;
    card.netCreditCost = null;

    message.success("删除成功");
  } catch {
    message.error("删除失败");
  }
}

function confirmRemoveBatchCardTask(card: BatchGenerateCard) {
  Modal.confirm({
    title: "确认删除这个任务？",
    content: "删除后会移除当前任务卡片中的全部结果图与任务记录。",
    centered: true,
    async onOk() {
      await removeBatchCardTask(card);
    },
  });
}

function duplicateCard(card: BatchGenerateCard) {
  if (cards.value.length >= MAX_BATCH_CARDS) {
    message.warning(`最多添加 ${MAX_BATCH_CARDS} 张配置卡片`);
    return;
  }

  const nextCard: BatchGenerateCard = {
    id: makeId("card"),
    sceneType: card.sceneType,
    prompt: card.prompt,
    model: card.model,
    size: card.size,
    resolution: card.resolution,
    customSize: card.customSize,
    customSizeEnabled: card.customSizeEnabled,
    customWidth: card.customWidth,
    customHeight: card.customHeight,
    numImages: getCardRequestedImageCount(card),
    referenceItems: cloneSuccessReferenceItems(card.referenceItems),
    status: "idle",
    taskId: null,
    taskIds: [],
    images: [],
    errorMessage: "",
    creditRefunded: false,
    netCreditCost: null,
    createdAt: null,
    dragActive: false,
    dragCounter: 0,
    highlighted: false,
    cancelRequested: false,
  };
  normalizeCardSelections(nextCard);
  const cardIndex = cards.value.findIndex((item) => item.id === card.id);
  cards.value.splice(cardIndex >= 0 ? cardIndex + 1 : cards.value.length, 0, nextCard);
  highlightCard(nextCard);
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function getDownloadFilename(imageId: number, imageUrl?: string) {
  const cleanPath = (imageUrl || "").split("?")[0] || "";
  const suffix = cleanPath.includes(".") ? cleanPath.slice(cleanPath.lastIndexOf(".")) : ".png";
  return `banana_${imageId}${suffix || ".png"}`;
}

async function downloadBlob(imageId: number, imageUrl: string, previewUrl?: string) {
  const url = getDownloadUrl(imageId, imageUrl, previewUrl);
  const headers: Record<string, string> = {};
  const token = localStorage.getItem("token");
  if (token && !/^https?:\/\//.test(url)) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url, { headers });
  if (!response.ok) throw new Error("download_failed");

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = getDownloadFilename(imageId, imageUrl);
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function downloadAllImages() {
  if (!downloadableImages.value.length) {
    message.warning("当前没有可下载的结果图");
    return;
  }

  let successCount = 0;
  for (const image of downloadableImages.value) {
    try {
      await downloadBlob(image.id, image.image_url, image.preview_url);
      successCount += 1;
      await wait(180);
    } catch {
      // continue downloading remaining images
    }
  }

  if (!successCount) {
    message.error("批量下载失败，请重试");
    return;
  }
  if (successCount < downloadableImages.value.length) {
    message.warning(`已下载 ${successCount} 张，部分图片下载失败`);
    return;
  }
  message.success(`已开始下载 ${successCount} 张图片`);
}

function getCardTaskLabel(card: BatchGenerateCard) {
  const index = cards.value.findIndex((item) => item.id === card.id);
  return index === -1 ? "任务" : `任务${index + 1}`;
}

function queueCardsForSubmit(targetCards: BatchGenerateCard[]) {
  const invalidMessages: string[] = [];
  let queuedCount = 0;

  targetCards.forEach((card) => {
    const blockingReason = getCardBlockingReason(card);
    if (blockingReason) {
      invalidMessages.push(`${getCardTaskLabel(card)}：${blockingReason}`);
      return;
    }
    card.errorMessage = "";
    card.creditRefunded = false;
    card.netCreditCost = null;
    syncCardTaskIds(card, []);
    card.images = createPendingImages(getCardRequestedImageCount(card));
    card.createdAt = null;
    card.status = "queued_local";
    queuedCount += 1;
  });

  if (queuedCount > 0) {
    scheduleQueuePump(0);
  }

  if (invalidMessages.length) {
    message.warning(invalidMessages[0]);
  } else if (queuedCount > 0) {
    message.success(`已加入 ${queuedCount} 张卡片到批量队列`);
  }
}

async function startBatchGenerate() {
  if (!(await ensureAuthenticated())) return;
  const targetCards = cards.value.filter((card) => ["idle", "failed", "success"].includes(card.status));
  if (!targetCards.length) {
    message.warning("当前没有可提交的卡片");
    return;
  }
  queueCardsForSubmit(targetCards);
}

async function retryCard(card: BatchGenerateCard) {
  if (!(await ensureAuthenticated())) return;
  queueCardsForSubmit([card]);
}

function startSingleCard(card: BatchGenerateCard) {
  if (["queued_local", "idle", "failed", "success"].includes(card.status)) {
    void retryCard(card);
  }
}

function buildCreateTaskPayload(card: BatchGenerateCard, numImages: number) {
  return {
    model: card.model,
    prompt: card.prompt.trim(),
    num_images: numImages,
    size: card.customSizeEnabled || hideAspectRatio(card.model) ? "" : card.size,
    resolution: card.customSizeEnabled || hideResolution(card.model) ? "" : card.resolution,
    custom_size: card.customSizeEnabled && supportsCustomSize(card.model) ? card.customSize : "",
    mode: "generate" as const,
    reference_images: isImageEditModel(card.model) && buildReferenceUrls(card.referenceItems).length
      ? buildReferenceUrls(card.referenceItems)
      : undefined,
  };
}

async function submitCard(card: BatchGenerateCard, requestedCount = getCardRequestedImageCount(card)) {
  const imageCount = normalizeNumImages(requestedCount, 1);
  card.status = "submitting";
  card.errorMessage = "";
  card.images = createPendingImages(imageCount);
  card.cancelRequested = false;
  syncCardTaskIds(card, []);

  try {
    const res = await createTask(buildCreateTaskPayload(card, imageCount));
    const taskIds = res.task_ids?.length
      ? res.task_ids.map((id) => String(id || "").trim()).filter(Boolean)
      : (res.task_id ? [String(res.task_id)] : []);
    if (!taskIds.length) {
      throw new Error("服务端没有返回任务 ID");
    }

    if (card.cancelRequested) {
      await Promise.allSettled(taskIds.map((taskId) => deleteHistoryTask(taskId)));
      void refreshCurrentUser();
      return;
    }

    syncCardTaskIds(card, taskIds);
    ensureCardImageSlots(card, taskIds.length);
    if (taskIds.length < imageCount) {
      message.info(`当前剩余 ${taskIds.length} 个生成名额，已自动发起 ${taskIds.length} 个任务`);
    }
    card.status = "pending";
    card.createdAt = new Date().toISOString();
    ensurePolling();
    void refreshCurrentUser();
  } catch (err: any) {
    const detail = String(err?.response?.data?.detail || err?.message || "");
    if (isInsufficientCreditsError(err)) {
      card.status = "failed";
      card.errorMessage = formatGenerationErrorMessage(detail, "积分不足");
      card.images = createFailedImages(imageCount, card.errorMessage);
      showInsufficientCreditsPurchase(detail);
      return;
    }

    if (isSubmissionLimitError(err)) {
      card.status = "queued_local";
      card.images = createPendingImages(imageCount);
      card.errorMessage = "当前提交较频繁，系统会自动稍后重试";
      scheduleQueuePump(SUBMISSION_RETRY_DELAY_MS);
      return;
    }

    card.status = "failed";
    card.errorMessage = formatGenerationErrorMessage(detail, "创建任务失败");
    card.images = createFailedImages(imageCount, card.errorMessage);
  }
}

async function pumpQueue() {
  const availableSlots = Math.min(remainingSlots.value, remainingSubmissionSlots.value);
  if (availableSlots <= 0) return;

  const queuedCards = cards.value.filter((card) => card.status === "queued_local");
  if (!queuedCards.length) return;

  const allocations: Array<{ card: BatchGenerateCard; count: number }> = [];
  let remaining = availableSlots;
  queuedCards.forEach((card) => {
    if (remaining <= 0) return;
    const requested = getCardRequestedImageCount(card);
    const count = Math.min(requested, remaining);
    if (count <= 0) return;
    if (count < requested) {
      message.info(`当前剩余 ${count} 个生成名额，已自动为「${getCardTaskLabel(card)}」发起 ${count} 个任务`);
    }
    allocations.push({ card, count });
    remaining -= count;
  });
  if (!allocations.length) return;

  const inFlightCount = allocations.reduce((total, item) => total + item.count, 0);
  submissionInFlightCount += inFlightCount;
  try {
    await Promise.all(allocations.map(({ card, count }) => submitCard(card, count)));
  } finally {
    submissionInFlightCount = Math.max(0, submissionInFlightCount - inFlightCount);
  }

  if (
    cards.value.some((card) => card.status === "queued_local")
    && remainingSlots.value > 0
    && remainingSubmissionSlots.value > 0
  ) {
    scheduleQueuePump(350);
  }
}

function scheduleQueuePump(delay = 0) {
  if (queueTimer) clearTimeout(queueTimer);
  queueTimer = setTimeout(() => {
    queueTimer = null;
    void pumpQueue();
  }, delay);
}

function applyTaskSlotToCard(card: BatchGenerateCard, task: TaskResult, index: number) {
  ensureCardImageSlots(card, Math.max(card.images.length, index + 1, getCardTaskIds(card).length));
  const taskImage = task.images?.[0];
  if (taskImage) {
    card.images[index] = taskImage;
  } else if (["pending", "queued", "processing"].includes(task.status)) {
    if (card.images[index]?.status !== "success") {
      card.images[index] = {
        id: card.images[index]?.id || -(Date.now() + index),
        image_url: "",
        status: "pending",
      };
    }
  } else if (task.status === "failed") {
    const currentImage = card.images[index];
    card.images[index] = {
      id: currentImage && currentImage.id ? currentImage.id : -(index + 1),
      image_url: "",
      status: "failed",
      error_message: task.error_message || "",
    };
  }

  if (!card.createdAt && task.created_at) {
    card.createdAt = task.created_at;
  }
  if (task.credit_refunded) {
    card.creditRefunded = true;
  }

  if (task.status === "failed") {
    const slotError = getPreferredGenerationErrorMessage(
      task.error_message,
      task.images?.[0]?.error_message,
      Boolean(task.credit_refunded),
      "生成失败，请重试",
      Boolean(task.used_fallback_api),
      task.api_attempts,
      task.provider_error_message,
    );
    if (!card.images.some((image) => image.status === "success" || image.status === "pending")) {
      card.errorMessage = slotError;
    }
    if (card.images[index]) {
      card.images[index] = {
        ...card.images[index],
        error_message: slotError,
      };
    }
  }
}

function refreshCardFromTasks(card: BatchGenerateCard, resultMap: Map<string, TaskResult>) {
  const previousStatus = card.status;
  const slotStatuses: TaskResult["status"][] = [];
  let resolvedCreditCount = 0;
  let netCreditCost = 0;
  let hasRefundedTask = false;
  const taskIds = getCardTaskIds(card);

  taskIds.forEach((taskId, index) => {
    const task = resultMap.get(taskId);
    if (!task) return;
    slotStatuses.push(task.status);
    resolvedCreditCount += 1;
    netCreditCost += Boolean(task.credit_refunded) ? 0 : Number(task.credit_cost || 0);
    hasRefundedTask = hasRefundedTask || Boolean(task.credit_refunded);
    applyTaskSlotToCard(card, task, index);
  });
  if (resolvedCreditCount === taskIds.length && taskIds.length) {
    card.netCreditCost = netCreditCost;
    card.creditRefunded = hasRefundedTask;
  } else if (resolvedCreditCount > 0) {
    card.creditRefunded = card.creditRefunded || hasRefundedTask;
  }
  if (
    card.images.some((image) => image.status === "pending")
    || slotStatuses.includes("processing")
    || slotStatuses.includes("queued")
    || slotStatuses.includes("pending")
  ) {
    if (slotStatuses.includes("processing")) {
      card.status = "processing";
    } else if (slotStatuses.includes("queued")) {
      card.status = "queued";
    } else if (["submitting", "pending", "queued", "processing"].includes(card.status)) {
      card.status = card.status === "submitting" ? "pending" : card.status;
    } else {
      card.status = "pending";
    }
  } else {
    refreshCardAggregateStatus(card);
  }
  return previousStatus !== card.status && ["success", "failed"].includes(card.status);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function ensurePolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    void pollTaskResults();
  }, POLL_INTERVAL_MS);
}

async function pollTaskResults() {
  if (taskPollingInFlight.value) return;

  const activeCards = cards.value.filter((card) => hasIncompleteCardSlots(card));

  if (!activeCards.length) {
    stopPolling();
    if (cards.value.some((card) => card.status === "queued_local")) {
      scheduleQueuePump(0);
    }
    return;
  }

  const taskIds = Array.from(new Set(activeCards.flatMap((card) => getCardTaskIds(card))));
  if (!taskIds.length) {
    stopPolling();
    return;
  }

  taskPollingInFlight.value = true;
  try {
    const results = await getTasks(taskIds);
    const resultMap = new Map(results.map((item) => [item.id, item]));
    let shouldRefreshUser = false;

    activeCards.forEach((card) => {
      if (refreshCardFromTasks(card, resultMap)) {
        shouldRefreshUser = true;
      }
    });

    if (shouldRefreshUser) {
      void refreshCurrentUser();
    }
  } catch {
    // keep current state and continue polling next round
  } finally {
    taskPollingInFlight.value = false;
  }

  if (cards.value.some((card) => card.status === "queued_local")) {
    scheduleQueuePump(0);
  }
}

function shouldShowGeneratingCard(card: BatchGenerateCard) {
  if (card.status === "idle" || card.status === "failed") return false;
  return card.images.some((item) => item.status === "pending")
    || ["queued_local", "submitting", "pending", "queued", "processing"].includes(card.status);
}

function getResultMessage(card: BatchGenerateCard) {
  const successCount = getSuccessImages(card).length;
  const failedCount = card.images.filter((image) => image.status === "failed").length;
  if (card.status === "queued_local") return "已加入本地等待队列，系统会在有空闲并发后自动提交。";
  if (card.status === "submitting") return "正在提交任务到服务端。";
  if (card.status === "pending" || card.status === "queued") return "任务已创建，正在等待服务端处理。";
  if (card.status === "processing") return "服务端正在生成图片。";
  if (successCount > 0 && failedCount > 0) return "部分图片生成失败，可预览已完成的结果。";
  if (card.status === "success") return "生成完成，可预览或下载图片。";
  if (card.errorMessage) return card.errorMessage;
  return "";
}

function getCardResultGridColumns(card: BatchGenerateCard) {
  return Math.max(card.images.length, 1) <= 1 ? 1 : 2;
}

function getSlotErrorMessage(card: BatchGenerateCard, image: ImageResult) {
  return image.error_message || card.errorMessage || "生成失败";
}

function canFeedbackBatchSlot(card: BatchGenerateCard, index: number) {
  return Boolean(getSlotTaskId(card, index) && card.images[index] && card.images[index].status !== "pending");
}

async function loadTaskScenes() {
  sceneConfigLoading.value = true;
  try {
    taskScenes.value = await getTaskScenes();
    sceneConfigLoaded.value = true;
  } catch (err: any) {
    const detail = String(err?.response?.data?.detail || err?.message || "");
    message.error(formatGenerationErrorMessage(detail, "加载模型配置失败"));
  } finally {
    sceneConfigLoading.value = false;
  }
}

onMounted(async () => {
  window.addEventListener("paste", handleBatchReferencePaste);
  await loadTaskScenes();
  localStorage.removeItem(BATCH_GENERATE_DRAFT_KEY);
  restoreBatchGenerateDraft();
  normalizeGlobalSelections();
  cards.value.forEach((card) => normalizeCardSelections(card));
  await loadActiveHistoryCards();
  ensureInitialCard();
  if (cards.value.some((card) => hasIncompleteCardSlots(card))) {
    ensurePolling();
  }
  if (cards.value.some((card) => card.status === "queued_local")) {
    scheduleQueuePump(0);
  }
  draftHydrationReady.value = true;
  persistBatchGenerateDraft();
});

onBeforeUnmount(() => {
  stopPolling();
  if (queueTimer) clearTimeout(queueTimer);
  unbindGlobalReferenceDragHandlers?.();
  unbindCardReferenceDragHandlers.forEach((unbind) => unbind());
  unbindCardReferenceDragHandlers.clear();
  window.removeEventListener("paste", handleBatchReferencePaste);
  pendingPastePreviewUrls.value.forEach((url) => revokeObjectUrl(url));
  globalReferenceItems.value.forEach((item) => revokeObjectUrl(item.objectUrl));
  cards.value.forEach((card) => card.referenceItems.forEach((item) => revokeObjectUrl(item.objectUrl)));
});
</script>

<template>
  <div class="batch-generate-page">
    <a-card class="batch-panel batch-panel-global" :loading="sceneConfigLoading">
      <template #title>
        <div class="panel-title-row panel-title-row-global">
          <div class="panel-title-block">
            <span class="panel-title-text">全局应用设置</span>
          </div>
        </div>
      </template>
      <template #extra>
        <div class="global-panel-actions">
          <a-segmented
            class="global-scene-switch"
            :value="globalSettings.sceneType"
            :options="sceneTypeOptions"
            @update:value="handleGlobalSceneTypeChange($event as BatchSceneMode)"
          />
          <a-button
            type="primary"
            class="global-apply-btn batch-action-btn batch-action-btn-primary"
            :disabled="globalUploading"
            @click="applyGlobalSettingsToAll"
          >
            应用到全部
          </a-button>
        </div>
      </template>

      <div v-if="sceneConfigLoaded" class="panel-body panel-body-compact global-panel-body">
        <div class="batch-aspect-auto-row">
          <a-switch v-model:checked="aspectRatioAutoDetectEnabled" size="small" class="warm-switch" />
          <div class="batch-aspect-auto-text">
            <span>比例自动识别</span>
            <a-tooltip title="开启后，上传、拖拽或粘贴到某个配置的第一张参考图时，会自动选择最匹配的宽高比。">
              <button type="button" class="batch-aspect-auto-help" aria-label="比例自动识别说明">
                <QuestionCircleOutlined />
              </button>
            </a-tooltip>
          </div>
          <template v-if="supportsCustomSize(globalSettings.model)">
            <a-switch
              :checked="globalSettings.customSizeEnabled"
              size="small"
              class="warm-switch"
              @change="onGlobalCustomSizeToggle"
            />
            <div class="batch-aspect-auto-text">
              <span>自定义分辨率</span>
              <a-tooltip overlay-class-name="custom-size-help-tooltip" placement="top">
                <template #title>
                  <div class="custom-size-help-tip">
                    <div>开启后可手动输入宽高像素值：</div>
                    <ul>
                      <li>宽高须为 16 的倍数</li>
                      <li>长短边比例不超过 3:1</li>
                      <li>最大边长不超过 3840px</li>
                      <li>总像素数不得低于 655360px</li>
                    </ul>
                    <div class="custom-size-help-note">仅 G-Image2 模型支持自定义</div>
                  </div>
                </template>
                <button type="button" class="batch-aspect-auto-help" aria-label="自定义分辨率说明">
                  <QuestionCircleOutlined />
                </button>
              </a-tooltip>
            </div>
          </template>
        </div>
        <div class="global-settings-layout" :class="{ 'has-reference-column': globalSettings.sceneType === 'image_edit' }">
            <div class="global-params-column">
              <div class="field-block field-block-no-title">
                <ModelCategorySelect
                  class="card-setting-select"
                  :model-value="globalSettings.model"
                  :options="getModelSelectOptions(globalSettings.sceneType, globalSettings.customSizeEnabled ? '' : globalSettings.resolution)"
                  placeholder="选择全局模型"
                  @update:model-value="handleGlobalModelChange"
                />
              </div>

              <div v-if="!hideAspectRatio(globalSettings.model) && !globalSettings.customSizeEnabled" class="field-block field-block-no-title">
                <AspectRatioPicker
                  :model-value="globalSettings.size"
                  :options="getAspectRatioOptions(globalSettings.model)"
                  @update:model-value="globalSettings.size = $event"
                />
              </div>
              <div v-else-if="globalSettings.customSizeEnabled" class="field-block field-block-no-title batch-custom-size-field">
                <span class="batch-custom-size-label">宽度</span>
                <div class="custom-size-input-wrap">
                  <a-input-number
                    v-digits-only
                    :value="globalSettings.customWidth"
                    class="warm-input-number custom-size-input"
                    :class="{ 'is-invalid': !!getTargetCustomDimensionError(globalSettings, globalSettings.model, 'width') }"
                    :step="CUSTOM_SIZE_PIXEL_MULTIPLE"
                    :precision="0"
                    :parser="parseCustomSizeInput"
                    :formatter="formatCustomSizeInput"
                    :status="getTargetCustomDimensionError(globalSettings, globalSettings.model, 'width') ? 'error' : undefined"
                    placeholder="宽度"
                    @update:value="handleCustomWidthChange(globalSettings, globalSettings.model, $event)"
                  />
                  <span class="custom-size-unit">px</span>
                </div>
                <div v-if="getTargetCustomDimensionError(globalSettings, globalSettings.model, 'width')" class="custom-size-error">
                  {{ getTargetCustomDimensionError(globalSettings, globalSettings.model, 'width') }}
                </div>
              </div>

              <div v-if="!hideResolution(globalSettings.model) && !globalSettings.customSizeEnabled" class="field-block field-block-no-title">
                <OptionGridPicker
                  :model-value="globalSettings.resolution"
                  :options="getResolutionOptions(globalSettings.model)"
                  panel-title="选择分辨率"
                  placeholder="选择分辨率"
                  @update:model-value="globalSettings.resolution = $event"
                />
              </div>
              <div v-else-if="globalSettings.customSizeEnabled" class="field-block field-block-no-title batch-custom-size-field">
                <span class="batch-custom-size-label">高度</span>
                <div class="custom-size-input-wrap">
                  <a-input-number
                    v-digits-only
                    :value="globalSettings.customHeight"
                    class="warm-input-number custom-size-input"
                    :class="{ 'is-invalid': !!getTargetCustomDimensionError(globalSettings, globalSettings.model, 'height') }"
                    :step="CUSTOM_SIZE_PIXEL_MULTIPLE"
                    :precision="0"
                    :parser="parseCustomSizeInput"
                    :formatter="formatCustomSizeInput"
                    :status="getTargetCustomDimensionError(globalSettings, globalSettings.model, 'height') ? 'error' : undefined"
                    placeholder="高度"
                    @update:value="handleCustomHeightChange(globalSettings, globalSettings.model, $event)"
                  />
                  <span class="custom-size-unit">px</span>
                </div>
                <div v-if="getTargetCustomDimensionError(globalSettings, globalSettings.model, 'height')" class="custom-size-error">
                  {{ getTargetCustomDimensionError(globalSettings, globalSettings.model, 'height') }}
                </div>
              </div>

              <div class="field-block field-block-no-title">
                <OptionGridPicker
                  :model-value="String(globalSettings.numImages)"
                  :options="BATCH_IMAGE_COUNT_OPTIONS"
                  panel-title="选择图片数量"
                  placeholder="选择数量"
                  @update:model-value="globalSettings.numImages = Number($event)"
                />
              </div>
            </div>

            <div class="field-block global-prompt-field field-block-no-title">
              <a-textarea
                v-model:value="globalSettings.prompt"
                :rows="3"
                :maxlength="10000"
                placeholder="描述您想要生成的图片..."
                class="global-prompt-textarea"
              />
            </div>

            <div
              v-if="globalSettings.sceneType === 'image_edit'"
              :ref="setGlobalReferenceUploadBlockRef"
              class="field-block batch-ref-upload-block global-ref-upload-block"
              :class="{ 'is-reference-drag-over': globalReferenceDragActive }"
            >
              <div class="panel-head">
                <h3>参考图</h3>
                <span class="panel-hint">(最多 {{ getMaxReferenceImages(globalSettings.model) }} 张，支持拖拽、粘贴上传)</span>
              </div>

              <input
                ref="globalFileInput"
                class="hidden-input"
                type="file"
                accept="image/*"
                multiple
                @change="handleGlobalReferenceChange"
              />

              <div class="upload-grid">
                <div
                  v-for="(item, index) in globalReferenceItems"
                  :key="item.id"
                  class="upload-thumb"
                  @click="openPreview({ id: 0, image_url: item.remoteUrl || item.localUrl, preview_url: item.remoteUrl || item.localUrl, status: 'success' })"
                >
                  <img :src="getReferencePreviewUrl(item)" alt="参考图" />
                  <div v-if="item.status !== 'success'" class="upload-thumb-mask" :class="{ error: item.status === 'failed' }">
                    <a-spin v-if="item.status === 'uploading'" size="small" />
                    <span v-else>上传失败</span>
                  </div>
                  <button
                    type="button"
                    class="thumb-remove"
                    aria-label="删除参考图"
                    @click.stop="removeReferenceItem(globalReferenceItems, index)"
                  >
                    <CloseOutlined />
                  </button>
                </div>

                <div
                  v-if="globalReferenceItems.length < getMaxReferenceImages(globalSettings.model)"
                  class="upload-add"
                  @click="triggerGlobalReferenceUpload"
                >
                  <a-spin v-if="globalUploading" size="small" />
                  <template v-else>
                    <UploadOutlined class="upload-add-icon" />
                    <span>{{ globalReferenceDragActive ? "松开上传" : "拖拽、粘贴或点击" }}</span>
                  </template>
                </div>
              </div>
            </div>
          </div>
      </div>
    </a-card>

    <div class="toolbar-row">
      <div class="toolbar-left">
        <a-button
          type="primary"
          class="batch-action-btn batch-action-btn-primary"
          :disabled="sceneConfigLoading || globalUploading"
          @click="startBatchGenerate"
        >
          <template #icon><PlayCircleOutlined /></template>
          开始批量生成
        </a-button>
        <a-button
          class="batch-action-btn batch-action-btn-neutral"
          :disabled="!hasFinishedCards"
          @click="clearFinishedCards"
        >
          <template #icon><DeleteOutlined /></template>
          清空已完成/失败
        </a-button>
        <a-button
          class="batch-action-btn batch-action-btn-secondary"
          :disabled="!downloadableImages.length"
          @click="downloadAllImages"
        >
          <template #icon><DownloadOutlined /></template>
          下载全部
        </a-button>
      </div>
      <div class="toolbar-note">
        生图卡片可手动新增到并发上限，提交时系统会自动按空闲槽位依次发起请求。
      </div>
    </div>

    <TransitionGroup name="batch-card" tag="div" class="batch-task-card-list">
      <a-card
        v-for="(card, index) in cards"
        :key="card.id"
        class="batch-card batch-card-compact"
        :class="{ 'batch-card-highlighted': card.highlighted }"
      >
        <template #title>
          <div class="panel-title-row">
            <span>任务{{ index + 1 }}</span>
            <a-tag :color="getStatusColor(card.status)">{{ getStatusLabel(card.status) }}</a-tag>
          </div>
        </template>
        <template #extra>
          <div class="card-header-actions">
            <a-segmented
              class="global-scene-switch"
              :value="card.sceneType"
              :options="sceneTypeOptions"
              :disabled="isCardLocked(card)"
              @update:value="handleCardSceneTypeChange(card, $event as BatchSceneMode)"
            />
            <a-tooltip :title="getCardCloseButtonTitle(card)">
              <a-button type="text" danger class="card-close-btn" :disabled="!canRemoveCard(card)" @click="removeCard(card)">
                <template #icon><CloseOutlined /></template>
              </a-button>
            </a-tooltip>
          </div>
        </template>

        <div class="panel-body panel-body-card">
          <div class="card-form-grid">
            <div class="field-block field-block-inline-fit field-block-no-title setting-model-row">
              <ModelCategorySelect
                class="card-setting-select"
                :model-value="card.model"
                :disabled="isCardLocked(card)"
                :options="getModelSelectOptions(card.sceneType, card.customSizeEnabled ? '' : card.resolution)"
                placeholder="选择模型"
                @update:model-value="handleCardModelChange(card, $event)"
              />
            </div>

            <div v-if="supportsCustomSize(card.model)" class="batch-aspect-auto-row batch-card-custom-size-row">
              <a-switch
                :checked="card.customSizeEnabled"
                size="small"
                class="warm-switch"
                :disabled="isCardLocked(card)"
                @change="(checked: boolean | string | number) => onCardCustomSizeToggle(card, Boolean(checked))"
              />
              <div class="batch-aspect-auto-text">
                <span>自定义分辨率</span>
                <a-tooltip overlay-class-name="custom-size-help-tooltip" placement="top">
                  <template #title>
                    <div class="custom-size-help-tip">
                      <div>开启后可手动输入宽高像素值，并与宽高比/分辨率互斥。</div>
                    </div>
                  </template>
                  <button type="button" class="batch-aspect-auto-help" aria-label="自定义分辨率说明">
                    <QuestionCircleOutlined />
                  </button>
                </a-tooltip>
              </div>
            </div>

            <div class="setting-inline-row setting-inline-row-primary">
              <div
                v-if="!hideAspectRatio(card.model) && !card.customSizeEnabled"
                class="field-block field-block-inline-fit field-block-no-title setting-model-cell"
                :class="{ 'card-setting-disabled': isCardLocked(card) }"
              >
                <AspectRatioPicker
                  :model-value="card.size"
                  :options="getAspectRatioOptions(card.model)"
                  @update:model-value="card.size = $event"
                />
              </div>
              <div
                v-else-if="card.customSizeEnabled"
                class="field-block field-block-inline-fit field-block-no-title setting-quarter-cell batch-custom-size-field batch-custom-size-field-bare"
                :class="{ 'card-setting-disabled': isCardLocked(card) }"
              >
                <div class="custom-size-input-wrap">
                  <a-input-number
                    v-digits-only
                    :value="card.customWidth"
                    class="warm-input-number custom-size-input"
                    :class="{ 'is-invalid': !!getTargetCustomDimensionError(card, card.model, 'width') }"
                    :disabled="isCardLocked(card)"
                    :step="CUSTOM_SIZE_PIXEL_MULTIPLE"
                    :precision="0"
                    :parser="parseCustomSizeInput"
                    :formatter="formatCustomSizeInput"
                    :status="getTargetCustomDimensionError(card, card.model, 'width') ? 'error' : undefined"
                    placeholder="宽度"
                    @update:value="handleCustomWidthChange(card, card.model, $event)"
                  />
                  <span class="custom-size-unit">px</span>
                </div>
              </div>

              <div
                v-if="!hideResolution(card.model) && !card.customSizeEnabled"
                class="field-block field-block-inline-fit field-block-no-title setting-quarter-cell"
                :class="{ 'card-setting-disabled': isCardLocked(card) }"
              >
                <OptionGridPicker
                  :model-value="card.resolution"
                  :options="getResolutionOptions(card.model)"
                  panel-title="选择分辨率"
                  placeholder="选择分辨率"
                  @update:model-value="card.resolution = $event"
                />
              </div>
              <div
                v-else-if="card.customSizeEnabled"
                class="field-block field-block-inline-fit field-block-no-title setting-quarter-cell batch-custom-size-field batch-custom-size-field-bare"
                :class="{ 'card-setting-disabled': isCardLocked(card) }"
              >
                <div class="custom-size-input-wrap">
                  <a-input-number
                    v-digits-only
                    :value="card.customHeight"
                    class="warm-input-number custom-size-input"
                    :class="{ 'is-invalid': !!getTargetCustomDimensionError(card, card.model, 'height') }"
                    :disabled="isCardLocked(card)"
                    :step="CUSTOM_SIZE_PIXEL_MULTIPLE"
                    :precision="0"
                    :parser="parseCustomSizeInput"
                    :formatter="formatCustomSizeInput"
                    :status="getTargetCustomDimensionError(card, card.model, 'height') ? 'error' : undefined"
                    placeholder="高度"
                    @update:value="handleCustomHeightChange(card, card.model, $event)"
                  />
                  <span class="custom-size-unit">px</span>
                </div>
              </div>

              <div
                class="field-block field-block-inline-fit field-block-no-title setting-quarter-cell"
                :class="{ 'card-setting-disabled': isCardLocked(card) }"
              >
                <OptionGridPicker
                  :model-value="String(card.numImages)"
                  :options="BATCH_IMAGE_COUNT_OPTIONS"
                  panel-title="选择图片数量"
                  placeholder="选择数量"
                  @update:model-value="card.numImages = Number($event)"
                />
              </div>
            </div>

            <div
              v-if="card.sceneType === 'image_edit'"
              :ref="(el) => setCardReferenceUploadBlockRef(card.id, el)"
              class="field-block batch-ref-upload-block"
              :class="{ 'is-reference-drag-over': card.dragActive }"
            >
              <div class="panel-head">
                <h3>参考图</h3>
                <span class="panel-hint">
                  {{ isImageEditModel(card.model) ? `(最多 ${getMaxReferenceImages(card.model)} 张，支持拖拽、粘贴上传)` : "(可上传参考图，当前模型默认不使用)" }}
                </span>
              </div>

              <input
                :ref="(el) => setCardFileInput(card.id, el)"
                class="hidden-input"
                type="file"
                accept="image/*"
                multiple
                @change="handleCardReferenceChange(card.id, $event)"
              />

              <div class="upload-grid">
                <div
                  v-for="(item, refIndex) in card.referenceItems"
                  :key="item.id"
                  class="upload-thumb"
                  @click="openPreview({ id: 0, image_url: item.remoteUrl || item.localUrl, preview_url: item.remoteUrl || item.localUrl, status: 'success' })"
                >
                  <img :src="getReferencePreviewUrl(item)" alt="参考图" />
                  <div v-if="item.status !== 'success'" class="upload-thumb-mask" :class="{ error: item.status === 'failed' }">
                    <a-spin v-if="item.status === 'uploading'" size="small" />
                    <span v-else>上传失败</span>
                  </div>
                  <button
                    type="button"
                    class="thumb-remove"
                    aria-label="删除参考图"
                    :disabled="isCardLocked(card)"
                    @click.stop="removeReferenceItem(card.referenceItems, refIndex)"
                  >
                    <CloseOutlined />
                  </button>
                </div>

                <div
                  v-if="card.referenceItems.length < getMaxReferenceImages(card.model)"
                  class="upload-add"
                  :class="{ disabled: isCardLocked(card) }"
                  @click="triggerCardReferenceUpload(card.id)"
                >
                  <a-spin v-if="hasUploadingReferences(card.referenceItems)" size="small" />
                  <template v-else>
                    <UploadOutlined class="upload-add-icon" />
                    <span>{{ card.dragActive ? "松开上传" : "拖拽、粘贴或点击" }}</span>
                  </template>
                </div>
              </div>
            </div>

            <div class="field-block field-block-wide field-block-no-title">
              <a-textarea
                v-model:value="card.prompt"
                :rows="4"
                :maxlength="10000"
                :disabled="isCardLocked(card)"
                placeholder="描述您想要生成的图片..."
              />
            </div>
          </div>

          <div class="result-panel result-panel-compact">
            <div class="result-panel-head">
              <div class="result-panel-actions">
                <a-button
                  type="primary"
                  class="single-submit-btn batch-action-btn batch-action-btn-primary"
                  :disabled="!['failed', 'idle', 'success'].includes(card.status)"
                  @click="startSingleCard(card)"
                >
                  <template #icon><PlayCircleOutlined /></template>
                  {{ getSingleSubmitButtonLabel(card) }}
                </a-button>
                <a-button
                  class="batch-action-btn batch-action-btn-neutral"
                  :disabled="cards.length >= MAX_BATCH_CARDS"
                  @click="duplicateCard(card)"
                >
                  <template #icon><CopyOutlined /></template>
                  复制任务
                </a-button>
              </div>
            </div>

            <div class="result-body">
              <div v-if="!shouldShowGeneratingCard(card) && getResultMessage(card)" class="result-info">
                <div class="result-message">
                  <CheckCircleFilled v-if="card.status === 'success'" class="success-icon" />
                  <span>{{ getResultMessage(card) }}</span>
                </div>
              </div>

              <div
                class="result-preview-shell"
                :class="{
                  'is-single': card.images.length <= 1,
                  'is-multi': card.images.length > 1,
                  'is-scrollable': card.images.length > 4,
                }"
                :style="{
                  '--result-columns': String(getCardResultGridColumns(card)),
                }"
              >
                <template v-if="card.images.length">
                  <div
                    v-for="(image, imageIndex) in card.images"
                    :key="`${card.id}-${getSlotTaskId(card, imageIndex) || image.id || imageIndex}`"
                    class="result-slot is-clickable"
                    @click="openBatchTaskDetail(card, imageIndex)"
                  >
                    <div v-if="image.status === 'success' && (image.image_url || image.preview_url)" class="result-success-frame">
                      <img :src="getDisplayImageUrl(image)" alt="生图结果" class="result-image" />
                      <div class="result-hover-actions result-hover-actions-top">
                        <a-button
                          v-if="canFeedbackBatchSlot(card, imageIndex)"
                          shape="circle"
                          class="result-hover-action"
                          @click.stop="openFeedbackDialogForBatchCard(card, imageIndex)"
                        >
                          <template #icon><MessageOutlined /></template>
                        </a-button>
                        <a-button
                          v-if="canDeleteBatchCardTask(card)"
                          shape="circle"
                          class="result-hover-action result-hover-action-danger"
                          @click.stop="confirmRemoveBatchCardTask(card)"
                        >
                          <template #icon><DeleteOutlined /></template>
                        </a-button>
                      </div>
                      <div class="result-hover-actions">
                        <a-button shape="circle" class="result-hover-action" @click.stop="openPreview(image)">
                          <template #icon><EyeOutlined /></template>
                        </a-button>
                        <a-button
                          v-if="canEditBatchGeneratedImage(card, image)"
                          shape="circle"
                          class="result-hover-action"
                          @click.stop="handleEditBatchGeneratedImage(card, image)"
                        >
                          <template #icon><EditOutlined /></template>
                        </a-button>
                        <a-button
                          shape="circle"
                          class="result-hover-action"
                          :href="getDownloadUrl(image.id, image.image_url, image.preview_url)"
                          target="_blank"
                          @click.stop
                        >
                          <template #icon><DownloadOutlined /></template>
                        </a-button>
                      </div>
                    </div>
                    <div v-else-if="image.status === 'failed'" class="result-failed">
                      <img :src="failedResultAsset" alt="生成失败" class="failed-image" />
                      <div class="result-hover-actions result-hover-actions-top">
                        <a-button
                          v-if="canFeedbackBatchSlot(card, imageIndex)"
                          shape="circle"
                          class="result-hover-action"
                          @click.stop="openFeedbackDialogForBatchCard(card, imageIndex)"
                        >
                          <template #icon><MessageOutlined /></template>
                        </a-button>
                        <a-button
                          v-if="canDeleteBatchCardTask(card)"
                          shape="circle"
                          class="result-hover-action result-hover-action-danger"
                          @click.stop="confirmRemoveBatchCardTask(card)"
                        >
                          <template #icon><DeleteOutlined /></template>
                        </a-button>
                      </div>
                      <div class="result-failed-overlay">
                        <span>{{ getSlotErrorMessage(card, image) }}</span>
                      </div>
                    </div>
                    <div v-else class="result-generating">
                      <a-spin size="large" />
                      <span class="result-generating-title">正在生成图片...</span>
                      <span class="result-generating-sub">预计 30 秒 ～ 2 分钟</span>
                    </div>
                  </div>
                </template>
                <div v-else class="result-empty is-clickable" @click="openBatchTaskDetail(card)">
                  <span>结果图将在这里展示</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </a-card>
      <button
        v-if="canAddMoreCards"
        type="button"
        class="batch-add-placeholder"
        @click="addCard"
      >
        <span class="batch-add-placeholder-icon">+</span>
        <span class="batch-add-placeholder-text">添加新任务</span>
      </button>
    </TransitionGroup>

    <a-modal v-model:open="previewVisible" title="图片预览" :footer="null" width="880px">
      <img :src="previewCurrent" alt="预览图" class="preview-modal-image" />
    </a-modal>
    <a-modal
      v-model:open="pasteDialogVisible"
      title="选择粘贴作用范围"
      width="760px"
      :confirm-loading="pasteDialogSubmitting"
      ok-text="开始应用"
      cancel-text="取消"
      @ok="confirmPasteDialog"
      @cancel="resetPasteDialogState"
    >
      <div class="paste-scope-dialog">
        <div class="paste-scope-tip">
          已检测到 {{ pendingPasteFiles.length }} 张粘贴图片。图片只会上传一次，若作用到多个卡片，将复用同一张已上传参考图。
        </div>
        <div v-if="pendingPastePreviewUrls.length" class="paste-preview-grid">
          <button
            v-for="(url, index) in pendingPastePreviewUrls"
            :key="`${url}-${index}`"
            type="button"
            class="paste-preview-item"
            @click="previewCurrent = url; previewVisible = true"
          >
            <img :src="url" :alt="`粘贴图片 ${index + 1}`" />
          </button>
        </div>
        <a-radio-group v-model:value="pasteDialogScope" class="paste-scope-group">
          <a-radio-button value="global" :disabled="globalSettings.sceneType !== 'image_edit'">加入全局参考图</a-radio-button>
          <a-radio-button value="all_cards" :disabled="!pasteEligibleCards.length">作用到所有卡片</a-radio-button>
          <a-radio-button value="single_card" :disabled="!pasteEligibleCards.length">作用到选中卡片</a-radio-button>
        </a-radio-group>
        <div class="paste-scope-desc-inline">
          <template v-if="pasteDialogScope === 'global'">
            后续可继续通过“应用到全部”带入所有卡片。
          </template>
          <template v-else-if="pasteDialogScope === 'all_cards'">
            会按每张图编辑卡片自己的参考图上限分别加入。
          </template>
          <template v-else>
            可多选卡片，仅把粘贴图片加入你选中的那些卡片。
          </template>
        </div>
        <div v-if="pasteDialogScope === 'single_card'" class="paste-card-grid">
          <button
            v-for="card in pasteEligibleCards"
            :key="card.id"
            type="button"
            class="paste-card-chip"
            :class="{ active: pasteDialogTargetCardIds.includes(card.id) }"
            @click="togglePasteTargetCard(card.id)"
          >
            <div class="paste-card-chip-head">
              <span class="paste-card-chip-title">任务 {{ cards.findIndex((item) => item.id === card.id) + 1 }}</span>
              <span
                class="paste-card-chip-check"
                :class="{ active: pasteDialogTargetCardIds.includes(card.id) }"
                aria-hidden="true"
              >
                <span class="paste-card-chip-check-icon">{{ pasteDialogTargetCardIds.includes(card.id) ? "✓" : "" }}</span>
              </span>
            </div>
            <div class="paste-card-chip-subhead">
              <span class="paste-card-chip-meta">
                {{ card.referenceItems.length }}/{{ getMaxReferenceImages(card.model) }} 张参考图
              </span>
            </div>
            <div class="paste-card-chip-desc">{{ card.prompt.trim() || "未填写提示词" }}</div>
          </button>
        </div>
      </div>
    </a-modal>
    <HistoryDetailDialog
      v-model:open="detailOpen"
      :item="detailItem"
      :model-options="detailModelOptions"
      hide-credit-cost
      :has-prev="hasDetailPrev"
      :has-next="hasDetailNext"
      show-actions
      @reedit="handleDetailReedit"
      @download="handleDetailDownload"
      @navigate-prev="navigateBatchTaskDetail(-1)"
      @navigate-next="navigateBatchTaskDetail(1)"
    />
    <FeedbackDialog
      v-model:open="feedbackDialogOpen"
      :task-id="feedbackTarget?.taskId"
      :model="feedbackTarget?.model"
      :prompt="feedbackTarget?.prompt"
      :created-at="feedbackTarget?.createdAt"
    />
  </div>
</template>

<style scoped lang="scss">
.batch-generate-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 10px 0 24px;
}

.batch-panel,
.batch-card {
  border-radius: 12px;
  border: 1px solid var(--theme-border);
  box-shadow: none;
}

.batch-card {
  transform-origin: center top;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    background-color var(--motion-duration-fast) var(--motion-ease-soft);
  will-change: transform, box-shadow;
}

.batch-card:hover,
.batch-card:focus-within {
  transform: translateY(-3px);
  border-color: rgba(255, 184, 77, 0.56);
  box-shadow:
    0 12px 28px rgba(34, 22, 10, 0.08),
    0 4px 12px rgba(245, 158, 11, 0.08);
}

.batch-card.batch-card-move:hover,
.batch-card.batch-card-move:focus-within {
  transform: none;
}

.batch-card-highlighted {
  border-color: rgba(255, 172, 38, 0.72);
  box-shadow:
    0 0 0 2px rgba(255, 172, 38, 0.18),
    0 12px 26px rgba(245, 158, 11, 0.16);
  animation: batch-card-highlight-pulse 2.4s ease;
}

@keyframes batch-card-highlight-pulse {
  0% {
    border-color: rgba(255, 172, 38, 0.18);
    box-shadow:
      0 0 0 0 rgba(255, 172, 38, 0),
      0 0 0 rgba(245, 158, 11, 0);
  }
  22% {
    border-color: rgba(255, 172, 38, 0.82);
    box-shadow:
      0 0 0 4px rgba(255, 172, 38, 0.24),
      0 16px 30px rgba(245, 158, 11, 0.2);
  }
  100% {
    border-color: rgba(255, 172, 38, 0.18);
    box-shadow:
      0 0 0 0 rgba(255, 172, 38, 0),
      0 0 0 rgba(245, 158, 11, 0);
  }
}

.batch-card-enter-active,
.batch-card-leave-active {
  transition:
    opacity var(--motion-duration-reveal-slower) var(--motion-ease-enter),
    transform var(--motion-duration-reveal-slower) var(--motion-ease-enter),
    filter var(--motion-duration-reveal-slower) var(--motion-ease-enter);
}

.batch-card-move {
  transition: transform var(--motion-duration-reveal) var(--motion-ease-soft);
}

.batch-add-placeholder.batch-card-move,
.batch-card.batch-card-move {
  transition: transform var(--motion-duration-reveal) var(--motion-ease-soft) !important;
}

.batch-card-enter-from {
  opacity: 0;
  transform: translateY(18px) scale(0.985);
  filter: blur(4px);
}

.batch-card-leave-to {
  opacity: 0;
  transform: translateY(-10px) scale(0.985);
  filter: blur(3px);
}

.batch-card-leave-active {
  pointer-events: none;
  position: absolute;
  z-index: 1;
  width: calc((100% - 36px) / 4);
}

.panel-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.panel-title-row-global {
  align-items: flex-start;
}

.panel-title-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.panel-title-text {
  color: var(--theme-title);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.2;
}

.card-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.card-close-btn {
  padding-inline: 4px;
  min-width: 28px;
  height: 28px;
}

.panel-title-tip {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 400;
}

.panel-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-body-compact {
  gap: 10px;
}

.batch-panel-global :deep(.ant-card-head) {
  min-height: 52px;
  padding: 0 16px;
}

.batch-panel-global :deep(.ant-card-head-title),
.batch-panel-global :deep(.ant-card-extra) {
  padding: 8px 0;
}

.global-panel-body {
  gap: 12px;
}

.global-panel-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.batch-aspect-auto-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.batch-aspect-auto-text {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 13px;
}

.batch-aspect-auto-help {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: color var(--motion-duration-fast) var(--motion-ease-soft);
}

.batch-aspect-auto-help:hover {
  color: var(--theme-accent);
}

.batch-card-custom-size-row {
  margin-bottom: 0;
}

.field-block.batch-custom-size-field {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.batch-custom-size-label {
  flex: 0 0 auto;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}

.custom-size-input-wrap {
  position: relative;
  flex: 1 1 0;
  min-width: 96px;
  max-width: 132px;
  margin-left: auto;
}

.batch-custom-size-field-bare .custom-size-input-wrap {
  max-width: none;
  margin-left: 0;
}

.custom-size-error {
  flex: 1 1 100%;
  margin-top: 0;
  color: #d4380d;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
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

.batch-custom-size-field :deep(.custom-size-input.ant-input-number) {
  display: flex;
  align-items: center;
  width: 100%;
  height: 34px;
  min-height: 34px;
  border-radius: 10px !important;
}

.batch-custom-size-field :deep(.custom-size-input.ant-input-number .ant-input-number-input) {
  height: 34px;
  line-height: 34px;
  padding-right: 36px;
  font-size: 13px;
}

.batch-custom-size-field :deep(.custom-size-input.is-invalid.ant-input-number),
.batch-custom-size-field :deep(.custom-size-input.ant-input-number-status-error) {
  border-color: #d4380d !important;
}

.global-scene-switch {
  flex-shrink: 0;
}

.global-settings-layout {
  display: grid;
  grid-template-columns: minmax(168px, 200px) minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
  min-height: 118px;
}

.global-settings-layout.has-reference-column {
  grid-template-columns: minmax(168px, 200px) minmax(0, 1fr) minmax(0, 1fr);
}

.global-params-column {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  height: 100%;
}

.global-prompt-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  min-height: 0;
  height: 100%;
}

.global-prompt-textarea {
  flex: 1;
  min-height: 0;
}

.batch-panel-global .global-prompt-textarea :deep(textarea) {
  height: 100% !important;
  min-height: 118px;
  resize: none;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.global-settings-row {
  display: grid;
  grid-template-columns: minmax(120px, 150px) minmax(180px, 1fr) minmax(240px, 1.2fr) repeat(3, minmax(120px, auto));
  gap: 10px;
  align-items: end;
}

.global-settings-row-inline {
  grid-template-columns: minmax(180px, 1.3fr) repeat(3, minmax(110px, auto));
  align-items: center;
}

.global-setting-inline-row-primary {
  display: flex;
  gap: 8px;
  align-items: center;
}

.global-ref-upload-block {
  margin-top: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 118px;
}

.global-ref-upload-block .upload-grid {
  flex: 1;
  align-content: start;
}

.batch-panel-global .global-params-column :deep(.card-setting-select),
.batch-panel-global .global-params-column :deep(.option-grid-picker) {
  width: 100%;
  max-width: 100%;
}

.batch-panel-global .global-params-column :deep(.card-setting-select) {
  background: linear-gradient(180deg, var(--theme-control-bg), var(--theme-panel-bg-soft));
  border: 1px solid var(--theme-control-border);
  border-radius: 10px;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 4px 12px var(--theme-shadow-soft);
}

.batch-panel-global .global-params-column :deep(.card-setting-select .ant-select-selector) {
  height: 34px !important;
  min-height: 34px;
  border: none !important;
  border-radius: 10px !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 10px !important;
  font-size: 13px;
  font-weight: 600;
}

.batch-panel-global .global-params-column :deep(.card-setting-select .ant-select-selection-item),
.batch-panel-global .global-params-column :deep(.card-setting-select .ant-select-selection-placeholder) {
  line-height: 34px !important;
}

.batch-panel-global .global-params-column :deep(.card-setting-select .ant-select-selection-item) {
  font-weight: 700;
}

.batch-panel-global .global-params-column :deep(.card-setting-select .ant-select-selection-placeholder) {
  font-weight: 400;
}

.batch-model-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: 2px 0;
}

.batch-model-option-label {
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
}

.batch-model-option-desc {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.3;
}

.batch-panel-global .global-params-column :deep(.option-grid-trigger) {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  height: 34px;
  min-height: 34px;
  border-radius: 10px;
  padding: 0 10px;
  font-size: 13px;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 4px 12px var(--theme-shadow-soft);
}

.batch-panel-global .global-params-column :deep(.option-grid-trigger:hover),
.batch-panel-global .global-params-column :deep(.option-grid-trigger.open) {
  transform: none;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 4px 12px var(--theme-shadow-soft);
}

.batch-panel-global .global-params-column :deep(.option-grid-trigger.open) {
  border-color: var(--theme-border-accent);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 0 0 3px var(--theme-focus-ring),
    0 4px 12px var(--theme-shadow-soft);
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.field-block-no-title {
  justify-content: center;
}

.field-block-no-title .field-label {
  display: none;
}

.field-block-wide {
  grid-column: 1 / -1;
}

.global-apply-btn {
  min-width: 108px;
}

.batch-action-btn {
  height: 34px;
  padding: 0 14px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(245, 158, 11, 0.16);
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft);
}

.batch-action-btn:hover,
.batch-action-btn:focus {
  transform: translateY(-1px);
}

.batch-action-btn:disabled,
.batch-action-btn.ant-btn-disabled {
  transform: none !important;
  box-shadow: none !important;
}

.batch-action-btn-primary {
  border: none !important;
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  box-shadow: 0 10px 22px var(--theme-shadow-strong);
}

.batch-action-btn-primary:hover,
.batch-action-btn-primary:focus {
  border: none !important;
  background: var(--theme-accent-strong) !important;
  color: var(--theme-accent-contrast) !important;
  box-shadow: 0 14px 26px var(--theme-shadow-strong) !important;
}

.batch-action-btn-secondary {
  border: 1px solid var(--theme-panel-border-strong) !important;
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
  box-shadow: 0 8px 18px var(--theme-shadow-soft);
}

.batch-action-btn-secondary:hover,
.batch-action-btn-secondary:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
  box-shadow: 0 12px 22px var(--theme-shadow-medium) !important;
}

.batch-action-btn-neutral {
  border: 1px solid var(--theme-control-border) !important;
  background: linear-gradient(180deg, var(--theme-control-bg), var(--theme-panel-bg-soft)) !important;
  color: var(--theme-title) !important;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 8px 18px var(--theme-shadow-soft);
}

.batch-action-btn-neutral:hover,
.batch-action-btn-neutral:focus {
  border-color: var(--theme-border-strong) !important;
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-control-bg)) !important;
  color: var(--theme-title) !important;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 12px 22px var(--theme-shadow-medium) !important;
}

:deep(.global-scene-switch.ant-segmented) {
  padding: 3px;
  border: none !important;
  border-radius: 10px !important;
  background: var(--theme-panel-bg-strong) !important;
  box-shadow: inset 0 0 0 1px var(--theme-panel-border) !important;
}

:deep(.global-scene-switch .ant-segmented-group) {
  gap: 2px;
}

:deep(.global-scene-switch .ant-segmented-item) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  line-height: 24px;
  font-size: 12px;
  font-weight: 600;
  color: var(--theme-accent-text);
  border-radius: 8px;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);
}

:deep(.global-scene-switch .ant-segmented-item-label) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  line-height: 1;
}

:deep(.global-scene-switch .ant-segmented-item-selected) {
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  box-shadow: 0 6px 16px var(--theme-shadow-strong) !important;
}

.field-label {
  color: var(--theme-title);
  font-size: 12px;
  font-weight: 600;
}

.field-tip {
  color: var(--text-muted);
  font-size: 11px;
}

.reference-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reference-section-inline {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: nowrap;
}

.reference-section-inline .section-label-row {
  min-width: 180px;
  justify-content: flex-start;
}

.reference-section-inline .reference-toolbar {
  flex-shrink: 0;
}

.reference-section-inline .reference-list {
  flex: 1;
  grid-template-columns: repeat(auto-fill, minmax(88px, 88px));
  justify-content: flex-end;
}

.section-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.reference-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hidden-input {
  display: none;
}

.reference-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(116px, 1fr));
  gap: 8px;
}

.reference-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border: 1px solid var(--theme-border);
  border-radius: 10px;
  background: var(--theme-panel-bg);
}

.reference-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 10px;
  background: color-mix(in srgb, var(--theme-accent) 6%, var(--theme-panel-bg));
}

.reference-item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.panel-head h3 {
  margin: 0;
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 600;
}

.panel-hint {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.batch-ref-upload-block {
  padding: 8px;
  border: 1px solid var(--theme-border);
  border-radius: 12px;
  background: var(--theme-panel-bg);
  transition:
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);
}

.batch-ref-upload-block.is-reference-drag-over {
  border-color: var(--theme-border-accent);
  background: color-mix(in srgb, var(--theme-accent) 6%, var(--theme-panel-bg));
  box-shadow: 0 0 0 3px var(--theme-focus-ring);
}

.upload-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-content: start;
}

.upload-thumb {
  position: relative;
  overflow: hidden;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: 8px;
  border: 1px solid var(--theme-border);
  cursor: pointer;
  background: var(--theme-panel-bg-muted);
}

.upload-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.upload-thumb-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(76, 52, 26, 0.38);
  color: #fff;
  font-size: 10px;
}

.upload-thumb-mask.error {
  background: rgba(185, 64, 64, 0.48);
}

.thumb-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 2;
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  cursor: pointer;
  font-size: 9px;
  opacity: 0;
  transform: scale(0.92);
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.upload-thumb:hover .thumb-remove,
.upload-thumb:focus-within .thumb-remove {
  opacity: 1;
  transform: scale(1);
}

.thumb-remove:hover,
.thumb-remove:focus-visible {
  background: rgba(0, 0, 0, 0.92);
}

.upload-add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  padding: 4px;
  border: 1px dashed var(--theme-border-accent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--theme-accent) 4%, var(--theme-panel-bg));
  color: var(--theme-accent-text);
  font-size: 9px;
  line-height: 1.15;
  cursor: pointer;
  text-align: center;
}

.upload-add-icon {
  font-size: 14px;
}

.toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-note {
  color: var(--text-muted);
  font-size: 12px;
}

.batch-task-card-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
  width: 100%;
}

.batch-task-card-list > :deep(.ant-card) {
  min-width: 0;
}

.batch-card-compact :deep(.ant-card-head) {
  min-height: 46px;
  padding: 0 10px;
}

.batch-card-compact :deep(.ant-card-head-title) {
  padding: 8px 0;
  font-size: 13px;
}

.batch-card-compact :deep(.ant-card-body) {
  padding: 10px;
}

.batch-add-placeholder {
  min-height: 100%;
  border: 1px dashed var(--theme-border-accent);
  border-radius: 24px;
  background: color-mix(in srgb, var(--theme-accent) 6%, var(--theme-panel-bg));
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 20px 40px var(--theme-shadow-soft);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 32px 20px;
  color: var(--theme-accent-text);
  cursor: pointer;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.batch-add-placeholder:hover,
.batch-add-placeholder:focus {
  transform: translateY(-2px);
  border-color: var(--theme-accent);
  color: var(--theme-accent-text-hover);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 0 0 3px var(--theme-focus-ring),
    0 24px 46px var(--theme-shadow-medium);
  background: color-mix(in srgb, var(--theme-accent) 9%, var(--theme-panel-bg));
}

.batch-add-placeholder-icon {
  font-size: 64px;
  line-height: 1;
  font-weight: 500;
}

.batch-add-placeholder-text {
  font-size: 16px;
  line-height: 1.3;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.panel-body-card {
  gap: 10px;
}

.field-block-inline-fit {
  min-width: 0;
}

.card-setting-disabled {
  pointer-events: none;
  opacity: 0.6;
}

.card-form-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.setting-model-row {
  width: 100%;
}

.setting-inline-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  align-items: start;
}

.setting-inline-row-primary {
  display: flex;
  gap: 8px;
  align-items: center;
}

.setting-model-cell {
  flex: 2 1 0;
  min-width: 0;
}

.setting-quarter-cell {
  flex: 1 1 0;
  min-width: 0;
}

.reference-section-card .section-label-row {
  align-items: flex-start;
  gap: 8px;
}

.result-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.result-panel-compact {
  gap: 8px;
  padding: 0;
  border-radius: 0;
}

.result-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.result-panel-actions {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.result-title {
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 600;
}

.single-submit-btn {
  min-width: 138px;
}

.single-submit-btn:hover,
.single-submit-btn:focus {
  color: #5b3300 !important;
}

.result-body {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(240px, 320px);
  gap: 18px;
  align-items: stretch;
}

.result-panel-compact .result-body {
  grid-template-columns: 1fr;
  gap: 8px;
}

.result-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-message {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--theme-title);
  font-size: 12px;
  line-height: 1.55;
}

.success-icon {
  color: var(--theme-accent);
}

.result-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.result-preview-shell {
  --result-gap: 8px;
  display: grid;
  grid-template-columns: repeat(var(--result-columns, 1), minmax(0, 1fr));
  gap: var(--result-gap);
  width: 100%;
  aspect-ratio: 1 / 1;
  overflow: hidden;
}

.result-preview-shell.is-single {
  grid-template-rows: minmax(0, 1fr);
}

.result-preview-shell.is-multi {
  grid-auto-rows: calc((100% - var(--result-gap)) / 2);
}

.result-preview-shell.is-scrollable {
  overflow-y: auto;
  padding-right: 2px;
}

.result-preview-shell.is-scrollable::-webkit-scrollbar {
  width: 6px;
}

.result-preview-shell.is-scrollable::-webkit-scrollbar-thumb {
  border-radius: 8px;
  background: var(--theme-border);
}

.result-slot {
  position: relative;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
  aspect-ratio: 1 / 1;
  overflow: hidden;
}

.result-slot.is-clickable,
.result-empty.is-clickable {
  cursor: pointer;
}

.result-slot > * {
  width: 100%;
  height: 100%;
}

.result-preview-shell.is-single .result-empty {
  width: 100%;
  height: 100%;
}

.result-success-frame {
  position: relative;
  overflow: hidden;
  width: 100%;
  height: 100%;
  border-radius: 10px;
}

.result-image {
  width: 100%;
  height: 100%;
  border-radius: 10px;
  border: 1px solid var(--theme-border);
  object-fit: contain;
  background: var(--theme-panel-bg-muted);
  display: block;
}

.result-hover-actions {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.result-hover-actions-top {
  top: 12px;
  right: 12px;
  bottom: auto;
}

.result-success-frame:hover .result-hover-actions,
.result-success-frame:focus-within .result-hover-actions,
.result-failed:hover .result-hover-actions,
.result-failed:focus-within .result-hover-actions,
.result-slot:hover .result-hover-actions,
.result-slot:focus-within .result-hover-actions {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.result-hover-action {
  border: 1px solid rgba(255, 240, 214, 0.18) !important;
  background: rgba(76, 52, 26, 0.58) !important;
  color: #fff7ea !important;
  box-shadow: 0 10px 20px rgba(34, 22, 10, 0.22);
  backdrop-filter: blur(10px);
  width: 30px;
  height: 30px;
  min-width: 30px;
  padding: 0;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);
}

.result-hover-action:hover,
.result-hover-action:focus {
  background: rgba(76, 52, 26, 0.78) !important;
  border-color: rgba(255, 240, 214, 0.26) !important;
  color: #fffdfa !important;
  box-shadow: 0 14px 26px rgba(34, 22, 10, 0.28);
}

.result-hover-action-danger {
  border-color: rgba(255, 214, 209, 0.18) !important;
  background: rgba(180, 58, 43, 0.88) !important;
  color: #fff5f2 !important;
  box-shadow: 0 10px 22px rgba(140, 40, 28, 0.24);
}

.result-hover-action-danger:hover,
.result-hover-action-danger:focus {
  background: rgba(201, 73, 60, 0.98) !important;
  border-color: rgba(255, 224, 220, 0.24) !important;
  color: #fff7f5 !important;
  box-shadow: 0 14px 26px rgba(140, 40, 28, 0.34);
}

.result-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 14px;
  border: 1px dashed var(--theme-border);
  border-radius: 10px;
  color: var(--text-muted);
  text-align: center;
  font-size: 12px;
  background: var(--theme-empty-bg);
}

.result-generating {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  height: 100%;
  padding: 14px;
  border: 1px dashed var(--theme-border);
  border-radius: 10px;
  text-align: center;
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.1), rgba(255, 250, 240, 0.16));
}

.result-generating-title {
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 600;
}

.result-generating-sub {
  color: var(--text-muted);
  font-size: 12px;
}

.result-preview-shell.is-multi .result-generating {
  gap: 6px;
  padding: 10px;
}

.result-preview-shell.is-multi .result-generating-title {
  font-size: 12px;
}

.result-preview-shell.is-multi .result-generating-sub {
  display: none;
}

.result-failed {
  position: relative;
  overflow: hidden;
  width: 100%;
  height: 100%;
  border: 1px dashed var(--theme-border);
  border-radius: 10px;
  background: var(--theme-empty-bg);
}

.failed-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.result-failed-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  text-align: center;
  color: #c9493c;
  font-size: 13px;
  font-weight: 600;
  background: linear-gradient(
    180deg,
    rgba(255, 233, 228, 0.42),
    rgba(255, 221, 214, 0.92)
  );
}

.preview-modal-image {
  display: block;
  width: 100%;
  max-height: 75vh;
  object-fit: contain;
}

.paste-scope-dialog {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.paste-scope-tip {
  color: var(--text-secondary);
  line-height: 1.7;
}

.paste-preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
  gap: 10px;
}

.paste-preview-item {
  aspect-ratio: 1;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  border-radius: 12px;
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
  cursor: pointer;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);
}

.paste-preview-item:hover {
  transform: translateY(-1px);
  border-color: var(--theme-panel-border-strong);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
}

.paste-preview-item img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.paste-scope-group {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.paste-scope-group :deep(.ant-radio-button-wrapper) {
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  border-inline-start-width: 1px;
  border-color: var(--theme-panel-border);
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
  color: var(--text-primary);
  font-weight: 600;
}

.paste-scope-group :deep(.ant-radio-button-wrapper:not(:first-child)::before) {
  display: none;
}

.paste-scope-group :deep(.ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled)) {
  border-color: color-mix(in srgb, var(--theme-accent) 34%, transparent);
  background: color-mix(in srgb, var(--theme-accent) 10%, var(--theme-panel-bg));
  color: var(--theme-accent);
  box-shadow: 0 0 0 2px rgba(var(--theme-accent-rgb), 0.1);
}

.paste-scope-group :deep(.ant-radio-button-wrapper-disabled) {
  opacity: 0.52;
}

.paste-scope-desc-inline {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.paste-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.paste-card-chip {
  padding: 12px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 12px;
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
  text-align: left;
  cursor: pointer;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.paste-card-chip:hover {
  transform: translateY(-1px);
  border-color: var(--theme-panel-border-strong);
}

.paste-card-chip.active {
  border-color: color-mix(in srgb, var(--theme-accent) 34%, transparent);
  background: color-mix(in srgb, var(--theme-accent) 8%, var(--theme-panel-bg));
  box-shadow: 0 0 0 2px rgba(var(--theme-accent-rgb), 0.12);
}

.paste-card-chip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.paste-card-chip-subhead {
  margin-top: 6px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
}

.paste-card-chip-title {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
}

.paste-card-chip-check {
  width: 20px;
  height: 20px;
  border: 1.5px solid color-mix(in srgb, var(--theme-accent) 32%, var(--theme-panel-border));
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--theme-accent-rgb), 0.04);
  transition:
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.paste-card-chip-check.active {
  border-color: var(--theme-accent);
  background: var(--theme-accent);
  box-shadow: 0 6px 14px rgba(var(--theme-accent-rgb), 0.22);
}

.paste-card-chip-check-icon {
  color: var(--theme-accent-contrast);
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
}

.paste-card-chip-meta {
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.paste-card-chip-desc {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.batch-card-compact .setting-inline-row-primary :deep(.card-setting-select),
.batch-card-compact .setting-inline-row-primary :deep(.option-grid-picker) {
  width: 100%;
  max-width: 100%;
}

.batch-card-compact .setting-inline-row-primary :deep(.card-setting-select) {
  background: linear-gradient(180deg, var(--theme-control-bg), var(--theme-panel-bg-soft));
  border: 1px solid var(--theme-control-border);
  border-radius: 10px;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 4px 12px var(--theme-shadow-soft);
}

.batch-card-compact .setting-inline-row-primary :deep(.card-setting-select .ant-select-selector) {
  height: 34px !important;
  min-height: 34px;
  border: none !important;
  border-radius: 10px !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 10px !important;
  font-size: 13px;
  font-weight: 600;
}

.batch-card-compact .setting-inline-row-primary :deep(.card-setting-select .ant-select-selection-item),
.batch-card-compact .setting-inline-row-primary :deep(.card-setting-select .ant-select-selection-placeholder) {
  line-height: 34px !important;
}

.batch-card-compact .setting-inline-row-primary :deep(.card-setting-select .ant-select-selection-item) {
  font-weight: 700;
}

.batch-card-compact .setting-inline-row-primary :deep(.card-setting-select .ant-select-selection-placeholder) {
  font-weight: 400;
}

.batch-card-compact .setting-inline-row-primary :deep(.option-grid-trigger) {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  height: 34px;
  min-height: 34px;
  border-radius: 10px;
  padding: 0 10px;
  font-size: 13px;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 4px 12px var(--theme-shadow-soft);
}

.batch-card-compact .setting-inline-row-primary :deep(.option-grid-trigger:hover),
.batch-card-compact .setting-inline-row-primary :deep(.option-grid-trigger.open) {
  transform: none;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 4px 12px var(--theme-shadow-soft);
}

.batch-card-compact .setting-inline-row-primary :deep(.option-grid-trigger.open) {
  border-color: var(--theme-border-accent);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 0 0 3px var(--theme-focus-ring),
    0 4px 12px var(--theme-shadow-soft);
}

.batch-card-compact :deep(.ant-select-selector),
.batch-card-compact :deep(.option-grid-trigger) {
  min-height: 34px;
  height: 34px;
}

.batch-card-compact :deep(.ant-select-selector) {
  display: flex;
  align-items: center;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}

.batch-card-compact :deep(.ant-select-selection-item),
.batch-card-compact :deep(.ant-select-selection-placeholder) {
  line-height: 34px !important;
}

.batch-panel :deep(.ant-select-selector) {
  display: flex;
  align-items: center;
}

.batch-panel :deep(.ant-select-selection-item),
.batch-panel :deep(.ant-select-selection-placeholder) {
  line-height: 32px !important;
}

@media (max-width: 1080px) {
  .result-body {
    grid-template-columns: 1fr;
  }

  .global-settings-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .global-settings-row-inline {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .global-settings-layout,
  .global-settings-layout.has-reference-column {
    grid-template-columns: 1fr;
  }

  .global-setting-inline-row-primary .setting-model-cell {
    flex: 1 1 100%;
  }

  .global-setting-inline-row-primary .setting-quarter-cell {
    flex: 1 1 calc(50% - 4px);
  }

  .setting-inline-row-primary {
    flex-wrap: wrap;
  }

  .setting-inline-row-primary .setting-model-cell {
    flex: 1 1 100%;
  }

  .setting-inline-row-primary .setting-quarter-cell {
    flex: 1 1 calc(50% - 4px);
  }

  .batch-panel-global :deep(.ant-card-head) {
    padding: 0 14px;
  }

  .setting-inline-row {
    grid-template-columns: 1fr;
  }

  .reference-section-inline {
    flex-direction: column;
    align-items: stretch;
  }

  .batch-task-card-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .batch-card-leave-active {
    width: calc((100% - 12px) / 2);
  }
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .batch-panel-global :deep(.ant-card-head) {
    min-height: auto;
  }

  .batch-panel-global :deep(.ant-card-head-wrapper) {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .batch-panel-global :deep(.ant-card-extra) {
    margin-inline-start: 0;
  }

  .global-panel-actions {
    width: 100%;
    justify-content: space-between;
  }

  .global-apply-btn {
    min-width: 0;
  }

  .global-settings-row {
    grid-template-columns: 1fr;
  }

  .global-settings-row-inline {
    display: flex;
    flex-direction: column;
  }

  .global-settings-layout,
  .global-settings-layout.has-reference-column {
    grid-template-columns: 1fr;
  }

  .global-setting-inline-row-primary .setting-model-cell,
  .global-setting-inline-row-primary .setting-quarter-cell {
    flex: 1 1 100%;
  }

  .setting-inline-row-primary .setting-model-cell,
  .setting-inline-row-primary .setting-quarter-cell {
    flex: 1 1 100%;
  }

  .batch-task-card-list {
    grid-template-columns: repeat(auto-fit, minmax(100%, 1fr));
  }

  .batch-card-leave-active {
    width: 100%;
  }

  .batch-generate-page {
    padding: 16px;
  }
}
</style>

<style>
.custom-size-help-tooltip .custom-size-help-tip {
  font-size: 12px;
  line-height: 1.6;
}

.custom-size-help-tooltip .custom-size-help-tip ul {
  margin: 6px 0 0;
  padding-left: 18px;
}

.custom-size-help-tooltip .custom-size-help-tip li {
  margin: 2px 0;
}

.custom-size-help-tooltip .custom-size-help-note {
  margin-top: 8px;
  opacity: 0.82;
}
</style>
