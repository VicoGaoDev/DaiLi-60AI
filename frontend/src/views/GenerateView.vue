<script setup lang="ts">
import { ref, computed, defineAsyncComponent, defineComponent, h, inject, nextTick, onActivated, onBeforeUnmount, onMounted, watch, type Ref } from "vue";
import { message, Modal } from "ant-design-vue";
import dayjs from "dayjs";
import { useRoute, useRouter } from "vue-router";
import {
  APPLY_CHAT_GENERATE_DRAFT_EVENT,
  CHAT_DRAFT_KEY,
  CHAT_GENERATE_TASKS_CREATED_EVENT,
  type ChatGenerateTasksPayload,
} from "@/lib/chatGenerateDraft";
import { saveImageToVideoDraft } from "@/lib/videoGenerateDraft";
import {
  FontSizeOutlined,
  CloseOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  EyeOutlined,
  PictureOutlined,
  SearchOutlined,
  HighlightOutlined,
  ScissorOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  LoadingOutlined,
  InfoCircleFilled,
  ReloadOutlined,
  ThunderboltOutlined,
  ExperimentOutlined,
  EllipsisOutlined,
  DownOutlined,
  MessageOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  UnorderedListOutlined,
  VideoCameraOutlined,
  DoubleLeftOutlined,
  DoubleRightOutlined,
  FilterOutlined,
  CalendarOutlined,
  ExpandOutlined,
  ReadOutlined,
} from "@ant-design/icons-vue";
import { createBoard, listBoards, updateBoard } from "@/api/boards";
import { getTaskScenes } from "@/api/config";
import { deleteHistoryTask, fetchHistory } from "@/api/history";
import { createTask, getTasks } from "@/api/tasks";
import { createTemplateFromTaskImage, listTemplateTags, type TemplatePayload } from "@/api/templates";
import {
  deleteImage,
  exceedsRealtimeImagePreviewLimit,
  getDisplayImageUrl,
  getDownloadUrl,
  getPreviewImageSrc,
  getPreviewImageUrl,
  LARGE_IMAGE_PREVIEW_NOTICE,
  resolveImageUrl,
} from "@/api/images";
import { optimizePrompt } from "@/api/promptOptimize";
import { reversePrompt } from "@/api/promptReverse";
import { createUserPrompt } from "@/api/userPrompts";
import { getMe } from "@/api/auth";
import { isSupportedImageUploadFile } from "@/api/upload";
import { useAuthStore } from "@/stores/auth";
import AspectRatioPicker from "@/components/generate/AspectRatioPicker.vue";
import ModelCategorySelect from "@/components/generate/ModelCategorySelect.vue";
import GenerateStyleTags from "@/components/generate/GenerateStyleTags.vue";
import OptionGridPicker from "@/components/generate/OptionGridPicker.vue";
import { formatSelectedGenerateCameraLabel, type GenerateCameraSelection } from "@/lib/generateCameras";
import { composeGeneratePrompt, formatSelectedGenerateStyleLabel, parseGeneratePrompt } from "@/lib/generateStyles";
import NavGenerateImageIcon from "@/components/icons/NavGenerateImageIcon.vue";
import SketchBoardIcon from "@/components/icons/SketchBoardIcon.vue";
import PromptInterceptionTip from "@/components/generate/PromptInterceptionTip.vue";
import ImageSourceActionSheet from "@/components/generate/ImageSourceActionSheet.vue";
import SmartCutoutPanel from "@/components/generate/SmartCutoutPanel.vue";
import UpdateLogEntryButton from "@/components/update-log/UpdateLogEntryButton.vue";
import { useImageSourcePicker } from "@/composables/useImageSourcePicker";
import { appendTransientImageNonce, useTransientImageLoad } from "@/composables/useTransientImageLoad";
import { useUserAssets } from "@/composables/useUserAssets";
import { withBaseUrl } from "@/lib/assets";
import { useExpiredResultAsset } from "@/lib/expiredResultAsset";
import { buildQuickSavePromptTitle, imageUrlToFile } from "@/lib/userLibraryQuickSave";
import {
  extractApiErrorDetail,
  formatGenerationErrorMessage,
  getPreferredGenerationErrorMessage,
} from "@/lib/generationErrors";
import {
  GENERATE_RESULT_COLUMN_COUNT_KEY,
  readStoredGridColumnCount,
  writeStoredGridColumnCount,
} from "@/lib/gridColumnPreference";
import {
  boardIdFromKey,
  boardKeyFromId,
  DEFAULT_BOARD_KEY,
  GENERATE_BOARD_KEY,
  readStoredBoardKey,
  writeStoredBoardKey,
} from "@/lib/boardPreference";
import type { BoardKey, GenerationModelOption, ImageResult, PublicPromptOptimizeStyle, SceneOptionItem, TaskApiAttempt, TaskResult, TaskSceneConfig, TaskSource, TaskType, TemplateTag, UserAsset, UserBoardSummary, UserHistoryCard, UserPrompt } from "@/types";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const loginModalVisible = inject<Ref<boolean>>("loginModalVisible")!;
const openPurchaseEntry = inject<() => void>("openPurchaseEntry");
const RepaintCanvas = defineAsyncComponent(() => import("@/components/generate/RepaintCanvas.vue"));
const GenerateCameraPicker = defineAsyncComponent(() => import("@/components/generate/GenerateCameraPicker.vue"));
const GenerateStylePicker = defineAsyncComponent(() => import("@/components/generate/GenerateStylePicker.vue"));
const UserAssetPicker = defineAsyncComponent(() => import("@/components/assets/UserAssetPicker.vue"));
const SketchBoardDialog = defineAsyncComponent(() => import("@/components/generate/SketchBoardDialog.vue"));
const UserPromptLibraryModal = defineAsyncComponent(() => import("@/components/prompts/UserPromptLibraryModal.vue"));
const PromptOptimizeStyleDialog = defineAsyncComponent(() => import("@/components/generate/PromptOptimizeStyleDialog.vue"));
const PromptExpandDialog = defineAsyncComponent(() => import("@/components/generate/PromptExpandDialog.vue"));
const FeedbackDialog = defineAsyncComponent(() => import("@/components/feedback/FeedbackDialog.vue"));
const HistoryDetailDialog = defineAsyncComponent(() => import("@/components/history/HistoryDetailDialog.vue"));
const TemplateFormDialog = defineAsyncComponent(() => import("@/components/templates/TemplateFormDialog.vue"));
const AUTH_USER_REFRESH_INTERVAL_MS = 60_000;
let lastAuthUserRefreshAt = 0;
let authUserRefreshPromise: Promise<void> | null = null;

function getBodyPopupContainer() {
  return document.body;
}

function isInsufficientCreditsError(err: any) {
  const detail = String(err?.response?.data?.detail || err?.message || "");
  return detail.includes("积分不足");
}

function isImageUploadTooLarge(file: File) {
  return file.size > MAX_IMAGE_UPLOAD_SIZE_BYTES;
}

function showInsufficientCreditsPurchase(detail?: string) {
  if (detail) {
    message.warning(detail);
  }
  openPurchaseEntry?.();
}

type GenerateMode = "textGenerate" | "imageEdit" | "inpaint" | "smartCutout" | "promptReverse";
type GeneratedTaskStatusFilter = "pending" | "processing" | "success" | "failed";
type GeneratedTaskDatePreset = "today" | "yesterday" | "week" | "custom";
type ResultCardAspectRatio = "1:1" | "2:3" | "3:2" | "3:4" | "4:3" | "16:9" | "9:16";
const GENERATED_TASK_HISTORY_PAGE_SIZE = 20;
const GENERATED_TASK_RETENTION_DAYS = 15;
const MAX_IMAGE_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024;
const MAX_IMAGE_UPLOAD_SIZE_TEXT = "20MB";
const MAX_ACTIVE_GENERATION_IMAGES = 12;
const RESULT_CARD_ASPECT_OPTIONS: Array<{ label: string; value: ResultCardAspectRatio }> = [
  { label: "1:1", value: "1:1" },
  { label: "2:3", value: "2:3" },
  { label: "3:2", value: "3:2" },
  { label: "3:4", value: "3:4" },
  { label: "4:3", value: "4:3" },
  { label: "16:9", value: "16:9" },
  { label: "9:16", value: "9:16" },
];
const GENERATION_IMAGE_COUNT_OPTIONS: SceneOptionItem[] = Array.from(
  { length: MAX_ACTIVE_GENERATION_IMAGES },
  (_, index) => {
    const value = String(index + 1);
    return { label: value, value };
  },
);
const DEFAULT_SCENE_COSTS: Record<string, number> = {
  banana: 4,
  banana2: 4,
  banana_pro: 4,
  banana_pro_plus: 4,
  banana_edit: 4,
  banana2_edit: 4,
  banana_pro_edit: 4,
  banana_pro_plus_edit: 4,
  prompt_reverse: 1,
  prompt_optimize: 1,
  inpaint: 4,
  smart_cutout: 4,
};

const GENERATE_MENU_ENTRY_EVENT = "banana:generate-menu-entry";
const generateMode = ref<GenerateMode>("imageEdit");
const isConfigPanelCollapsed = ref(false);
function expandConfigPanelForEditing() {
  if (isConfigPanelCollapsed.value) {
    isConfigPanelCollapsed.value = false;
  }
}

function handleGenerateMenuEntry() {
  expandConfigPanelForEditing();
}

function handleChatGenerateDraft() {
  expandConfigPanelForEditing();
  applyDraft(
    localStorage.getItem(CHAT_DRAFT_KEY),
    "已从 AI 对话回填提示词，可继续编辑后生成",
    CHAT_DRAFT_KEY,
  );
}

function handleChatGenerateTasksCreated(event: Event) {
  const detail = (event as CustomEvent<ChatGenerateTasksPayload>).detail;
  upsertChatGeneratedTasks(detail);
}

function upsertChatGeneratedTasks(payload?: ChatGenerateTasksPayload | null) {
  const taskIds = (payload?.taskIds || [])
    .map((taskId) => String(taskId || "").trim())
    .filter(Boolean);
  if (!taskIds.length) return;

  const existingIds = new Set(
    generatedTasks.value
      .map((task) => task.taskId)
      .filter((taskId): taskId is string => Boolean(taskId)),
  );
  const referenceImages = Array.isArray(payload?.referenceImages)
    ? payload.referenceImages.map((url) => String(url || "").trim()).filter(Boolean)
    : [];
  const mode: SubmitMode = payload?.modeHint === "image_edit" || referenceImages.length
    ? "imageEdit"
    : "textGenerate";
  const perCardImageCount = taskIds.length > 1
    ? 1
    : Math.max(1, Number(payload?.numImages) || 1);
  const newcomers = taskIds
    .filter((taskId) => !existingIds.has(taskId))
    .map((taskId) => ({
      localId: `chat-${taskId}`,
      taskId,
      mode,
      prompt: payload?.prompt || "",
      model: payload?.model || undefined,
      numImages: perCardImageCount,
      size: payload?.size || "1:1",
      resolution: payload?.resolution || "2K",
      customSize: payload?.customSize || "",
      referenceImages,
      referenceImageThumbs: referenceImages,
      createdAt: new Date().toISOString(),
      status: "pending" as const,
      errorMessage: "",
      creditRefunded: false,
      failureRefundRemainingCount: null,
      images: createPendingImages(perCardImageCount),
    }));

  if (newcomers.length) {
    generatedTasks.value = [...newcomers, ...generatedTasks.value];
    if (resultBodyRef.value) resultBodyRef.value.scrollTop = 0;
  }

  startTaskPolling();
  void refreshTasks(taskIds);
  getMe().then((user) => auth.updateUser(user)).catch(() => {});
}

const failedResultAsset = withBaseUrl("failed-result.svg");
const generateEmptyStateAsset = withBaseUrl("generate-task-card-minimal-a.svg");
const smartCutoutTipAsset = withBaseUrl("docs/tutorial/20-smart-cutout-compare-tip.jpg");
const expiredResultAsset = useExpiredResultAsset();
const prompt = ref("");
const repaintPrompt = ref("");
const lastSavedPromptText = ref("");
const lastSavedRepaintPromptText = ref("");
const TASK_PROMPT_MAX_LENGTH = 10000;
const selectedModel = ref("");
const numImages = ref(1);
const resolution = ref("2K");
const size = ref("");
const customSize = ref("");
const customSizeEnabled = ref(false);
const customWidth = ref(1024);
const customHeight = ref(1024);
const aspectRatioAutoDetectEnabled = ref(readStoredAspectRatioAutoDetectEnabled());
const selectedColorStyleId = ref("");
const selectedLightingStyleId = ref("");
const selectedCameraBodyId = ref("");
const selectedCameraLensId = ref("");
const selectedCameraFocalId = ref("");
const selectedCameraApertureId = ref("");
const selectedNumImages = computed({
  get: () => String(numImages.value),
  set: (value: string) => {
    numImages.value = Math.min(
      MAX_ACTIVE_GENERATION_IMAGES,
      Math.max(1, Number(value) || 1),
    );
  },
});

type GeneratedTaskStatus = TaskResult["status"] | "submitting";
type SubmitMode = Exclude<GenerateMode, "promptReverse">;

interface GeneratedTaskItem {
  localId: string;
  taskId: string | null;
  mode: SubmitMode;
  prompt: string;
  model?: string;
  numImages: number;
  size: string;
  resolution: string;
  customSize: string;
  referenceImages: string[];
  referenceImageThumbs: string[];
  sourceImage?: string;
  sourceImageThumb?: string;
  maskImage?: string;
  maskImageThumb?: string;
  createdAt: string;
  status: GeneratedTaskStatus;
  errorMessage?: string;
  providerErrorMessage?: string;
  creditRefunded?: boolean;
  failureRefundRemainingCount?: number | null;
  usedFallbackApi?: boolean;
  apiAttempts?: TaskApiAttempt[];
  images: ImageResult[];
}

const generatedTasks = ref<GeneratedTaskItem[]>([]);
const failureRefundRemainingCount = ref<number | null>(null);
const generatedTaskHistoryPage = ref(0);
const generatedTaskHistoryTotal = ref(0);
const generatedTasksLoading = ref(false);
const generatedTasksLoadingMore = ref(false);
const resultBodyRef = ref<HTMLElement | null>(null);
const resultPanelRef = ref<HTMLElement | null>(null);
const generatedTaskLoadMoreAnchor = ref<HTMLElement | null>(null);
const resultViewOptionsOpen = ref(false);
const generatedTaskFilterOpen = ref(false);
const generatedTaskTypeFilter = ref<TaskType | undefined>(undefined);
const generatedTaskSourceFilter = ref<TaskSource | undefined>(undefined);
const generatedTaskModelFilter = ref<string | undefined>(undefined);
const generatedTaskStatusFilter = ref<GeneratedTaskStatusFilter | undefined>(undefined);
const generatedTaskPromptFilter = ref("");
const generatedTaskDateRangeFilter = ref<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
const generatedTaskDatePreset = ref<GeneratedTaskDatePreset | null>(null);
const generatedTaskHideExpiredFilter = ref(true);
const generatedTaskHideFailedFilter = ref(false);

const taskPollTimer = ref<ReturnType<typeof setInterval> | null>(null);
const taskPollingInFlight = ref(false);
const activeStatusPollTimer = ref<ReturnType<typeof setInterval> | null>(null);
const activeStatusRefreshInFlight = ref(false);
let generatedTaskLoadMoreObserver: IntersectionObserver | null = null;
let generatedTaskLoadRequestId = 0;
let generatedTaskFilterDebounceTimer: number | null = null;
const remoteActiveGenerationImageCount = ref(0);
const remoteActiveTaskIds = ref<Set<string>>(new Set());
const templateDialogOpen = ref(false);
const templateDialogSaving = ref(false);
const templateSourceImageId = ref<number | null>(null);
const templateInitialValue = ref<TemplatePayload | null>(null);
const templateTags = ref<TemplateTag[]>([]);

type UploadItemStatus = "uploading" | "success" | "failed";

interface UploadPreviewItem {
  id: string;
  localUrl: string;
  remoteUrl: string;
  status: UploadItemStatus;
  objectUrl?: string;
  fileName?: string;
  savedToAsset?: boolean;
}

const DEFAULT_MAX_REFERENCE_IMAGES = 6;
const referenceItems = ref<UploadPreviewItem[]>([]);
const assetPickerOpen = ref(false);
const sketchBoardOpen = ref(false);
const pickingGeneratedReference = ref(false);
const quickSavingReferenceIds = ref<string[]>([]);
const quickSavingPromptKeys = ref<string[]>([]);
const fileInput = ref<HTMLInputElement | null>(null);
const {
  accept: imageFileAccept,
  sheetOpen: imageSourceSheetOpen,
  requestPick: requestImageSourcePick,
  pickFromCamera,
  pickFromGallery,
  pickFromFiles,
  cancelSheet: cancelImageSourceSheet,
} = useImageSourcePicker();
const referenceUploadBlockRef = ref<HTMLElement | null>(null);
const referenceDragActive = ref(false);
const referenceDragCounter = ref(0);
let unbindReferenceDragHandlers: (() => void) | null = null;
const referencePickerOpening = ref(false);
const sourceImageUrl = ref("");
const sourcePreviewUrl = ref("");
const repaintMaskUrl = ref("");
const sourceUploading = ref(false);
const sourceInput = ref<HTMLInputElement | null>(null);
const sourcePickerOpening = ref(false);
const reverseImageUrl = ref("");
const reverseUploading = ref(false);
const reverseInput = ref<HTMLInputElement | null>(null);
const reversePickerOpening = ref(false);
const reverseLoading = ref(false);
const reversePromptResult = ref("");
const promptOptimizeLoading = ref(false);
type PromptOptimizeTarget = "prompt" | "repaintPrompt";
type PromptOptimizePayload = {
  prompt: string;
  reference_images?: string[];
  style_name: string;
  style_prompt: string;
};
const promptOptimizeTarget = ref<PromptOptimizeTarget | null>(null);
const activePromptOptimizeRequestId = ref<number | null>(null);
const promptOptimizeStyleDialogOpen = ref(false);
const pendingPromptOptimizePayload = ref<Omit<PromptOptimizePayload, "style_name" | "style_prompt"> | null>(null);
const pendingPromptOptimizeTarget = ref<PromptOptimizeTarget | null>(null);
const PROMPT_OPTIMIZE_TOOLTIP = "提示词优化：保留原意，并结合参考图理解画面，自动补全构图、光线、画风和细节，让提示词更适合出图";
let promptOptimizeRequestSeq = 0;
let promptOptimizeAbortController: AbortController | null = null;
const cancelledPromptOptimizeRequestIds = new Set<number>();
const brushSize = ref(28);
const repaintTool = ref<"paint" | "erase" | "rect" | "circle" | "text">("paint");
const repaintLineColor = ref<string>("#c38d36");
const hasRepaintMask = ref(false);
const canUndoMask = ref(false);
const canRedoMask = ref(false);
const smartCutoutPanelRef = ref<{
  applySource: (sourceUrl: string, maskUrl?: string, promptText?: string) => void;
  clear: () => void;
} | null>(null);
const pendingSmartCutoutApply = ref<{ sourceUrl: string; maskUrl: string; prompt: string } | null>(null);
const repaintCanvasRef = ref<{
  clearMask: () => void;
  hasDrawnMask: () => boolean;
  exportMaskBlob: () => Promise<Blob | null>;
  undo: () => boolean;
  canUndo: () => boolean;
  redo: () => boolean;
  canRedo: () => boolean;
} | null>(null);

const previewVisible = ref(false);
const previewCurrent = ref("");
const previewImageLoading = ref(false);
const detailOpen = ref(false);
const detailItem = ref<UserHistoryCard | null>(null);
const detailTaskLocalId = ref<string | null>(null);
const feedbackDialogOpen = ref(false);
const loadedResultMediaKeys = ref<Set<string>>(new Set());
const hdPreviewRequestedKeys = ref<Set<string>>(new Set());
const hdPreviewLoadedKeys = ref<Set<string>>(new Set());
const expandedResultMoreKeys = ref<Set<string>>(new Set());
const generatedResultImageLoad = useTransientImageLoad();
const detailPreloadedMediaKeys = ref<string[]>([]);
const feedbackTarget = ref<{
  taskId: string;
  model?: string;
  prompt: string;
  createdAt: string;
} | null>(null);
const { uploadFiles: uploadUserAssetFiles } = useUserAssets();
const viewportWidth = ref(typeof window === "undefined" ? 1200 : window.innerWidth);
const RESULT_COLUMN_OPTIONS = [3, 4, 5, 6, 7, 8] as const;
type ResultColumnOption = typeof RESULT_COLUMN_OPTIONS[number];
const DEFAULT_RESULT_COLUMN_COUNT: ResultColumnOption = 3;
const GENERATE_RESULT_CARD_ASPECT_RATIO_SESSION_KEY = "generateResultCardAspectRatio";

const preferredResultColumnCount = ref<ResultColumnOption>(
  readStoredGridColumnCount(
    GENERATE_RESULT_COLUMN_COUNT_KEY,
    RESULT_COLUMN_OPTIONS,
    DEFAULT_RESULT_COLUMN_COUNT,
  ),
);
const resultCardAspectRatio = ref<ResultCardAspectRatio>(readStoredResultCardAspectRatio());
const boards = ref<UserBoardSummary[]>([]);
const boardsLoading = ref(false);
const selectedBoardKey = ref<BoardKey>(DEFAULT_BOARD_KEY);
const boardSelectionReady = ref(false);
const selectedBoardId = computed(() => boardIdFromKey(selectedBoardKey.value));
const selectedBoard = computed(() => (
  boards.value.find((board) => boardKeyFromId(board.id) === selectedBoardKey.value) || null
));
const visibleBoardOptions = computed(() => {
  const defaultBoards = boards.value.filter((board) => board.is_default);
  const recentBoards = boards.value.filter((board) => !board.is_default).slice(0, 10);
  const selectedExtra = selectedBoard.value && !defaultBoards.includes(selectedBoard.value) && !recentBoards.includes(selectedBoard.value)
    ? [selectedBoard.value]
    : [];
  return [...defaultBoards, ...recentBoards, ...selectedExtra];
});
const canRenameSelectedBoard = computed(() => !!selectedBoard.value && !selectedBoard.value.is_default && typeof selectedBoard.value.id === "number");
const boardRenameDialogOpen = ref(false);
const boardRenameSaving = ref(false);
const boardRenameName = ref("");
const VNodes = defineComponent({
  props: {
    vnodes: {
      type: null,
      required: true,
    },
  },
  render() {
    return this.vnodes;
  },
});

const promptLibraryVisible = ref(false);
const sceneConfigLoading = ref(true);
const submittingGenerate = ref(false);
const HISTORY_DRAFT_KEY = "generateDraftFromHistory";
const TEMPLATE_DRAFT_KEY = "generateDraftFromTemplate";
const ASPECT_RATIO_AUTO_DETECT_STORAGE_KEY = "generateAspectRatioAutoDetectEnabled";
const taskScenes = ref<TaskSceneConfig[]>([]);
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
const REPAINT_COLOR_OPTIONS = [
  { label: "金棕", value: "#c38d36" },
  { label: "紫色", value: "#746bff" },
  { label: "青绿", value: "#2fa39b" },
  { label: "玫红", value: "#d95f8d" },
] as const;

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

const resultEmptyTitle = computed(() => (
  generateMode.value === "promptReverse" ? "提示词反推结果会在左侧展示" : "生图结果将在这里展示"
));
const resultEmptyDesc = computed(() => (
  generateMode.value === "promptReverse"
    ? "上传图片后点击「开始反推」，即可得到适合 AI 绘画的中文提示词"
    : "在左侧设置提示词和参数后发起任务，右侧会按当前分类分页展示生图任务结果"
));
const firstReferenceItem = computed(() => referenceItems.value[0] || null);
const referenceUrls = computed(() => (
  referenceItems.value
    .filter((item) => item.status === "success" && item.remoteUrl)
    .map((item) => item.remoteUrl)
));
const uploading = computed(() => referenceItems.value.some((item) => item.status === "uploading"));
const hasPendingReferenceUploads = computed(() => referenceItems.value.some((item) => item.status === "uploading"));
const hasFailedReferenceUploads = computed(() => referenceItems.value.some((item) => item.status === "failed"));
let filePickerRecoveryTimer: number | null = null;
const sourceDisplayUrl = computed(() => getPreviewImageSrc(sourcePreviewUrl.value || sourceImageUrl.value));
const isTextGenerateMode = computed(() => generateMode.value === "textGenerate");
const isImageEditMode = computed(() => generateMode.value === "imageEdit");
const isSmartCutoutMode = computed(() => generateMode.value === "smartCutout");
const smartCutoutScene = computed(() => taskScenes.value.find((item) => item.scene_key === "smart_cutout"));
const SHOW_MODEL_NEW_BADGES = false;
const textGenerateModels = computed(() => (
  taskScenes.value
    .filter((item) => item.scene_type === "generate" && item.scene_key !== "prompt_reverse" && item.scene_key !== "inpaint" && item.scene_key !== "smart_cutout")
    .map(toGenerationModelOption)
));
const imageEditModels = computed(() => {
  const models = taskScenes.value
    .filter((item) => item.scene_type === "image_edit")
    .map(toGenerationModelOption);
  return models.length ? models : textGenerateModels.value;
});
const templateModelOptions = computed(() => {
  const optionMap = new Map<string, GenerationModelOption>();
  [...textGenerateModels.value, ...imageEditModels.value].forEach((item) => {
    if (!optionMap.has(item.model_key)) optionMap.set(item.model_key, item);
  });
  return Array.from(optionMap.values());
});
const NEW_MODEL_KEYS = new Set(["banana2_lite", "banana2_lite_edit"]);
const generationModels = computed(() => (isImageEditMode.value ? imageEditModels.value : textGenerateModels.value));
const generationModelSelectOptions = computed(() => (
  generationModels.value.map((model) => ({
    value: model.model_key,
    label: model.model_label,
    description: model.model_description,
    sortOrder: model.sort_order,
    categoryId: model.category_id,
    categoryName: model.category_name,
    categorySortOrder: model.category_sort_order,
  }))
));
const detailModelOptions = computed(() => (
  taskScenes.value.map((scene) => ({
    label: scene.scene_label,
    value: scene.scene_key,
  }))
));
const generatedTaskFilterModelOptions = computed(() => {
  const optionMap = new Map<string, string>();
  detailModelOptions.value.forEach((item) => optionMap.set(item.value, item.label));
  return Array.from(optionMap.entries()).map(([value, label]) => ({ value, label }));
});
const generatedTaskActiveFilterCount = computed(() => {
  let count = 0;
  if (generatedTaskHideExpiredFilter.value) count += 1;
  if (generatedTaskHideFailedFilter.value) count += 1;
  if (generatedTaskTypeFilter.value) count += 1;
  if (generatedTaskSourceFilter.value) count += 1;
  if (generatedTaskModelFilter.value) count += 1;
  if (generatedTaskStatusFilter.value) count += 1;
  if (generatedTaskPromptFilter.value.trim()) count += 1;
  if (generatedTaskDateRangeFilter.value) count += 1;
  return count;
});

const GENERATED_TASK_TYPE_FILTER_LABELS: Record<string, string> = {
  text_generate: "文生图",
  image_edit: "图编辑",
  inpaint: "局部重绘",
  smart_cutout: "智能抠图",
};
const GENERATED_TASK_SOURCE_FILTER_LABELS: Record<string, string> = {
  web: "Web",
  app: "App",
  api: "API",
};
const GENERATED_TASK_STATUS_FILTER_LABELS: Record<string, string> = {
  pending: "等待中",
  processing: "处理中",
  success: "成功",
  failed: "失败",
};

const generatedTaskFilterSummary = computed(() => {
  const parts: string[] = [];
  if (generatedTaskHideExpiredFilter.value) parts.push("不展示已过期任务图片（15天之前）");
  if (generatedTaskHideFailedFilter.value) parts.push("不展示错误任务图片");
  if (generatedTaskTypeFilter.value) {
    parts.push(`类型：${GENERATED_TASK_TYPE_FILTER_LABELS[generatedTaskTypeFilter.value] || generatedTaskTypeFilter.value}`);
  }
  if (generatedTaskSourceFilter.value) {
    parts.push(`来源：${GENERATED_TASK_SOURCE_FILTER_LABELS[generatedTaskSourceFilter.value] || generatedTaskSourceFilter.value}`);
  }
  if (generatedTaskStatusFilter.value) {
    parts.push(`状态：${GENERATED_TASK_STATUS_FILTER_LABELS[generatedTaskStatusFilter.value] || generatedTaskStatusFilter.value}`);
  }
  if (generatedTaskModelFilter.value) {
    const modelLabel = generatedTaskFilterModelOptions.value.find((item) => item.value === generatedTaskModelFilter.value)?.label
      || generatedTaskModelFilter.value;
    parts.push(`模型：${modelLabel}`);
  }
  const promptKeyword = generatedTaskPromptFilter.value.trim();
  if (promptKeyword) parts.push(`提示词：${promptKeyword}`);
  if (generatedTaskDateRangeFilter.value) {
    const [start, end] = generatedTaskDateRangeFilter.value;
    parts.push(`日期：${start.format("YYYY-MM-DD")} ~ ${end.format("YYYY-MM-DD")}`);
  }
  return parts.join("；");
});

function normalizeRouteGenerateMode(value: unknown): GenerateMode {
  const normalized = Array.isArray(value) ? value[0] : value;
  if (normalized === "textGenerate" || normalized === "imageEdit" || normalized === "inpaint" || normalized === "smartCutout" || normalized === "promptReverse") {
    return normalized;
  }
  return "imageEdit";
}

function applyRouteGenerateMode() {
  const nextMode = normalizeRouteGenerateMode(route.query.mode);
  if (generateMode.value !== nextMode) {
    generateMode.value = nextMode;
  }
}
function isNewModel(model?: Pick<GenerationModelOption, "model_key" | "model_label"> | null) {
  if (!model) return false;
  return NEW_MODEL_KEYS.has(model.model_key) || /lite/i.test(model.model_label);
}
const hasBlockedUploads = computed(() => {
  if (generateMode.value === "inpaint") {
    return !!sourcePreviewUrl.value && !sourceImageUrl.value;
  }
  if (isImageEditMode.value) {
    return hasPendingReferenceUploads.value || hasFailedReferenceUploads.value;
  }
  return false;
});
function currentCameraSelection(): GenerateCameraSelection {
  return {
    bodyId: selectedCameraBodyId.value,
    lensId: selectedCameraLensId.value,
    focalId: selectedCameraFocalId.value,
    apertureId: selectedCameraApertureId.value,
  };
}

const selectedPromptTagCount = computed(() => (
  [
    selectedColorStyleId.value,
    selectedLightingStyleId.value,
    selectedCameraBodyId.value || selectedCameraLensId.value || selectedCameraFocalId.value || selectedCameraApertureId.value,
  ].filter(Boolean).length
));
const hasSelectedGenerateStyles = computed(() => selectedPromptTagCount.value > 0);
const canClickGenerate = computed(() => {
  if (hasBlockedUploads.value) return false;
  if (isImageEditMode.value) return true;
  return !!activePrompt.value.trim() || hasSelectedGenerateStyles.value;
});
const localUncountedActiveGenerationImageCount = computed(() => (
  generatedTasks.value.reduce((total, task) => {
    if (!["submitting", "pending", "queued", "processing"].includes(task.status)) return total;
    if (task.taskId && remoteActiveTaskIds.value.has(task.taskId)) return total;
    return total + Math.max(task.images.length, task.numImages || 1);
  }, 0)
));
const activeGenerationImageCount = computed(() => (
  remoteActiveGenerationImageCount.value + localUncountedActiveGenerationImageCount.value
));
const remainingGenerationImageSlots = computed(() => Math.max(
  MAX_ACTIVE_GENERATION_IMAGES - activeGenerationImageCount.value,
  0
));
const selectedModelOption = computed(
  () => generationModels.value.find((item) => item.model_key === selectedModel.value) || null
);
const maxReferenceImages = computed(() => {
  if (!isImageEditMode.value) return 0;
  const configured = Number(selectedModelOption.value?.max_reference_images || 0);
  return configured > 0 ? configured : DEFAULT_MAX_REFERENCE_IMAGES;
});
const sizeOptions = computed(() => (
  selectedModelOption.value?.aspect_ratio_options?.length
    ? selectedModelOption.value.aspect_ratio_options
    : DEFAULT_ASPECT_RATIO_OPTIONS
));
const resolutionOptions = computed(() => (
  selectedModelOption.value?.image_size_options?.length
    ? selectedModelOption.value.image_size_options
    : DEFAULT_IMAGE_SIZE_OPTIONS
));
const hideAspectRatio = computed(() => (
  (isTextGenerateMode.value || isImageEditMode.value) && !!selectedModelOption.value?.hide_aspect_ratio
));
const hideResolution = computed(() => (
  (isTextGenerateMode.value || isImageEditMode.value) && !!selectedModelOption.value?.hide_resolution
));
const customSizeScene = computed(() => (
  isSmartCutoutMode.value ? smartCutoutScene.value : selectedModelOption.value
));
const supportsCustomSize = computed(() => (
  (isTextGenerateMode.value || isImageEditMode.value || isSmartCutoutMode.value)
  && customSizeScene.value?.hide_custom_size === false
));
const CUSTOM_SIZE_PIXEL_MULTIPLE = 16;
const CUSTOM_SIZE_MAX_ASPECT_RATIO = 3;
const CUSTOM_SIZE_MAX_SIDE = 3840;
const CUSTOM_SIZE_MIN_PIXELS = 655360;
const customSizeMin = computed(() => Math.max(1, Number(customSizeScene.value?.custom_size_min || 256)));
const customSizeMax = computed(() => Math.max(customSizeMin.value, Number(customSizeScene.value?.custom_size_max || 4096)));
const customSizeLimit = computed(() => Math.min(customSizeMax.value, CUSTOM_SIZE_MAX_SIDE));
const customSizeStep = computed(() => Math.max(1, Number(customSizeScene.value?.custom_size_step || 8)));

function snapToCustomSizeMultiple(value: number) {
  return Math.round(value / CUSTOM_SIZE_PIXEL_MULTIPLE) * CUSTOM_SIZE_PIXEL_MULTIPLE;
}

function stepCustomDimension(current: number, direction: 1 | -1) {
  const multiple = CUSTOM_SIZE_PIXEL_MULTIPLE;
  const next = direction > 0
    ? Math.ceil((current + multiple) / multiple) * multiple
    : Math.floor((current - 1) / multiple) * multiple;
  return Math.min(customSizeLimit.value, Math.max(customSizeMin.value, next));
}

function parseCustomSizeInput(value: string) {
  return String(value ?? "").replace(/\D/g, "");
}

function formatCustomSizeInput(value: string | number) {
  return String(value ?? "").replace(/\D/g, "");
}

function bindDigitsOnlyInput(input: HTMLInputElement) {
  const sanitize = () => {
    const digits = input.value.replace(/\D/g, "");
    if (input.value !== digits) {
      input.value = digits;
    }
  };

  const abortIme = (event: Event) => {
    event.preventDefault();
    event.stopPropagation();
    input.setAttribute("readonly", "readonly");
    sanitize();
    requestAnimationFrame(() => {
      input.removeAttribute("readonly");
      sanitize();
    });
  };

  const onKeydown = (event: KeyboardEvent) => {
    if (event.isComposing || event.key === "Process" || event.key === "Unidentified") {
      event.preventDefault();
      abortIme(event);
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (["Backspace", "Delete", "Tab", "Enter", "Escape", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      return;
    }
    if (/^\d$/.test(event.key)) return;
    event.preventDefault();
  };

  const onBeforeInput = (event: InputEvent) => {
    if (event.isComposing || event.inputType === "insertCompositionText") {
      event.preventDefault();
      abortIme(event);
      return;
    }
    if (event.data && !/^\d+$/.test(event.data)) {
      event.preventDefault();
    }
  };

  const onPaste = (event: ClipboardEvent) => {
    event.preventDefault();
    const digits = (event.clipboardData?.getData("text") ?? "").replace(/\D/g, "");
    if (!digits) return;
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    input.value = `${input.value.slice(0, start)}${digits}${input.value.slice(end)}`.replace(/\D/g, "");
    const caret = Math.min(input.value.length, start + digits.length);
    input.setSelectionRange(caret, caret);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  };

  input.setAttribute("inputmode", "numeric");
  input.setAttribute("pattern", "[0-9]*");
  input.setAttribute("lang", "en");
  input.setAttribute("autocomplete", "off");
  input.addEventListener("keydown", onKeydown, true);
  input.addEventListener("beforeinput", onBeforeInput as EventListener, true);
  input.addEventListener("compositionstart", abortIme, true);
  input.addEventListener("compositionupdate", abortIme, true);
  input.addEventListener("compositionend", abortIme, true);
  input.addEventListener("input", sanitize, true);
  input.addEventListener("paste", onPaste, true);

  return () => {
    input.removeEventListener("keydown", onKeydown, true);
    input.removeEventListener("beforeinput", onBeforeInput as EventListener, true);
    input.removeEventListener("compositionstart", abortIme, true);
    input.removeEventListener("compositionupdate", abortIme, true);
    input.removeEventListener("compositionend", abortIme, true);
    input.removeEventListener("input", sanitize, true);
    input.removeEventListener("paste", onPaste, true);
  };
}

const digitsOnlyCleanups = new WeakMap<HTMLElement, () => void>();
const digitsOnlyBoundInputs = new WeakMap<HTMLElement, HTMLInputElement>();

const vDigitsOnly = {
  mounted(el: HTMLElement) {
    const input = el.tagName === "INPUT" ? el as HTMLInputElement : el.querySelector("input");
    if (!input) return;
    digitsOnlyCleanups.set(el, bindDigitsOnlyInput(input));
    digitsOnlyBoundInputs.set(el, input);
  },
  updated(el: HTMLElement) {
    const input = el.tagName === "INPUT" ? el as HTMLInputElement : el.querySelector("input");
    if (!input || digitsOnlyBoundInputs.get(el) === input) return;
    digitsOnlyCleanups.get(el)?.();
    digitsOnlyCleanups.set(el, bindDigitsOnlyInput(input));
    digitsOnlyBoundInputs.set(el, input);
  },
  unmounted(el: HTMLElement) {
    digitsOnlyCleanups.get(el)?.();
    digitsOnlyCleanups.delete(el);
    digitsOnlyBoundInputs.delete(el);
  },
};

function applyCustomDimensionChange(current: number, incoming: number | string | null) {
  const next = Number(incoming);
  if (!Number.isFinite(next)) return current;
  if (Number.isFinite(current) && next === current + CUSTOM_SIZE_PIXEL_MULTIPLE) {
    return stepCustomDimension(current, 1);
  }
  if (Number.isFinite(current) && next === current - CUSTOM_SIZE_PIXEL_MULTIPLE) {
    return stepCustomDimension(current, -1);
  }
  return next;
}

function handleCustomWidthChange(value: number | string | null) {
  customWidth.value = applyCustomDimensionChange(Number(customWidth.value), value);
}

function handleCustomHeightChange(value: number | string | null) {
  customHeight.value = applyCustomDimensionChange(Number(customHeight.value), value);
}

function normalizeCustomDimension(value: number) {
  const snapped = snapToCustomSizeMultiple(Number(value) || customSizeMin.value);
  return Math.min(customSizeLimit.value, Math.max(customSizeMin.value, snapped));
}

function resetCustomSizeInput() {
  customSizeEnabled.value = false;
  customWidth.value = normalizeCustomDimension(1024);
  customHeight.value = normalizeCustomDimension(1024);
  customSize.value = "";
}

function parseCustomSizeValue(value?: string | null) {
  const normalized = String(value || "").trim();
  if (!normalized) return null;
  const match = normalized.match(/^(\d+)\s*[xX×*]\s*(\d+)$/);
  if (!match) return null;
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }
  return { width, height };
}

function applyCustomSizeFromValue(value?: string | null) {
  const parsed = parseCustomSizeValue(value);
  if (!parsed) {
    resetCustomSizeInput();
    return;
  }
  customSizeEnabled.value = true;
  customWidth.value = parsed.width;
  customHeight.value = parsed.height;
  customSize.value = `${parsed.width}x${parsed.height}`;
}

function refillCustomSizeFromValue(value?: string | null) {
  applyCustomSizeFromValue(value);
  void nextTick(() => applyCustomSizeFromValue(value));
}

function syncCustomSizeToCurrentLimits() {
  if (!supportsCustomSize.value) {
    if (customSizeEnabled.value || customSize.value) {
      resetCustomSizeInput();
    } else {
      customWidth.value = normalizeCustomDimension(Number(customWidth.value) || 1024);
      customHeight.value = normalizeCustomDimension(Number(customHeight.value) || 1024);
    }
    return;
  }
  if (!customSizeEnabled.value) {
    customWidth.value = normalizeCustomDimension(Number(customWidth.value) || 1024);
    customHeight.value = normalizeCustomDimension(Number(customHeight.value) || 1024);
    return;
  }
  customWidth.value = normalizeCustomDimension(Number(customWidth.value));
  customHeight.value = normalizeCustomDimension(Number(customHeight.value));
  customSize.value = `${Number(customWidth.value)}x${Number(customHeight.value)}`;
}

function onCustomSizeToggle(checked: boolean) {
  customSizeEnabled.value = checked;
  if (!checked) {
    customSize.value = "";
    return;
  }
  customSize.value = `${Number(customWidth.value)}x${Number(customHeight.value)}`;
}

function getCustomDimensionError(value: number, otherValue: number) {
  if (!Number.isInteger(value)) {
    return "必须是16倍数";
  }
  if (value % CUSTOM_SIZE_PIXEL_MULTIPLE !== 0) {
    return "必须是16倍数";
  }
  if (value > CUSTOM_SIZE_MAX_SIDE) {
    return `最大边长不超过 ${CUSTOM_SIZE_MAX_SIDE}px`;
  }
  if (value < customSizeMin.value || value > customSizeMax.value) {
    return `须为 ${customSizeMin.value}-${customSizeMax.value} 的整数`;
  }
  if (
    Number.isInteger(otherValue)
    && otherValue > 0
    && value > otherValue * CUSTOM_SIZE_MAX_ASPECT_RATIO
  ) {
    return `长短边比例不能超过 ${CUSTOM_SIZE_MAX_ASPECT_RATIO}:1`;
  }
  if (Number.isInteger(otherValue) && otherValue > 0 && value * otherValue < CUSTOM_SIZE_MIN_PIXELS) {
    return `总像素数不得低于 ${CUSTOM_SIZE_MIN_PIXELS}px`;
  }
  return "";
}

const customWidthError = computed(() => (
  customSizeEnabled.value ? getCustomDimensionError(Number(customWidth.value), Number(customHeight.value)) : ""
));
const customHeightError = computed(() => (
  customSizeEnabled.value ? getCustomDimensionError(Number(customHeight.value), Number(customWidth.value)) : ""
));

function validateCustomSizeInput() {
  if (!customSizeEnabled.value) return true;
  if (customWidthError.value || customHeightError.value) {
    const tips = [
      customWidthError.value ? `宽度${customWidthError.value}` : "",
      customHeightError.value ? `高度${customHeightError.value}` : "",
    ].filter(Boolean);
    message.warning(tips.join("；"));
    return false;
  }
  customSize.value = `${Number(customWidth.value)}x${Number(customHeight.value)}`;
  return true;
}
const smartCutoutSizeOptions = computed(() => (
  smartCutoutScene.value?.aspect_ratio_options?.length
    ? smartCutoutScene.value.aspect_ratio_options
    : DEFAULT_ASPECT_RATIO_OPTIONS
));
const smartCutoutResolutionOptions = computed(() => (
  smartCutoutScene.value?.image_size_options?.length
    ? smartCutoutScene.value.image_size_options
    : DEFAULT_IMAGE_SIZE_OPTIONS
));
const sceneCostMap = computed(() => Object.fromEntries(taskScenes.value.map((item) => [item.scene_key, item.credit_cost])));
function resolveSceneCreditCost(sceneKey: string, targetResolution = resolution.value) {
  const scene = generationModels.value.find((item) => item.model_key === sceneKey)
    || taskScenes.value.find((item) => item.scene_key === sceneKey);
  const resolutionKey = (targetResolution || "").trim();
  const resolutionCosts = scene?.resolution_credit_costs || {};
  if (resolutionKey && Object.prototype.hasOwnProperty.call(resolutionCosts, resolutionKey)) {
    return Number(resolutionCosts[resolutionKey] || 0);
  }
  return scene?.credit_cost
    ?? sceneCostMap.value[sceneKey]
    ?? DEFAULT_SCENE_COSTS[sceneKey]
    ?? 0;
}
const selectedModelCreditCost = computed(() => resolveSceneCreditCost(selectedModel.value, resolution.value));
const promptReverseCreditCost = computed(() => sceneCostMap.value.prompt_reverse ?? DEFAULT_SCENE_COSTS.prompt_reverse);
const promptOptimizeCreditCost = computed(() => sceneCostMap.value.prompt_optimize ?? DEFAULT_SCENE_COSTS.prompt_optimize);
const inpaintCreditCost = computed(() => sceneCostMap.value.inpaint ?? DEFAULT_SCENE_COSTS.inpaint);
const smartCutoutCreditCost = computed(() => resolveSceneCreditCost(
  "smart_cutout",
  customSizeEnabled.value ? "" : resolution.value,
));
const isExtendedToolMode = computed(() => generateMode.value === "promptReverse" || generateMode.value === "inpaint" || generateMode.value === "smartCutout");
const activeExtendedToolLabel = computed(() => (
  generateMode.value === "promptReverse"
    ? "提示词反推"
    : generateMode.value === "inpaint"
      ? "局部重绘"
      : generateMode.value === "smartCutout"
        ? "智能抠图"
        : "更多工具"
));
const activeExtendedToolMenuKeys = computed(() => (
  isExtendedToolMode.value ? [generateMode.value] : []
));

watch(
  () => maxReferenceImages.value,
  (limit) => {
    if (!isImageEditMode.value || limit <= 0 || referenceItems.value.length <= limit) return;
    const removedItems = referenceItems.value.slice(limit);
    removedItems.forEach((item) => revokeObjectUrl(item.objectUrl));
    referenceItems.value = referenceItems.value.slice(0, limit);
    message.warning(`当前模型最多支持 ${limit} 张参考图，已自动保留前 ${limit} 张`);
  }
);

const accentIndicatorStyle = { fontSize: "20px", color: "var(--theme-icon)" };
const smallAccentIndicatorStyle = { fontSize: "18px", color: "var(--theme-icon)" };
const neutralIndicatorStyle = { fontSize: "24px", color: "var(--text-secondary)" };

type GenerateTaskPayload = {
  model?: string;
  prompt: string;
  num_images: number;
  size: string;
  resolution: string;
  custom_size?: string;
  mode?: "generate" | "inpaint" | "smart_cutout";
  reference_images?: string[];
  source_image?: string;
  mask_image?: string;
  board_id?: number | null;
};

type GeneratedTaskDraft = Omit<GeneratedTaskItem, "localId" | "taskId" | "createdAt" | "status" | "images">;

function createPendingImages(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: -(Date.now() + index + Math.floor(Math.random() * 1000)),
    image_url: "",
    status: "pending" as const,
  }));
}

function parseAspectRatio(value?: string) {
  if (!value) return null;
  const normalized = value.trim();
  const ratioMatch = normalized.match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
  if (ratioMatch) {
    const width = Number(ratioMatch[1]);
    const height = Number(ratioMatch[2]);
    if (width > 0 && height > 0) return `${width} / ${height}`;
  }

  const sizeMatch = normalized.match(/^(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)$/);
  if (sizeMatch) {
    const width = Number(sizeMatch[1]);
    const height = Number(sizeMatch[2]);
    if (width > 0 && height > 0) return `${width} / ${height}`;
  }

  return null;
}

function normalizeHexColor(color: string) {
  const value = String(color || "").trim();
  if (/^#[0-9a-fA-F]{6}$/.test(value)) return value;
  if (/^#[0-9a-fA-F]{3}$/.test(value)) {
    return `#${value.slice(1).split("").map((char) => `${char}${char}`).join("")}`;
  }
  return REPAINT_COLOR_OPTIONS[0].value;
}

function hexToRgba(color: string, alpha: number) {
  const normalized = normalizeHexColor(color);
  const r = Number.parseInt(normalized.slice(1, 3), 16);
  const g = Number.parseInt(normalized.slice(3, 5), 16);
  const b = Number.parseInt(normalized.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
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

function isResultCardAspectRatio(value: string | null): value is ResultCardAspectRatio {
  return RESULT_CARD_ASPECT_OPTIONS.some((item) => item.value === value);
}

function readStoredResultCardAspectRatio(): ResultCardAspectRatio {
  if (typeof window === "undefined") return "1:1";
  const storedValue = sessionStorage.getItem(GENERATE_RESULT_CARD_ASPECT_RATIO_SESSION_KEY);
  return isResultCardAspectRatio(storedValue) ? storedValue : "1:1";
}

function writeStoredResultCardAspectRatio(value: ResultCardAspectRatio) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(GENERATE_RESULT_CARD_ASPECT_RATIO_SESSION_KEY, value);
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

async function maybeAutoDetectAspectRatioFromFirstReference(source: File | string) {
  if (!aspectRatioAutoDetectEnabled.value || hideAspectRatio.value || !sizeOptions.value.length) return;
  try {
    const dimensions = typeof source === "string"
      ? await loadImageDimensions(resolveImageUrl(source))
      : await readImageDimensionsFromFile(source);
    const matchedValue = getClosestAspectRatioValue(dimensions.width, dimensions.height, sizeOptions.value);
    if (matchedValue && sizeOptions.value.some((item) => item.value === matchedValue)) {
      size.value = matchedValue;
    }
  } catch {
    // Ignore dimension read failures and keep the current aspect ratio.
  }
}

function createLocalGeneratedTask(taskDraft: GeneratedTaskDraft): GeneratedTaskItem {
  return {
    localId: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    taskId: null,
    ...taskDraft,
    numImages: 1,
    createdAt: new Date().toISOString(),
    status: "submitting",
    errorMessage: "",
    creditRefunded: false,
    failureRefundRemainingCount: null,
    images: createPendingImages(1),
  };
}

function isGeneratedTaskExpired(task: Pick<GeneratedTaskItem, "createdAt" | "status">) {
  if (task.status !== "success") return false;
  if (!task.createdAt) return false;
  return dayjs().diff(dayjs(task.createdAt), "day", true) >= GENERATED_TASK_RETENTION_DAYS;
}

function getGeneratedTaskRetentionStart() {
  return dayjs().subtract(GENERATED_TASK_RETENTION_DAYS, "day");
}

const resultItems = computed(() => (
  generatedTasks.value.flatMap((task) => task.images.map((img, index) => ({
    taskLocalId: task.localId,
    taskId: task.taskId,
    task,
    image: img,
    index,
  }))).filter((item) => {
    if (!generatedTaskHideFailedFilter.value) return true;
    return item.task.status !== "failed" && item.image.status !== "failed";
  })
));

const hasMoreGeneratedTasks = computed(() => (
  auth.isLoggedIn
  && generatedTaskHistoryPage.value > 0
  && generatedTaskHistoryPage.value * GENERATED_TASK_HISTORY_PAGE_SIZE < generatedTaskHistoryTotal.value
));

function getResultItemKey(item: {
  taskLocalId: string;
  index: number;
  image: { id: number; status: string };
}) {
  return `${item.taskLocalId}-${item.index}`;
}

const resultColumnCount = computed(() => {
  if (viewportWidth.value <= 640) return 1;
  if (viewportWidth.value <= 960) return Math.min(2, preferredResultColumnCount.value);
  return preferredResultColumnCount.value;
});
const isDesktopGeneratedTaskAutoLoad = computed(() => viewportWidth.value > 960);
const isMobileGeneratedTaskManualLoad = computed(() => !isDesktopGeneratedTaskAutoLoad.value);

const resultListStyle = computed(() => ({
  gridTemplateColumns: `repeat(${resultColumnCount.value}, minmax(0, 1fr))`,
  "--generate-result-card-aspect": resultCardAspectRatio.value.replace(":", " / "),
}));

watch(preferredResultColumnCount, (count) => {
  writeStoredGridColumnCount(GENERATE_RESULT_COLUMN_COUNT_KEY, count);
});

watch(resultCardAspectRatio, (value) => {
  writeStoredResultCardAspectRatio(value);
});

watch(generatedTasks, (tasks) => {
  if (!detailOpen.value || !detailTaskLocalId.value) return;
  const latest = tasks.find((task) => (
    task.localId === detailTaskLocalId.value
    || (!!detailItem.value?.task_id && task.taskId === detailItem.value.task_id)
  ));
  if (!latest) return;
  const focusedImageId = detailItem.value?.image_id;
  const focusedImage = typeof focusedImageId === "number"
    ? latest.images.find((image) => image.id === focusedImageId)
    : undefined;
  detailItem.value = convertGeneratedTaskToHistoryCard(latest, focusedImage);
});

watch(
  resultItems,
  (items) => {
    const validKeys = new Set<string>();
    for (const item of items) {
      const key = getGeneratedResultMediaLoadKey(item.task, item.image, item.index);
      validKeys.add(key);
      const shouldTrackSource = item.image.status === "success"
        && !isGeneratedTaskExpired(item.task)
        && !shouldShowGeneratedLargeImagePreviewNotice(item.task, item.image, item.index);
      generatedResultImageLoad.syncSource(key, shouldTrackSource ? getResultDisplayUrl(item.image) : "");
    }
    generatedResultImageLoad.clearExcept(validKeys);
  },
  { immediate: true },
);

function syncViewportWidth() {
  viewportWidth.value = window.innerWidth;
}

function updateGeneratedTask(localId: string, updater: (task: GeneratedTaskItem) => GeneratedTaskItem) {
  generatedTasks.value = generatedTasks.value.map((task) => (
    task.localId === localId ? updater(task) : task
  ));
}

function updateGeneratedTaskByTaskId(taskId: string, updater: (task: GeneratedTaskItem) => GeneratedTaskItem) {
  generatedTasks.value = generatedTasks.value.map((task) => (
    task.taskId === taskId ? updater(task) : task
  ));
}

const activePollingTaskIds = computed(() => (
  generatedTasks.value
    .filter((task) => task.taskId && task.status !== "success" && task.status !== "failed")
    .map((task) => task.taskId as string)
));

function stopAllTaskPolling() {
  if (taskPollTimer.value) {
    clearInterval(taskPollTimer.value);
    taskPollTimer.value = null;
  }
  taskPollingInFlight.value = false;
}

function handleExtendedToolMenuClick({ key }: { key: string }) {
  if (key === "promptReverse" || key === "inpaint" || key === "smartCutout") {
    generateMode.value = key;
  }
}

function syncFailureRefundRemainingCount(value: number | null | undefined) {
  if (typeof value === "number" && value >= 0) {
    failureRefundRemainingCount.value = value;
  }
}

function syncTaskFromResult(taskId: string, data: TaskResult) {
  const current = generatedTasks.value.find((task) => task.taskId === taskId);
  if (!current) return;
  const previousStatus = current.status;
  const nextErrorMessage = data.error_message || data.images.find((image) => image.status === "failed" && image.error_message)?.error_message || "";
  syncFailureRefundRemainingCount(data.failure_refund_remaining_count);
  updateGeneratedTaskByTaskId(taskId, (task) => ({
    ...task,
    status: data.status,
    errorMessage: nextErrorMessage,
    providerErrorMessage: data.provider_error_message || task.providerErrorMessage,
    creditRefunded: Boolean(data.credit_refunded),
    failureRefundRemainingCount: data.failure_refund_remaining_count ?? task.failureRefundRemainingCount ?? null,
    usedFallbackApi: Boolean(data.used_fallback_api),
    apiAttempts: Array.isArray(data.api_attempts) ? data.api_attempts : (task.apiAttempts || []),
    createdAt: data.created_at || task.createdAt,
    model: data.model || task.model,
    size: data.size || task.size,
    resolution: data.resolution || task.resolution,
    customSize: data.custom_size || task.customSize,
    numImages: data.num_images || task.numImages,
    referenceImages: Array.isArray(data.reference_images) && data.reference_images.length
      ? data.reference_images
      : task.referenceImages,
    referenceImageThumbs: Array.isArray(data.reference_image_thumbs) && data.reference_image_thumbs.length
      ? data.reference_image_thumbs
      : task.referenceImageThumbs,
    sourceImage: data.source_image || task.sourceImage,
    sourceImageThumb: data.source_image_thumb || task.sourceImageThumb,
    maskImage: data.mask_image || task.maskImage,
    maskImageThumb: data.mask_image_thumb || task.maskImageThumb,
    images: data.images.length ? data.images : task.images,
  }));
  if (previousStatus !== data.status && (data.status === "success" || data.status === "failed")) {
    data.status === "success"
      ? message.success(`任务 #${taskId} 已完成`)
      : message.warning(getPreferredGenerationErrorMessage(
        data.error_message,
        data.images.find((image) => image.status === "failed" && image.error_message)?.error_message,
        Boolean(data.credit_refunded),
        "生成失败，请重试",
        Boolean(data.used_fallback_api),
        data.api_attempts,
        data.provider_error_message,
      ));
  }
}

function syncTasksFromResults(items: TaskResult[]) {
  items.forEach((item) => syncTaskFromResult(item.id, item));
}

async function syncFailureRefundRemainingCountFromTaskIds(taskIds: string[]) {
  const normalizedTaskIds = Array.from(new Set(taskIds.filter(Boolean)));
  if (!normalizedTaskIds.length) return;
  const items = await getTasks(normalizedTaskIds);
  items.forEach((item) => syncFailureRefundRemainingCount(item.failure_refund_remaining_count));
}

async function refreshTasks(taskIds = activePollingTaskIds.value) {
  if (!taskIds.length) {
    stopAllTaskPolling();
    return [];
  }
  const items = await getTasks(taskIds);
  syncTasksFromResults(items);
  void loadGlobalActiveGenerationStatus();
  if (!activePollingTaskIds.value.length) {
    stopAllTaskPolling();
  }
  return items;
}

function convertHistoryCardToGeneratedTask(item: UserHistoryCard): GeneratedTaskItem {
  const fallbackImageCount = Math.max(1, Number(item.num_images || item.images.length || 1));
  const taskMode: SubmitMode = item.mode === "inpaint"
    ? "inpaint"
    : item.mode === "smart_cutout"
      ? "smartCutout"
      : Array.isArray(item.reference_images) && item.reference_images.length
        ? "imageEdit"
        : "textGenerate";
  return {
    localId: `history-${item.task_id || item.history_id || "unknown"}`,
    taskId: item.task_id || null,
    mode: taskMode,
    prompt: item.prompt || "",
    model: item.model || undefined,
    numImages: fallbackImageCount,
    size: item.size || "1:1",
    resolution: item.resolution || "2K",
    customSize: item.custom_size || "",
    referenceImages: Array.isArray(item.reference_images) ? item.reference_images : [],
    referenceImageThumbs: Array.isArray(item.reference_image_thumbs) && item.reference_image_thumbs.length
      ? item.reference_image_thumbs
      : (Array.isArray(item.reference_images) ? item.reference_images : []),
    sourceImage: item.source_image || undefined,
    sourceImageThumb: item.source_image_thumb || item.source_image || undefined,
    maskImage: item.mask_image || undefined,
    maskImageThumb: item.mask_image_thumb || item.mask_image || undefined,
    createdAt: item.created_at,
    status: item.status as GeneratedTaskStatus,
    errorMessage: item.error_message || item.images.find((image) => image.status === "failed" && image.error_message)?.error_message || "",
    providerErrorMessage: item.provider_error_message || "",
    creditRefunded: Boolean(item.credit_refunded),
    failureRefundRemainingCount: null,
    usedFallbackApi: Boolean(item.used_fallback_api),
    apiAttempts: item.api_attempts || [],
    images: item.images.length ? item.images : createPendingImages(fallbackImageCount),
  };
}

function getGeneratedTaskFailureMessage(task: GeneratedTaskItem, image: ImageResult) {
  return getPreferredGenerationErrorMessage(
    task.errorMessage,
    image.error_message,
    Boolean(task.creditRefunded),
    "生成失败，请重试",
    Boolean(task.usedFallbackApi),
    task.apiAttempts,
    task.providerErrorMessage,
  );
}

function isGeneratedResultFailed(task: GeneratedTaskItem, image: ImageResult) {
  return task.status === "failed" && image.status === "failed";
}

function canRemoveGeneratedResult(task: GeneratedTaskItem, image: ImageResult) {
  return image.status === "success" || isGeneratedResultFailed(task, image);
}

async function loadGlobalActiveGenerationStatus() {
  if (!auth.isLoggedIn) {
    remoteActiveGenerationImageCount.value = 0;
    remoteActiveTaskIds.value = new Set();
    stopGlobalActiveStatusPolling();
    return;
  }
  if (activeStatusRefreshInFlight.value) return;
  activeStatusRefreshInFlight.value = true;
  try {
    const activeItems = generatedTasks.value.filter((item) => item.status === "pending" || item.status === "processing");
    const activeTaskIds = new Set<string>();
    activeItems.forEach((item) => {
      if (item.taskId) activeTaskIds.add(item.taskId);
    });
    remoteActiveTaskIds.value = activeTaskIds;
    remoteActiveGenerationImageCount.value = activeItems.length;
  } catch {
    // Keep the last known count if the lightweight status refresh fails.
  } finally {
    activeStatusRefreshInFlight.value = false;
    syncGlobalActiveStatusPolling();
  }
}

function stopGlobalActiveStatusPolling() {
  if (!activeStatusPollTimer.value) return;
  clearInterval(activeStatusPollTimer.value);
  activeStatusPollTimer.value = null;
}

function syncGlobalActiveStatusPolling() {
  if (!auth.isLoggedIn || activeGenerationImageCount.value <= 0) {
    stopGlobalActiveStatusPolling();
    return;
  }
  if (activeStatusPollTimer.value) return;
  activeStatusPollTimer.value = setInterval(() => {
    void loadGlobalActiveGenerationStatus();
  }, 8000);
}

function reloadGeneratedTasksForFilters() {
  if (!auth.isLoggedIn) return;
  generatedTasks.value = [];
  stopAllTaskPolling();
  void loadRecentGeneratedTasks();
}

function scheduleGeneratedTaskFilterReload() {
  if (generatedTaskFilterDebounceTimer) {
    window.clearTimeout(generatedTaskFilterDebounceTimer);
    generatedTaskFilterDebounceTimer = null;
  }
  generatedTaskFilterDebounceTimer = window.setTimeout(() => {
    generatedTaskFilterDebounceTimer = null;
    reloadGeneratedTasksForFilters();
  }, 320);
}

function setGeneratedTaskDatePreset(preset: GeneratedTaskDatePreset) {
  generatedTaskDatePreset.value = preset;
  const now = dayjs();
  if (preset === "today") {
    generatedTaskDateRangeFilter.value = [now, now];
    return;
  }
  if (preset === "yesterday") {
    const yesterday = now.subtract(1, "day");
    generatedTaskDateRangeFilter.value = [yesterday, yesterday];
    return;
  }
  if (preset === "week") {
    generatedTaskDateRangeFilter.value = [now.subtract(6, "day"), now];
  }
}

function handleGeneratedTaskCustomDateChange(value: [dayjs.Dayjs, dayjs.Dayjs] | null) {
  generatedTaskDatePreset.value = value ? "custom" : null;
}

function resetGeneratedTaskFilters() {
  generatedTaskHideExpiredFilter.value = true;
  generatedTaskHideFailedFilter.value = false;
  generatedTaskTypeFilter.value = undefined;
  generatedTaskSourceFilter.value = undefined;
  generatedTaskModelFilter.value = undefined;
  generatedTaskStatusFilter.value = undefined;
  generatedTaskPromptFilter.value = "";
  generatedTaskDateRangeFilter.value = null;
  generatedTaskDatePreset.value = null;
}

function resetGeneratedTaskPagination() {
  generatedTaskHistoryPage.value = 0;
  generatedTaskHistoryTotal.value = 0;
  generatedTasksLoadingMore.value = false;
}

function getGeneratedTaskIdentity(task: GeneratedTaskItem) {
  return task.taskId ? `task:${task.taskId}` : `local:${task.localId}`;
}

function setupGeneratedTaskLoadMoreObserver(target: HTMLElement | null) {
  generatedTaskLoadMoreObserver?.disconnect();
  generatedTaskLoadMoreObserver = null;
  if (!target || !isDesktopGeneratedTaskAutoLoad.value) return;

  generatedTaskLoadMoreObserver = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadMoreGeneratedTasks();
    },
    { root: resultBodyRef.value, rootMargin: "0px 0px 260px 0px", threshold: 0.01 }
  );
  generatedTaskLoadMoreObserver.observe(target);
}

function handleGeneratedTaskResultScroll(event: Event) {
  if (!isDesktopGeneratedTaskAutoLoad.value) return;
  const target = event.currentTarget as HTMLElement | null;
  maybeLoadMoreGeneratedTasksNearBottom(target);
}

function maybeLoadMoreGeneratedTasksNearBottom(target = resultBodyRef.value) {
  if (!isDesktopGeneratedTaskAutoLoad.value) return;
  if (!target || !hasMoreGeneratedTasks.value) return;
  if (generatedTasksLoading.value || generatedTasksLoadingMore.value) return;
  const distanceToBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
  if (distanceToBottom <= 320) void loadMoreGeneratedTasks();
}

function getGeneratedTaskHistoryFilters() {
  const boardId = selectedBoardId.value;
  const dateRange = generatedTaskDateRangeFilter.value;
  let startDate = dateRange?.[0]?.startOf("day") ?? null;
  const endDate = dateRange?.[1]?.endOf("day") ?? null;

  if (generatedTaskHideExpiredFilter.value) {
    const retentionStart = getGeneratedTaskRetentionStart();
    startDate = !startDate || startDate.isBefore(retentionStart) ? retentionStart : startDate;
  }

  return {
    include_prompt_reverse: false,
    board_scope: selectedBoardKey.value === DEFAULT_BOARD_KEY ? "default" as const : undefined,
    board_id: boardId ?? undefined,
    mode: generatedTaskTypeFilter.value,
    source: generatedTaskSourceFilter.value,
    model: generatedTaskModelFilter.value,
    status: generatedTaskStatusFilter.value,
    exclude_failed: generatedTaskHideFailedFilter.value || undefined,
    prompt: generatedTaskPromptFilter.value.trim() || undefined,
    start_date: startDate?.toISOString(),
    end_date: endDate?.toISOString(),
  };
}

async function loadBoardsForGenerate() {
  if (!auth.isLoggedIn) {
    boards.value = [];
    selectedBoardKey.value = DEFAULT_BOARD_KEY;
    boardSelectionReady.value = true;
    return;
  }
  boardsLoading.value = true;
  try {
    boards.value = (await listBoards({ includeStats: false, includePreviews: false })).items;
    selectedBoardKey.value = readStoredBoardKey(GENERATE_BOARD_KEY, boards.value, DEFAULT_BOARD_KEY);
  } catch {
    boards.value = [{ id: null, name: "默认分类", is_default: true, asset_count: 0, updated_at: null, preview_urls: [] }];
    selectedBoardKey.value = DEFAULT_BOARD_KEY;
  } finally {
    boardSelectionReady.value = true;
    boardsLoading.value = false;
  }
}

async function handleCreateBoardFromGenerate() {
  if (!auth.isLoggedIn || boardsLoading.value) return;
  boardsLoading.value = true;
  try {
    const board = await createBoard();
    const boardKey = boardKeyFromId(board.id);
    boards.value = [...boards.value.filter((item) => item.id !== board.id), board];
    selectedBoardKey.value = boardKey;
    message.success("分类已创建");
  } catch {
    message.error("创建分类失败");
  } finally {
    boardsLoading.value = false;
  }
}

function handleGoBoardListFromGenerate() {
  router.push("/history");
}

async function handleRenameSelectedBoardFromGenerate() {
  if (!canRenameSelectedBoard.value || !selectedBoard.value || typeof selectedBoard.value.id !== "number") {
    message.info("默认分类不可重命名");
    return;
  }
  boardRenameName.value = selectedBoard.value.name;
  boardRenameDialogOpen.value = true;
}

async function submitRenameSelectedBoardFromGenerate() {
  if (!canRenameSelectedBoard.value || !selectedBoard.value || typeof selectedBoard.value.id !== "number") return;
  const nextName = boardRenameName.value.trim();
  if (!nextName) {
    message.warning("分类名称不能为空");
    return;
  }
  if (nextName === selectedBoard.value.name) {
    boardRenameDialogOpen.value = false;
    return;
  }
  boardRenameSaving.value = true;
  try {
    const updatedBoard = await updateBoard(selectedBoard.value.id, nextName);
    boards.value = boards.value.map((board) => (board.id === updatedBoard.id ? updatedBoard : board));
    boardRenameDialogOpen.value = false;
    message.success("分类已重命名");
  } catch {
    message.error("重命名失败");
  } finally {
    boardRenameSaving.value = false;
  }
}

async function loadRecentGeneratedTasks() {
  if (!auth.isLoggedIn) {
    generatedTasks.value = [];
    resetGeneratedTaskPagination();
    stopAllTaskPolling();
    return;
  }

  const requestId = ++generatedTaskLoadRequestId;
  generatedTasksLoading.value = true;
  resetGeneratedTaskPagination();

  try {
    await loadGeneratedTaskHistoryPages({ reset: true, requestId });
  } catch {
    stopAllTaskPolling();
  } finally {
    if (requestId === generatedTaskLoadRequestId) {
      generatedTasksLoading.value = false;
      void nextTick(() => maybeLoadMoreGeneratedTasksNearBottom());
    }
  }
}

async function loadMoreGeneratedTasks() {
  if (!auth.isLoggedIn || generatedTasksLoading.value || generatedTasksLoadingMore.value || !hasMoreGeneratedTasks.value) return;
  const requestId = generatedTaskLoadRequestId;
  let loadedMoreSuccessfully = false;
  generatedTasksLoadingMore.value = true;
  try {
    await loadGeneratedTaskHistoryPages({ reset: false, requestId });
    loadedMoreSuccessfully = true;
  } catch {
    message.error("加载更多生成任务失败");
  } finally {
    if (requestId === generatedTaskLoadRequestId) {
      generatedTasksLoadingMore.value = false;
      if (loadedMoreSuccessfully) void nextTick(() => maybeLoadMoreGeneratedTasksNearBottom());
    }
  }
}

async function loadGeneratedTaskHistoryPages({
  reset,
  requestId,
}: {
  reset: boolean;
  requestId: number;
}) {
  const seenTaskIds = new Set(
    reset
      ? []
      : generatedTasks.value
          .map((task) => task.taskId)
          .filter((taskId): taskId is string => Boolean(taskId))
  );
  const loadedTasks: GeneratedTaskItem[] = [];
  const failedTaskIds: string[] = [];
  let nextPage = reset ? 1 : generatedTaskHistoryPage.value + 1;
  let total = reset ? Infinity : generatedTaskHistoryTotal.value;
  let lastLoadedPage = generatedTaskHistoryPage.value;

  if (total !== Infinity && (nextPage - 1) * GENERATED_TASK_HISTORY_PAGE_SIZE >= total) return;

  const res = await fetchHistory(nextPage, GENERATED_TASK_HISTORY_PAGE_SIZE, getGeneratedTaskHistoryFilters());
  if (requestId !== generatedTaskLoadRequestId) return;

  total = res.total;
  lastLoadedPage = nextPage;

  res.items.forEach((item) => {
    if (item.mode === "promptReverse" || !item.task_id || seenTaskIds.has(item.task_id)) return;
    seenTaskIds.add(item.task_id);
    loadedTasks.push(convertHistoryCardToGeneratedTask(item));
    if (item.status === "failed") failedTaskIds.push(String(item.task_id));
  });

  generatedTaskHistoryPage.value = lastLoadedPage;
  generatedTaskHistoryTotal.value = total === Infinity ? 0 : total;
  const preserveInFlightTasks = reset
    ? generatedTasks.value.filter((task) => {
      if (task.status === "submitting" && !task.taskId) return true;
      if (!task.taskId || seenTaskIds.has(task.taskId)) return false;
      return task.status === "submitting"
        || task.status === "pending"
        || task.status === "queued"
        || task.status === "processing";
    })
    : [];
  generatedTasks.value = reset
    ? [...preserveInFlightTasks, ...loadedTasks]
    : [
        ...generatedTasks.value,
        ...loadedTasks.filter((task) => {
          const taskIdentity = getGeneratedTaskIdentity(task);
          return !generatedTasks.value.some((current) => getGeneratedTaskIdentity(current) === taskIdentity);
        }),
      ];

  if (failedTaskIds.length) {
    try {
      await syncFailureRefundRemainingCountFromTaskIds(failedTaskIds);
    } catch {
      // Ignore remaining-count sync failures; the page can still render history normally.
    }
  }

  if (!activePollingTaskIds.value.length) {
    stopAllTaskPolling();
    return;
  }

  try {
    const items = await refreshTasks(activePollingTaskIds.value);
    if (items.some((item) => item.status !== "success" && item.status !== "failed")) startTaskPolling();
  } catch {
    startTaskPolling();
  }
}

function startTaskPolling() {
  if (taskPollTimer.value) return;
  taskPollTimer.value = setInterval(async () => {
    if (taskPollingInFlight.value || !activePollingTaskIds.value.length) {
      if (!activePollingTaskIds.value.length) stopAllTaskPolling();
      return;
    }
    taskPollingInFlight.value = true;
    try {
      await refreshTasks();
    } catch {
      stopAllTaskPolling();
    } finally {
      taskPollingInFlight.value = false;
    }
  }, 5000);
}

function applyPromptWithGenerateStyles(fullPrompt: string, target: "prompt" | "repaintPrompt") {
  const parsed = parseGeneratePrompt(fullPrompt);
  selectedColorStyleId.value = parsed.colorStyleId;
  selectedLightingStyleId.value = parsed.lightingStyleId;
  selectedCameraBodyId.value = parsed.camera.bodyId;
  selectedCameraLensId.value = parsed.camera.lensId;
  selectedCameraFocalId.value = parsed.camera.focalId;
  selectedCameraApertureId.value = parsed.camera.apertureId;
  if (target === "repaintPrompt") {
    repaintPrompt.value = parsed.userPrompt;
    return;
  }
  prompt.value = parsed.userPrompt;
}

function buildSubmitPrompt(userPrompt: string) {
  const assembled = composeGeneratePrompt(
    userPrompt,
    selectedColorStyleId.value,
    selectedLightingStyleId.value,
    currentCameraSelection(),
  );
  if (assembled.length > TASK_PROMPT_MAX_LENGTH) {
    message.warning("加上风格提示词后超出长度限制，请缩短提示词或取消部分风格");
    return "";
  }
  return assembled;
}

function getTaskDraftCreditCost(task: GeneratedTaskItem, nextNumImages = task.numImages) {
  if (task.mode === "inpaint") return inpaintCreditCost.value;
  if (task.mode === "smartCutout") {
    return resolveSceneCreditCost("smart_cutout", task.customSize ? "" : task.resolution);
  }
  const perImageCost = task.model ? resolveSceneCreditCost(task.model, task.resolution) : selectedModelCreditCost.value;
  return nextNumImages * perImageCost;
}

async function submitGeneratedTask(
  payload: GenerateTaskPayload,
  taskDraft: GeneratedTaskDraft
) {
  const taskCount = Math.max(1, payload.num_images);
  const localTasks = Array.from({ length: taskCount }, () => createLocalGeneratedTask(taskDraft));
  const localTaskIds = new Set(localTasks.map((task) => task.localId));
  generatedTasks.value = [...localTasks, ...generatedTasks.value];
  void nextTick(() => {
    requestAnimationFrame(() => {
      scrollGeneratedResultsIntoViewOnMobile();
    });
  });

  try {
    const res = await createTask({
      ...payload,
      board_id: payload.board_id ?? selectedBoardId.value,
    });
    const taskIds = res.task_ids?.length ? res.task_ids : (res.task_id ? [res.task_id] : []);
    if (taskIds.length > 1 && taskIds.length <= localTasks.length) {
      const acceptedLocalTasks = localTasks.slice(0, taskIds.length);
      const extraTaskIds = new Set(localTasks.slice(taskIds.length).map((task) => task.localId));
      generatedTasks.value = generatedTasks.value.filter((task) => !extraTaskIds.has(task.localId));
      acceptedLocalTasks.forEach((localTask, index) => {
        const taskId = taskIds[index];
        updateGeneratedTask(localTask.localId, (task) => ({ ...task, taskId, status: "pending" }));
      });
      if (taskIds.length < localTasks.length) {
        message.info(`当前剩余 ${taskIds.length} 个生成名额，已自动发起 ${taskIds.length} 个任务`);
      }
      startTaskPolling();
      void refreshTasks(taskIds);
    } else if (taskIds.length === 1) {
      const legacyTaskId = taskIds[0];
      const [primaryTask, ...extraTasks] = localTasks;
      const extraTaskIds = new Set(extraTasks.map((task) => task.localId));

      generatedTasks.value = generatedTasks.value
        .filter((task) => !extraTaskIds.has(task.localId))
        .map((task) => (
          task.localId === primaryTask.localId
            ? {
                ...task,
                taskId: legacyTaskId,
                numImages: taskCount,
                status: "pending",
                images: createPendingImages(taskCount),
              }
            : task
        ));

      startTaskPolling();
      void refreshTasks([legacyTaskId]);
    } else {
      throw new Error("服务端返回的任务数量异常");
    }

    pickingGeneratedReference.value = false;
    getMe().then((u) => auth.updateUser(u)).catch(() => {});
  } catch (err: any) {
    generatedTasks.value = generatedTasks.value.filter((task) => !localTaskIds.has(task.localId));
    throw err;
  }
}

function refreshAuthUserInBackground() {
  if (authUserRefreshPromise) return;
  authUserRefreshPromise = getMe()
    .then((user) => {
      auth.updateUser(user);
      lastAuthUserRefreshAt = Date.now();
    })
    .catch(() => {})
    .finally(() => {
      authUserRefreshPromise = null;
    });
}

async function ensureAuthenticated() {
  if (!auth.isLoggedIn) {
    loginModalVisible.value = true;
    return false;
  }
  if (auth.user) {
    const now = Date.now();
    if (now - lastAuthUserRefreshAt >= AUTH_USER_REFRESH_INTERVAL_MS) {
      refreshAuthUserInBackground();
    }
    return true;
  }
  try {
    auth.updateUser(await getMe());
    lastAuthUserRefreshAt = Date.now();
    return true;
  } catch {
    loginModalVisible.value = true;
    return false;
  }
}

function ensureLoggedIn() {
  if (!auth.isLoggedIn) {
    loginModalVisible.value = true;
    return false;
  }
  return true;
}

function goTutorial() {
  void router.push("/tutorial/generate");
}

function triggerUpload() {
  if (!auth.isLoggedIn) {
    loginModalVisible.value = true;
    return;
  }
  getMe().then((user) => auth.updateUser(user)).catch(() => {
    clearReferencePickerOpening();
    loginModalVisible.value = true;
  });
  requestImageSourcePick(fileInput.value, {
    onOpen: () => {
      referencePickerOpening.value = true;
      scheduleFilePickerRecovery();
    },
    onCancel: clearReferencePickerOpening,
  });
}

function clearReferencePickerOpening() {
  referencePickerOpening.value = false;
}

function clearSourcePickerOpening() {
  sourcePickerOpening.value = false;
}

function clearReversePickerOpening() {
  reversePickerOpening.value = false;
}

function clearAllPickerOpeningStates() {
  clearReferencePickerOpening();
  clearSourcePickerOpening();
  clearReversePickerOpening();
}

function clearFilePickerRecoveryTimer() {
  if (filePickerRecoveryTimer != null) {
    window.clearTimeout(filePickerRecoveryTimer);
    filePickerRecoveryTimer = null;
  }
}

function scheduleFilePickerRecovery(delay = 8000) {
  clearFilePickerRecoveryTimer();
  filePickerRecoveryTimer = window.setTimeout(() => {
    clearAllPickerOpeningStates();
    filePickerRecoveryTimer = null;
  }, delay);
}

function handleFilePickerFocusReturn() {
  scheduleFilePickerRecovery(400);
}

function handleDocumentVisibilityChange() {
  if (document.visibilityState === "visible") {
    handleFilePickerFocusReturn();
  }
}

function revokeObjectUrl(url?: string) {
  if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
}

function syncReferenceItems(urls: string[]) {
  referenceItems.value.forEach((item) => revokeObjectUrl(item.objectUrl));
  referenceItems.value = urls.map((url, index) => ({
    id: `${Date.now()}-${index}-${url}`,
    localUrl: url,
    remoteUrl: url,
    status: "success",
  }));
}

function getReferencePreviewUrl(item: UploadPreviewItem) {
  return getPreviewImageSrc(item.localUrl || item.remoteUrl);
}

function isSavingReferenceToLibrary(itemId: string) {
  return quickSavingReferenceIds.value.includes(itemId);
}

function canQuickSaveReferenceItem(item: UploadPreviewItem) {
  return item.status === "success" && !!item.objectUrl && !item.savedToAsset;
}

function isQuickSavePromptPending(promptKey: string) {
  return quickSavingPromptKeys.value.includes(promptKey);
}

function composeLibraryPromptContent(userPrompt: string) {
  return composeGeneratePrompt(
    userPrompt,
    selectedColorStyleId.value,
    selectedLightingStyleId.value,
    currentCameraSelection(),
  );
}

function buildLibraryPromptTitle(userPrompt: string) {
  const userTitle = (userPrompt || "").replace(/\s+/g, " ").trim();
  if (userTitle) return buildQuickSavePromptTitle(userTitle);
  const labels = [
    formatSelectedGenerateStyleLabel(selectedColorStyleId.value, selectedLightingStyleId.value),
    formatSelectedGenerateCameraLabel(currentCameraSelection()),
  ].filter(Boolean);
  return labels.join(" · ") || "我的提示词";
}

function canQuickSavePrompt(content: string, lastSavedContent: string) {
  const normalized = composeLibraryPromptContent(content);
  return !!normalized && normalized !== lastSavedContent.trim();
}

function markPromptQuickSaved(value: string) {
  lastSavedPromptText.value = value;
}

function markRepaintPromptQuickSaved(value: string) {
  lastSavedRepaintPromptText.value = value;
}

async function saveReferenceItemToLibrary(item: UploadPreviewItem) {
  if (!(await ensureAuthenticated())) return;
  if (!canQuickSaveReferenceItem(item)) return;
  if (isSavingReferenceToLibrary(item.id)) return;
  quickSavingReferenceIds.value = [...quickSavingReferenceIds.value, item.id];
  try {
    const file = await imageUrlToFile(item.objectUrl || item.localUrl, {
      fileName: item.fileName,
      fallbackPrefix: "reference-image",
    });
    await uploadUserAssetFiles([file]);
    updateReferenceItem(item.id, { savedToAsset: true });
    message.success("已加入我的素材");
  } catch (err: any) {
    message.error(err?.response?.data?.detail || err?.message || "加入我的素材失败");
  } finally {
    quickSavingReferenceIds.value = quickSavingReferenceIds.value.filter((id) => id !== item.id);
  }
}

function confirmSaveReferenceItem(item: UploadPreviewItem) {
  Modal.confirm({
    title: "加入我的素材",
    content: "确认将这张参考图加入我的素材吗？",
    centered: true,
    okText: "确认加入",
    cancelText: "取消",
    async onOk() {
      await saveReferenceItemToLibrary(item);
    },
  });
}

async function savePromptToLibrary(content: string, promptKey: string, onSaved: (value: string) => void, title?: string) {
  const normalized = content.trim();
  if (!normalized) return;
  if (!(await ensureAuthenticated())) return;
  if (isQuickSavePromptPending(promptKey)) return;
  quickSavingPromptKeys.value = [...quickSavingPromptKeys.value, promptKey];
  try {
    const promptTitle = (title || "").trim() || buildQuickSavePromptTitle(normalized);
    await createUserPrompt({ title: promptTitle, content: normalized });
    onSaved(normalized);
    message.success("已加入我的提示词");
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "加入我的提示词失败");
  } finally {
    quickSavingPromptKeys.value = quickSavingPromptKeys.value.filter((key) => key !== promptKey);
  }
}

function confirmSavePromptToLibrary(content: string, promptKey: string, onSaved: (value: string) => void) {
  const normalized = composeLibraryPromptContent(content);
  if (!normalized) return;
  if (normalized.length > TASK_PROMPT_MAX_LENGTH) {
    message.warning("加上风格后超出长度限制，请缩短提示词或取消部分风格");
    return;
  }
  const title = buildLibraryPromptTitle(content);
  Modal.confirm({
    title: "加入我的提示词",
    content: `确认将当前提示词加入我的提示词吗？将使用“${title}”作为默认标题。`,
    centered: true,
    okText: "确认加入",
    cancelText: "取消",
    async onOk() {
      await savePromptToLibrary(normalized, promptKey, onSaved, title);
    },
  });
}

function getReversePreviewUrl() {
  return getPreviewImageSrc(reverseImageUrl.value);
}

function updateReferenceItem(id: string, patch: Partial<UploadPreviewItem>) {
  const index = referenceItems.value.findIndex((item) => item.id === id);
  if (index === -1) return;
  referenceItems.value[index] = {
    ...referenceItems.value[index],
    ...patch,
  };
}

function addLibraryAssetToReference(asset: UserAsset) {
  const limit = maxReferenceImages.value;
  const shouldAutoDetect = referenceItems.value.length === 0;
  if (referenceItems.value.some((item) => item.remoteUrl === asset.image_url)) {
    message.info("这张素材已在参考图中");
    return false;
  }
  if (referenceItems.value.length >= limit) {
    message.warning(`当前模型最多支持 ${limit} 张参考图`);
    return false;
  }
  referenceItems.value.push({
    id: `asset-${asset.id}-${Date.now()}`,
    localUrl: asset.thumb_url || asset.image_url,
    remoteUrl: asset.image_url,
    status: "success",
    fileName: asset.file_name,
    savedToAsset: true,
  });
  if (shouldAutoDetect) {
    void maybeAutoDetectAspectRatioFromFirstReference(asset.image_url);
  }
  return true;
}

function addLibraryAssetsToReference(assets: UserAsset[]) {
  const limit = maxReferenceImages.value;
  const shouldAutoDetect = referenceItems.value.length === 0;
  if (limit <= 0) {
    message.warning("当前模型不支持参考图");
    return false;
  }
  const existingUrls = new Set(
    referenceItems.value
      .map((item) => item.remoteUrl)
      .filter((url): url is string => !!url),
  );
  const uniqueAssets = assets.filter((asset) => !existingUrls.has(asset.image_url));
  if (!uniqueAssets.length) {
    message.info("所选素材均已在参考图中");
    return false;
  }
  const remainingSlots = Math.max(0, limit - referenceItems.value.length);
  if (uniqueAssets.length > remainingSlots) {
    message.warning(
      remainingSlots > 0
        ? `当前模型最多支持 ${limit} 张参考图，还可添加 ${remainingSlots} 张，已选 ${uniqueAssets.length} 张`
        : `当前模型最多支持 ${limit} 张参考图`,
    );
    return false;
  }
  const now = Date.now();
  uniqueAssets.forEach((asset, index) => {
    referenceItems.value.push({
      id: `asset-${asset.id}-${now}-${index}`,
      localUrl: asset.thumb_url || asset.image_url,
      remoteUrl: asset.image_url,
      status: "success",
      fileName: asset.file_name,
      savedToAsset: true,
    });
  });
  if (shouldAutoDetect && uniqueAssets[0]) {
    void maybeAutoDetectAspectRatioFromFirstReference(uniqueAssets[0].image_url);
  }
  if (uniqueAssets.length < assets.length) {
    message.success(`已添加 ${uniqueAssets.length} 张参考图，其余素材已在参考图中`);
  }
  return true;
}

function getGeneratedImageReferenceUrl(img: ImageResult) {
  return (img.image_url || img.preview_url || img.thumb_url || "").trim();
}

function isGeneratedImageAlreadyReferenced(img: ImageResult) {
  const url = getGeneratedImageReferenceUrl(img);
  return !!url && referenceItems.value.some((item) => item.remoteUrl === url);
}

function canShowGeneratedReferenceAdd(task: GeneratedTaskItem, img: ImageResult) {
  return pickingGeneratedReference.value
    && isImageEditMode.value
    && canEditGeneratedImage(task, img);
}

function getScrollableAncestor(el: HTMLElement) {
  let parent = el.parentElement;
  while (parent) {
    const { overflowY } = getComputedStyle(parent);
    const canScroll = (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay")
      && parent.scrollHeight > parent.clientHeight + 1;
    if (canScroll) return parent;
    parent = parent.parentElement;
  }
  return (document.scrollingElement as HTMLElement | null) || document.documentElement;
}

function scrollGeneratedResultsIntoViewOnMobile() {
  if (viewportWidth.value > 960) return;
  const target = resultPanelRef.value;
  if (!target) return;
  const scroller = getScrollableAncestor(target);
  const isDocumentScroller = scroller === document.documentElement || scroller === document.body;
  const offset = isDocumentScroller ? 80 : 8;
  const scrollerRect = scroller.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const nextTop = scroller.scrollTop + (targetRect.top - scrollerRect.top) - offset;
  scroller.scrollTo({ top: Math.max(0, nextTop), behavior: "smooth" });
}

function togglePickingGeneratedReference() {
  if (pickingGeneratedReference.value) {
    pickingGeneratedReference.value = false;
    return;
  }
  if (!ensureLoggedIn()) return;
  if (!isImageEditMode.value) return;
  if (referenceItems.value.length >= maxReferenceImages.value) {
    message.warning(`当前模型最多支持 ${maxReferenceImages.value} 张参考图`);
    return;
  }
  const hasPickable = resultItems.value.some((item) => canEditGeneratedImage(item.task, item.image));
  if (!hasPickable) {
    message.warning("暂无已生成图片可添加");
    return;
  }
  pickingGeneratedReference.value = true;
  void nextTick(() => {
    requestAnimationFrame(() => {
      scrollGeneratedResultsIntoViewOnMobile();
    });
  });
}

function toggleGeneratedImageAsReference(task: GeneratedTaskItem, img: ImageResult) {
  const imageUrl = getGeneratedImageReferenceUrl(img);
  if (!imageUrl) {
    message.warning("当前结果图暂不可添加为参考图");
    return;
  }
  const existingIndex = referenceItems.value.findIndex((item) => item.remoteUrl === imageUrl);
  if (existingIndex !== -1) {
    removeReference(existingIndex);
    return;
  }
  const limit = maxReferenceImages.value;
  if (referenceItems.value.length >= limit) {
    message.warning(`当前模型最多支持 ${limit} 张参考图`);
    return;
  }
  const shouldAutoDetect = referenceItems.value.length === 0;
  referenceItems.value.push({
    id: `generated-${task.localId}-${img.id || Date.now()}`,
    localUrl: img.thumb_url || img.preview_url || imageUrl,
    remoteUrl: imageUrl,
    status: "success",
  });
  if (shouldAutoDetect) {
    void maybeAutoDetectAspectRatioFromFirstReference(imageUrl);
  }
}

watch(isImageEditMode, (isImageEdit) => {
  if (!isImageEdit) pickingGeneratedReference.value = false;
});

async function handlePickUserAsset(asset: UserAsset) {
  if (addLibraryAssetToReference(asset)) {
    assetPickerOpen.value = false;
  }
}

async function handlePickUserAssets(assets: UserAsset[]) {
  if (addLibraryAssetsToReference(assets)) {
    assetPickerOpen.value = false;
  }
}

async function openAssetPicker() {
  if (!ensureLoggedIn()) return;
  assetPickerOpen.value = true;
}

function openSketchBoard() {
  if (!ensureLoggedIn()) return;
  if (referenceItems.value.length >= maxReferenceImages.value) {
    message.warning(`当前模型最多支持 ${maxReferenceImages.value} 张参考图`);
    return;
  }
  sketchBoardOpen.value = true;
}

function handleSketchBoardConfirm(file: File) {
  sketchBoardOpen.value = false;
  void uploadReferenceFiles([file], "已作为参考图");
}

async function uploadReferenceFiles(files: File[], successText?: string) {
  const imageFiles = files.filter((file) => isReferenceImageFile(file));
  if (!imageFiles.length) {
    if (files.length) {
      message.warning("仅支持上传图片文件");
    }
    return;
  }

  const remainingSlots = Math.max(0, maxReferenceImages.value - referenceItems.value.length);
  if (!remainingSlots) {
    message.warning(`当前模型最多上传 ${maxReferenceImages.value} 张参考图`);
    return;
  }

  const referenceLimitedFiles = imageFiles.slice(0, remainingSlots);
  const skippedDueToModel = imageFiles.length - referenceLimitedFiles.length;

  if (skippedDueToModel > 0) {
    message.warning(`当前模型最多支持 ${maxReferenceImages.value} 张参考图，本次仅上传前 ${referenceLimitedFiles.length} 张`);
  }
  if (!referenceLimitedFiles.length) return;

  let uploadedCount = 0;
  let failedCount = 0;
  let oversizedCount = 0;
  let shouldAutoDetectFirstReference = referenceItems.value.length === 0;
  const { uploadReferenceImage } = await import("@/api/upload");

  for (const file of referenceLimitedFiles) {
    if (isImageUploadTooLarge(file)) {
      oversizedCount += 1;
      continue;
    }

    const objectUrl = URL.createObjectURL(file);
    const item: UploadPreviewItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      localUrl: objectUrl,
      remoteUrl: "",
      status: "uploading",
      objectUrl,
      fileName: file.name,
      savedToAsset: false,
    };
    referenceItems.value.push(item);

    try {
      const res = await uploadReferenceImage(file, "ref");
      updateReferenceItem(item.id, {
        remoteUrl: res.url,
        status: "success",
      });
      uploadedCount += 1;
      if (shouldAutoDetectFirstReference) {
        shouldAutoDetectFirstReference = false;
        void maybeAutoDetectAspectRatioFromFirstReference(file);
      }
    } catch (err: any) {
      updateReferenceItem(item.id, { status: "failed" });
      failedCount += 1;
    }
  }

  if (uploadedCount > 0) {
    message.success(successText || `成功上传 ${uploadedCount} 张参考图`);
  }
  if (oversizedCount > 0) {
    message.warning(`${oversizedCount} 张图片超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}，已跳过`);
  }
  if (failedCount > 0) {
    message.error(`${failedCount} 张参考图上传失败，请重试`);
  }
}

function resetReferenceDragState() {
  referenceDragCounter.value = 0;
  referenceDragActive.value = false;
}

function isReferenceFileDragEvent(event: DragEvent) {
  const types = Array.from(event.dataTransfer?.types || []);
  return types.includes("Files");
}

function isReferenceImageFile(file: File) {
  return isSupportedImageUploadFile(file);
}

async function processReferenceDropFiles(files: File[]) {
  if (!(await ensureAuthenticated())) return;
  if (!files.length) return;
  await uploadReferenceFiles(files);
}

function getClipboardImageFiles(event: ClipboardEvent) {
  const clipboardItems = Array.from(event.clipboardData?.items || []);
  const itemFiles = clipboardItems
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter((file): file is File => !!file && isReferenceImageFile(file));
  if (itemFiles.length) return itemFiles;
  return Array.from(event.clipboardData?.files || []).filter((file) => isReferenceImageFile(file));
}

async function handleReferencePaste(event: ClipboardEvent) {
  if (generateMode.value !== "imageEdit") return;
  const files = getClipboardImageFiles(event);
  if (!files.length) return;
  event.preventDefault();
  event.stopPropagation();
  await processReferenceDropFiles(files);
}

function bindReferenceDragHandlers(element: HTMLElement) {
  const handleDragEnter = (event: DragEvent) => {
    if (!isReferenceFileDragEvent(event)) return;
    event.preventDefault();
    event.stopPropagation();
    referenceDragCounter.value += 1;
    referenceDragActive.value = true;
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
    referenceDragCounter.value = Math.max(0, referenceDragCounter.value - 1);
    if (referenceDragCounter.value === 0) {
      referenceDragActive.value = false;
    }
  };

  const handleDrop = (event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    resetReferenceDragState();

    const files = Array.from(event.dataTransfer?.files || []);
    if (!files.length) return;
    void processReferenceDropFiles(files);
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

watch(referenceUploadBlockRef, (element) => {
  unbindReferenceDragHandlers?.();
  unbindReferenceDragHandlers = element ? bindReferenceDragHandlers(element) : null;
}, { flush: "post" });

async function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  clearReferencePickerOpening();
  clearFilePickerRecoveryTimer();
  if (!files.length) return;

  try {
    await uploadReferenceFiles(files);
  } finally {
    input.value = "";
  }
}

function removeReference(index: number) {
  const item = referenceItems.value[index];
  if (item) revokeObjectUrl(item.objectUrl);
  referenceItems.value.splice(index, 1);
}

function triggerSourceUpload() {
  if (!auth.isLoggedIn) {
    loginModalVisible.value = true;
    return;
  }
  getMe().then((user) => auth.updateUser(user)).catch(() => {
    clearSourcePickerOpening();
    loginModalVisible.value = true;
  });
  requestImageSourcePick(sourceInput.value, {
    onOpen: () => {
      sourcePickerOpening.value = true;
      scheduleFilePickerRecovery();
    },
    onCancel: clearSourcePickerOpening,
  });
}

async function handleSourceFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  clearSourcePickerOpening();
  clearFilePickerRecoveryTimer();
  if (!file) return;

  if (!isReferenceImageFile(file)) {
    message.warning("仅支持上传图片文件");
    input.value = "";
    return;
  }

  if (isImageUploadTooLarge(file)) {
    message.warning(`图片大小不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
    input.value = "";
    return;
  }

  revokeObjectUrl(sourcePreviewUrl.value);
  sourcePreviewUrl.value = URL.createObjectURL(file);
  sourceImageUrl.value = "";
  sourceUploading.value = true;
  try {
    const { uploadReferenceImage } = await import("@/api/upload");
    const res = await uploadReferenceImage(file, "source");
    sourceImageUrl.value = res.url;
    repaintMaskUrl.value = "";
    hasRepaintMask.value = false;
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
  repaintMaskUrl.value = "";
  hasRepaintMask.value = false;
  canUndoMask.value = false;
  canRedoMask.value = false;
}

function triggerReverseUpload() {
  if (!auth.isLoggedIn) {
    loginModalVisible.value = true;
    return;
  }
  getMe().then((user) => auth.updateUser(user)).catch(() => {
    clearReversePickerOpening();
    loginModalVisible.value = true;
  });
  requestImageSourcePick(reverseInput.value, {
    onOpen: () => {
      reversePickerOpening.value = true;
      scheduleFilePickerRecovery();
    },
    onCancel: clearReversePickerOpening,
  });
}

async function handleReverseFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  clearReversePickerOpening();
  clearFilePickerRecoveryTimer();
  if (!file) return;

  if (!isReferenceImageFile(file)) {
    message.warning("仅支持上传图片文件");
    input.value = "";
    return;
  }

  if (isImageUploadTooLarge(file)) {
    message.warning(`图片大小不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
    input.value = "";
    return;
  }

  reverseUploading.value = true;
  try {
    const { uploadReferenceImage } = await import("@/api/upload");
    const res = await uploadReferenceImage(file, "reverse");
    reverseImageUrl.value = res.url;
    reversePromptResult.value = "";
    message.success("反推图片上传成功");
  } catch {
    message.error("图片上传失败，请重试");
  } finally {
    reverseUploading.value = false;
    input.value = "";
  }
}

function removeReverseImage() {
  reverseImageUrl.value = "";
  reversePromptResult.value = "";
}

function clearRepaintMask() {
  repaintMaskUrl.value = "";
  repaintCanvasRef.value?.clearMask();
  hasRepaintMask.value = false;
  canUndoMask.value = false;
  canRedoMask.value = false;
}

function undoRepaintMask() {
  const changed = repaintCanvasRef.value?.undo();
  if (!changed) return;
  hasRepaintMask.value = repaintCanvasRef.value?.hasDrawnMask() ?? false;
  canUndoMask.value = repaintCanvasRef.value?.canUndo() ?? false;
  canRedoMask.value = repaintCanvasRef.value?.canRedo() ?? false;
}

function redoRepaintMask() {
  const changed = repaintCanvasRef.value?.redo();
  if (!changed) return;
  hasRepaintMask.value = repaintCanvasRef.value?.hasDrawnMask() ?? false;
  canUndoMask.value = repaintCanvasRef.value?.canUndo() ?? false;
  canRedoMask.value = repaintCanvasRef.value?.canRedo() ?? false;
}

function handleMaskChange(value: boolean) {
  hasRepaintMask.value = value;
  canUndoMask.value = repaintCanvasRef.value?.canUndo() ?? false;
  canRedoMask.value = repaintCanvasRef.value?.canRedo() ?? false;
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

const creditCost = computed(() => {
  if (generateMode.value === "inpaint") return inpaintCreditCost.value;
  if (generateMode.value === "smartCutout") return smartCutoutCreditCost.value;
  return numImages.value * selectedModelCreditCost.value;
});
const actualSubmitImageCount = computed(() => (
  generateMode.value === "inpaint"
    ? Math.min(1, remainingGenerationImageSlots.value)
    : Math.min(numImages.value, remainingGenerationImageSlots.value)
));
const actualSubmitCreditCost = computed(() => {
  if (generateMode.value === "inpaint") return inpaintCreditCost.value;
  if (generateMode.value === "smartCutout") return smartCutoutCreditCost.value;
  return actualSubmitImageCount.value * selectedModelCreditCost.value;
});
const userCredits = computed(() => auth.user?.credits ?? 0);
const canCreateTemplateFromTask = computed(() => auth.isAdmin);
const isSuperAdmin = computed(() => auth.isSuperAdmin);
const generateButtonText = computed(() => {
  if (submittingGenerate.value) {
    return "提交中...";
  }
  if (generateMode.value === "inpaint" && sourceUploading.value) {
    return "原图上传中...";
  }
  if (generateMode.value === "inpaint" && sourcePreviewUrl.value && !sourceImageUrl.value) {
    return "原图未上传完成";
  }
  if (isImageEditMode.value && hasPendingReferenceUploads.value) {
    return "参考图上传中...";
  }
  if (isImageEditMode.value && hasFailedReferenceUploads.value) {
    return "参考图上传失败，请处理后再生成";
  }
  if (remainingGenerationImageSlots.value <= 0) {
    return "生成队列已满";
  }
  return `开始生成 · ${actualSubmitCreditCost.value} 积分`;
});
const promptReverseButtonText = computed(() => {
  if (reverseLoading.value) return "提示词反推中...";
  return isSuperAdmin.value ? "开始反推" : `开始反推 · ${promptReverseCreditCost.value} 积分`;
});
const activePrompt = computed(() => (
  generateMode.value === "inpaint" ? repaintPrompt.value : prompt.value
));

function getPromptOptimizeReferenceImages() {
  if (generateMode.value === "imageEdit") {
    return [...referenceUrls.value];
  }
  if (generateMode.value === "inpaint") {
    return sourceImageUrl.value.trim() ? [sourceImageUrl.value.trim()] : [];
  }
  return [];
}

function applyOptimizedPrompt(nextPrompt: string, target: PromptOptimizeTarget) {
  if (target === "repaintPrompt") {
    repaintPrompt.value = nextPrompt;
    return;
  }
  prompt.value = nextPrompt;
}

const isPromptOptimizeOnMainPrompt = computed(() => (
  promptOptimizeLoading.value && promptOptimizeTarget.value === "prompt"
));
const isPromptOptimizeOnRepaintPrompt = computed(() => (
  promptOptimizeLoading.value && promptOptimizeTarget.value === "repaintPrompt"
));

function getPromptOptimizeTarget(): PromptOptimizeTarget {
  return generateMode.value === "inpaint" ? "repaintPrompt" : "prompt";
}

const promptExpandOpen = ref(false);
const promptExpandTarget = ref<PromptOptimizeTarget>("prompt");
const promptExpandValue = computed(() => (
  promptExpandTarget.value === "repaintPrompt" ? repaintPrompt.value : prompt.value
));
const promptExpandPlaceholder = computed(() => (
  promptExpandTarget.value === "repaintPrompt"
    ? "描述需要局部重绘后的效果..."
    : "描述您想要生成的图片..."
));

function openPromptExpand(target: PromptOptimizeTarget) {
  if (target === "prompt" && isPromptOptimizeOnMainPrompt.value) return;
  if (target === "repaintPrompt" && isPromptOptimizeOnRepaintPrompt.value) return;
  promptExpandTarget.value = target;
  promptExpandOpen.value = true;
}

function applyExpandedPrompt(value: string) {
  if (promptExpandTarget.value === "repaintPrompt") {
    repaintPrompt.value = value;
    return;
  }
  prompt.value = value;
}

async function runPromptOptimize(
  payload: PromptOptimizePayload,
  target: PromptOptimizeTarget,
) {
  const requestId = ++promptOptimizeRequestSeq;
  const controller = new AbortController();
  activePromptOptimizeRequestId.value = requestId;
  promptOptimizeTarget.value = target;
  promptOptimizeAbortController = controller;
  promptOptimizeLoading.value = true;
  try {
    const res = await optimizePrompt(payload, controller.signal);
    if (cancelledPromptOptimizeRequestIds.has(requestId) || activePromptOptimizeRequestId.value !== requestId) {
      return;
    }
    const optimizedPrompt = (res.prompt || "").trim();
    if (!optimizedPrompt) {
      message.error("提示词优化返回内容为空");
      return;
    }
    applyOptimizedPrompt(optimizedPrompt, target);
    message.success("提示词已优化并回填");
    getMe().then((u) => auth.updateUser(u)).catch(() => {});
  } catch (err: any) {
    if (cancelledPromptOptimizeRequestIds.has(requestId) || err?.code === "ERR_CANCELED" || err?.name === "CanceledError") {
      return;
    }
    const detail = err?.response?.data?.detail || "";
    if (isInsufficientCreditsError(err)) {
      showInsufficientCreditsPurchase(detail);
      return;
    }
    message.error(detail || "提示词优化失败");
  } finally {
    cancelledPromptOptimizeRequestIds.delete(requestId);
    if (activePromptOptimizeRequestId.value === requestId) {
      activePromptOptimizeRequestId.value = null;
      promptOptimizeTarget.value = null;
      promptOptimizeLoading.value = false;
    }
    if (promptOptimizeAbortController === controller) {
      promptOptimizeAbortController = null;
    }
  }
}

function cancelPromptOptimize() {
  const requestId = activePromptOptimizeRequestId.value;
  if (requestId == null) return;
  cancelledPromptOptimizeRequestIds.add(requestId);
  activePromptOptimizeRequestId.value = null;
  promptOptimizeTarget.value = null;
  promptOptimizeLoading.value = false;
  promptOptimizeAbortController?.abort();
  promptOptimizeAbortController = null;
}

function confirmCancelPromptOptimize() {
  if (!promptOptimizeLoading.value || activePromptOptimizeRequestId.value == null) return;
  Modal.confirm({
    title: "确认取消提示词优化？",
    content: "取消后，即使本次优化结果稍后返回，也不会回填到输入框。",
    centered: true,
    okText: "确认取消",
    cancelText: "继续等待",
    okButtonProps: { danger: true },
    onOk: () => {
      cancelPromptOptimize();
      message.info("已取消提示词优化");
    },
  });
}

function openPromptOptimizeStyleDialog(
  payload: Omit<PromptOptimizePayload, "style_name" | "style_prompt">,
  target: PromptOptimizeTarget,
) {
  pendingPromptOptimizePayload.value = payload;
  pendingPromptOptimizeTarget.value = target;
  promptOptimizeStyleDialogOpen.value = true;
}

function closePromptOptimizeStyleDialog() {
  promptOptimizeStyleDialogOpen.value = false;
  pendingPromptOptimizePayload.value = null;
  pendingPromptOptimizeTarget.value = null;
}

function handlePromptOptimizeStyleConfirm(style: PublicPromptOptimizeStyle) {
  if (!pendingPromptOptimizePayload.value || !pendingPromptOptimizeTarget.value) {
    message.warning("提示词优化请求已失效，请重新发起");
    closePromptOptimizeStyleDialog();
    return;
  }
  const normalizedPrompt = activePrompt.value.trim();
  if (!normalizedPrompt) {
    message.warning("请先输入需要优化的提示词");
    return;
  }
  const payload: PromptOptimizePayload = {
    ...pendingPromptOptimizePayload.value,
    prompt: normalizedPrompt,
    style_name: style.name,
    style_prompt: style.style_prompt,
  };
  const target = pendingPromptOptimizeTarget.value;
  closePromptOptimizeStyleDialog();
  void runPromptOptimize(payload, target);
}

async function handlePromptOptimize() {
  if (promptOptimizeLoading.value) return;
  if (!(await ensureAuthenticated())) return;
  if (generateMode.value === "imageEdit" && hasPendingReferenceUploads.value) {
    message.warning("参考图仍在上传中，请稍候再优化");
    return;
  }
  if (generateMode.value === "inpaint" && sourceUploading.value) {
    message.warning("原图仍在上传中，请稍候再优化");
    return;
  }
  if (generateMode.value === "inpaint" && sourcePreviewUrl.value && !sourceImageUrl.value) {
    message.warning("原图未上传完成，请稍候再优化");
    return;
  }
  if (!isSuperAdmin.value && userCredits.value < promptOptimizeCreditCost.value) {
    showInsufficientCreditsPurchase(`积分不足，需要 ${promptOptimizeCreditCost.value} 积分，当前余额 ${userCredits.value}`);
    return;
  }

  const payload = {
    prompt: activePrompt.value.trim(),
    reference_images: getPromptOptimizeReferenceImages(),
  };
  const target = getPromptOptimizeTarget();
  openPromptOptimizeStyleDialog(payload, target);
}

async function handlePromptReverse() {
  if (!(await ensureAuthenticated())) return;
  if (!reverseImageUrl.value.trim()) {
    message.warning("请先上传需要反推提示词的图片");
    return;
  }
  if (!isSuperAdmin.value && userCredits.value < promptReverseCreditCost.value) {
    showInsufficientCreditsPurchase(`积分不足，需要 ${promptReverseCreditCost.value} 积分，当前余额 ${userCredits.value}`);
    return;
  }

  reverseLoading.value = true;
  try {
    const res = await reversePrompt(reverseImageUrl.value);
    reversePromptResult.value = res.prompt;
    message.success("提示词反推完成");
    getMe().then((u) => auth.updateUser(u)).catch(() => {});
  } catch (err: any) {
    const detail = err.response?.data?.detail || "";
    if (isInsufficientCreditsError(err)) {
      showInsufficientCreditsPurchase(detail);
      return;
    }
    message.error(detail || "提示词反推失败");
  } finally {
    reverseLoading.value = false;
  }
}

function copyReversePrompt() {
  if (!reversePromptResult.value.trim()) return;
  navigator.clipboard.writeText(reversePromptResult.value).then(() => {
    message.success("已复制提示词");
  });
}

function applyReversePrompt() {
  if (!reversePromptResult.value.trim()) return;
  prompt.value = reversePromptResult.value;
  generateMode.value = "textGenerate";
  message.success("已带入到文生图");
}

function promptSwitchToTextGenerate(messageText: string) {
  Modal.confirm({
    title: "当前为图编辑",
    content: messageText,
    centered: true,
    okText: "去文生图",
    cancelText: "取消",
    onOk: () => {
      generateMode.value = "textGenerate";
    },
  });
}

async function handleGenerate() {
  if (generateMode.value === "smartCutout") return;
  if (isImageEditMode.value && hasPendingReferenceUploads.value) {
    message.warning("参考图仍在上传中，请稍候再发起任务");
    return;
  }
  if (isImageEditMode.value && hasFailedReferenceUploads.value) {
    message.warning("存在上传失败的参考图，请删除或重新上传后再试");
    return;
  }
  if (isImageEditMode.value && !referenceUrls.value.length) {
    promptSwitchToTextGenerate("图编辑必须先上传参考图。若你现在没有参考图，请切换到文生图发起任务。");
    return;
  }
  if (!activePrompt.value.trim() && !hasSelectedGenerateStyles.value) {
    message.warning("请输入提示词");
    return;
  }
  if (supportsCustomSize.value && !validateCustomSizeInput()) return;
  if (!auth.isLoggedIn) {
    loginModalVisible.value = true;
    return;
  }

  submittingGenerate.value = true;
  await nextTick();
  try {
    const [authenticated] = await Promise.all([
      ensureAuthenticated(),
      loadGlobalActiveGenerationStatus(),
    ]);
    if (!authenticated) return;
    const availableSlots = remainingGenerationImageSlots.value;
    if (availableSlots <= 0) {
      message.warning(`当前最多允许同时生成 ${MAX_ACTIVE_GENERATION_IMAGES} 张图片，请等待部分任务完成后再试`);
      return;
    }
    if (!isSuperAdmin.value && userCredits.value < actualSubmitCreditCost.value) {
      showInsufficientCreditsPurchase(`积分不足，需要 ${actualSubmitCreditCost.value} 积分，当前余额 ${userCredits.value}`);
      return;
    }

    const submitPrompt = buildSubmitPrompt(activePrompt.value);
    if (!submitPrompt) return;

    let payload: GenerateTaskPayload;
    let requestedImageCount = 1;

    if (generateMode.value === "inpaint") {
      if (!sourceImageUrl.value.trim()) {
        message.warning(sourceUploading.value ? "原图上传中，请稍候再试" : "请先上传需要局部重绘的原图");
        return;
      }
      if (!hasRepaintMask.value || !repaintCanvasRef.value?.hasDrawnMask()) {
        message.warning("请先在原图上涂抹需要重绘的区域");
        return;
      }
      const maskBlob = await repaintCanvasRef.value.exportMaskBlob();
      if (!maskBlob) {
        message.warning("蒙版生成失败，请重新涂抹后再试");
        return;
      }
      const maskFile = new File([maskBlob], `mask-${Date.now()}.png`, { type: "image/png" });
      let maskUploadUrl = "";
      try {
        const { uploadReferenceImage } = await import("@/api/upload");
        const uploaded = await uploadReferenceImage(maskFile, "mask");
        maskUploadUrl = uploaded.url;
      } catch {
        message.error("蒙版上传失败，请重试");
        return;
      }
      payload = {
        mode: "inpaint",
        prompt: submitPrompt,
        num_images: 1,
        size: size.value,
        resolution: resolution.value,
        custom_size: "",
        source_image: sourceImageUrl.value,
        mask_image: maskUploadUrl,
      };
    } else {
      requestedImageCount = Math.min(numImages.value, availableSlots);
      payload = {
        mode: "generate",
        model: selectedModel.value,
        prompt: submitPrompt,
        num_images: requestedImageCount,
        size: customSizeEnabled.value || hideAspectRatio.value ? "" : size.value,
        resolution: customSizeEnabled.value || hideResolution.value ? "" : resolution.value,
        custom_size: customSizeEnabled.value ? customSize.value : "",
        reference_images: isImageEditMode.value && referenceUrls.value.length ? referenceUrls.value : undefined,
      };
      if (requestedImageCount < numImages.value) {
        message.info(`当前剩余 ${requestedImageCount} 个生成名额，已自动发起 ${requestedImageCount} 个任务`);
      }
    }

    const submitMode: SubmitMode = generateMode.value === "imageEdit"
      ? "imageEdit"
      : generateMode.value === "textGenerate"
        ? "textGenerate"
        : "inpaint";
    await submitGeneratedTask(payload, {
      mode: submitMode,
      prompt: submitPrompt,
      model: payload.model,
      numImages: payload.num_images,
      size: payload.size,
      resolution: payload.resolution,
      customSize: payload.custom_size || "",
      referenceImages: payload.reference_images ? [...payload.reference_images] : [],
      referenceImageThumbs: payload.reference_images ? [...payload.reference_images] : [],
      sourceImage: payload.source_image || payload.reference_images?.[0],
      sourceImageThumb: payload.source_image || payload.reference_images?.[0],
      maskImage: payload.mask_image || payload.reference_images?.[1],
      maskImageThumb: payload.mask_image || payload.reference_images?.[1],
    });
    void loadGlobalActiveGenerationStatus();
  } catch (err: any) {
    const detail = extractApiErrorDetail(err);
    if (isInsufficientCreditsError(err)) {
      showInsufficientCreditsPurchase(detail);
      return;
    }
    message.error(formatGenerationErrorMessage(detail, "创建任务失败"));
  } finally {
    submittingGenerate.value = false;
  }
}

function applySmartCutoutSource(sourceUrl: string, maskUrl = "", promptText = "") {
  if (smartCutoutPanelRef.value) {
    smartCutoutPanelRef.value.applySource(sourceUrl, maskUrl, promptText);
    pendingSmartCutoutApply.value = null;
    return;
  }
  pendingSmartCutoutApply.value = { sourceUrl, maskUrl, prompt: promptText };
}

async function handleSmartCutoutSubmit(payload: { prompt: string; sourceImageUrl: string; maskImageUrl: string }) {
  if (!auth.isLoggedIn) {
    loginModalVisible.value = true;
    return;
  }

  submittingGenerate.value = true;
  await nextTick();
  try {
    const [authenticated] = await Promise.all([
      ensureAuthenticated(),
      loadGlobalActiveGenerationStatus(),
    ]);
    if (!authenticated) return;
    if (remainingGenerationImageSlots.value <= 0) {
      message.warning(`当前最多允许同时生成 ${MAX_ACTIVE_GENERATION_IMAGES} 张图片，请等待部分任务完成后再试`);
      return;
    }
    if (!isSuperAdmin.value && userCredits.value < smartCutoutCreditCost.value) {
      showInsufficientCreditsPurchase(`积分不足，需要 ${smartCutoutCreditCost.value} 积分，当前余额 ${userCredits.value}`);
      return;
    }

    if (supportsCustomSize.value && !validateCustomSizeInput()) return;
    const submitPrompt = payload.prompt.trim() || "智能抠图";
    const referenceImages = [payload.sourceImageUrl, payload.maskImageUrl].filter(Boolean);
    const taskPayload: GenerateTaskPayload = {
      mode: "smart_cutout",
      prompt: submitPrompt,
      num_images: 1,
      size: customSizeEnabled.value || !!smartCutoutScene.value?.hide_aspect_ratio ? "" : size.value,
      resolution: customSizeEnabled.value || !!smartCutoutScene.value?.hide_resolution ? "" : resolution.value,
      custom_size: customSizeEnabled.value ? customSize.value : "",
      reference_images: referenceImages.length ? referenceImages : undefined,
    };
    await submitGeneratedTask(taskPayload, {
      mode: "smartCutout",
      prompt: submitPrompt,
      model: taskPayload.model,
      numImages: 1,
      size: taskPayload.size,
      resolution: taskPayload.resolution,
      customSize: taskPayload.custom_size || "",
      referenceImages,
      referenceImageThumbs: [...referenceImages],
      sourceImage: payload.sourceImageUrl || undefined,
      sourceImageThumb: payload.sourceImageUrl || undefined,
      maskImage: payload.maskImageUrl || undefined,
      maskImageThumb: payload.maskImageUrl || undefined,
    });
    void loadGlobalActiveGenerationStatus();
  } catch (err: any) {
    const detail = extractApiErrorDetail(err);
    if (isInsufficientCreditsError(err)) {
      showInsufficientCreditsPurchase(detail);
      return;
    }
    message.error(formatGenerationErrorMessage(detail, "创建任务失败"));
  } finally {
    submittingGenerate.value = false;
  }
}

function handleReeditTask(task: GeneratedTaskItem) {
  expandConfigPanelForEditing();
  generateMode.value = task.mode;
  size.value = task.size || sizeOptions.value[0]?.value || "1:1";
  resolution.value = task.resolution || "2K";

  if (task.mode === "inpaint") {
    applyPromptWithGenerateStyles(task.prompt, "repaintPrompt");
    prompt.value = "";
    syncReferenceItems([]);
    revokeObjectUrl(sourcePreviewUrl.value);
    sourcePreviewUrl.value = "";
    sourceImageUrl.value = task.sourceImage || task.referenceImages[0] || "";
    repaintMaskUrl.value = task.maskImage || task.referenceImages[1] || "";
    hasRepaintMask.value = false;
    canUndoMask.value = false;
    canRedoMask.value = false;
  } else if (task.mode === "smartCutout") {
    prompt.value = "";
    repaintPrompt.value = "";
    syncReferenceItems([]);
    applySmartCutoutSource(
      task.sourceImage || task.referenceImages[0] || "",
      task.maskImage || task.referenceImages[1] || "",
      task.prompt || "",
    );
  } else {
    generateMode.value = task.referenceImages.length ? "imageEdit" : "textGenerate";
    applyPromptWithGenerateStyles(task.prompt, "prompt");
    repaintPrompt.value = "";
    if (task.model) selectedModel.value = task.model;
    numImages.value = Math.min(MAX_ACTIVE_GENERATION_IMAGES, Math.max(1, Number(task.numImages || 1)));
    syncReferenceItems(task.referenceImages);
    revokeObjectUrl(sourcePreviewUrl.value);
    sourcePreviewUrl.value = "";
    sourceImageUrl.value = "";
    repaintMaskUrl.value = "";
    hasRepaintMask.value = false;
    canUndoMask.value = false;
    canRedoMask.value = false;
    repaintCanvasRef.value?.clearMask();
  }
  refillCustomSizeFromValue(task.customSize);
  message.success("已回填到编辑区");
}

function handleEditImageTask(task: GeneratedTaskItem, image: ImageResult) {
  const referenceImage = image.image_url || image.preview_url || "";
  if (!referenceImage) {
    message.warning("当前结果图暂不可用于图编辑");
    return;
  }
  expandConfigPanelForEditing();
  generateMode.value = "imageEdit";
  applyPromptWithGenerateStyles(task.prompt, "prompt");
  repaintPrompt.value = "";
  size.value = task.size || sizeOptions.value[0]?.value || "1:1";
  resolution.value = task.resolution || "2K";
  refillCustomSizeFromValue(task.customSize);
  numImages.value = Math.min(MAX_ACTIVE_GENERATION_IMAGES, Math.max(1, Number(task.numImages || 1)));
  syncReferenceItems([referenceImage]);
  revokeObjectUrl(sourcePreviewUrl.value);
  sourcePreviewUrl.value = "";
  sourceImageUrl.value = "";
  repaintMaskUrl.value = "";
  reverseImageUrl.value = "";
  reversePromptResult.value = "";
  hasRepaintMask.value = false;
  canUndoMask.value = false;
  canRedoMask.value = false;
  repaintCanvasRef.value?.clearMask();
  window.scrollTo({ top: 0, behavior: "smooth" });
  message.success("已切换到图编辑，并载入当前结果图");
}

async function handleRegenerate(task: GeneratedTaskItem) {
  const smartCutoutRefs = [
    task.referenceImages[0] || task.sourceImage || "",
    task.referenceImages[1] || task.maskImage || "",
  ].filter(Boolean);
  const payload: GenerateTaskPayload = task.mode === "inpaint"
    ? {
        mode: "inpaint",
        prompt: task.prompt,
        num_images: 1,
        size: task.size,
        resolution: task.resolution,
        custom_size: "",
        source_image: task.sourceImage,
        mask_image: task.maskImage,
      }
    : task.mode === "smartCutout"
      ? {
        mode: "smart_cutout",
        prompt: task.prompt || "智能抠图",
        num_images: 1,
        size: task.size,
        resolution: task.resolution,
        custom_size: task.customSize || "",
        reference_images: smartCutoutRefs,
      }
    : {
        mode: "generate",
        model: task.model,
        prompt: task.prompt,
        num_images: 1,
        size: task.size,
        resolution: task.resolution,
        custom_size: task.customSize,
        reference_images: task.referenceImages.length ? task.referenceImages : undefined,
      };

  if (task.mode === "inpaint" && (!task.sourceImage || !task.maskImage)) {
    message.warning("当前局部重绘任务缺少完整参数，请使用重新编辑后再提交");
    return;
  }
  if (task.mode === "smartCutout" && smartCutoutRefs.length > 2) {
    message.warning("当前智能抠图任务参数异常，请使用重新编辑后再提交");
    return;
  }
  const regenerateCost = getTaskDraftCreditCost(task, 1);
  if (!isSuperAdmin.value && userCredits.value < regenerateCost) {
    showInsufficientCreditsPurchase(`积分不足，需要 ${regenerateCost} 积分，当前余额 ${userCredits.value}`);
    return;
  }
  try {
    await submitGeneratedTask(payload, {
      mode: task.mode,
      prompt: task.prompt,
      model: task.model,
      numImages: 1,
      size: task.size,
      resolution: task.resolution,
      customSize: task.customSize,
      referenceImages: [...task.referenceImages],
      referenceImageThumbs: task.referenceImageThumbs.length ? [...task.referenceImageThumbs] : [...task.referenceImages],
      sourceImage: task.sourceImage,
      sourceImageThumb: task.sourceImageThumb || task.sourceImage,
      maskImage: task.maskImage,
      maskImageThumb: task.maskImageThumb || task.maskImage,
    });
    message.success("已发起新的生图任务");
  } catch (err: any) {
    const detail = err.response?.data?.detail || "";
    if (isInsufficientCreditsError(err)) {
      showInsufficientCreditsPurchase(detail);
      return;
    }
    message.error(formatGenerationErrorMessage(detail, "重新生成失败"));
  }
}

function handlePreview(url: string) {
  previewCurrent.value = url;
  previewVisible.value = true;
  if (!url) {
    previewImageLoading.value = false;
    return;
  }
  previewImageLoading.value = true;
  const loader = new Image();
  loader.onload = () => {
    if (previewCurrent.value !== url) return;
    previewImageLoading.value = false;
  };
  loader.onerror = () => {
    if (previewCurrent.value !== url) return;
    previewImageLoading.value = false;
  };
  loader.src = url;
  if (loader.complete && loader.naturalWidth > 0) {
    previewImageLoading.value = false;
  }
}

function convertGeneratedTaskToHistoryCard(task: GeneratedTaskItem, focusedImage?: ImageResult): UserHistoryCard {
  const primaryImage = focusedImage
    || task.images.find((image) => image.status === "success")
    || task.images[0];
  const taskType = task.mode === "inpaint"
    ? "inpaint"
    : task.mode === "smartCutout"
      ? "smart_cutout"
    : task.referenceImages.length
      ? "image_edit"
      : "text_generate";
  const mode = task.mode === "inpaint"
    ? "inpaint"
    : task.mode === "smartCutout"
      ? "smart_cutout"
      : "generate";
  const status = task.status === "submitting" ? "pending" : task.status;

  return {
    item_type: "task",
    display_id: task.taskId || task.localId,
    task_id: task.taskId,
    image_id: typeof primaryImage?.id === "number" && primaryImage.id > 0 ? primaryImage.id : null,
    is_pinned: false,
    image_url: primaryImage?.image_url || "",
    preview_url: primaryImage?.preview_url,
    thumb_url: primaryImage?.thumb_url,
    status,
    image_format: primaryImage?.image_format,
    image_size_bytes: primaryImage?.image_size_bytes,
    task_type: taskType,
    model: task.model || "",
    source: "web",
    mode,
    prompt: task.prompt || "",
    reference_images: [...task.referenceImages],
    reference_image_thumbs: task.referenceImageThumbs.length
      ? [...task.referenceImageThumbs]
      : [...task.referenceImages],
    source_image: task.sourceImage || "",
    source_image_thumb: task.sourceImageThumb || task.sourceImage || "",
    mask_image: task.maskImage || "",
    mask_image_thumb: task.maskImageThumb || task.maskImage || "",
    num_images: task.numImages,
    size: task.size || "",
    resolution: task.resolution || "",
    custom_size: task.customSize || "",
    credit_cost: getTaskDraftCreditCost(task),
    credit_refunded: Boolean(task.creditRefunded),
    used_fallback_api: Boolean(task.usedFallbackApi),
    created_at: task.createdAt,
    error_message: task.errorMessage || "",
    provider_error_message: task.providerErrorMessage || "",
    images: task.images.length ? task.images : [],
    api_attempts: task.apiAttempts || [],
  };
}

const detailImageIndex = ref(0);

function openGeneratedTaskDetail(task: GeneratedTaskItem, focusedImage?: ImageResult) {
  detailTaskLocalId.value = task.localId;
  const focusedIndex = focusedImage
    ? task.images.findIndex((image) => (
      image === focusedImage
      || (typeof image.id === "number" && image.id > 0 && image.id === focusedImage.id)
    ))
    : 0;
  detailImageIndex.value = focusedIndex >= 0 ? focusedIndex : 0;
  detailPreloadedMediaKeys.value = getDetailPreloadedMediaKeys(task, focusedImage);
  detailItem.value = convertGeneratedTaskToHistoryCard(task, focusedImage);
  detailOpen.value = true;
}

const detailResultIndex = computed(() => {
  if (!detailOpen.value || !detailTaskLocalId.value) return -1;
  return resultItems.value.findIndex((item) => (
    item.taskLocalId === detailTaskLocalId.value
    && item.index === detailImageIndex.value
  ));
});

const hasDetailPrev = computed(() => detailResultIndex.value > 0);
const hasDetailNext = computed(() => (
  detailResultIndex.value >= 0
  && detailResultIndex.value < resultItems.value.length - 1
));

function navigateGeneratedTaskDetail(delta: -1 | 1) {
  const nextIndex = detailResultIndex.value + delta;
  const nextItem = resultItems.value[nextIndex];
  if (!nextItem) return;
  openGeneratedTaskDetail(nextItem.task, nextItem.image);
}

function handleDetailReedit(item: UserHistoryCard) {
  const task = generatedTasks.value.find((entry) => (
    entry.localId === detailTaskLocalId.value
    || (!!item.task_id && entry.taskId === item.task_id)
  ));
  detailOpen.value = false;
  if (task) {
    handleReeditTask(task);
    return;
  }
  handleReeditTask({
    localId: detailTaskLocalId.value || `detail-${item.task_id || "unknown"}`,
    taskId: item.task_id || null,
    mode: item.mode === "inpaint"
      ? "inpaint"
      : item.mode === "smart_cutout"
        ? "smartCutout"
        : (item.reference_images.length ? "imageEdit" : "textGenerate"),
    prompt: item.prompt || "",
    model: item.model || undefined,
    numImages: Math.max(1, Number(item.num_images || 1)),
    size: item.size || "1:1",
    resolution: item.resolution || "2K",
    customSize: item.custom_size || "",
    referenceImages: [...(item.reference_images || [])],
    referenceImageThumbs: item.reference_image_thumbs?.length
      ? [...item.reference_image_thumbs]
      : [...(item.reference_images || [])],
    sourceImage: item.source_image || undefined,
    sourceImageThumb: item.source_image_thumb || item.source_image || undefined,
    maskImage: item.mask_image || undefined,
    maskImageThumb: item.mask_image_thumb || item.mask_image || undefined,
    createdAt: item.created_at,
    status: item.status,
    errorMessage: item.error_message || "",
    creditRefunded: Boolean(item.credit_refunded),
    images: item.images || [],
  });
}

function handleDetailDownload(item: UserHistoryCard) {
  if (typeof item.image_id !== "number" || !item.image_url) return;
  handleDownload(item.image_id, item.image_url, item.preview_url);
}

function openFeedbackDialogForGeneratedTask(task: GeneratedTaskItem) {
  if (!task.taskId) {
    message.warning("当前任务尚未生成完成，暂时无法提交反馈");
    return;
  }
  feedbackTarget.value = {
    taskId: task.taskId,
    model: task.model,
    prompt: task.prompt,
    createdAt: task.createdAt,
  };
  feedbackDialogOpen.value = true;
}

function getResultDisplayUrl(img: ImageResult) {
  return getDisplayImageUrl(img);
}

function getGeneratedResultMediaState(task: GeneratedTaskItem, img: ImageResult, index: number) {
  const key = getGeneratedResultMediaLoadKey(task, img, index);
  return generatedResultImageLoad.getState(key);
}

function getGeneratedHdWebpUrl(img: ImageResult) {
  return getPreviewImageUrl({
    image_url: img.image_url || "",
    preview_url: img.preview_url || "",
    thumb_url: "",
  });
}

function canViewGeneratedHdImage(task: GeneratedTaskItem, img: ImageResult) {
  return img.status === "success" && !isGeneratedTaskExpired(task) && !!getGeneratedHdWebpUrl(img);
}

function handleViewGeneratedHdImage(task: GeneratedTaskItem, img: ImageResult, index: number) {
  if (!canViewGeneratedHdImage(task, img)) {
    message.warning(isGeneratedTaskExpired(task) ? "原图已过期，无法查看高清图" : "当前结果图暂无高清图");
    return;
  }
  const hdUrl = getGeneratedHdWebpUrl(img);
  const key = getGeneratedResultMediaLoadKey(task, img, index);
  if (!hdPreviewRequestedKeys.value.has(key)) {
    const next = new Set(hdPreviewRequestedKeys.value);
    next.add(key);
    hdPreviewRequestedKeys.value = next;
  }
  handlePreview(hdUrl);
  if (hdPreviewLoadedKeys.value.has(key)) return;
  const loader = new Image();
  loader.onload = () => {
    if (hdPreviewLoadedKeys.value.has(key)) return;
    const nextLoaded = new Set(hdPreviewLoadedKeys.value);
    nextLoaded.add(key);
    hdPreviewLoadedKeys.value = nextLoaded;
    if (previewCurrent.value === hdUrl) {
      previewImageLoading.value = false;
    }
  };
  loader.src = hdUrl;
}

function isGeneratedResultMoreExpanded(item: { taskLocalId: string; index: number; image: { id: number; status: string } }) {
  return expandedResultMoreKeys.value.has(getResultItemKey(item));
}

function toggleGeneratedResultMore(item: { taskLocalId: string; index: number; image: { id: number; status: string } }) {
  const key = getResultItemKey(item);
  const next = new Set(expandedResultMoreKeys.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedResultMoreKeys.value = next;
}

function collapseGeneratedResultMore(item: { taskLocalId: string; index: number; image: { id: number; status: string } }) {
  const key = getResultItemKey(item);
  if (expandedResultMoreKeys.value.has(key)) {
    const next = new Set(expandedResultMoreKeys.value);
    next.delete(key);
    expandedResultMoreKeys.value = next;
  }
  const active = document.activeElement;
  if (active instanceof HTMLElement && active.closest(".result-card")) {
    active.blur();
  }
}

function hasGeneratedMoreActions(task: GeneratedTaskItem, img: ImageResult) {
  return canGenerateVideoFromGeneratedImage(task, img)
    || canEditGeneratedImage(task, img)
    || canInpaintGeneratedImage(task, img);
}

function getGeneratedResultDisplayUrl(task: GeneratedTaskItem, img: ImageResult, index: number) {
  if (img.status !== "success") return getResultDisplayUrl(img);
  if (isGeneratedTaskExpired(task)) return expiredResultAsset.value;
  if (shouldShowGeneratedLargeImagePreviewNotice(task, img, index)) return "";
  const displayUrl = getResultDisplayUrl(img);
  if (!displayUrl) return "";
  const state = getGeneratedResultMediaState(task, img, index);
  return appendTransientImageNonce(displayUrl, state.nonce);
}

function shouldShowGeneratedLargeImagePreviewNotice(task: GeneratedTaskItem, img: ImageResult, index = 0) {
  return img.status === "success" && !isGeneratedTaskExpired(task) && exceedsRealtimeImagePreviewLimit(img.image_size_bytes);
}

function getGeneratedResultMediaLoadKey(task: GeneratedTaskItem, img: ImageResult, index: number) {
  return `generated-result:${task.localId}:${img.id}:${index}`;
}

function markGeneratedResultMediaLoaded(task: GeneratedTaskItem, img: ImageResult, index: number) {
  const key = getGeneratedResultMediaLoadKey(task, img, index);
  generatedResultImageLoad.markLoaded(key, getResultDisplayUrl(img));
  if (loadedResultMediaKeys.value.has(key)) return;
  const next = new Set(loadedResultMediaKeys.value);
  next.add(key);
  loadedResultMediaKeys.value = next;
}

function handleGeneratedResultMediaError(task: GeneratedTaskItem, img: ImageResult, index: number) {
  if (img.status !== "success" || isGeneratedTaskExpired(task)) return;
  if (shouldShowGeneratedLargeImagePreviewNotice(task, img, index)) return;
  const source = getResultDisplayUrl(img);
  if (!source) return;
  const key = getGeneratedResultMediaLoadKey(task, img, index);
  generatedResultImageLoad.scheduleRetry(key, source);
}

function shouldShowGeneratedUploadingState(task: GeneratedTaskItem, img: ImageResult, index: number) {
  if (img.status !== "success") return false;
  if (isGeneratedTaskExpired(task)) return false;
  if (shouldShowGeneratedLargeImagePreviewNotice(task, img, index)) return false;
  const source = getResultDisplayUrl(img);
  if (!source) return true;
  return getGeneratedResultMediaState(task, img, index).phase === "retrying";
}

function shouldShowGeneratedLoadFailedState(task: GeneratedTaskItem, img: ImageResult, index: number) {
  if (img.status !== "success") return false;
  if (isGeneratedTaskExpired(task)) return false;
  if (shouldShowGeneratedLargeImagePreviewNotice(task, img, index)) return false;
  const source = getResultDisplayUrl(img);
  if (!source) return false;
  return getGeneratedResultMediaState(task, img, index).phase === "failed";
}

function shouldRenderGeneratedResultImage(task: GeneratedTaskItem, img: ImageResult, index: number) {
  if (img.status !== "success") return false;
  const displayUrl = getGeneratedResultDisplayUrl(task, img, index);
  if (!displayUrl) return false;
  const phase = getGeneratedResultMediaState(task, img, index).phase;
  return phase !== "retrying" && phase !== "failed";
}

function getDetailPreloadedMediaKeys(task: GeneratedTaskItem, focusedImage?: ImageResult) {
  const targetIndex = focusedImage
    ? task.images.findIndex((image) => (
      image === focusedImage || (typeof image.id === "number" && image.id > 0 && image.id === focusedImage.id)
    ))
    : task.images.findIndex((image) => image.status === "success");
  const normalizedIndex = targetIndex >= 0 ? targetIndex : 0;
  const targetImage = focusedImage || task.images[normalizedIndex];
  if (!targetImage) return [];
  if (typeof targetImage.id !== "number" || targetImage.id <= 0) return [];
  const cardKey = getGeneratedResultMediaLoadKey(task, targetImage, normalizedIndex);
  const keys: string[] = [];
  if (hdPreviewLoadedKeys.value.has(cardKey)) {
    keys.push(`detail-result-enhanced:${String(targetImage.id)}`);
  }
  if (loadedResultMediaKeys.value.has(cardKey) && !hdPreviewLoadedKeys.value.has(cardKey)) {
    keys.push(`detail-result-base:${String(targetImage.id)}`);
  }
  return keys;
}

function canEditGeneratedImage(task: GeneratedTaskItem, img: ImageResult) {
  return img.status === "success" && !isGeneratedTaskExpired(task) && !!(img.image_url || img.preview_url);
}

function canInpaintGeneratedImage(task: GeneratedTaskItem, img: ImageResult) {
  return canEditGeneratedImage(task, img) && !!(img.image_url || img.preview_url || img.thumb_url);
}

function canGenerateVideoFromGeneratedImage(task: GeneratedTaskItem, img: ImageResult) {
  return canEditGeneratedImage(task, img) && !!(img.image_url || img.preview_url || img.thumb_url);
}

function handleGenerateVideoFromGeneratedImage(task: GeneratedTaskItem, img: ImageResult) {
  const referenceImage = img.image_url || img.preview_url || img.thumb_url || "";
  if (!referenceImage) {
    message.warning("当前结果图暂不可用于生成视频");
    return;
  }
  if (!saveImageToVideoDraft({ referenceImage, prompt: task.prompt || "" })) {
    message.warning("当前结果图暂不可用于生成视频");
    return;
  }
  router.push("/video-generate");
}

function handleInpaintGeneratedImage(task: GeneratedTaskItem, img: ImageResult) {
  const sourceImage = img.image_url || img.preview_url || img.thumb_url || "";
  if (!sourceImage) {
    message.warning("当前结果图暂不可用于局部重绘");
    return;
  }
  expandConfigPanelForEditing();
  generateMode.value = "inpaint";
  repaintPrompt.value = task.prompt || "";
  prompt.value = "";
  size.value = task.size || sizeOptions.value[0]?.value || "1:1";
  resolution.value = task.resolution || "2K";
  refillCustomSizeFromValue(task.customSize);
  numImages.value = 1;
  syncReferenceItems([]);
  revokeObjectUrl(sourcePreviewUrl.value);
  sourcePreviewUrl.value = "";
  sourceImageUrl.value = sourceImage;
  repaintMaskUrl.value = "";
  hasRepaintMask.value = false;
  canUndoMask.value = false;
  canRedoMask.value = false;
  repaintCanvasRef.value?.clearMask();
  message.success("已带入局部重绘");
}

function handleSmartCutoutGeneratedImage(task: GeneratedTaskItem, img: ImageResult) {
  const sourceImage = img.image_url || img.preview_url || img.thumb_url || "";
  if (!sourceImage) {
    message.warning("当前结果图暂不可用于智能抠图");
    return;
  }
  expandConfigPanelForEditing();
  generateMode.value = "smartCutout";
  prompt.value = "";
  repaintPrompt.value = "";
  size.value = task.size || sizeOptions.value[0]?.value || "1:1";
  resolution.value = task.resolution || "2K";
  refillCustomSizeFromValue(task.customSize);
  numImages.value = 1;
  syncReferenceItems([]);
  applySmartCutoutSource(sourceImage);
  message.success("已带入智能抠图");
}

function openSmartCutoutFromImageEdit() {
  const firstReference = firstReferenceItem.value;
  const firstReferenceUrl = firstReference?.remoteUrl?.trim() || "";
  expandConfigPanelForEditing();
  generateMode.value = "smartCutout";
  prompt.value = "";
  repaintPrompt.value = "";
  numImages.value = 1;
  syncReferenceItems([]);

  if (!firstReference) {
    applySmartCutoutSource("");
    message.success("已切换到智能抠图");
    return;
  }

  if (firstReference.status === "success" && firstReferenceUrl) {
    applySmartCutoutSource(firstReferenceUrl);
    message.success("已带第一张目标图进入智能抠图");
    return;
  }

  applySmartCutoutSource("");
  message.warning(
    firstReference.status === "uploading"
      ? "已切换到智能抠图，第一张目标图仍在上传中，未自动带入"
      : "已切换到智能抠图，第一张目标图上传失败，未自动带入",
  );
}

async function ensureTemplateTagsLoaded() {
  if (templateTags.value.length) return;
  try {
    templateTags.value = await listTemplateTags();
  } catch {
    templateTags.value = [];
  }
}

async function openTemplateDialogFromGeneratedImage(task: GeneratedTaskItem, img: ImageResult) {
  if (!canCreateTemplateFromTask.value) return;
  if (img.status !== "success" || !img.id) {
    message.warning("当前结果图暂不可创建模版");
    return;
  }
  if (isGeneratedTaskExpired(task)) {
    message.warning("原图已过期，无法重新上传为模版");
    return;
  }
  await ensureTemplateTagsLoaded();
  templateSourceImageId.value = img.id;
  templateInitialValue.value = {
    prompt: task.prompt || "",
    model: task.model || templateModelOptions.value[0]?.model_key || "banana_pro",
    reference_images: [...task.referenceImages],
    num_images: 1,
    size: task.size || "1:1",
    resolution: task.resolution || "2K",
    custom_size: task.customSize || "",
    result_image: img.image_url || img.preview_url || "",
    sort_order: 0,
    tag_names: [],
  };
  templateDialogOpen.value = true;
}

async function handleSaveGeneratedTemplate(payload: TemplatePayload) {
  if (!templateSourceImageId.value) return;
  templateDialogSaving.value = true;
  try {
    const template = await createTemplateFromTaskImage(templateSourceImageId.value, payload);
    message.success(`已创建模版 #${template.id}`);
    templateDialogOpen.value = false;
    templateSourceImageId.value = null;
    templateInitialValue.value = null;
    templateTags.value = await listTemplateTags();
  } catch (err: any) {
    const detail = err?.response?.data?.detail || "创建模版失败";
    message.error(detail);
  } finally {
    templateDialogSaving.value = false;
  }
}

function handleDownload(imageId: number, imageUrl: string, previewUrl?: string) {
  const a = document.createElement("a");
  a.href = getDownloadUrl(imageId, imageUrl, previewUrl);
  a.download = `banana_${imageId}.png`;
  a.click();
}

async function openPromptLibrary() {
  if (!ensureLoggedIn()) return;
  promptLibraryVisible.value = true;
}

async function removeGeneratedTask(task: GeneratedTaskItem) {
  if (!task.taskId) {
    generatedTasks.value = generatedTasks.value.filter((item) => item.localId !== task.localId);
    if (detailTaskLocalId.value === task.localId) {
      detailOpen.value = false;
      detailItem.value = null;
      detailTaskLocalId.value = null;
    }
    stopAllTaskPolling();
    if (activePollingTaskIds.value.length) startTaskPolling();
    message.success("已移除当前任务卡片");
    return;
  }

  try {
    await deleteHistoryTask(task.taskId);
    generatedTasks.value = generatedTasks.value.filter((item) => item.taskId !== task.taskId);
    if (
      detailTaskLocalId.value === task.localId
      || (detailItem.value?.task_id && detailItem.value.task_id === task.taskId)
    ) {
      detailOpen.value = false;
      detailItem.value = null;
      detailTaskLocalId.value = null;
    }
    stopAllTaskPolling();
    if (activePollingTaskIds.value.length) startTaskPolling();
    await loadRecentGeneratedTasks();
    message.success("删除成功");
  } catch {
    message.error("删除失败");
  }
}

function confirmRemoveGeneratedTask(task: GeneratedTaskItem) {
  const isLocalOnly = !task.taskId;
  const isGenerating = task.status === "submitting" || task.status === "pending" || task.status === "queued" || task.status === "processing";

  Modal.confirm({
    title: isLocalOnly ? "确认移除这张任务卡片？" : "确认删除这个任务？",
    content: isLocalOnly
      ? "这会从当前页面移除该本地任务卡片，不影响服务器中的其他记录。"
      : isGenerating
        ? "删除后会移除该任务及其当前结果，历史记录中的对应任务也会一并删除。"
        : "删除后会移除该任务及其结果图，历史记录中的对应任务也会一并删除。",
    centered: true,
    async onOk() {
      await removeGeneratedTask(task);
    },
  });
}

function useLibraryPrompt(item: UserPrompt) {
  const content = (item.content || "").trim();
  if (!content) {
    message.warning("该提示词内容为空");
    return;
  }
  applyPromptWithGenerateStyles(
    content,
    generateMode.value === "inpaint" ? "repaintPrompt" : "prompt",
  );
  message.success("已回填到编辑区");
}

function applyDraft(raw: string | null, successText: string, storageKey: string) {
  if (!raw) return;
  try {
    const draft = JSON.parse(raw) as {
      mode?: "generate" | "imageEdit" | "textGenerate" | "inpaint" | "smartCutout" | "smart_cutout" | "promptReverse";
      prompt?: string;
      model?: string;
      reference_images?: string[];
      num_images?: number;
      size?: string;
      resolution?: string;
      custom_size?: string;
      source_image?: string;
      mask_image?: string;
    };
    const draftMode: GenerateMode = draft.mode === "inpaint"
      ? "inpaint"
      : draft.mode === "smartCutout" || draft.mode === "smart_cutout"
        ? "smartCutout"
      : draft.mode === "promptReverse"
        ? "promptReverse"
        : draft.mode === "imageEdit"
          ? "imageEdit"
          : draft.mode === "textGenerate"
            ? "textGenerate"
            : Array.isArray(draft.reference_images) && draft.reference_images.length
              ? "imageEdit"
              : "textGenerate";
    generateMode.value = draftMode;
    size.value = draft.size || sizeOptions.value[0]?.value || "1:1";
    resolution.value = draft.resolution || "2K";

    if (draftMode === "inpaint") {
      applyPromptWithGenerateStyles(draft.prompt || "", "repaintPrompt");
      revokeObjectUrl(sourcePreviewUrl.value);
      sourceImageUrl.value = draft.source_image || draft.reference_images?.[0] || "";
      sourcePreviewUrl.value = "";
      repaintMaskUrl.value = draft.mask_image || draft.reference_images?.[1] || "";
      hasRepaintMask.value = false;
      canUndoMask.value = false;
      canRedoMask.value = false;
      prompt.value = "";
      syncReferenceItems([]);
      numImages.value = 1;
      reverseImageUrl.value = "";
      reversePromptResult.value = "";
    } else if (draftMode === "smartCutout") {
      prompt.value = "";
      repaintPrompt.value = "";
      syncReferenceItems([]);
      numImages.value = 1;
      reverseImageUrl.value = "";
      reversePromptResult.value = "";
      applySmartCutoutSource(
        draft.source_image || draft.reference_images?.[0] || "",
        draft.mask_image || draft.reference_images?.[1] || "",
        draft.prompt || "",
      );
    } else if (draftMode === "promptReverse") {
      reverseImageUrl.value = draft.source_image || "";
      reversePromptResult.value = draft.prompt || "";
      prompt.value = "";
      repaintPrompt.value = "";
      syncReferenceItems([]);
      revokeObjectUrl(sourcePreviewUrl.value);
      sourcePreviewUrl.value = "";
      sourceImageUrl.value = "";
      repaintMaskUrl.value = "";
      hasRepaintMask.value = false;
      canUndoMask.value = false;
      canRedoMask.value = false;
      numImages.value = 1;
    } else {
      applyPromptWithGenerateStyles(draft.prompt || "", "prompt");
      selectedModel.value = draft.model || selectedModel.value;
      syncReferenceItems(Array.isArray(draft.reference_images) ? draft.reference_images.slice(0, maxReferenceImages.value) : []);
      numImages.value = Math.min(MAX_ACTIVE_GENERATION_IMAGES, Math.max(1, Number(draft.num_images || 1)));
      repaintPrompt.value = "";
      revokeObjectUrl(sourcePreviewUrl.value);
      sourcePreviewUrl.value = "";
      sourceImageUrl.value = "";
      repaintMaskUrl.value = "";
      reverseImageUrl.value = "";
      reversePromptResult.value = "";
      hasRepaintMask.value = false;
      canUndoMask.value = false;
      canRedoMask.value = false;
      repaintCanvasRef.value?.clearMask();
    }
    refillCustomSizeFromValue(draft.custom_size);
    localStorage.removeItem(storageKey);
    message.success(successText);
  } catch {
    localStorage.removeItem(storageKey);
  }
}

async function loadTaskSceneConfigs() {
  try {
    taskScenes.value = await getTaskScenes();
  } catch {
    // ignore scene config loading failures, backend will still validate on submit
  } finally {
    sceneConfigLoading.value = false;
  }
}

onMounted(async () => {
  syncViewportWidth();
  window.addEventListener("resize", syncViewportWidth);
  window.addEventListener("focus", handleFilePickerFocusReturn);
  window.addEventListener("paste", handleReferencePaste);
  window.addEventListener(GENERATE_MENU_ENTRY_EVENT, handleGenerateMenuEntry);
  window.addEventListener(APPLY_CHAT_GENERATE_DRAFT_EVENT, handleChatGenerateDraft);
  window.addEventListener(CHAT_GENERATE_TASKS_CREATED_EVENT, handleChatGenerateTasksCreated);
  document.addEventListener("visibilitychange", handleDocumentVisibilityChange);
  await Promise.all([loadTaskSceneConfigs(), loadBoardsForGenerate()]);
  await Promise.all([loadRecentGeneratedTasks(), loadGlobalActiveGenerationStatus()]);
  applyDraft(
    localStorage.getItem(HISTORY_DRAFT_KEY),
    "已回填历史任务参数，可继续编辑后重新生成",
    HISTORY_DRAFT_KEY
  );
  applyDraft(
    localStorage.getItem(TEMPLATE_DRAFT_KEY),
    "已套用创意模版参数，可继续编辑后生成",
    TEMPLATE_DRAFT_KEY
  );
  applyDraft(
    localStorage.getItem(CHAT_DRAFT_KEY),
    "已从 AI 对话回填提示词，可继续编辑后生成",
    CHAT_DRAFT_KEY
  );
  applyRouteGenerateMode();
});

onActivated(async () => {
  await loadBoardsForGenerate();
  void loadRecentGeneratedTasks();
  void loadGlobalActiveGenerationStatus();
});

onBeforeUnmount(() => {
  cancelPromptOptimize();
  stopAllTaskPolling();
  stopGlobalActiveStatusPolling();
  generatedResultImageLoad.dispose();
  generatedTaskLoadMoreObserver?.disconnect();
  generatedTaskLoadMoreObserver = null;
  if (generatedTaskFilterDebounceTimer) {
    window.clearTimeout(generatedTaskFilterDebounceTimer);
    generatedTaskFilterDebounceTimer = null;
  }
  window.removeEventListener("resize", syncViewportWidth);
  window.removeEventListener("focus", handleFilePickerFocusReturn);
  window.removeEventListener("paste", handleReferencePaste);
  window.removeEventListener(GENERATE_MENU_ENTRY_EVENT, handleGenerateMenuEntry);
  window.removeEventListener(APPLY_CHAT_GENERATE_DRAFT_EVENT, handleChatGenerateDraft);
  window.removeEventListener(CHAT_GENERATE_TASKS_CREATED_EVENT, handleChatGenerateTasksCreated);
  document.removeEventListener("visibilitychange", handleDocumentVisibilityChange);
  clearFilePickerRecoveryTimer();
  unbindReferenceDragHandlers?.();
  unbindReferenceDragHandlers = null;
  referenceItems.value.forEach((item) => revokeObjectUrl(item.objectUrl));
  revokeObjectUrl(sourcePreviewUrl.value);
});

watch(generationModels, (models) => {
  if (!models.length) {
    selectedModel.value = "";
    return;
  }
  if (!models.some((item) => item.model_key === selectedModel.value)) {
    selectedModel.value = models[0].model_key;
  }
}, { immediate: true });

watch(generatedTaskLoadMoreAnchor, (target) => {
  setupGeneratedTaskLoadMoreObserver(target);
});

watch(isDesktopGeneratedTaskAutoLoad, (isDesktop) => {
  setupGeneratedTaskLoadMoreObserver(generatedTaskLoadMoreAnchor.value);
  if (!isDesktop) {
    isConfigPanelCollapsed.value = false;
  }
});

watch([
  generatedTaskHideExpiredFilter,
  generatedTaskHideFailedFilter,
  generatedTaskTypeFilter,
  generatedTaskSourceFilter,
  generatedTaskModelFilter,
  generatedTaskStatusFilter,
  generatedTaskPromptFilter,
  generatedTaskDateRangeFilter,
], () => {
  scheduleGeneratedTaskFilterReload();
});

watch(
  () => route.query.mode,
  () => {
    applyRouteGenerateMode();
  },
);

watch(smartCutoutPanelRef, (panel) => {
  if (!panel || !pendingSmartCutoutApply.value) return;
  const pending = pendingSmartCutoutApply.value;
  pendingSmartCutoutApply.value = null;
  panel.applySource(pending.sourceUrl, pending.maskUrl, pending.prompt);
});

watch(sizeOptions, (options) => {
  if (hideAspectRatio.value || !options.length) return;
  if (!size.value || !options.some((item) => item.value === size.value)) {
    size.value = options[0].value;
  }
}, { immediate: true });

watch(
  [() => generateMode.value, smartCutoutSizeOptions],
  ([mode, options]) => {
    if (mode !== "smartCutout" || !options.length) return;
    if (!size.value || !options.some((item) => item.value === size.value)) {
      size.value = options[0].value;
    }
  },
  { immediate: true },
);

watch(
  [() => generateMode.value, smartCutoutResolutionOptions],
  ([mode, options]) => {
    if (mode !== "smartCutout" || !options.length) return;
    if (!resolution.value || !options.some((item) => item.value === resolution.value)) {
      resolution.value = options[0].value;
    }
  },
  { immediate: true },
);

watch(aspectRatioAutoDetectEnabled, (enabled) => {
  writeStoredAspectRatioAutoDetectEnabled(enabled);
});

watch([resolutionOptions, hideResolution], ([options, shouldHide]) => {
  if (shouldHide || !options.length) return;
  if (!options.some((item) => item.value === resolution.value)) {
    resolution.value = options[0].value;
  }
}, { immediate: true });

watch(
  [() => selectedModel.value, () => generateMode.value, customSizeMin, customSizeMax, customSizeStep, supportsCustomSize],
  syncCustomSizeToCurrentLimits,
  { immediate: true },
);

watch(selectedBoardKey, async (key) => {
  if (!boardSelectionReady.value) return;
  writeStoredBoardKey(GENERATE_BOARD_KEY, key);
  generatedTasks.value = [];
  stopAllTaskPolling();
  await Promise.all([loadRecentGeneratedTasks(), loadGlobalActiveGenerationStatus()]);
});

watch(() => auth.isLoggedIn, async (isLoggedIn) => {
  if (isLoggedIn) {
    boardSelectionReady.value = false;
    await loadBoardsForGenerate();
    await Promise.all([loadRecentGeneratedTasks(), loadGlobalActiveGenerationStatus()]);
    return;
  }
  generatedTasks.value = [];
  generatedTaskLoadRequestId += 1;
  resetGeneratedTaskPagination();
  boards.value = [];
  selectedBoardKey.value = DEFAULT_BOARD_KEY;
  remoteActiveGenerationImageCount.value = 0;
  remoteActiveTaskIds.value = new Set();
  stopAllTaskPolling();
  stopGlobalActiveStatusPolling();
});
</script>

<template>
  <div class="generate-page">
    <div class="generate-workbench" :class="{ 'config-collapsed': isConfigPanelCollapsed }">
      <transition name="config-panel-slide">
        <div v-if="!isConfigPanelCollapsed" class="left-col">
          <div class="generate-mode-shell">
          <div class="generate-mode-switch">
            <div class="mode-switch-cluster">
              <div class="mode-switch-group mode-switch-group-primary">
                <button
                  type="button"
                  class="mode-switch-btn"
                  :class="{ active: generateMode === 'textGenerate' }"
                  @click="generateMode = 'textGenerate'"
                >
                  <span class="generate-tab-label">
                    <FontSizeOutlined />
                    <span>文生图</span>
                  </span>
                </button>
                <button
                  type="button"
                  class="mode-switch-btn"
                  :class="{ active: generateMode === 'imageEdit' }"
                  @click="generateMode = 'imageEdit'"
                >
                  <span class="generate-tab-label">
                    <NavGenerateImageIcon />
                    <span>图编辑</span>
                  </span>
                </button>
              </div>
            </div>

            <div class="mode-switch-cluster">
              <div class="mode-switch-group mode-switch-group-secondary">
                <a-dropdown
                  :trigger="isDesktopGeneratedTaskAutoLoad ? ['hover'] : ['click']"
                  placement="bottomRight"
                  overlay-class-name="generate-tool-dropdown"
                >
                  <button
                    type="button"
                    class="mode-switch-btn tool tool-trigger"
                    :class="{ active: isExtendedToolMode }"
                  >
                    <span class="mode-switch-trigger-content">
                      <AppstoreOutlined class="mode-switch-trigger-icon" />
                      <span class="mode-switch-trigger-value">{{ activeExtendedToolLabel }}</span>
                    </span>
                    <DownOutlined class="mode-switch-trigger-arrow" />
                  </button>
                  <template #overlay>
                    <a-menu
                      class="generate-tool-menu"
                      :selected-keys="activeExtendedToolMenuKeys"
                      @click="handleExtendedToolMenuClick"
                    >
                      <a-menu-item key="promptReverse">
                        <span class="generate-tool-menu-item-label">
                          <SearchOutlined />
                          <span>提示词反推</span>
                        </span>
                      </a-menu-item>
                      <a-menu-item key="inpaint">
                        <span class="generate-tool-menu-item-label">
                          <HighlightOutlined />
                          <span>局部重绘</span>
                        </span>
                      </a-menu-item>
                      <a-menu-item key="smartCutout">
                        <span class="generate-tool-menu-item-label">
                          <ScissorOutlined />
                          <span>智能抠图</span>
                        </span>
                      </a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
                <a-tooltip v-if="isDesktopGeneratedTaskAutoLoad" title="收起配置">
                  <button
                    type="button"
                    class="mode-switch-btn config-collapse-btn"
                    aria-label="收起配置"
                    @click="isConfigPanelCollapsed = true"
                  >
                    <DoubleLeftOutlined />
                  </button>
                </a-tooltip>
              </div>
            </div>
          </div>

          <transition name="generate-panel-slide" mode="out-in">
            <section
              v-if="generateMode === 'textGenerate'"
              key="textGenerate"
              class="work-panel settings-panel generate-config-panel"
            >
              <div class="settings-scroll">
              <template v-if="sceneConfigLoading">
                <div class="config-skeleton-shell" aria-hidden="true">
                  <div class="config-skeleton-section">
                    <div class="config-skeleton-line config-skeleton-line-title"></div>
                    <div class="config-skeleton-line config-skeleton-line-control"></div>
                  </div>
                  <div class="config-skeleton-section">
                    <div class="config-skeleton-line config-skeleton-line-title"></div>
                    <div class="config-skeleton-line config-skeleton-line-area"></div>
                  </div>
                  <div class="config-skeleton-row">
                    <div class="config-skeleton-chip"></div>
                    <div class="config-skeleton-chip"></div>
                    <div class="config-skeleton-chip"></div>
                  </div>
                  <div class="config-skeleton-section config-skeleton-section-last">
                    <div class="config-skeleton-line config-skeleton-line-title config-skeleton-line-short"></div>
                    <div class="config-skeleton-line config-skeleton-line-slider"></div>
                  </div>
                </div>
              </template>
              <template v-else>
              <div class="settings-row model-row config-section">
                <div class="setting-item setting-item-full">
                  <div class="setting-label-row">
                    <label>选择模型</label>
                    <div class="model-help-group">
                      <div class="model-help">
                        <a-popover
                          trigger="click"
                          placement="bottomRight"
                          overlay-class-name="model-help-popover"
                          :get-popup-container="getBodyPopupContainer"
                        >
                          <template #content>
                            <div class="model-help-tip batch-mode-tip">
                              <div class="batch-mode-tip-title">如何连续生成多张图？</div>
                              <ol class="batch-mode-tip-list">
                                <li>写好提示词后点击「开始生成」，任务会出现在右侧「生成任务」面板。</li>
                                <li>提交后左侧内容不会清空，可立即修改提示词、参考图或参数。</li>
                                <li>再次点击「开始生成」，即可并行发起新任务，无需等待上一张出图。</li>
                                <li>最多 {{ MAX_ACTIVE_GENERATION_IMAGES }} 张图同时在生成（当前 {{ activeGenerationImageCount }} / {{ MAX_ACTIVE_GENERATION_IMAGES }}）。</li>
                              </ol>
                              <div class="batch-mode-tip-note">
                                也可通过「图片数量」一次发起多张（1–{{ MAX_ACTIVE_GENERATION_IMAGES }} 张），会占用对应数量的并发名额。
                              </div>
                            </div>
                          </template>
                          <button type="button" class="model-help-trigger">
                            <AppstoreOutlined />
                            <span>批量模式</span>
                          </button>
                        </a-popover>
                      </div>
                      <div class="model-help">
                        <a-popover
                          trigger="click"
                          placement="bottomRight"
                          overlay-class-name="model-help-popover"
                          :get-popup-container="getBodyPopupContainer"
                        >
                          <template #content>
                            <div class="model-help-tip">
                              <div class="model-help-grid model-help-grid-head">
                                <div>模型</div>
                                <div>细节与质量</div>
                                <div>伪影</div>
                                <div>推荐使用场景</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2.5 Flare</div>
                                <div>优于 G-Image 2，出图更利落，细节更好</div>
                                <div>较少</div>
                                <div>日常首选（社媒、商品图、快速试稿、批量生产）</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2.5 Sunburst</div>
                                <div>更精细，改图控制更好</div>
                                <div>最少</div>
                                <div>成片、复杂编辑、局部精修，需要只改指定位置时使用</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2 · 顶级</div>
                                <div>最高保真度，锐利边缘、精细纹理、文字表现最佳</div>
                                <div>最少</div>
                                <div>最终成品、完美文字、高清精度需求（印刷、专业输出、复杂构图）</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2 · 高质量</div>
                                <div>平衡，细节较好</div>
                                <div>较少</div>
                                <div>大多数日常生产用途（社交媒体、网页素材等）</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2 · 性价比</div>
                                <div>较粗糙，细节一般</div>
                                <div>较多</div>
                                <div>快速迭代、草稿、缩略图、高频批量生成、成本敏感场景</div>
                              </div>
                              <div class="model-help-grid">
                                <div>Nano Banana Pro</div>
                                <div>极致细节、复杂构图、干净文字</div>
                                <div>最少</div>
                                <div>需要极致细节、复杂构图、文字排版时使用</div>
                              </div>
                              <div class="model-help-grid">
                                <div>Nano Banana 2</div>
                                <div>接近 Pro，速度与质量平衡最佳</div>
                                <div>较少</div>
                                <div>大多数人日常使用首选（性价比最高）</div>
                              </div>
                              <div class="model-help-grid">
                                <div>Nano Banana 2 Lite</div>
                                <div>轻量版，出图更快，细节略弱于 Nano Banana 2</div>
                                <div>一般</div>
                                <div>快速出图、日常草稿、成本敏感场景</div>
                              </div>
                              <div class="model-help-grid">
                                <div>Nano Banana</div>
                                <div>一般，适合快速草稿验证</div>
                                <div>较多</div>
                                <div>现在较少使用，主要用于低成本快速测试</div>
                              </div>
                            </div>
                          </template>
                          <button type="button" class="model-help-trigger">
                            <BarChartOutlined />
                            <span>模型对比</span>
                          </button>
                        </a-popover>
                      </div>
                    </div>
                  </div>
                  <div class="model-select-wrap">
                    <ModelCategorySelect
                      v-model="selectedModel"
                      :options="generationModelSelectOptions"
                      variant="flat"
                      popup-class-name="generate-dropdown"
                    />
                    <span v-if="SHOW_MODEL_NEW_BADGES" class="model-new-badge model-new-badge-selected">新模型</span>
                  </div>
                </div>
              </div>

              <div class="prompt-block config-section">
                <div class="prompt-label-row">
                  <div class="prompt-label-main">
                    <label>提示词</label>
                    <PromptInterceptionTip />
                    <a-tooltip v-if="canQuickSavePrompt(prompt, lastSavedPromptText)" title="加入我的提示词">
                      <button
                        type="button"
                        class="prompt-quick-save-btn"
                        aria-label="加入我的提示词"
                        :disabled="isQuickSavePromptPending('prompt')"
                        @click="confirmSavePromptToLibrary(prompt, 'prompt', markPromptQuickSaved)"
                      >
                        <PlusOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                  <div class="prompt-label-actions">
                    <GenerateCameraPicker
                      v-model:body-id="selectedCameraBodyId"
                      v-model:lens-id="selectedCameraLensId"
                      v-model:focal-id="selectedCameraFocalId"
                      v-model:aperture-id="selectedCameraApertureId"
                    />
                    <GenerateStylePicker
                      v-model:color-style-id="selectedColorStyleId"
                      v-model:lighting-style-id="selectedLightingStyleId"
                    />
                    <a-tooltip :title="PROMPT_OPTIMIZE_TOOLTIP">
                      <button
                        type="button"
                        class="prompt-icon-btn"
                        aria-label="提示词优化"
                        :disabled="promptOptimizeLoading"
                        @click="handlePromptOptimize"
                      >
                        <LoadingOutlined v-if="promptOptimizeLoading" />
                        <ExperimentOutlined v-else />
                      </button>
                    </a-tooltip>
                    <a-tooltip title="我的提示词">
                      <button type="button" class="prompt-icon-btn" aria-label="我的提示词" @click="openPromptLibrary">
                        <FontSizeOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                </div>
                <div
                  class="prompt-input-wrap"
                  :class="{
                    'has-style-tags': hasSelectedGenerateStyles,
                    'has-style-tags-stacked': selectedPromptTagCount > 3,
                  }"
                >
                  <GenerateStyleTags
                    v-model:color-style-id="selectedColorStyleId"
                    v-model:lighting-style-id="selectedLightingStyleId"
                    v-model:camera-body-id="selectedCameraBodyId"
                    v-model:camera-lens-id="selectedCameraLensId"
                    v-model:camera-focal-id="selectedCameraFocalId"
                    v-model:camera-aperture-id="selectedCameraApertureId"
                  />
                  <a-textarea
                    v-model:value="prompt"
                    :rows="5"
                    :placeholder="hasSelectedGenerateStyles ? '' : '描述您想要生成的图片...'"
                    class="prompt-input"
                    :maxlength="TASK_PROMPT_MAX_LENGTH"
                    :allow-clear="!isPromptOptimizeOnMainPrompt"
                    :readonly="isPromptOptimizeOnMainPrompt"
                    show-count
                  />
                  <a-tooltip title="放大编辑">
                    <span class="prompt-expand-btn-wrap">
                      <button
                        type="button"
                        class="prompt-expand-btn"
                        aria-label="放大编辑"
                        :disabled="isPromptOptimizeOnMainPrompt"
                        @click="openPromptExpand('prompt')"
                      >
                        <ExpandOutlined />
                      </button>
                    </span>
                  </a-tooltip>
                  <div v-if="isPromptOptimizeOnMainPrompt" class="prompt-optimize-status">
                    <div class="prompt-optimize-status-text">
                      <LoadingOutlined spin />
                      <span>优化中，约 10 秒左右</span>
                    </div>
                    <button type="button" class="prompt-optimize-cancel-btn" @click="confirmCancelPromptOptimize">取消</button>
                  </div>
                </div>
              </div>

              <div class="settings-row settings-row-inline config-section compact-config-section">
                <div v-if="!hideAspectRatio && !customSizeEnabled" class="setting-item setting-item-inline">
                  <label>宽高比</label>
                  <AspectRatioPicker v-model="size" :options="sizeOptions" />
                </div>
                <div v-else-if="customSizeEnabled" class="setting-item setting-item-inline">
                  <label>宽度</label>
                    <div class="custom-size-input-wrap">
                      <a-input-number
                      v-digits-only
                      :value="customWidth"
                      class="warm-input-number custom-size-input"
                      :class="{ 'is-invalid': !!customWidthError }"
                      :step="CUSTOM_SIZE_PIXEL_MULTIPLE"
                      :precision="0"
                      :parser="parseCustomSizeInput"
                      :formatter="formatCustomSizeInput"
                      :status="customWidthError ? 'error' : undefined"
                      @update:value="handleCustomWidthChange"
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
                      v-digits-only
                      :value="customHeight"
                      class="warm-input-number custom-size-input"
                      :class="{ 'is-invalid': !!customHeightError }"
                      :step="CUSTOM_SIZE_PIXEL_MULTIPLE"
                      :precision="0"
                      :parser="parseCustomSizeInput"
                      :formatter="formatCustomSizeInput"
                      :status="customHeightError ? 'error' : undefined"
                      @update:value="handleCustomHeightChange"
                    />
                      <span class="custom-size-unit">px</span>
                    </div>
                  <div v-if="customHeightError" class="custom-size-error">{{ customHeightError }}</div>
                </div>
                <div class="setting-item setting-item-inline">
                  <label>图片数量</label>
                  <OptionGridPicker
                    v-model="selectedNumImages"
                    :options="GENERATION_IMAGE_COUNT_OPTIONS"
                    panel-title="选择图片数量"
                    placeholder="选择图片数量"
                  />
                </div>
              </div>
              <div
                v-if="!hideAspectRatio || supportsCustomSize"
                class="settings-row config-section custom-size-bottom-row"
              >
                <div v-if="!hideAspectRatio" class="aspect-ratio-auto-row">
                  <a-switch v-model:checked="aspectRatioAutoDetectEnabled" size="small" class="aspect-ratio-auto-switch" />
                  <div class="aspect-ratio-auto-text">
                    <span class="aspect-ratio-auto-label">比例自动识别</span>
                    <a-tooltip
                      title="开启后，上传第一张参考图或从我的素材添加第一张参考图时，会自动选择最匹配的宽高比。"
                      placement="top"
                      :get-popup-container="getBodyPopupContainer"
                    >
                      <button type="button" class="aspect-ratio-auto-help" aria-label="比例自动识别说明">
                        <QuestionCircleOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                </div>
                <div v-if="supportsCustomSize" class="aspect-ratio-auto-row custom-size-toggle-row">
                  <a-switch v-model:checked="customSizeEnabled" size="small" class="aspect-ratio-auto-switch" @change="onCustomSizeToggle" />
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
                          <div class="custom-size-help-note">仅 G-Image2 模型支持自定义</div>
                        </div>
                      </template>
                      <button type="button" class="aspect-ratio-auto-help" aria-label="自定义分辨率说明">
                        <QuestionCircleOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                </div>
              </div>
              </template>

              </div>

              <div class="settings-footer">
                <div class="generate-link-tip">
                  <div class="generate-link-tip-left">
                    <a
                      href="https://80ai.net/gptimage2-prompt"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="generate-link-tip-anchor"
                    >
                      提示词灵感
                    </a>
                    (500+模版)
                  </div>
                  <div class="generate-link-tip-right">
                    <strong>{{ MAX_ACTIVE_GENERATION_IMAGES }}</strong> 个并发（{{ activeGenerationImageCount }} / {{ MAX_ACTIVE_GENERATION_IMAGES }}）
                  </div>
                </div>
                <div class="generate-action-row">
                  <a-button size="large" class="generate-btn generate-btn-secondary" @click="router.push('/batch-generate')">
                    批量生图
                  </a-button>
                  <a-button
                    type="primary"
                    size="large"
                    :loading="submittingGenerate"
                    :disabled="sceneConfigLoading || !canClickGenerate || submittingGenerate"
                    class="generate-btn"
                    @click="handleGenerate"
                  >
                    <template #icon><ThunderboltOutlined /></template>
                    {{ generateButtonText }}
                  </a-button>
                </div>
              </div>
            </section>

            <section
              v-else-if="generateMode === 'imageEdit'"
              key="imageEdit"
              class="work-panel settings-panel generate-config-panel"
            >
              <div class="settings-scroll">
              <template v-if="sceneConfigLoading">
                <div class="config-skeleton-shell" aria-hidden="true">
                  <div class="config-skeleton-section">
                    <div class="config-skeleton-line config-skeleton-line-title"></div>
                    <div class="config-skeleton-line config-skeleton-line-control"></div>
                  </div>
                  <div class="config-skeleton-section">
                    <div class="config-skeleton-line config-skeleton-line-title"></div>
                    <div class="config-skeleton-line config-skeleton-line-area"></div>
                  </div>
                  <div class="config-skeleton-row">
                    <div class="config-skeleton-chip"></div>
                    <div class="config-skeleton-chip"></div>
                    <div class="config-skeleton-chip"></div>
                  </div>
                  <div class="config-skeleton-section config-skeleton-section-last">
                    <div class="config-skeleton-line config-skeleton-line-title config-skeleton-line-short"></div>
                    <div class="config-skeleton-line config-skeleton-line-slider"></div>
                  </div>
                </div>
              </template>
              <template v-else>
              <div class="settings-row model-row config-section">
                <div class="setting-item setting-item-full">
                  <div class="setting-label-row">
                    <label>选择模型</label>
                    <div class="model-help-group">
                      <div class="model-help">
                        <a-popover
                          trigger="click"
                          placement="bottomRight"
                          overlay-class-name="model-help-popover"
                          :get-popup-container="getBodyPopupContainer"
                        >
                          <template #content>
                            <div class="model-help-tip batch-mode-tip">
                              <div class="batch-mode-tip-title">如何连续生成多张图？</div>
                              <ol class="batch-mode-tip-list">
                                <li>写好提示词后点击「开始生成」，任务会出现在右侧「生成任务」面板。</li>
                                <li>提交后左侧内容不会清空，可立即修改提示词、参考图或参数。</li>
                                <li>再次点击「开始生成」，即可并行发起新任务，无需等待上一张出图。</li>
                                <li>最多 {{ MAX_ACTIVE_GENERATION_IMAGES }} 张图同时在生成（当前 {{ activeGenerationImageCount }} / {{ MAX_ACTIVE_GENERATION_IMAGES }}）。</li>
                              </ol>
                              <div class="batch-mode-tip-note">
                                也可通过「图片数量」一次发起多张（1–{{ MAX_ACTIVE_GENERATION_IMAGES }} 张），会占用对应数量的并发名额。
                              </div>
                            </div>
                          </template>
                          <button type="button" class="model-help-trigger">
                            <AppstoreOutlined />
                            <span>批量模式</span>
                          </button>
                        </a-popover>
                      </div>
                      <div class="model-help">
                        <a-popover
                          trigger="click"
                          placement="bottomRight"
                          overlay-class-name="model-help-popover"
                          :get-popup-container="getBodyPopupContainer"
                        >
                          <template #content>
                            <div class="model-help-tip">
                              <div class="model-help-grid model-help-grid-head">
                                <div>模型</div>
                                <div>细节与质量</div>
                                <div>伪影</div>
                                <div>推荐使用场景</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2.5 Flare</div>
                                <div>优于 G-Image 2，出图更利落，细节更好</div>
                                <div>较少</div>
                                <div>日常首选（社媒、商品图、快速试稿、批量生产）</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2.5 Sunburst</div>
                                <div>更精细，改图控制更好</div>
                                <div>最少</div>
                                <div>成片、复杂编辑、局部精修，需要只改指定位置时使用</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2 · 顶级</div>
                                <div>最高保真度，锐利边缘、精细纹理、文字表现最佳</div>
                                <div>最少</div>
                                <div>最终成品、完美文字、高清精度需求（印刷、专业输出、复杂构图）</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2 · 高质量</div>
                                <div>平衡，细节较好</div>
                                <div>较少</div>
                                <div>大多数日常生产用途（社交媒体、网页素材等）</div>
                              </div>
                              <div class="model-help-grid">
                                <div>G-Image 2 · 性价比</div>
                                <div>较粗糙，细节一般</div>
                                <div>较多</div>
                                <div>快速迭代、草稿、缩略图、高频批量生成、成本敏感场景</div>
                              </div>
                              <div class="model-help-grid">
                                <div>Nano Banana Pro</div>
                                <div>极致细节、复杂构图、干净文字</div>
                                <div>最少</div>
                                <div>需要极致细节、复杂构图、文字排版时使用</div>
                              </div>
                              <div class="model-help-grid">
                                <div>Nano Banana 2</div>
                                <div>接近 Pro，速度与质量平衡最佳</div>
                                <div>较少</div>
                                <div>大多数人日常使用首选（性价比最高）</div>
                              </div>
                              <div class="model-help-grid">
                                <div>Nano Banana 2 Lite</div>
                                <div>轻量版，出图更快，细节略弱于 Nano Banana 2</div>
                                <div>一般</div>
                                <div>快速出图、日常草稿、成本敏感场景</div>
                              </div>
                              <div class="model-help-grid">
                                <div>Nano Banana</div>
                                <div>一般，适合快速草稿验证</div>
                                <div>较多</div>
                                <div>已较少使用，主要用于低成本快速测试</div>
                              </div>
                            </div>
                          </template>
                          <button type="button" class="model-help-trigger">
                            <BarChartOutlined />
                            <span>模型对比</span>
                          </button>
                        </a-popover>
                      </div>
                    </div>
                  </div>
                  <div class="model-select-wrap">
                    <ModelCategorySelect
                      v-model="selectedModel"
                      :options="generationModelSelectOptions"
                      variant="flat"
                      popup-class-name="generate-dropdown"
                    />
                    <span v-if="SHOW_MODEL_NEW_BADGES" class="model-new-badge model-new-badge-selected">新模型</span>
                  </div>
                </div>
              </div>

              <div
                ref="referenceUploadBlockRef"
                class="field-block ref-upload-block config-section"
                :class="{ 'is-reference-drag-over': referenceDragActive }"
              >
                <div class="panel-head">
                  <div class="panel-head-main">
                    <h3>参考图</h3>
                    <span class="panel-hint">(最多 {{ maxReferenceImages }} 张<span class="panel-hint-extra">，支持拖拽、粘贴上传</span>)</span>
                  </div>
                  <div class="panel-head-actions">
                    <a-tooltip overlay-class-name="smart-cutout-entry-tooltip">
                      <template #title>
                        <div class="smart-cutout-entry-tip">
                          <p>智能抠图：支持根据提示词自动抠图，也可手动涂抹并自定义抠图区域，结果图为透明背景 PNG</p>
                          <img
                            :src="smartCutoutTipAsset"
                            alt="智能抠图前后对比：左边是原图，右边是透明背景结果"
                            class="smart-cutout-entry-tip-img"
                          />
                        </div>
                      </template>
                      <button
                        type="button"
                        class="prompt-icon-btn"
                        aria-label="智能抠图"
                        @click="openSmartCutoutFromImageEdit"
                      >
                        <ScissorOutlined />
                      </button>
                    </a-tooltip>
                    <a-tooltip title="我的素材">
                      <button type="button" class="prompt-icon-btn" aria-label="我的素材" @click.stop="openAssetPicker">
                        <NavGenerateImageIcon />
                      </button>
                    </a-tooltip>
                  </div>
                </div>

                <input
                  ref="fileInput"
                  class="native-file-input"
                  type="file"
                  :accept="imageFileAccept"
                  multiple
                  @change="handleFileChange"
                />

                <div class="upload-grid">
                  <div
                    v-for="(item, idx) in referenceItems"
                    :key="item.id"
                    class="upload-thumb"
                    @click="handlePreview(getReferencePreviewUrl(item))"
                  >
                    <img :src="getReferencePreviewUrl(item)" alt="参考图" />
                    <div v-if="item.status !== 'success'" class="upload-thumb-mask" :class="{ error: item.status === 'failed' }">
                      <a-spin
                        v-if="item.status === 'uploading'"
                        :indicator="h(LoadingOutlined, { style: smallAccentIndicatorStyle })"
                      />
                      <span v-else>上传失败</span>
                    </div>
                    <a-tooltip v-if="canQuickSaveReferenceItem(item)" title="加入我的素材">
                      <button
                        type="button"
                        class="thumb-save"
                        aria-label="加入我的素材"
                        :disabled="isSavingReferenceToLibrary(item.id)"
                        @click.stop="confirmSaveReferenceItem(item)"
                      >
                        <PlusOutlined />
                      </button>
                    </a-tooltip>
                    <button
                      type="button"
                      class="thumb-remove"
                      aria-label="删除参考图"
                      @click.stop="removeReference(idx)"
                    >
                      <CloseOutlined />
                    </button>
                  </div>

                  <div
                    v-if="referenceItems.length < maxReferenceImages"
                    class="upload-add-group"
                    :class="{
                      'is-picking': pickingGeneratedReference,
                      'has-thumbs': referenceItems.length > 0,
                    }"
                  >
                    <div
                      class="upload-add"
                      @click="triggerUpload"
                    >
                      <a-spin
                        v-if="referencePickerOpening"
                        :indicator="h(LoadingOutlined, { style: accentIndicatorStyle })"
                      />
                      <template v-else>
                        <CloudUploadOutlined class="upload-add-icon" style="font-size: 22px" />
                        <span>{{ referenceDragActive ? "松开上传" : "拖拽或点击" }}</span>
                      </template>
                    </div>
                    <div class="upload-add-extras">
                      <button
                        type="button"
                        class="upload-add upload-add-extra upload-add-assets"
                        title="我的素材"
                        @click.stop="openAssetPicker"
                      >
                        <NavGenerateImageIcon class="upload-add-icon" />
                        <span>我的素材</span>
                      </button>
                      <button
                        type="button"
                        class="upload-add upload-add-extra upload-add-from-generated"
                        :class="{ active: pickingGeneratedReference }"
                        :title="pickingGeneratedReference ? '点击可取消' : '已生成图片中选择'"
                        @click.stop="togglePickingGeneratedReference"
                      >
                        <PlusOutlined class="upload-add-icon" style="font-size: 20px" />
                        <span v-if="pickingGeneratedReference">点击可取消</span>
                        <span v-else>已生成图<br>片中选择</span>
                      </button>
                      <button
                        type="button"
                        class="upload-add upload-add-extra"
                        title="画板"
                        @click.stop="openSketchBoard"
                      >
                        <SketchBoardIcon class="upload-add-icon" />
                        <span>画板</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div class="prompt-block config-section">
                <div class="prompt-label-row">
                  <div class="prompt-label-main">
                    <label>提示词</label>
                    <PromptInterceptionTip />
                    <a-tooltip v-if="canQuickSavePrompt(prompt, lastSavedPromptText)" title="加入我的提示词">
                      <button
                        type="button"
                        class="prompt-quick-save-btn"
                        aria-label="加入我的提示词"
                        :disabled="isQuickSavePromptPending('prompt')"
                        @click="confirmSavePromptToLibrary(prompt, 'prompt', markPromptQuickSaved)"
                      >
                        <PlusOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                  <div class="prompt-label-actions">
                    <GenerateCameraPicker
                      v-model:body-id="selectedCameraBodyId"
                      v-model:lens-id="selectedCameraLensId"
                      v-model:focal-id="selectedCameraFocalId"
                      v-model:aperture-id="selectedCameraApertureId"
                    />
                    <GenerateStylePicker
                      v-model:color-style-id="selectedColorStyleId"
                      v-model:lighting-style-id="selectedLightingStyleId"
                    />
                    <a-tooltip :title="PROMPT_OPTIMIZE_TOOLTIP">
                      <button
                        type="button"
                        class="prompt-icon-btn"
                        aria-label="提示词优化"
                        :disabled="promptOptimizeLoading"
                        @click="handlePromptOptimize"
                      >
                        <LoadingOutlined v-if="promptOptimizeLoading" />
                        <ExperimentOutlined v-else />
                      </button>
                    </a-tooltip>
                    <a-tooltip title="我的提示词">
                      <button type="button" class="prompt-icon-btn" aria-label="我的提示词" @click="openPromptLibrary">
                        <FontSizeOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                </div>
                <div
                  class="prompt-input-wrap"
                  :class="{
                    'has-style-tags': hasSelectedGenerateStyles,
                    'has-style-tags-stacked': selectedPromptTagCount > 3,
                  }"
                >
                  <GenerateStyleTags
                    v-model:color-style-id="selectedColorStyleId"
                    v-model:lighting-style-id="selectedLightingStyleId"
                    v-model:camera-body-id="selectedCameraBodyId"
                    v-model:camera-lens-id="selectedCameraLensId"
                    v-model:camera-focal-id="selectedCameraFocalId"
                    v-model:camera-aperture-id="selectedCameraApertureId"
                  />
                  <a-textarea
                    v-model:value="prompt"
                    :rows="5"
                    :placeholder="hasSelectedGenerateStyles ? '' : '描述您想要生成的图片...'"
                    class="prompt-input"
                    :maxlength="TASK_PROMPT_MAX_LENGTH"
                    :allow-clear="!isPromptOptimizeOnMainPrompt"
                    :readonly="isPromptOptimizeOnMainPrompt"
                    show-count
                  />
                  <a-tooltip title="放大编辑">
                    <span class="prompt-expand-btn-wrap">
                      <button
                        type="button"
                        class="prompt-expand-btn"
                        aria-label="放大编辑"
                        :disabled="isPromptOptimizeOnMainPrompt"
                        @click="openPromptExpand('prompt')"
                      >
                        <ExpandOutlined />
                      </button>
                    </span>
                  </a-tooltip>
                  <div v-if="isPromptOptimizeOnMainPrompt" class="prompt-optimize-status">
                    <div class="prompt-optimize-status-text">
                      <LoadingOutlined spin />
                      <span>优化中，约 10 秒左右</span>
                    </div>
                    <button type="button" class="prompt-optimize-cancel-btn" @click="confirmCancelPromptOptimize">取消</button>
                  </div>
                </div>
              </div>

              <div class="settings-row settings-row-inline config-section compact-config-section">
                <div v-if="!hideAspectRatio && !customSizeEnabled" class="setting-item setting-item-inline">
                  <label>宽高比</label>
                  <AspectRatioPicker v-model="size" :options="sizeOptions" />
                </div>
                <div v-else-if="customSizeEnabled" class="setting-item setting-item-inline">
                  <label>宽度</label>
                    <div class="custom-size-input-wrap">
                      <a-input-number
                      v-digits-only
                      :value="customWidth"
                      class="warm-input-number custom-size-input"
                      :class="{ 'is-invalid': !!customWidthError }"
                      :step="CUSTOM_SIZE_PIXEL_MULTIPLE"
                      :precision="0"
                      :parser="parseCustomSizeInput"
                      :formatter="formatCustomSizeInput"
                      :status="customWidthError ? 'error' : undefined"
                      @update:value="handleCustomWidthChange"
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
                      v-digits-only
                      :value="customHeight"
                      class="warm-input-number custom-size-input"
                      :class="{ 'is-invalid': !!customHeightError }"
                      :step="CUSTOM_SIZE_PIXEL_MULTIPLE"
                      :precision="0"
                      :parser="parseCustomSizeInput"
                      :formatter="formatCustomSizeInput"
                      :status="customHeightError ? 'error' : undefined"
                      @update:value="handleCustomHeightChange"
                    />
                      <span class="custom-size-unit">px</span>
                    </div>
                  <div v-if="customHeightError" class="custom-size-error">{{ customHeightError }}</div>
                </div>
                <div class="setting-item setting-item-inline">
                  <label>图片数量</label>
                  <OptionGridPicker
                    v-model="selectedNumImages"
                    :options="GENERATION_IMAGE_COUNT_OPTIONS"
                    panel-title="选择图片数量"
                    placeholder="选择图片数量"
                  />
                </div>
              </div>
              <div
                v-if="!hideAspectRatio || supportsCustomSize"
                class="settings-row config-section custom-size-bottom-row"
              >
                <div v-if="!hideAspectRatio" class="aspect-ratio-auto-row">
                  <a-switch v-model:checked="aspectRatioAutoDetectEnabled" size="small" class="aspect-ratio-auto-switch" />
                  <div class="aspect-ratio-auto-text">
                    <span class="aspect-ratio-auto-label">比例自动识别</span>
                    <a-tooltip
                      title="开启后，上传第一张参考图或从我的素材添加第一张参考图时，会自动选择最匹配的宽高比。"
                      placement="top"
                      :get-popup-container="getBodyPopupContainer"
                    >
                      <button type="button" class="aspect-ratio-auto-help" aria-label="比例自动识别说明">
                        <QuestionCircleOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                </div>
                <div v-if="supportsCustomSize" class="aspect-ratio-auto-row custom-size-toggle-row">
                  <a-switch v-model:checked="customSizeEnabled" size="small" class="aspect-ratio-auto-switch" @change="onCustomSizeToggle" />
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
                          <div class="custom-size-help-note">仅 G-Image2 模型支持自定义</div>
                        </div>
                      </template>
                      <button type="button" class="aspect-ratio-auto-help" aria-label="自定义分辨率说明">
                        <QuestionCircleOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                </div>
              </div>
              </template>

              </div>

              <div class="settings-footer">
                <div class="generate-link-tip">
                  <div class="generate-link-tip-left">
                    <a
                      href="https://80ai.net/gptimage2-prompt"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="generate-link-tip-anchor"
                    >
                      提示词灵感
                    </a>
                    (500+模版)
                  </div>
                  <div class="generate-link-tip-right">
                    <strong>{{ MAX_ACTIVE_GENERATION_IMAGES }}</strong> 个并发（{{ activeGenerationImageCount }} / {{ MAX_ACTIVE_GENERATION_IMAGES }}）
                  </div>
                </div>
                <div class="generate-action-row">
                  <a-button size="large" class="generate-btn generate-btn-secondary" @click="router.push('/batch-generate')">
                    批量生图
                  </a-button>
                  <a-button
                    type="primary"
                    size="large"
                    :loading="submittingGenerate"
                    :disabled="sceneConfigLoading || !canClickGenerate || submittingGenerate"
                    class="generate-btn"
                    @click="handleGenerate"
                  >
                    <template #icon><ThunderboltOutlined /></template>
                    {{ generateButtonText }}
                  </a-button>
                </div>
              </div>
            </section>

            <section
              v-else-if="generateMode === 'promptReverse'"
              key="promptReverse"
              class="work-panel settings-panel prompt-reverse-panel"
            >
              <div class="settings-scroll">
              <div class="field-block">
                <div class="panel-head">
                  <h3>上传图片</h3>
                  <span class="panel-hint">(每次反推消耗 1 积分)</span>
                </div>

                <input
                  ref="reverseInput"
                  class="native-file-input"
                  type="file"
                  :accept="imageFileAccept"
                  @change="handleReverseFileChange"
                />

                <div
                  v-if="!reverseImageUrl"
                  class="source-upload-empty"
                  @click="triggerReverseUpload"
                >
                  <a-spin
                    v-if="reverseUploading || reversePickerOpening"
                    :indicator="h(LoadingOutlined, { style: accentIndicatorStyle })"
                  />
                  <template v-else>
                    <CloudUploadOutlined class="source-upload-icon" />
                    <div class="source-upload-title">点击上传图片</div>
                    <div class="source-upload-desc">系统将自动分析图片内容并反推出专业中文提示词</div>
                  </template>
                </div>

                <div v-else class="reverse-preview-shell" @click="handlePreview(getReversePreviewUrl())">
                  <button type="button" class="canvas-remove-btn" @click.stop="removeReverseImage">
                    <CloseOutlined />
                  </button>
                  <img :src="getReversePreviewUrl()" alt="提示词反推图片" class="reverse-preview-image" />
                </div>
              </div>

              <transition name="generate-panel-slide" mode="out-in">
                <div v-if="reversePromptResult" key="reverse-result" class="reverse-result-card">
                  <div class="panel-head">
                    <h3>反推结果</h3>
                  </div>
                  <a-textarea
                    :value="reversePromptResult"
                    :rows="8"
                    readonly
                    class="prompt-input reverse-result-input"
                  />
                  <div class="reverse-actions">
                    <a-button class="reverse-action-btn reverse-action-btn-secondary" @click="copyReversePrompt">
                      <template #icon><CopyOutlined /></template>
                      复制提示词
                    </a-button>
                    <a-button class="reverse-action-btn reverse-action-btn-primary" type="primary" @click="applyReversePrompt">
                      带入文生图
                    </a-button>
                  </div>
                </div>

                <div v-else key="reverse-placeholder" class="reverse-result-placeholder">
                  上传图片后，点击「开始反推」即可获得适合 AI 绘画的中文提示词。
                </div>
              </transition>
              </div>

              <div class="settings-footer">
                <div class="generate-link-tip">
                  <div class="generate-link-tip-left">
                    <a
                      href="https://80ai.net/gptimage2-prompt"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="generate-link-tip-anchor"
                    >
                      提示词灵感
                    </a>
                    (500+模版)
                  </div>
                </div>
                <a-button
                  type="primary"
                  block
                  size="large"
                  :loading="reverseLoading || reverseUploading"
                  class="generate-btn"
                  @click="handlePromptReverse"
                >
                  <template #icon><ThunderboltOutlined /></template>
                  {{ promptReverseButtonText }}
                </a-button>
              </div>
            </section>

            <section
              v-else-if="generateMode === 'inpaint'"
              key="inpaint"
              class="work-panel settings-panel inpaint-panel"
            >
              <div class="settings-scroll">
              <div class="field-block">
                <div class="panel-head">
                  <h3>绘制区域</h3>
                  <span class="panel-hint">(必传，涂抹后仅重绘选区)</span>
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
                    <div class="source-upload-title">点击上传原图</div>
                    <div class="source-upload-desc">上传后可直接在图片上涂抹需要重绘的区域</div>
                  </template>
                </div>

                <template v-else>
                  <div class="repaint-status-card" :class="{ ready: hasRepaintMask }">
                    <div class="repaint-status-title">
                      {{ hasRepaintMask ? "已选择重绘区域" : "请在图片上涂抹需要重绘的区域" }}
                    </div>
                    <div class="repaint-status-desc">
                      {{ hasRepaintMask
                        ? "提交后只会修改已涂抹部分，未涂抹区域保持不变。"
                        : "先上传原图，再直接在图片上绘制需要重绘的局部范围。" }}
                    </div>
                    <div v-if="sourceUploading || (!sourceImageUrl && sourcePreviewUrl)" class="repaint-status-uploading">
                      {{ sourceUploading ? "原图上传中，完成后可提交任务" : "原图上传未完成，请重新上传后再试" }}
                    </div>
                  </div>

                  <div class="repaint-canvas-shell">
                    <button type="button" class="canvas-remove-btn" @click.stop="removeSourceImage">
                      <CloseOutlined />
                    </button>
                    <RepaintCanvas
                      ref="repaintCanvasRef"
                      :image-url="sourceDisplayUrl"
                      :mask-url="resolveImageUrl(repaintMaskUrl)"
                      :brush-size="brushSize"
                      :tool="repaintTool"
                      :line-color="repaintLineColor"
                      @mask-change="handleMaskChange"
                    />
                  </div>

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
                      <button
                        type="button"
                        class="tool-btn"
                        @click="clearRepaintMask"
                      >
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
              </div>

              <div class="prompt-block inpaint-prompt-block">
                <div class="prompt-label-row">
                  <div class="prompt-label-main">
                    <label>提示词</label>
                    <PromptInterceptionTip />
                    <a-tooltip v-if="canQuickSavePrompt(repaintPrompt, lastSavedRepaintPromptText)" title="加入我的提示词">
                      <button
                        type="button"
                        class="prompt-quick-save-btn"
                        aria-label="加入我的提示词"
                        :disabled="isQuickSavePromptPending('repaint-prompt')"
                        @click="confirmSavePromptToLibrary(repaintPrompt, 'repaint-prompt', markRepaintPromptQuickSaved)"
                      >
                        <PlusOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                  <div class="prompt-label-actions">
                    <GenerateCameraPicker
                      v-model:body-id="selectedCameraBodyId"
                      v-model:lens-id="selectedCameraLensId"
                      v-model:focal-id="selectedCameraFocalId"
                      v-model:aperture-id="selectedCameraApertureId"
                    />
                    <GenerateStylePicker
                      v-model:color-style-id="selectedColorStyleId"
                      v-model:lighting-style-id="selectedLightingStyleId"
                    />
                    <a-tooltip :title="PROMPT_OPTIMIZE_TOOLTIP">
                      <button
                        type="button"
                        class="prompt-icon-btn"
                        aria-label="提示词优化"
                        :disabled="promptOptimizeLoading"
                        @click="handlePromptOptimize"
                      >
                        <LoadingOutlined v-if="promptOptimizeLoading" />
                        <ExperimentOutlined v-else />
                      </button>
                    </a-tooltip>
                    <a-tooltip title="我的提示词">
                      <button type="button" class="prompt-icon-btn" aria-label="我的提示词" @click="openPromptLibrary">
                        <FontSizeOutlined />
                      </button>
                    </a-tooltip>
                  </div>
                </div>
                <div
                  class="prompt-input-wrap"
                  :class="{
                    'has-style-tags': hasSelectedGenerateStyles,
                    'has-style-tags-stacked': selectedPromptTagCount > 3,
                  }"
                >
                  <GenerateStyleTags
                    v-model:color-style-id="selectedColorStyleId"
                    v-model:lighting-style-id="selectedLightingStyleId"
                    v-model:camera-body-id="selectedCameraBodyId"
                    v-model:camera-lens-id="selectedCameraLensId"
                    v-model:camera-focal-id="selectedCameraFocalId"
                    v-model:camera-aperture-id="selectedCameraApertureId"
                  />
                  <a-textarea
                    v-model:value="repaintPrompt"
                    :rows="5"
                    :placeholder="hasSelectedGenerateStyles ? '' : '描述需要局部重绘后的效果...'"
                    class="prompt-input"
                    :maxlength="TASK_PROMPT_MAX_LENGTH"
                    :allow-clear="!isPromptOptimizeOnRepaintPrompt"
                    :readonly="isPromptOptimizeOnRepaintPrompt"
                    show-count
                  />
                  <a-tooltip title="放大编辑">
                    <span class="prompt-expand-btn-wrap">
                      <button
                        type="button"
                        class="prompt-expand-btn"
                        aria-label="放大编辑"
                        :disabled="isPromptOptimizeOnRepaintPrompt"
                        @click="openPromptExpand('repaintPrompt')"
                      >
                        <ExpandOutlined />
                      </button>
                    </span>
                  </a-tooltip>
                  <div v-if="isPromptOptimizeOnRepaintPrompt" class="prompt-optimize-status">
                    <div class="prompt-optimize-status-text">
                      <LoadingOutlined spin />
                      <span>优化中，约 10 秒左右</span>
                    </div>
                    <button type="button" class="prompt-optimize-cancel-btn" @click="confirmCancelPromptOptimize">取消</button>
                  </div>
                </div>
              </div>
              </div>

              <div class="settings-footer">
                <a-button
                  type="primary"
                  block
                  size="large"
                  :loading="sourceUploading || submittingGenerate"
                  :disabled="!canClickGenerate || submittingGenerate"
                  class="generate-btn"
                  @click="handleGenerate"
                >
                  <template #icon><ThunderboltOutlined /></template>
                  {{ generateButtonText }}
                </a-button>
              </div>
            </section>

            <SmartCutoutPanel
              v-else-if="generateMode === 'smartCutout'"
              key="smartCutout"
              ref="smartCutoutPanelRef"
              class="work-panel settings-panel smart-cutout-panel"
              v-model:size="size"
              v-model:resolution="resolution"
              :size-options="smartCutoutSizeOptions"
              :resolution-options="smartCutoutResolutionOptions"
              :hide-aspect-ratio="!!smartCutoutScene?.hide_aspect_ratio"
              :hide-resolution="!!smartCutoutScene?.hide_resolution"
              :supports-custom-size="supportsCustomSize"
              :custom-size-enabled="customSizeEnabled"
              :custom-width="customWidth"
              :custom-height="customHeight"
              :custom-width-error="customWidthError"
              :custom-height-error="customHeightError"
              :custom-size-step="CUSTOM_SIZE_PIXEL_MULTIPLE"
              :parse-custom-size-input="parseCustomSizeInput"
              :format-custom-size-input="formatCustomSizeInput"
              :credit-cost="smartCutoutCreditCost"
              :submitting="submittingGenerate"
              :is-super-admin="isSuperAdmin"
              :queue-full="remainingGenerationImageSlots <= 0"
              @update:custom-size-enabled="onCustomSizeToggle"
              @update:custom-width="handleCustomWidthChange"
              @update:custom-height="handleCustomHeightChange"
              @submit="handleSmartCutoutSubmit"
              @request-login="loginModalVisible = true"
            />
          </transition>
          </div>
        </div>
      </transition>

      <section
        ref="resultPanelRef"
        class="work-panel result-panel"
        :class="{ 'config-panel-is-collapsed': isConfigPanelCollapsed }"
      >
        <div class="result-head">
          <div class="result-head-main">
            <a-tooltip v-if="isDesktopGeneratedTaskAutoLoad && isConfigPanelCollapsed" title="展开配置">
              <button
                type="button"
                class="result-config-expand-btn"
                aria-label="展开配置"
                @click="isConfigPanelCollapsed = false"
              >
                <DoubleRightOutlined />
                <span>展开配置</span>
              </button>
            </a-tooltip>
            <a-select
              v-if="auth.isLoggedIn"
              v-model:value="selectedBoardKey"
              :loading="boardsLoading"
              placeholder="选择分类"
              class="history-filter-control history-filter-board"
            >
              <template #dropdownRender="{ menuNode: menu }">
                <VNodes :vnodes="menu" />
                <div class="generate-board-dropdown-actions" @mousedown.prevent>
                  <button
                    type="button"
                    class="generate-board-dropdown-action"
                    :disabled="!canRenameSelectedBoard || boardsLoading"
                    @click.stop="handleRenameSelectedBoardFromGenerate"
                  >
                    <EditOutlined />
                    <span>重命名</span>
                  </button>
                  <button
                    type="button"
                    class="generate-board-dropdown-action"
                    :disabled="boardsLoading"
                    @click.stop="handleCreateBoardFromGenerate"
                  >
                    <PlusOutlined />
                    <span>新建分类</span>
                  </button>
                  <button
                    type="button"
                    class="generate-board-dropdown-action"
                    @click.stop="handleGoBoardListFromGenerate"
                  >
                    <UnorderedListOutlined />
                    <span>返回分类列表</span>
                  </button>
                </div>
              </template>
              <a-select-option
                v-for="board in visibleBoardOptions"
                :key="boardKeyFromId(board.id)"
                :value="boardKeyFromId(board.id)"
              >
                {{ board.name }}
              </a-select-option>
            </a-select>
            <div class="result-retain-badge">
              <InfoCircleFilled class="result-retain-icon" />
              <span class="result-retain-text">
                <span class="result-retain-clause">
                  每日前 <span class="result-tip-highlight">20</span> 次失败任务不扣积分
                  <span v-if="failureRefundRemainingCount !== null">（剩余{{ failureRefundRemainingCount }}次）</span>
                </span>
                <span class="result-tip-divider">/</span>
                <span class="result-retain-clause">
                  服务器保留原图 <span class="result-tip-highlight">15</span> 天
                </span>
              </span>
            </div>
          </div>
          <div class="result-head-meta">
            <a-tooltip title="使用教程">
              <button
                type="button"
                class="result-filter-trigger"
                aria-label="打开使用教程"
                @click="goTutorial"
              >
                <ReadOutlined />
              </button>
            </a-tooltip>
            <a-popover
              v-model:open="resultViewOptionsOpen"
              trigger="click"
              placement="bottomRight"
              overlay-class-name="generate-view-popover"
              :get-popup-container="getBodyPopupContainer"
            >
              <a-tooltip title="视图设置">
                <button
                  type="button"
                  class="result-filter-trigger result-view-trigger"
                  aria-label="打开视图设置"
                >
                  <AppstoreOutlined />
                </button>
              </a-tooltip>
              <template #content>
                <div class="generate-view-panel">
                  <div class="generate-view-section">
                    <div class="generate-view-panel-title">卡片形状</div>
                    <div class="generate-card-aspect-options">
                      <button
                        v-for="option in RESULT_CARD_ASPECT_OPTIONS"
                        :key="option.value"
                        type="button"
                        class="generate-card-aspect-option"
                        :class="{ active: resultCardAspectRatio === option.value }"
                        @click="resultCardAspectRatio = option.value"
                      >
                        <span class="generate-card-aspect-icon" :class="`aspect-${option.value.replace(':', '-')}`"></span>
                        <span>{{ option.label }}</span>
                      </button>
                    </div>
                  </div>
                  <div class="generate-view-section">
                    <div class="generate-view-panel-title">每行列数</div>
                  <a-radio-group
                    v-model:value="preferredResultColumnCount"
                    class="generate-view-column-group"
                  >
                    <a-radio-button
                      v-for="columnCount in RESULT_COLUMN_OPTIONS"
                      :key="columnCount"
                      :value="columnCount"
                    >
                      {{ columnCount }} 列
                    </a-radio-button>
                  </a-radio-group>
                  </div>
                </div>
              </template>
            </a-popover>
            <UpdateLogEntryButton />
            <a-popover
              v-model:open="generatedTaskFilterOpen"
              trigger="click"
              placement="bottomRight"
              overlay-class-name="generate-filter-popover"
              :get-popup-container="getBodyPopupContainer"
            >
              <a-tooltip title="筛选任务">
                <button
                  type="button"
                  class="result-filter-trigger"
                  :class="{ active: generatedTaskActiveFilterCount > 0 }"
                  aria-label="打开任务筛选"
                >
                  <FilterOutlined />
                  <span v-if="generatedTaskActiveFilterCount" class="result-filter-count">
                    {{ generatedTaskActiveFilterCount }}
                  </span>
                </button>
              </a-tooltip>
              <template #content>
                <div class="generate-filter-panel">
                  <div class="generate-filter-panel-head">
                    <div>
                      <div class="generate-filter-panel-title">筛选生成任务</div>
                      <div class="generate-filter-panel-desc">条件变化后会自动刷新当前分类任务</div>
                    </div>
                    <button type="button" class="generate-filter-reset" @click="resetGeneratedTaskFilters">
                      重置
                    </button>
                  </div>

                  <div class="generate-filter-expired-row">
                    <span>不展示已过期任务图片（15天之前）</span>
                    <a-switch
                      v-model:checked="generatedTaskHideExpiredFilter"
                      size="small"
                      class="warm-switch"
                    />
                  </div>

                  <div class="generate-filter-expired-row">
                    <span>不展示错误任务图片</span>
                    <a-switch
                      v-model:checked="generatedTaskHideFailedFilter"
                      size="small"
                      class="warm-switch"
                    />
                  </div>

                  <div class="generate-filter-grid">
                    <label class="generate-filter-field generate-filter-field-third">
                      <span>类型</span>
                      <a-select
                        v-model:value="generatedTaskTypeFilter"
                        allow-clear
                        placeholder="全部类型"
                        class="generate-filter-control"
                      >
                        <a-select-option value="text_generate">文生图</a-select-option>
                        <a-select-option value="image_edit">图编辑</a-select-option>
                        <a-select-option value="inpaint">局部重绘</a-select-option>
                        <a-select-option value="smart_cutout">智能抠图</a-select-option>
                      </a-select>
                    </label>
                    <label class="generate-filter-field generate-filter-field-third">
                      <span>来源</span>
                      <a-select
                        v-model:value="generatedTaskSourceFilter"
                        allow-clear
                        placeholder="全部来源"
                        class="generate-filter-control"
                      >
                        <a-select-option value="web">Web</a-select-option>
                        <a-select-option value="app">App</a-select-option>
                        <a-select-option value="api">API</a-select-option>
                      </a-select>
                    </label>
                    <label class="generate-filter-field generate-filter-field-third">
                      <span>状态</span>
                      <a-select
                        v-model:value="generatedTaskStatusFilter"
                        allow-clear
                        placeholder="全部状态"
                        class="generate-filter-control"
                      >
                        <a-select-option value="pending">等待中</a-select-option>
                        <a-select-option value="processing">处理中</a-select-option>
                        <a-select-option value="success">成功</a-select-option>
                        <a-select-option value="failed">失败</a-select-option>
                      </a-select>
                    </label>
                    <label class="generate-filter-field generate-filter-field-half">
                      <span>模型</span>
                      <a-select
                        v-model:value="generatedTaskModelFilter"
                        allow-clear
                        show-search
                        option-filter-prop="label"
                        placeholder="全部模型"
                        class="generate-filter-control"
                      >
                        <a-select-option
                          v-for="option in generatedTaskFilterModelOptions"
                          :key="option.value"
                          :value="option.value"
                          :label="option.label"
                        >
                          {{ option.label }}
                        </a-select-option>
                      </a-select>
                    </label>
                    <label class="generate-filter-field generate-filter-field-half">
                      <span>提示词</span>
                      <a-input
                        v-model:value="generatedTaskPromptFilter"
                        allow-clear
                        placeholder="按提示词筛选"
                        class="generate-filter-input"
                      />
                    </label>
                  </div>

                  <div class="generate-filter-date-card">
                    <div class="generate-filter-date-title">
                      <CalendarOutlined />
                      <span>日期</span>
                    </div>
                    <div class="generate-filter-date-presets">
                      <button
                        type="button"
                        class="generate-filter-date-preset"
                        :class="{ active: generatedTaskDatePreset === 'today' }"
                        @click="setGeneratedTaskDatePreset('today')"
                      >
                        今天
                      </button>
                      <button
                        type="button"
                        class="generate-filter-date-preset"
                        :class="{ active: generatedTaskDatePreset === 'yesterday' }"
                        @click="setGeneratedTaskDatePreset('yesterday')"
                      >
                        昨天
                      </button>
                      <button
                        type="button"
                        class="generate-filter-date-preset"
                        :class="{ active: generatedTaskDatePreset === 'week' }"
                        @click="setGeneratedTaskDatePreset('week')"
                      >
                        近一周
                      </button>
                    </div>
                    <div class="generate-filter-custom-date-row">
                      <button
                        type="button"
                        class="generate-filter-date-preset generate-filter-date-custom"
                        :class="{ active: generatedTaskDatePreset === 'custom' }"
                        @click="generatedTaskDatePreset = 'custom'"
                      >
                        自定义范围
                        <DownOutlined />
                      </button>
                      <a-range-picker
                        v-model:value="generatedTaskDateRangeFilter"
                        class="generate-filter-date-picker"
                        :allow-clear="true"
                        @change="handleGeneratedTaskCustomDateChange"
                      />
                    </div>
                  </div>
                </div>
              </template>
            </a-popover>
          </div>
        </div>

        <div v-if="pickingGeneratedReference" class="result-pick-reference-bar">
          <span>点击图片中间的 + 添加到参考图，再次点击可取消</span>
          <button type="button" class="result-pick-reference-done" @click="pickingGeneratedReference = false">完成</button>
        </div>
        <div ref="resultBodyRef" class="result-body" @scroll="handleGeneratedTaskResultScroll">
          <div v-if="generatedTasksLoading && !resultItems.length" class="result-empty result-loading-state">
            <a-spin :indicator="h(LoadingOutlined, { style: neutralIndicatorStyle })" />
            <div class="empty-title">正在加载生成任务...</div>
            <div class="empty-desc">会展示当前分类下的全部生图任务，继续下滑可自动加载更多。</div>
          </div>

          <template v-else-if="resultItems.length">
            <TransitionGroup
              name="generate-result"
              tag="div"
              class="result-list"
              :style="resultListStyle"
            >
              <div
                v-for="(item, index) in resultItems"
                :key="getResultItemKey(item)"
                class="result-card"
                :style="{
                  '--generate-result-delay': `${Math.min(index, 9) * 45}ms`,
                  '--result-pending-bg-image': `url('${generateEmptyStateAsset}')`,
                }"
                :class="{
                  pending: item.image.status === 'pending',
                  'is-picking-reference': canShowGeneratedReferenceAdd(item.task, item.image),
                }"
                @mouseleave="collapseGeneratedResultMore(item)"
              >
                  <div
                    v-if="item.taskId || item.image.status !== 'pending'"
                    class="result-top-actions"
                  >
                    <a-tooltip
                      v-if="canCreateTemplateFromTask && item.image.status === 'success'"
                      :title="isGeneratedTaskExpired(item.task) ? '原图已过期，无法创建模版' : '设为创意模版'"
                    >
                      <a-button
                        shape="circle"
                        class="icon-chip result-more-trigger result-template-trigger"
                        :disabled="isGeneratedTaskExpired(item.task)"
                        @click.stop="openTemplateDialogFromGeneratedImage(item.task, item.image)"
                      >
                        <template #icon><PictureOutlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-tooltip v-if="item.taskId" title="反馈">
                      <button
                        type="button"
                        class="result-more-trigger icon-chip"
                        :class="{ 'result-more-trigger-failed': isGeneratedResultFailed(item.task, item.image) }"
                        @click.stop="openFeedbackDialogForGeneratedTask(item.task)"
                      >
                        <MessageOutlined class="result-more-icon" />
                      </button>
                    </a-tooltip>
                    <a-tooltip v-if="canRemoveGeneratedResult(item.task, item.image)" title="删除">
                      <a-button
                        shape="circle"
                        class="icon-chip result-delete-trigger"
                        danger
                        @click.stop="confirmRemoveGeneratedTask(item.task)"
                      >
                        <template #icon><DeleteOutlined /></template>
                      </a-button>
                    </a-tooltip>
                  </div>
                  <div
                    class="result-frame"
                    :class="{
                      pending: item.image.status === 'pending',
                      failed: isGeneratedResultFailed(item.task, item.image),
                      clickable: true,
                    }"
                    @click="openGeneratedTaskDetail(item.task, item.image)"
                  >
                    <template v-if="shouldRenderGeneratedResultImage(item.task, item.image, item.index)">
                      <img
                        :src="getGeneratedResultDisplayUrl(item.task, item.image, item.index)"
                        alt="生成结果"
                        loading="lazy"
                        @load="markGeneratedResultMediaLoaded(item.task, item.image, item.index)"
                        @error="handleGeneratedResultMediaError(item.task, item.image, item.index)"
                      />
                      <div class="result-actions">
                        <template v-if="isGeneratedResultMoreExpanded(item)">
                          <a-tooltip v-if="canGenerateVideoFromGeneratedImage(item.task, item.image)" title="生成视频">
                            <a-button shape="circle" class="icon-chip" @click.stop="handleGenerateVideoFromGeneratedImage(item.task, item.image)">
                              <template #icon><VideoCameraOutlined /></template>
                            </a-button>
                          </a-tooltip>
                          <a-tooltip v-if="canEditGeneratedImage(item.task, item.image)" title="结果图编辑">
                            <a-button shape="circle" class="icon-chip" @click.stop="handleEditImageTask(item.task, item.image)">
                              <template #icon><EditOutlined /></template>
                            </a-button>
                          </a-tooltip>
                          <a-tooltip v-if="canInpaintGeneratedImage(item.task, item.image)" title="局部重绘">
                            <a-button
                              shape="circle"
                              class="icon-chip result-inpaint-trigger"
                              @click.stop="handleInpaintGeneratedImage(item.task, item.image)"
                            >
                              <template #icon><HighlightOutlined /></template>
                            </a-button>
                          </a-tooltip>
                          <a-tooltip v-if="canInpaintGeneratedImage(item.task, item.image)" title="智能抠图">
                            <a-button
                              shape="circle"
                              class="icon-chip"
                              @click.stop="handleSmartCutoutGeneratedImage(item.task, item.image)"
                            >
                              <template #icon><ScissorOutlined /></template>
                            </a-button>
                          </a-tooltip>
                        </template>
                        <a-tooltip v-if="hasGeneratedMoreActions(item.task, item.image)" title="更多">
                          <a-button shape="circle" class="icon-chip result-more-actions-trigger" @click.stop="toggleGeneratedResultMore(item)">
                            <template #icon><EllipsisOutlined /></template>
                          </a-button>
                        </a-tooltip>
                        <a-tooltip v-if="canViewGeneratedHdImage(item.task, item.image)" title="查看高清预览图">
                          <a-button
                            shape="circle"
                            class="icon-chip"
                            @click.stop="handleViewGeneratedHdImage(item.task, item.image, item.index)"
                          >
                            <template #icon><EyeOutlined /></template>
                          </a-button>
                        </a-tooltip>
                        <a-tooltip title="重新生成">
                          <a-button
                            shape="circle"
                            class="icon-chip"
                            :disabled="!item.taskId"
                            @click.stop="handleReeditTask(item.task)"
                          >
                            <template #icon><ReloadOutlined /></template>
                          </a-button>
                        </a-tooltip>
                        <a-tooltip title="下载原图">
                          <a-button
                            shape="circle"
                            class="icon-chip"
                            :disabled="isGeneratedTaskExpired(item.task)"
                            @click.stop="handleDownload(item.image.id, item.image.image_url, item.image.preview_url)"
                          >
                            <template #icon><DownloadOutlined /></template>
                          </a-button>
                        </a-tooltip>
                      </div>
                    </template>

                    <template v-else-if="shouldShowGeneratedLargeImagePreviewNotice(item.task, item.image, item.index)">
                      <div class="result-preview-notice">
                        <span>{{ LARGE_IMAGE_PREVIEW_NOTICE }}</span>
                      </div>
                      <div class="result-actions">
                        <template v-if="isGeneratedResultMoreExpanded(item)">
                          <a-tooltip v-if="canGenerateVideoFromGeneratedImage(item.task, item.image)" title="生成视频">
                            <a-button shape="circle" class="icon-chip" @click.stop="handleGenerateVideoFromGeneratedImage(item.task, item.image)">
                              <template #icon><VideoCameraOutlined /></template>
                            </a-button>
                          </a-tooltip>
                          <a-tooltip v-if="canEditGeneratedImage(item.task, item.image)" title="结果图编辑">
                            <a-button shape="circle" class="icon-chip" @click.stop="handleEditImageTask(item.task, item.image)">
                              <template #icon><EditOutlined /></template>
                            </a-button>
                          </a-tooltip>
                          <a-tooltip v-if="canInpaintGeneratedImage(item.task, item.image)" title="局部重绘">
                            <a-button
                              shape="circle"
                              class="icon-chip result-inpaint-trigger"
                              @click.stop="handleInpaintGeneratedImage(item.task, item.image)"
                            >
                              <template #icon><HighlightOutlined /></template>
                            </a-button>
                          </a-tooltip>
                          <a-tooltip v-if="canInpaintGeneratedImage(item.task, item.image)" title="智能抠图">
                            <a-button
                              shape="circle"
                              class="icon-chip"
                              @click.stop="handleSmartCutoutGeneratedImage(item.task, item.image)"
                            >
                              <template #icon><ScissorOutlined /></template>
                            </a-button>
                          </a-tooltip>
                        </template>
                        <a-tooltip v-if="hasGeneratedMoreActions(item.task, item.image)" title="更多">
                          <a-button shape="circle" class="icon-chip result-more-actions-trigger" @click.stop="toggleGeneratedResultMore(item)">
                            <template #icon><EllipsisOutlined /></template>
                          </a-button>
                        </a-tooltip>
                        <a-tooltip v-if="canViewGeneratedHdImage(item.task, item.image)" title="查看高清预览图">
                          <a-button
                            shape="circle"
                            class="icon-chip"
                            @click.stop="handleViewGeneratedHdImage(item.task, item.image, item.index)"
                          >
                            <template #icon><EyeOutlined /></template>
                          </a-button>
                        </a-tooltip>
                        <a-tooltip title="重新生成">
                          <a-button
                            shape="circle"
                            class="icon-chip"
                            :disabled="!item.taskId"
                            @click.stop="handleReeditTask(item.task)"
                          >
                            <template #icon><ReloadOutlined /></template>
                          </a-button>
                        </a-tooltip>
                        <a-tooltip title="下载原图">
                          <a-button
                            shape="circle"
                            class="icon-chip"
                            :disabled="isGeneratedTaskExpired(item.task)"
                            @click.stop="handleDownload(item.image.id, item.image.image_url, item.image.preview_url)"
                          >
                            <template #icon><DownloadOutlined /></template>
                          </a-button>
                        </a-tooltip>
                      </div>
                    </template>

                    <template v-else-if="shouldShowGeneratedUploadingState(item.task, item.image, item.index)">
                      <div class="frame-state">
                        <a-spin
                          :indicator="h(LoadingOutlined, { style: neutralIndicatorStyle })"
                        />
                        <span>图片加载中...</span>
                        <span class="frame-state-subtext">正在同步到云存储，通常只需几秒</span>
                      </div>
                      <div class="result-actions result-actions-pending">
                        <a-tooltip title="重新生成">
                          <a-button shape="circle" class="icon-chip" @click.stop="handleReeditTask(item.task)">
                            <template #icon><ReloadOutlined /></template>
                          </a-button>
                        </a-tooltip>
                      </div>
                    </template>

                    <template v-else-if="shouldShowGeneratedLoadFailedState(item.task, item.image, item.index)">
                      <div class="frame-state">
                        <span>图片加载较慢</span>
                        <span class="frame-state-subtext">已自动重试多次，请稍后再次打开</span>
                      </div>
                      <div class="result-actions result-actions-pending">
                        <a-tooltip title="重新生成">
                          <a-button shape="circle" class="icon-chip" @click.stop="handleReeditTask(item.task)">
                            <template #icon><ReloadOutlined /></template>
                          </a-button>
                        </a-tooltip>
                      </div>
                    </template>

                    <template v-else-if="isGeneratedResultFailed(item.task, item.image)">
                      <img :src="failedResultAsset" alt="生成失败" class="failed-image" />
                      <div class="frame-state error">
                        <span>{{ getGeneratedTaskFailureMessage(item.task, item.image) }}</span>
                      </div>
                      <div class="result-actions result-actions-failed">
                        <a-tooltip title="重新生成">
                          <a-button shape="circle" class="icon-chip" @click.stop="handleReeditTask(item.task)">
                            <template #icon><ReloadOutlined /></template>
                          </a-button>
                        </a-tooltip>
                      </div>
                    </template>

                    <template v-else>
                      <div class="frame-state">
                        <a-spin
                          :indicator="h(LoadingOutlined, { style: neutralIndicatorStyle })"
                        />
                        <span>正在生成图片...</span>
                        <span class="frame-state-subtext">预计 30 秒 ～ 2 分钟</span>
                      </div>
                      <div class="result-actions result-actions-pending">
                        <a-tooltip title="重新生成">
                          <a-button shape="circle" class="icon-chip" @click.stop="handleReeditTask(item.task)">
                            <template #icon><ReloadOutlined /></template>
                          </a-button>
                        </a-tooltip>
                      </div>
                    </template>
                    <button
                      v-if="canShowGeneratedReferenceAdd(item.task, item.image)"
                      type="button"
                      class="result-add-reference-btn"
                      :class="{ 'is-added': isGeneratedImageAlreadyReferenced(item.image) }"
                      :aria-label="isGeneratedImageAlreadyReferenced(item.image) ? '从参考图中移除' : '添加到参考图'"
                      @click.stop="toggleGeneratedImageAsReference(item.task, item.image)"
                    >
                      <span class="result-add-reference-icon">
                        <PlusOutlined />
                      </span>
                    </button>
                  </div>
                </div>
            </TransitionGroup>

            <div class="result-list-footnote">
              已展示 {{ generatedTasks.length }} 个任务 / {{ resultItems.length }} 张结果
              <span v-if="hasMoreGeneratedTasks">
                ，{{ isDesktopGeneratedTaskAutoLoad ? "继续下滑自动加载更多" : "可点击下方按钮继续加载更多" }}。
              </span>
              <span v-else-if="generatedTaskFilterSummary">，已加载该分类下符合筛选条件的全部任务。</span>
              <span v-else>，已加载该分类下全部任务。</span>
              <span v-if="generatedTaskFilterSummary">当前筛选：{{ generatedTaskFilterSummary }}。</span>
            </div>
            <div v-if="generatedTasksLoadingMore" class="result-load-more-tip">
              <a-spin size="small" />
              <span>正在加载更多生成任务...</span>
            </div>
            <div
              v-else-if="hasMoreGeneratedTasks && isMobileGeneratedTaskManualLoad"
              class="result-load-more-action"
            >
              <a-button block class="result-load-more-btn" @click="loadMoreGeneratedTasks">
                加载更多
              </a-button>
            </div>
            <div
              v-if="hasMoreGeneratedTasks && isDesktopGeneratedTaskAutoLoad"
              ref="generatedTaskLoadMoreAnchor"
              class="result-load-more-anchor"
              aria-hidden="true"
            />
          </template>

          <div v-else class="result-empty">
            <transition name="generate-panel-slide" mode="out-in">
              <div :key="generateMode" class="result-empty-copy">
                <div class="empty-illustration-shell">
                  <img
                    :src="generateEmptyStateAsset"
                    alt="生成结果占位插画"
                    class="empty-illustration"
                  />
                </div>
                <div class="empty-title">{{ resultEmptyTitle }}</div>
                <div class="empty-desc">{{ resultEmptyDesc }}</div>
              </div>
            </transition>
          </div>
        </div>
      </section>
    </div>

    <div v-if="previewVisible" style="display: none">
      <a-image
        :src="previewCurrent"
        :preview="{
          visible: previewVisible,
          onVisibleChange: (v: boolean) => {
            previewVisible = v;
            if (!v) previewImageLoading = false;
          },
        }"
      />
    </div>
    <Teleport to="body">
      <div v-if="previewVisible && previewImageLoading" class="hd-preview-loading" aria-label="高清预览图加载中">
        <a-spin :indicator="h(LoadingOutlined, { style: { fontSize: '36px', color: '#fff7ea' } })" />
      </div>
    </Teleport>
    <HistoryDetailDialog
      v-if="detailOpen"
      v-model:open="detailOpen"
      :item="detailItem"
      :preloaded-media-keys="detailPreloadedMediaKeys"
      :model-options="detailModelOptions"
      :has-prev="hasDetailPrev"
      :has-next="hasDetailNext"
      show-actions
      @reedit="handleDetailReedit"
      @download="handleDetailDownload"
      @navigate-prev="navigateGeneratedTaskDetail(-1)"
      @navigate-next="navigateGeneratedTaskDetail(1)"
    />
    <a-modal
      v-model:open="boardRenameDialogOpen"
      title="重命名分类"
      centered
      :confirm-loading="boardRenameSaving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitRenameSelectedBoardFromGenerate"
    >
      <a-input
        v-model:value="boardRenameName"
        placeholder="请输入分类名称"
        :maxlength="100"
        show-count
        @press-enter="submitRenameSelectedBoardFromGenerate"
      />
    </a-modal>
    <FeedbackDialog
      v-if="feedbackDialogOpen"
      v-model:open="feedbackDialogOpen"
      :task-id="feedbackTarget?.taskId"
      :model="feedbackTarget?.model"
      :prompt="feedbackTarget?.prompt"
      :created-at="feedbackTarget?.createdAt"
    />
    <UserPromptLibraryModal
      v-if="promptLibraryVisible"
      v-model:open="promptLibraryVisible"
      @select-prompt="useLibraryPrompt"
    />
    <UserAssetPicker
      v-if="assetPickerOpen"
      v-model:open="assetPickerOpen"
      title="我的素材"
      @select-asset="handlePickUserAsset"
      @select-assets="handlePickUserAssets"
    />
    <SketchBoardDialog
      v-if="sketchBoardOpen"
      v-model:open="sketchBoardOpen"
      @confirm="handleSketchBoardConfirm"
    />
    <TemplateFormDialog
      v-if="templateDialogOpen"
      v-model:open="templateDialogOpen"
      title="新增模版"
      ok-text="确认创建"
      :initial-value="templateInitialValue"
      :generation-models="templateModelOptions"
      :tags="templateTags"
      :confirm-loading="templateDialogSaving"
      @save="handleSaveGeneratedTemplate"
    />
    <PromptOptimizeStyleDialog
      v-if="promptOptimizeStyleDialogOpen"
      v-model:open="promptOptimizeStyleDialogOpen"
      @confirm="handlePromptOptimizeStyleConfirm"
      @update:open="(value) => { if (!value) closePromptOptimizeStyleDialog(); }"
    />
    <PromptExpandDialog
      v-model:open="promptExpandOpen"
      :value="promptExpandValue"
      :draft-key="promptExpandTarget"
      :maxlength="TASK_PROMPT_MAX_LENGTH"
      :placeholder="promptExpandPlaceholder"
      @confirm="applyExpandedPrompt"
    />
    <ImageSourceActionSheet
      v-if="imageSourceSheetOpen"
      @camera="pickFromCamera"
      @gallery="pickFromGallery"
      @files="pickFromFiles"
      @cancel="cancelImageSourceSheet"
    />
  </div>
</template>

<style scoped lang="scss">
.generate-page {
  min-height: calc(100vh - 112px);
  height: calc(100vh - 112px);
  background: var(--theme-page-base);
  --config-title-size: 14px;
  --config-title-gap: 8px;
  --config-title-color: var(--theme-title);
  --config-section-gap: 17px;
  --generate-config-min-width: 320px;
  --generate-config-fluid-width: 31vw;
  --generate-config-max-width: 470px;
  animation: generate-page-enter var(--motion-duration-reveal-soft) ease both;
}

:global(.app-layout-desktop-side-nav) .generate-page {
  min-height: calc(100dvh - 66px);
  height: calc(100dvh - 66px);
}

@keyframes generate-page-enter {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes generate-fade-up {
  from {
    opacity: 0;
    transform: translate3d(0, 16px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@keyframes generate-panel-in {
  from {
    opacity: 0;
    transform: translate3d(0, 18px, 0) scale(0.99);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

@keyframes generate-empty-float {
  0% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(0, -12px, 0);
  }
  100% {
    transform: translate3d(0, 0, 0);
  }
}

@keyframes generate-slide-left-in {
  from {
    opacity: 0;
    transform: translate3d(-28px, 0, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@keyframes generate-slide-right-in {
  from {
    opacity: 0;
    transform: translate3d(28px, 0, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

@keyframes result-panel-slide-left-in {
  from {
    transform: translate3d(48px, 0, 0);
  }
  to {
    transform: translate3d(0, 0, 0);
  }
}

.generate-workbench {
  position: relative;
  display: grid;
  grid-template-columns:
    clamp(
      var(--generate-config-min-width),
      var(--generate-config-fluid-width),
      var(--generate-config-max-width)
    )
    minmax(0, 1fr);
  gap: 20px;
  align-items: stretch;
  width: 100%;
  min-width: 0;
  min-height: 100%;
  height: 100%;
  animation: generate-fade-up var(--motion-duration-reveal) var(--motion-ease-enter) 0.04s both;
  transition:
    grid-template-columns var(--motion-duration-slide) var(--motion-ease-soft),
    gap var(--motion-duration-slide) var(--motion-ease-soft);
}

.generate-workbench.config-collapsed {
  grid-template-columns: minmax(0, 1fr);
  gap: 0;
}

@media (min-width: 1200px) and (hover: hover) and (pointer: fine) {
  .generate-workbench {
    --generate-config-min-width: 340px;
    --generate-config-fluid-width: 28vw;
    --generate-config-max-width: 520px;
  }
}

.left-col {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  min-width: var(--generate-config-min-width);
  max-width: var(--generate-config-max-width);
}

.config-panel-slide-enter-active,
.config-panel-slide-leave-active {
  overflow: hidden;
  transition:
    opacity var(--motion-duration-slide) var(--motion-ease-soft),
    transform var(--motion-duration-slide) var(--motion-ease-enter),
    filter var(--motion-duration-slide) var(--motion-ease-soft);
}

.config-panel-slide-leave-active {
  position: absolute;
  inset: 0 auto 0 0;
  z-index: 3;
  width: clamp(
    var(--generate-config-min-width),
    var(--generate-config-fluid-width),
    var(--generate-config-max-width)
  );
  pointer-events: none;
}

.config-panel-slide-enter-from,
.config-panel-slide-leave-to {
  opacity: 0;
  transform: translate3d(-28px, 0, 0) scaleX(0.96);
  filter: blur(6px);
}

.config-panel-slide-enter-to,
.config-panel-slide-leave-from {
  opacity: 1;
  transform: translate3d(0, 0, 0) scaleX(1);
  filter: blur(0);
}

.generate-mode-shell {
  display: flex;
  flex: 1;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  min-width: 0;
  background: transparent;
}

.generate-mode-switch {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
  min-width: 0;
  container-type: inline-size;
  container-name: generate-mode-switch;
}

.mode-switch-cluster {
  min-width: 0;
  display: flex;
  align-items: center;
}

.mode-switch-cluster:first-child {
  flex: 1 1 auto;
}

.mode-switch-cluster:last-child {
  flex: 0 0 auto;
}

.mode-switch-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mode-switch-group-primary {
  gap: 12px;
}

.mode-switch-group-secondary {
  gap: 8px;
  justify-content: flex-end;
}

.mode-switch-btn {
  appearance: none;
  border: 1px solid transparent;
  background: transparent;
  color: var(--theme-nav-text);
  padding: 0;
  border-radius: 16px;
  cursor: pointer;
  transition:
    color var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-press) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    color: var(--theme-nav-hover-text);
    transform: translateY(-1px);
  }

  &:active {
    transform: scale(0.97);
  }
}

.mode-switch-btn.active {
  color: var(--theme-accent-text);
}

.config-collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-color: var(--theme-control-border-strong);
  background: rgba(var(--theme-surface-strong-rgb), 0.74);
  color: var(--theme-accent-text);
  font-size: 16px;

  &:hover,
  &:focus-visible {
    color: var(--theme-accent-text-hover);
    border-color: var(--theme-border-strong);
    background: rgba(var(--theme-surface-strong-rgb), 0.9);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }
}

.mode-switch-group-primary .mode-switch-btn {
  height: 42px;
  min-width: 116px;
  border-radius: 14px;
  border-color: var(--theme-control-border-strong);
  background: rgba(var(--theme-surface-strong-rgb), 0.92);
  box-shadow: none;

  &:hover,
  &:focus {
    color: var(--theme-accent-text-hover);
    border-color: var(--theme-border-strong);
    background: rgba(var(--theme-page-base-rgb), 0.96);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }
}

.mode-switch-group-primary .mode-switch-btn.active,
.mode-switch-group-primary .mode-switch-btn.active:hover,
.mode-switch-group-primary .mode-switch-btn.active:focus {
  color: var(--theme-accent-contrast);
  border-color: transparent;
  background: var(--theme-accent);
  box-shadow: 0 14px 24px var(--theme-shadow-strong);
}

.mode-switch-btn.tool {
  min-width: 126px;
  border-width: 1px;
  border-style: solid;
  border-color: var(--theme-control-border-strong);
  background: rgba(var(--theme-surface-strong-rgb), 0.74);
  box-shadow: none;

  &:hover,
  &:focus {
    border-color: var(--theme-border-strong);
    background: rgba(var(--theme-surface-strong-rgb), 0.9);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }
}

.mode-switch-btn.tool.active {
  border-color: var(--theme-panel-border-strong);
  background: linear-gradient(180deg, rgba(var(--theme-surface-strong-rgb), 0.94), rgba(var(--theme-page-base-rgb), 0.9));
  box-shadow: 0 6px 14px var(--theme-shadow-soft);
}

.generate-tab-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  line-height: 1;
  min-height: 42px;
  padding: 0 14px;
  white-space: nowrap;

  .anticon,
  .nav-generate-image-icon {
    font-size: 16px;
    width: 1em;
    height: 1em;
    opacity: 0.88;
  }
}

.mode-switch-group-primary .generate-tab-label {
  min-height: 40px;
  padding: 0 18px;
  border-radius: 14px;
  font-weight: 700;

  .anticon,
  .nav-generate-image-icon {
    font-size: 17px;
  }
}

.tool-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 42px;
  min-height: 42px;
  padding: 0 10px;
  border-radius: 13px;
}

.mode-switch-trigger-content {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.mode-switch-trigger-icon {
  flex: 0 0 auto;
  font-size: 14px;
  opacity: 0.8;
}

.mode-switch-trigger-value {
  color: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.1;
  white-space: nowrap;
}

.mode-switch-trigger-arrow {
  color: inherit;
  font-size: 11px;
  opacity: 0.58;
}

@media (min-width: 961px) {
  @container generate-mode-switch (max-width: 430px) {
    .mode-switch-group-primary .mode-switch-btn {
      min-width: 0;
    }

    .mode-switch-btn.tool,
    .tool-trigger {
      min-width: 42px;
      width: 42px;
      padding: 0;
      justify-content: center;
      gap: 0;
    }

    .mode-switch-trigger-content {
      justify-content: center;
    }

    .mode-switch-trigger-icon {
      font-size: 16px;
      opacity: 0.88;
    }

    .mode-switch-trigger-value,
    .mode-switch-trigger-arrow {
      display: none;
    }
  }
}

.generate-tool-menu-item-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  line-height: 1.2;
}

/* --- Prompt (standalone) --- */
.settings-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 100%;
  min-height: 0;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.generate-config-panel {
  padding: 16px;
  border-radius: 24px;
  background: var(--theme-page-base);
  border-color: var(--theme-panel-border);
  box-shadow:
    0 18px 36px var(--theme-shadow-soft),
    inset 0 1px 0 var(--theme-panel-inset);
}

.generate-config-panel > * + * {
  margin-top: var(--config-section-gap);
}

.settings-scroll {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 0 10px 0 4px;
}

.settings-footer {
  position: relative;
  z-index: 3;
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 8px;
  background: var(--theme-page-base);
  container-type: inline-size;
  container-name: generate-footer;
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

.generate-link-tip {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  text-align: left;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.generate-link-tip-left,
.generate-link-tip-right {
  min-width: 0;
}

.generate-link-tip-right {
  flex-shrink: 0;
  text-align: right;
}

.generate-link-tip-anchor {
  color: var(--theme-accent-text);
  font-weight: 600;
  text-decoration: none;
}

.generate-link-tip-anchor:hover,
.generate-link-tip-anchor:focus {
  color: var(--theme-accent-text-hover);
  text-decoration: underline;
}

.config-section {
  position: relative;
  padding: 0 0 10px;
  transition: transform var(--motion-duration-base) var(--motion-ease-soft), opacity var(--motion-duration-base) var(--motion-ease-soft);
}

.compact-config-section {
  padding-top: 0;
  padding-bottom: 10px;
}

.prompt-block {
  display: flex;
  flex-direction: column;
}

.prompt-input-wrap {
  position: relative;
}

.prompt-expand-btn-wrap {
  position: absolute;
  right: 8px;
  bottom: 28px;
  z-index: 2;
}

.prompt-expand-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--theme-text-secondary, #8b7457);
  font-size: 18px;
  cursor: pointer;
}

.prompt-expand-btn:hover:not(:disabled) {
  background: var(--theme-panel-bg-muted, rgba(0, 0, 0, 0.05));
  color: var(--theme-title, #3d2f22);
}

.prompt-expand-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.prompt-optimize-status {
  position: absolute;
  right: 48px;
  bottom: 34px;
  left: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  pointer-events: none;
}

.prompt-optimize-status-text {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}

.prompt-optimize-cancel-btn {
  flex-shrink: 0;
  height: 24px;
  padding: 0 8px;
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 999px;
  background: var(--theme-control-bg);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  pointer-events: auto;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    color: var(--theme-accent-text-hover);
    background: var(--theme-control-hover-bg);
    border-color: var(--theme-border-strong);
    transform: translateY(-1px);
  }

  &:active {
    transform: scale(0.97);
  }
}

.prompt-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--config-title-gap);

  label {
    color: var(--config-title-color);
    font-size: 15px;
    font-weight: 700;
    line-height: 1.4;
    letter-spacing: 0.01em;
  }
}

.prompt-label-main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.prompt-label-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.history-btn {
  width: 32px;
  height: 32px;
  border-radius: 12px;
  color: var(--theme-accent-text) !important;
  font-size: 15px;
  background: var(--theme-control-bg) !important;
  border: 1px solid var(--theme-control-border-strong) !important;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    color: var(--theme-accent-text-hover) !important;
    background: var(--theme-control-hover-bg) !important;
    border-color: var(--theme-border-strong) !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }

  &:active {
    transform: scale(0.94);
  }
}

.prompt-library-btn,
.asset-library-btn {
  height: 32px;
  padding: 0 12px !important;
  border-radius: 12px;
  color: var(--theme-title) !important;
  font-size: 13px;
  font-weight: 600;
  background: var(--theme-control-bg) !important;
  border: 1px solid var(--theme-control-border-strong) !important;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    color: var(--theme-title) !important;
    background: var(--theme-control-hover-bg) !important;
    border-color: var(--theme-border-strong) !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }

  &:active {
    transform: scale(0.97);
  }
}

.prompt-icon-btn-wrap {
  display: inline-flex;
}

.prompt-icon-btn {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 12px;
  background: var(--theme-control-bg);
  color: var(--theme-title);
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-visible {
    background: var(--theme-control-hover-bg);
    border-color: var(--theme-border-strong);
    transform: translateY(-1px);
  }

  &:active {
    transform: scale(0.97);
  }

  &:disabled {
    cursor: wait;
    opacity: 0.7;
  }

  :deep(.anticon),
  :deep(.nav-generate-image-icon),
  :deep(.sketch-board-icon) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    font-size: 16px;
    width: 16px;
    height: 16px;
    overflow: visible;

    svg {
      display: block;
      width: 16px;
      height: 16px;
    }
  }

  :deep(.sketch-board-icon),
  :deep(.sketch-board-icon svg) {
    width: 14px;
    height: 14px;
    font-size: 14px;
  }
}

.generate-config-panel .prompt-input {
  border: none !important;
  background: transparent !important;
  padding: 0 !important;
  font-size: 14px;
  resize: none;
  box-shadow: none !important;

  &:focus {
    box-shadow: none !important;
  }

  :deep(textarea) {
    min-height: 144px;
    line-height: 1.7;
    color: var(--theme-title);
    border-radius: 14px !important;
    border: 1px solid var(--theme-control-border-strong) !important;
    background: var(--theme-field-bg, var(--theme-control-bg)) !important;
    padding: 12px 15px 42px !important;
    outline: none !important;
    box-shadow: inset 0 1px 0 var(--theme-panel-inset);
    transition: background var(--motion-duration-fast) var(--motion-ease-soft);
  }

  :deep(textarea:hover),
  :deep(textarea:focus),
  :deep(textarea:focus-visible) {
    border: 1px solid var(--theme-control-border-strong) !important;
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg)) !important;
    outline: none !important;
    box-shadow: inset 0 1px 0 var(--theme-panel-inset) !important;
    transform: none;
  }

  &.ant-input-textarea-show-count,
  :deep(.ant-input-textarea-show-count) {
    color: var(--theme-title) !important;
  }

  &.ant-input-textarea-show-count::after,
  :deep(.ant-input-textarea-show-count)::after,
  :deep(.ant-input-data-count) {
    color: var(--theme-title) !important;
    font-size: 12px;
  }

  :deep(textarea::placeholder) {
    color: var(--text-muted);
  }
}

.generate-config-panel .prompt-input-wrap.has-style-tags .prompt-input :deep(textarea) {
  padding-top: 48px !important;
}

.generate-config-panel .prompt-input-wrap.has-style-tags-stacked .prompt-input :deep(textarea) {
  padding-top: 80px !important;
}

.prompt-quick-save-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.78);
  color: #fff;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  opacity: 0.5;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    opacity var(--motion-duration-fast) var(--motion-ease-soft);
}

.prompt-quick-save-btn:hover,
.prompt-quick-save-btn:focus-visible {
  background: rgba(0, 0, 0, 0.92);
  opacity: 1;
  transform: translateY(-1px);
}

.prompt-quick-save-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

/* --- Settings row --- */
.settings-row {
  display: flex;
  gap: 16px;
  min-width: 0;
}

.settings-row-inline {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
  align-items: stretch;
}

.setting-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--config-title-gap);
  min-width: 0;

  label {
    color: var(--config-title-color);
    font-size: 15px;
    font-weight: 700;
    line-height: 1.4;
  }
}

.setting-item-full {
  flex: 1 1 100%;
}

.setting-item-inline {
  min-width: 0;
  max-width: 100%;
  align-items: stretch;
  gap: 10px;

  label {
    margin: 0;
    white-space: normal;
  }

  :deep(.option-grid-picker) {
    display: flex;
    width: 100%;
    min-width: 0;
  }

  :deep(.option-grid-trigger) {
    width: 100%;
    min-width: 0;
    justify-content: space-between;
  }
}

.custom-size-bottom-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
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

.custom-size-help-tooltip .custom-size-help-note {
  margin-top: 8px;
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

.config-skeleton-shell {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 6px;
}

.config-skeleton-section,
.config-skeleton-row {
  padding: 16px;
  border-radius: 20px;
  background: rgba(var(--theme-surface-strong-rgb), 0.96);
  border: 1px solid var(--theme-panel-border);
}

.config-skeleton-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-skeleton-section-last {
  padding-bottom: 20px;
}

.config-skeleton-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.config-skeleton-line,
.config-skeleton-chip {
  position: relative;
  overflow: hidden;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    rgba(var(--theme-page-base-rgb), 0.82),
    rgba(var(--theme-surface-strong-rgb), 0.98),
    rgba(var(--theme-page-base-rgb), 0.82)
  );
  background-size: 200% 100%;
  animation: config-skeleton-shimmer 1.4s ease-in-out infinite;
}

.config-skeleton-line-title {
  width: 72px;
  height: 14px;
}

.config-skeleton-line-short {
  width: 92px;
}

.config-skeleton-line-control {
  width: 100%;
  height: 52px;
}

.config-skeleton-line-area {
  width: 100%;
  height: 144px;
  border-radius: 18px;
}

.config-skeleton-chip {
  height: 52px;
}

.config-skeleton-line-slider {
  width: 100%;
  height: 56px;
  border-radius: 18px;
}

@keyframes config-skeleton-shimmer {
  0% {
    background-position: 100% 0;
  }

  100% {
    background-position: -100% 0;
  }
}

/* --- Card panel --- */
.work-panel {
  box-sizing: border-box;
  min-width: 0;
  max-width: 100%;
  background: var(--theme-page-base);
  border: 1px solid var(--theme-panel-border);
  border-radius: 24px;
  box-shadow: 0 18px 45px var(--theme-shadow-soft);
  padding: 20px;
  transition:
    transform var(--motion-duration-slide) var(--motion-ease-enter),
    opacity var(--motion-duration-slide) var(--motion-ease-soft),
    box-shadow var(--motion-duration-slide) var(--motion-ease-soft);
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

.panel-head-main {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.panel-head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-hint {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  line-height: 1.5;
}

/* --- Upload (compact) --- */
.generate-config-panel .ref-upload-block {
  position: relative;
  border-radius: 18px;
  transition:
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.generate-config-panel .ref-upload-block.is-reference-drag-over {
  background: color-mix(in srgb, var(--theme-accent) 8%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-accent) 28%, transparent);
}

.generate-config-panel .upload-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  container-type: inline-size;
}

.generate-config-panel .upload-thumb {
  position: relative;
  width: 77px;
  height: 77px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  flex-shrink: 0;
  cursor: zoom-in;
  box-shadow: 0 8px 18px var(--theme-shadow-soft);
  transition:
    transform var(--motion-duration-swift) var(--motion-ease-soft),
    box-shadow var(--motion-duration-swift) var(--motion-ease-soft),
    border-color var(--motion-duration-swift) var(--motion-ease-soft);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform var(--motion-duration-hover) var(--motion-ease-enter);
  }

  &:hover {
    transform: translateY(-2px);
    border-color: var(--theme-border-strong);
    box-shadow: 0 14px 24px var(--theme-shadow-medium);
  }

  &:hover img {
    transform: scale(1.04);
  }
}

.generate-config-panel .upload-thumb-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  background: rgba(var(--theme-surface-strong-rgb), 0.72);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  text-align: center;

  &.error {
    background: rgba(255, 245, 243, 0.9);
    color: #d6574b;
  }
}

.thumb-remove {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.82);
  color: #fff;
  font-size: 11px;
  line-height: 1;
  opacity: 0;
  cursor: pointer;
  transform: scale(0.92);
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.thumb-save {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.82);
  color: #fff;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transform: scale(0.9);
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.generate-config-panel .upload-thumb:hover .thumb-remove,
.generate-config-panel .upload-thumb:focus-within .thumb-remove,
.generate-config-panel .upload-thumb:hover .thumb-save,
.generate-config-panel .upload-thumb:focus-within .thumb-save {
  opacity: 1;
  transform: scale(1);
}

.thumb-save:hover,
.thumb-save:focus-visible,
.thumb-remove:hover,
.thumb-remove:focus-visible {
  background: rgba(0, 0, 0, 0.92);
}

.generate-config-panel .upload-add {
  width: 77px;
  height: 77px;
  border-radius: 16px;
  border: 1px dashed var(--theme-panel-border-strong);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  background: var(--theme-field-bg, var(--theme-control-bg));
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 10px 22px var(--theme-shadow-soft);
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);
  flex-shrink: 0;

  &:hover {
    border-color: var(--theme-border-strong);
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg));
    transform: translateY(-2px);
    box-shadow:
      inset 0 1px 0 var(--theme-panel-inset),
      0 14px 24px var(--theme-shadow-medium);
  }

  &:active {
    transform: scale(0.96);
  }
}

.generate-config-panel .upload-add-icon {
  color: currentColor;
}

.generate-config-panel .upload-add-group {
  position: relative;
  z-index: 4;
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
}

.generate-config-panel .upload-add-group > .upload-add:hover {
  transform: none;
}

.generate-config-panel .upload-add-extras {
  position: absolute;
  left: 100%;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-left: 8px;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
}

.generate-config-panel .upload-add-group:hover .upload-add-extras,
.generate-config-panel .upload-add-group:focus-within .upload-add-extras,
.generate-config-panel .upload-add-group.is-picking .upload-add-extras {
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}

.generate-config-panel .upload-add-group.has-thumbs .upload-add-extras {
  left: auto;
  right: 0;
  top: 100%;
  padding-left: 0;
  padding-top: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  max-width: min(340px, 100cqw);
}

.generate-config-panel .upload-add-extra {
  padding: 6px;
  font-size: 11px;
  line-height: 1.25;
  text-align: center;

  :deep(.anticon),
  :deep(.nav-generate-image-icon),
  :deep(.sketch-board-icon) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    width: 20px;
    height: 20px;

    svg {
      display: block;
      width: 20px;
      height: 20px;
    }
  }

  :deep(.sketch-board-icon),
  :deep(.sketch-board-icon svg) {
    width: 17px;
    height: 17px;
    font-size: 17px;
  }
}

.generate-config-panel .upload-add-from-generated.active {
  border-color: var(--theme-accent);
  color: var(--theme-accent-text);
}

.generate-config-panel .upload-add-assets span {
  white-space: nowrap;
}

@media (hover: none) {
  .generate-config-panel .upload-add-group {
    gap: 8px;
  }

  .generate-config-panel .upload-add-extras {
    position: static;
    left: auto;
    top: auto;
    padding-left: 0;
    opacity: 1;
    visibility: visible;
    pointer-events: auto;
  }
}

.generate-config-panel .ref-upload-block.is-reference-drag-over .upload-add {
  border-color: var(--theme-accent);
  color: var(--theme-accent-text);
  transform: translateY(-2px);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 14px 24px var(--theme-shadow-medium);
}

/* --- Fields --- */
.field-block + .field-block {
  margin-top: 12px;
}

.field-block label {
  display: block;
  margin-bottom: var(--config-title-gap);
  color: var(--config-title-color);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.4;
}

.setting-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: var(--config-title-gap);
}

.setting-label-row label {
  margin-bottom: 0;
}

.model-help-group {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
}

.model-help {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  cursor: pointer;
}

.model-help-trigger {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  padding: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  cursor: pointer;
  transition: color var(--motion-duration-fast) var(--motion-ease-soft);
}

.model-help:hover .model-help-trigger {
  color: var(--theme-accent-text-hover);
}

.model-help-grid {
  display: grid;
  grid-template-columns: 1.12fr 12px 1.2fr 20px 0.72fr 6px 1.8fr;
  gap: 0;
  padding: 12px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 13px;
  line-height: 1.55;
}

.model-help-grid > div:nth-child(2) {
  grid-column: 3;
}

.model-help-grid > div:nth-child(3) {
  grid-column: 5;
}

.model-help-grid > div:nth-child(4) {
  grid-column: 7;
}

.model-help-grid:first-child {
  border-top: none;
  padding-top: 0;
}

.model-help-grid:last-child {
  padding-bottom: 0;
}

.model-help-grid-head {
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
  line-height: 1.35;
}

.generate-config-panel .flat-select {
  width: 100%;
  background: var(--theme-field-bg, var(--theme-control-bg));
  border-radius: 16px;
  border: 1px solid var(--theme-control-border-strong);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 8px 18px var(--theme-card-shadow);
  transition: border-color var(--motion-duration-fast) var(--motion-ease-soft), box-shadow var(--motion-duration-fast) var(--motion-ease-soft), transform var(--motion-duration-fast) var(--motion-ease-soft), background var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    border-color: var(--theme-border-strong);
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg));
    transform: translateY(-1px);
    box-shadow:
      inset 0 1px 0 var(--theme-panel-inset),
      0 12px 22px var(--theme-card-shadow-strong);
  }

  &:focus-within {
    border-color: var(--theme-border-accent);
    box-shadow:
      inset 0 1px 0 var(--theme-panel-inset),
      0 0 0 3px var(--theme-focus-ring),
      0 12px 22px var(--theme-card-shadow-strong);
  }

  :deep(.ant-select-selector) {
    height: 48px !important;
    padding: 0 15px !important;
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    border-radius: 16px !important;
    font-weight: 600;
    color: var(--theme-title);
  }

  :deep(.ant-select-selection-item) {
    line-height: 48px !important;
  }

  :deep(.ant-select-arrow) {
    color: var(--text-muted);
  }

  :deep(.ant-select-selection-placeholder) {
    color: var(--text-muted);
  }
}

.model-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.model-option-label-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-option-label {
  font-weight: 700;
  color: var(--theme-title);
}

.model-option-desc {
  font-size: 12px;
  color: var(--text-secondary);
}

.model-select-wrap {
  position: relative;
}

.flat-select.flat-select-has-badge {
  :deep(.ant-select-selector) {
    padding-right: 86px !important;
  }
}

.model-new-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: linear-gradient(135deg, #ff8a34, #ff5f6d);
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  line-height: 1;
  box-shadow: 0 6px 14px rgba(255, 106, 77, 0.24);
}

.model-new-badge-selected {
  position: absolute;
  top: 50%;
  right: 34px;
  transform: translateY(-50%);
  pointer-events: none;
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

.generate-action-row {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  margin-top: 10px;
}

.generate-action-row .generate-btn {
  margin-top: 0;
  width: 100%;
}

@media (min-width: 961px) {
  @container generate-footer (max-width: 380px) {
    .generate-action-row {
      grid-template-columns: minmax(0, 1fr) max-content;
    }

    .generate-action-row .generate-btn {
      width: auto;
      min-width: max-content;
      white-space: nowrap;
    }

    .generate-action-row .generate-btn-secondary {
      width: 100%;
      min-width: 0;
      overflow: hidden;
    }
  }
}

.generate-btn.generate-btn-secondary {
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
  border: 1px solid var(--theme-panel-border-strong) !important;
  box-shadow: 0 14px 24px var(--theme-shadow-soft) !important;

  &:hover,
  &:focus {
    background: var(--theme-control-hover-bg) !important;
    color: var(--theme-accent-text-hover) !important;
    border-color: var(--theme-border-strong) !important;
    box-shadow: 0 16px 28px var(--theme-shadow-medium) !important;
  }

  &:disabled {
    background: var(--theme-control-hover-bg) !important;
    border-color: transparent !important;
    color: var(--text-muted) !important;
    box-shadow: none !important;
  }
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

.reverse-preview-shell {
  position: relative;
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  cursor: zoom-in;
  transition: transform var(--motion-duration-base) var(--motion-ease-soft), box-shadow var(--motion-duration-base) var(--motion-ease-soft);
}

.reverse-preview-image {
  width: 100%;
  display: block;
  max-height: 420px;
  object-fit: contain;
  transition: transform var(--motion-duration-hover) var(--motion-ease-enter);
}

.reverse-preview-shell:hover {
  transform: translateY(-2px);
  box-shadow: 0 18px 30px var(--theme-shadow-soft);
}

.reverse-preview-shell:hover .reverse-preview-image {
  transform: scale(1.01);
}

.reverse-result-card {
  margin-top: 2px;
  padding: 16px;
  border-radius: 20px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg);
}

.reverse-result-input {
  :deep(textarea) {
    min-height: 180px;
    font-family: "SF Mono", "Consolas", "Monaco", monospace;
    line-height: 1.7;
  }
}

.reverse-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.reverse-action-btn {
  height: 42px;
  border-radius: 14px;
  font-weight: 700;
  border: none !important;
  box-shadow: none !important;

  &:hover,
  &:focus {
    transform: translateY(-2px);
  }

  &:active {
    transform: scale(0.97);
  }
}

.reverse-action-btn-secondary {
  color: var(--theme-accent-text) !important;
  background: var(--theme-panel-bg-strong) !important;
  border: 1px solid var(--theme-panel-border-strong) !important;

  &:hover,
  &:focus {
    color: var(--theme-accent-text-hover) !important;
    background: var(--theme-control-hover-bg) !important;
    border-color: var(--theme-border-strong) !important;
  }
}

.reverse-action-btn-primary {
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  border: none !important;
  box-shadow: 0 14px 24px var(--theme-shadow-strong) !important;

  &:hover,
  &:focus {
    background: var(--primary-dark) !important;
    box-shadow: 0 16px 28px var(--theme-shadow-strong) !important;
  }
}

.reverse-result-placeholder {
  padding: 22px 18px;
  border-radius: 18px;
  border: 1px dashed var(--theme-panel-border-strong);
  background: rgba(var(--theme-page-base-rgb), 0.48);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.8;
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

.reverse-preview-shell:hover .canvas-remove-btn,
.reverse-preview-shell:focus-within .canvas-remove-btn,
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

.tool-btn-icon {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  stroke-width: 1.9;
  stroke-linecap: round;
  stroke-linejoin: round;
  fill: none;
  flex-shrink: 0;
}

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

.inpaint-prompt-block {
  margin-top: 6px;
}

/* --- Results --- */
.result-panel {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 16px 18px 18px;
  background: var(--theme-panel-bg);
  background-image: none;
}

.result-panel.config-panel-is-collapsed {
  animation: result-panel-slide-left-in var(--motion-duration-slide) var(--motion-ease-enter) both;
}

.result-config-expand-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 999px;
  background: rgba(var(--theme-surface-strong-rgb), 0.92);
  color: var(--theme-accent-text);
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  box-shadow: 0 10px 20px var(--theme-shadow-soft);
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-visible {
    color: var(--theme-accent-text-hover);
    border-color: var(--theme-border-strong);
    background: rgba(var(--theme-surface-strong-rgb), 0.98);
    transform: translateY(-1px);
    box-shadow: 0 14px 24px var(--theme-shadow-soft);
  }

  &:active {
    transform: scale(0.97);
  }
}

.result-filter-trigger {
  position: relative;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--theme-accent-text);
  font-size: 22px;
  cursor: pointer;
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    color var(--motion-duration-hover) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-visible,
  &.active {
    color: var(--theme-accent-text-hover);
    background: rgba(var(--theme-surface-strong-rgb), 0.86);
    transform: translateY(-1px);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }
}

.result-filter-count {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 17px;
  height: 17px;
  padding: 0 5px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--theme-accent-contrast);
  background: var(--theme-accent);
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
  box-shadow: 0 6px 12px var(--theme-shadow-strong);
}

.result-view-trigger {
  font-size: 21px;
}

.generate-view-panel {
  width: 260px;
  color: var(--theme-title);
}

.generate-view-section + .generate-view-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--theme-panel-border);
}

.generate-view-panel-title {
  color: var(--theme-title);
  font-size: 15px;
  font-weight: 800;
  line-height: 1.4;
}

.generate-view-panel-desc {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.generate-card-aspect-options {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.generate-card-aspect-option {
  min-height: 56px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 6px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-visible,
  &.active {
    color: var(--theme-title);
    border-color: var(--theme-border-strong);
    background: var(--theme-control-hover-bg);
  }

  &.active {
    color: var(--theme-accent-contrast);
    border-color: transparent;
    background: var(--theme-accent);
  }
}

.generate-card-aspect-icon {
  display: block;
  border: 2px solid currentColor;
  border-radius: 3px;
  opacity: 0.9;
}

.generate-card-aspect-icon.aspect-1-1 {
  width: 16px;
  height: 16px;
}

.generate-card-aspect-icon.aspect-2-3 {
  width: 13px;
  height: 20px;
}

.generate-card-aspect-icon.aspect-3-2 {
  width: 20px;
  height: 13px;
}

.generate-card-aspect-icon.aspect-3-4 {
  width: 15px;
  height: 20px;
}

.generate-card-aspect-icon.aspect-4-3 {
  width: 20px;
  height: 15px;
}

.generate-card-aspect-icon.aspect-16-9 {
  width: 22px;
  height: 13px;
}

.generate-card-aspect-icon.aspect-9-16 {
  width: 13px;
  height: 22px;
}

.generate-view-column-group {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;

  :deep(.ant-radio-button-wrapper) {
    height: 34px;
    padding: 0 8px;
    border: 1px solid var(--theme-control-border) !important;
    border-radius: 10px !important;
    background: var(--theme-control-bg);
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 700;
    line-height: 32px;
    text-align: center;
    box-shadow: none !important;
  }

  :deep(.ant-radio-button-wrapper::before) {
    display: none !important;
  }

  :deep(.ant-radio-button-wrapper-checked) {
    color: var(--theme-accent-contrast);
    border-color: transparent !important;
    background: var(--theme-accent);
  }
}

.generate-filter-panel {
  width: min(480px, calc(100vw - 32px));
  padding: 2px;
  color: var(--theme-title);
}

.generate-filter-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.generate-filter-panel-title {
  color: var(--theme-title);
  font-size: 15px;
  font-weight: 800;
  line-height: 1.4;
}

.generate-filter-panel-desc {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.generate-filter-reset {
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 999px;
  background: var(--theme-panel-bg-soft);
  color: var(--theme-accent-text);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition:
    color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-visible {
    color: var(--theme-accent-text-hover);
    border-color: var(--theme-border-strong);
    background: var(--theme-control-hover-bg);
  }
}

.generate-filter-expired-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding: 11px 12px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
}

.generate-filter-expired-row + .generate-filter-grid {
  margin-top: 2px;
}

.generate-filter-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 11px;
}

.generate-filter-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 7px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.generate-filter-field-third {
  grid-column: span 2;
}

.generate-filter-field-half {
  grid-column: span 3;
}

.generate-filter-control,
.generate-filter-input {
  width: 100%;
}

.generate-filter-control :deep(.ant-select-selector),
.generate-filter-input.ant-input-affix-wrapper {
  min-height: 36px !important;
  border-radius: 12px !important;
  border-color: var(--theme-control-border) !important;
  background: var(--theme-control-bg) !important;
  box-shadow: none !important;
}

.generate-filter-date-card {
  margin-top: 12px;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid var(--theme-panel-border);
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
}

.generate-filter-date-title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--theme-title);
  font-size: 15px;
  font-weight: 800;
  line-height: 1.3;

  .anticon {
    color: #27a7df;
    font-size: 20px;
  }
}

.generate-filter-date-presets {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.generate-filter-date-preset {
  min-height: 34px;
  padding: 0 11px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: var(--theme-control-hover-bg);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-visible,
  &.active {
    color: var(--theme-title);
    border-color: var(--theme-border-strong);
    background: var(--theme-panel-bg-strong);
  }

  &:active {
    transform: scale(0.98);
  }
}

.generate-filter-custom-date-row {
  display: grid;
  grid-template-columns: minmax(128px, 0.78fr) minmax(0, 1.22fr);
  gap: 8px;
  margin-top: 8px;
}

.generate-filter-date-custom {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.generate-filter-date-picker.ant-picker {
  width: 100%;
  min-height: 34px;
  border-radius: 10px !important;
  border-color: var(--theme-control-border) !important;
  background: var(--theme-control-bg) !important;
  box-shadow: none !important;
}

:global(.generate-filter-popover .ant-popover-inner) {
  border-radius: 20px;
  background: var(--theme-modal-bg);
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 22px 48px var(--theme-shadow-medium);
}

:global(.generate-view-popover .ant-popover-inner) {
  border-radius: 18px;
  background: var(--theme-modal-bg);
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 18px 38px var(--theme-shadow-medium);
}

:global(.generate-filter-popover .ant-popover-inner-content) {
  padding: 16px;
}

:global(.generate-view-popover .ant-popover-inner-content) {
  padding: 14px;
}

.result-canvas-entry-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: auto;
  min-height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: 999px;
  cursor: pointer;
  color: var(--theme-accent-contrast);
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.02em;
  white-space: nowrap;
  background: linear-gradient(135deg, var(--theme-accent-strong) 0%, var(--theme-accent) 100%);
  box-shadow:
    0 12px 24px var(--theme-shadow-strong),
    0 0 0 1px rgba(255, 255, 255, 0.18) inset;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    filter var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-visible {
    transform: translateY(-1px);
    filter: brightness(1.03);
    box-shadow:
      0 16px 28px var(--theme-shadow-strong),
      0 0 0 1px rgba(255, 255, 255, 0.24) inset;
  }

  &:active {
    transform: translateY(0) scale(0.985);
  }
}

.result-canvas-entry-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  filter: var(--theme-nav-icon-active-filter);
}

.result-canvas-entry-text {
  line-height: 1;
}

.result-canvas-entry-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset;
}

.result-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px 12px;
}

.result-head-center {
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}

.result-head-main {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.result-panel-head {
  margin-bottom: 2px;
}

.result-tips {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 0;
}

.result-tip-line {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.result-tip-highlight {
  display: inline;
  font-size: 18px;
  font-weight: 800;
  line-height: inherit;
  color: inherit;
}

.result-head-meta {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.result-head-meta :deep(.history-filter-control) {
  flex: 0 1 auto;
  min-width: 0;
}

.result-head-main :deep(.history-filter-board) {
  width: 148px;
  flex: 0 0 auto;
}

.result-head-main :deep(.history-filter-board .ant-select-selection-item) {
  font-weight: 700;
}

.result-head-meta :deep(.history-filter-columns) {
  width: 76px;
}

.generate-board-dropdown-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border-top: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
}

.generate-board-dropdown-action {
  width: 100%;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  padding: 0 10px;
  border: 0;
  border-radius: 10px;
  color: var(--theme-accent-text);
  background: var(--theme-panel-bg-strong);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}

.generate-board-dropdown-action:hover:not(:disabled) {
  color: var(--theme-accent-text-hover);
  background: var(--theme-control-hover-bg);
}

.generate-board-dropdown-action:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.result-head-meta :deep(.history-filter-columns.ant-select) {
  height: 30px;

  .ant-select-selector {
    height: 30px !important;
    min-height: 30px !important;
    padding: 0 8px !important;
    border-radius: 999px;
  }

  .ant-select-selection-search-input {
    height: 28px !important;
  }

  .ant-select-selection-item,
  .ant-select-selection-placeholder {
    line-height: 28px !important;
    font-size: 12px;
  }

  &:not(.ant-select-disabled):hover .ant-select-selector,
  &.ant-select-focused .ant-select-selector {
    transform: none;
  }
}

.result-retain-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 14px;
  border-radius: 999px;
  background: linear-gradient(180deg, rgba(var(--theme-surface-strong-rgb), 0.96), rgba(var(--theme-page-base-rgb), 0.92));
  border: 1px solid var(--theme-panel-border);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
  box-shadow: 0 10px 20px var(--theme-shadow-soft);
}

.result-retain-badge > .result-retain-text {
  display: inline-flex;
  align-items: center;
}

.result-retain-badge .result-tip-highlight {
  margin: 0 4px;
  line-height: 1;
  color: #16a34a;
}

.result-retain-icon {
  display: inline-flex;
  align-items: center;
  color: var(--theme-icon, var(--theme-accent, #ffab24));
  font-size: 16px;
}

.result-tip-divider {
  margin: 0 8px;
  color: var(--theme-text-secondary, #8b7457);
}

.result-list {
  display: grid;
  align-items: start;
  grid-template-columns: repeat(var(--generate-grid-columns, 4), minmax(0, 1fr));
  gap: 16px;
  margin-top: 12px;
  background: var(--theme-panel-bg);
  background-image: none;
}

.result-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 14px;
  padding-right: 4px;
  display: flex;
  flex-direction: column;
  background: var(--theme-panel-bg);
  background-image: none;
  scrollbar-width: thin;
  scrollbar-color: var(--theme-border-strong) transparent;

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    border-radius: 999px;
    border: 2px solid transparent;
    background-clip: padding-box;
    background: var(--theme-border-strong);
  }

  &:hover::-webkit-scrollbar-thumb {
    background: var(--theme-accent);
  }
}

.result-list-footnote {
  margin: 12px 4px 2px;
  padding: 0 2px 4px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.7;
  text-align: center;
}

.result-load-more-tip {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
}

.result-load-more-action {
  margin-top: 12px;
  width: 100%;
}

.result-load-more-btn {
  width: 100% !important;
  height: 42px !important;
  border-radius: 14px !important;
  font-size: 14px !important;
  font-weight: 700 !important;
  color: var(--theme-accent-text) !important;
  background: var(--theme-panel-bg-strong) !important;
  border: 1px solid var(--theme-panel-border-strong) !important;
  box-shadow: none !important;

  &:hover,
  &:focus {
    color: var(--theme-accent-text-hover) !important;
    background: var(--theme-control-hover-bg) !important;
    border-color: var(--theme-border-strong) !important;
  }
}

.result-load-more-anchor {
  width: 100%;
  height: 1px;
  margin-top: 1px;
}

.result-card {
  display: block;
  width: 100%;
  margin: 0;
  position: relative;
  border-radius: 16px;
  background: transparent;
  transition: transform var(--motion-duration-hover) var(--motion-ease-enter);

  &:hover {
    transform: translateY(-4px);
  }

  &:active {
    transform: scale(0.992);
  }
}

.result-frame {
  position: relative;
  aspect-ratio: var(--generate-result-card-aspect, 1 / 1);
  min-height: 0;
  border-radius: 16px;
  overflow: hidden;
  border: 1px dashed var(--theme-panel-border);
  background: #ffffff;
  box-shadow: 0 12px 24px var(--theme-shadow-soft);
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    box-shadow var(--motion-duration-hover) var(--motion-ease-soft),
    border-color var(--motion-duration-hover) var(--motion-ease-soft);

  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: contain;
    object-position: center;
    box-sizing: border-box;
    background: transparent;
    transition: transform var(--motion-duration-emphasis) var(--motion-ease-enter);
  }

  &.clickable {
    cursor: pointer;
  }

  &.pending {
    background:
      linear-gradient(180deg, rgba(255, 252, 246, 0.24), rgba(255, 248, 238, 0.34)),
      linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
  }

  &.pending::before {
    content: "";
    position: absolute;
    inset: 0;
    background: var(--result-pending-bg-image) center / cover no-repeat;
    opacity: 0.5;
    pointer-events: none;
  }

  &.failed {
    border-color: rgba(214, 87, 75, 0.34);
    background: linear-gradient(180deg, #fff0ed, #ffe1db);
    box-shadow: 0 14px 26px rgba(214, 87, 75, 0.16);
  }
}

.result-card:hover .result-frame.clickable {
  border-color: var(--theme-border-strong);
  box-shadow: 0 16px 28px var(--theme-shadow-medium);
}

.result-card:hover .result-frame.clickable img {
  transform: scale(1.03);
}

.result-card.is-picking-reference .result-actions,
.result-card.is-picking-reference .result-top-actions {
  display: none;
}

.result-card.is-picking-reference:hover .result-actions,
.result-card.is-picking-reference:focus-within .result-actions,
.result-card.is-picking-reference:hover .result-more-trigger.icon-chip,
.result-card.is-picking-reference:focus-within .result-more-trigger.icon-chip,
.result-card.is-picking-reference:hover .result-delete-trigger.icon-chip,
.result-card.is-picking-reference:focus-within .result-delete-trigger.icon-chip {
  opacity: 0 !important;
  pointer-events: none !important;
}

.result-add-reference-btn {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.result-add-reference-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.88);
  color: #111;
  font-size: 28px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.result-add-reference-btn:hover .result-add-reference-icon {
  transform: scale(1.06);
  background: #fff;
}

.result-add-reference-btn.is-added .result-add-reference-icon {
  background: var(--theme-accent);
  color: #fff;
}

.result-pick-reference-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 6px 0 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--theme-accent) 10%, var(--theme-panel-bg));
  border: 1px solid color-mix(in srgb, var(--theme-accent) 28%, var(--theme-panel-border));
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 600;
}

.result-pick-reference-done {
  flex: 0 0 auto;
  padding: 4px 12px;
  border: 0;
  border-radius: 999px;
  background: var(--theme-accent);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.failed-image {
  object-fit: contain !important;
  padding: 28px;
  background: linear-gradient(180deg, #fff2ef, #ffdcd5);
  opacity: 0.96;
}

.result-preview-notice {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  text-align: center;
  color: var(--theme-text-secondary);
  font-size: 13px;
  line-height: 1.7;
  background:
    linear-gradient(180deg, rgba(var(--theme-surface-strong-rgb), 0.78), rgba(var(--theme-page-base-rgb), 0.92)),
    linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg));
}

.result-actions {
  position: absolute;
  inset: auto 12px 12px auto;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  max-width: calc(100% - 24px);
  gap: 8px;
  opacity: 0;
  transform: translateY(6px);
  pointer-events: none;
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);

  .icon-chip {
    border: 1px solid rgba(255, 240, 214, 0.18) !important;
    background: rgba(76, 52, 26, 0.58) !important;
    color: #fff7ea !important;
    box-shadow: 0 10px 20px rgba(34, 22, 10, 0.22);
    backdrop-filter: blur(10px);

    &:hover,
    &:focus {
      background: rgba(76, 52, 26, 0.78) !important;
      border-color: rgba(255, 240, 214, 0.26) !important;
      color: #fffdfa !important;
      box-shadow: 0 14px 26px rgba(34, 22, 10, 0.28);
    }

    &:disabled {
      border-color: rgba(255, 240, 214, 0.08) !important;
      background: rgba(56, 40, 24, 0.34) !important;
      color: rgba(255, 247, 234, 0.45) !important;
      box-shadow: none;
      opacity: 1;
    }
  }

}

.result-top-actions {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 3;
  display: flex;
  gap: 8px;

  .icon-chip,
  .ant-btn,
  button {
    cursor: pointer;
  }

  .icon-chip:disabled,
  .ant-btn:disabled,
  button:disabled {
    cursor: not-allowed;
  }
}

.frame-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #8d7758;
  font-size: 14px;
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.1), rgba(255, 250, 240, 0.16));
  backdrop-filter: blur(0.25px);

  &.error {
    background: linear-gradient(
      180deg,
      rgba(255, 233, 228, 0.42),
      rgba(255, 221, 214, 0.92)
    );
    color: #c9493c;
  }
}

.frame-state-subtext {
  margin-top: -4px;
  color: rgba(141, 119, 88, 0.78);
  font-size: 12px;
}

.result-more-trigger.icon-chip {
  opacity: 0;
  transform: translateY(-6px);
  pointer-events: none;
  border: 1px solid rgba(255, 240, 214, 0.18) !important;
  background: rgba(76, 52, 26, 0.58) !important;
  color: #fff7ea !important;
  box-shadow: 0 10px 20px rgba(34, 22, 10, 0.22);
  backdrop-filter: blur(10px);
  transition:
    opacity var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus {
    background: rgba(76, 52, 26, 0.78) !important;
    border-color: rgba(255, 240, 214, 0.26) !important;
    color: #fffdfa !important;
    box-shadow: 0 14px 26px rgba(34, 22, 10, 0.28);
  }
}

.result-delete-trigger.icon-chip {
  opacity: 0;
  transform: translateY(-6px);
  pointer-events: none;
  border-color: rgba(255, 214, 209, 0.18) !important;
  background: rgba(180, 58, 43, 0.88) !important;
  color: #fff5f2 !important;
  box-shadow: 0 10px 22px rgba(140, 40, 28, 0.24);

  &:hover,
  &:focus {
    background: rgba(201, 73, 60, 0.98) !important;
    border-color: rgba(255, 224, 220, 0.24) !important;
    color: #fff7f5 !important;
    box-shadow: 0 14px 26px rgba(140, 40, 28, 0.34);
  }
}

.result-template-trigger.icon-chip {
  background: rgba(121, 80, 26, 0.64) !important;
  color: #fff4d8 !important;

  &:hover,
  &:focus {
    background: rgba(143, 94, 30, 0.82) !important;
    color: #fffaf0 !important;
  }
}

.result-inpaint-trigger.icon-chip {
  background: rgba(96, 74, 34, 0.68) !important;
  border-color: rgba(255, 226, 170, 0.22) !important;
  color: #fff2d4 !important;
  box-shadow: 0 10px 22px rgba(53, 34, 13, 0.24);

  &:hover,
  &:focus {
    background: rgba(122, 92, 40, 0.86) !important;
    border-color: rgba(255, 232, 188, 0.3) !important;
    color: #fffaf0 !important;
    box-shadow: 0 14px 26px rgba(53, 34, 13, 0.3);
  }
}

.result-more-icon {
  font-size: 14px;
}

.result-more-trigger-failed.icon-chip {
  border-color: rgba(255, 214, 209, 0.18) !important;
  background: rgba(180, 58, 43, 0.88) !important;
  color: #fff5f2 !important;
  box-shadow: 0 10px 22px rgba(140, 40, 28, 0.24);

  &:hover,
  &:focus {
    background: rgba(201, 73, 60, 0.98) !important;
    border-color: rgba(255, 224, 220, 0.24) !important;
    color: #fff7f5 !important;
    box-shadow: 0 14px 26px rgba(140, 40, 28, 0.34);
  }
}

.result-card:hover .result-actions,
.result-card:focus-within .result-actions {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.result-card:hover .result-more-trigger.icon-chip,
.result-card:focus-within .result-more-trigger.icon-chip,
.result-card:hover .result-delete-trigger.icon-chip,
.result-card:focus-within .result-delete-trigger.icon-chip {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.icon-chip {
  width: 32px;
  height: 32px;
  border-radius: 999px !important;
  border: none !important;
  background: rgba(255, 255, 255, 0.92) !important;
  color: #684825 !important;
  box-shadow: 0 10px 16px rgba(0, 0, 0, 0.1);
  font-size: 14px !important;
  cursor: pointer;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus {
    transform: translateY(-1px);
    box-shadow: 0 14px 22px rgba(0, 0, 0, 0.12);
  }

  &:active {
    transform: scale(0.93);
  }

  &:disabled {
    cursor: not-allowed;
  }

  &.danger {
    color: #d6574b !important;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .icon-chip {
  background: rgba(var(--theme-surface-strong-rgb), 0.92) !important;
  border: 1px solid var(--theme-panel-border) !important;
  color: var(--theme-accent-text) !important;
  box-shadow: 0 10px 16px var(--theme-shadow-soft);

  &:hover,
  &:focus {
    background: var(--theme-surface-strong) !important;
    color: var(--theme-accent-text-hover) !important;
    border-color: var(--theme-border-strong) !important;
    box-shadow: 0 14px 22px var(--theme-shadow-medium);
  }

  &.danger {
    color: #de8f84 !important;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-delete-trigger.icon-chip,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-more-trigger-failed.icon-chip {
  border-color: rgba(222, 143, 132, 0.24) !important;
  background: rgba(185, 56, 42, 0.82) !important;
  color: #fff5f2 !important;
  box-shadow: 0 12px 24px rgba(140, 40, 28, 0.3);

  &:hover,
  &:focus {
    background: rgba(185, 56, 42, 0.92) !important;
    border-color: rgba(240, 176, 166, 0.3) !important;
    color: #fff7f5 !important;
    box-shadow: 0 16px 28px rgba(140, 40, 28, 0.38);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-more-trigger.icon-chip {
  background: rgba(var(--theme-page-base-rgb), 0.82) !important;
  border-color: var(--theme-panel-border) !important;
  color: var(--theme-accent-contrast) !important;
  box-shadow: 0 10px 20px var(--theme-shadow-medium);
}

html[data-theme="midnight"] .generate-page .result-more-trigger.icon-chip {
  color: #ffffff !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-more-trigger.icon-chip:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-more-trigger.icon-chip:focus {
  background: rgba(var(--theme-page-base-rgb), 0.94) !important;
  border-color: var(--theme-border-strong) !important;
  color: #ffffff !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-template-trigger.icon-chip {
  background: rgba(143, 94, 30, 0.72) !important;
  border-color: rgba(255, 218, 150, 0.24) !important;
  color: #fff4d8 !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-template-trigger.icon-chip:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-template-trigger.icon-chip:focus {
  background: rgba(168, 112, 38, 0.86) !important;
  border-color: rgba(255, 226, 170, 0.34) !important;
  color: #fffaf0 !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-inpaint-trigger.icon-chip {
  background: rgba(120, 88, 34, 0.76) !important;
  border-color: rgba(255, 224, 166, 0.24) !important;
  color: #fff1cc !important;
  box-shadow: 0 12px 24px rgba(48, 30, 9, 0.3);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-inpaint-trigger.icon-chip:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-inpaint-trigger.icon-chip:focus {
  background: rgba(148, 108, 40, 0.9) !important;
  border-color: rgba(255, 231, 182, 0.34) !important;
  color: #fffaf0 !important;
  box-shadow: 0 16px 28px rgba(48, 30, 9, 0.36);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-more-trigger-failed.icon-chip {
  background: rgba(185, 56, 42, 0.82) !important;
  border-color: rgba(222, 143, 132, 0.28) !important;
  color: #fff5f2 !important;
}

/* --- Empty state --- */
.result-empty {
  flex: 1;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 20px 28px;
  animation: generate-fade-up var(--motion-duration-reveal) var(--motion-ease-enter) 0.2s both;
}

.result-empty-copy {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  max-width: 420px;
  text-align: center;
}

.result-loading-state {
  gap: 8px;
  text-align: center;
}

.empty-illustration-shell {
  width: min(100%, 220px);
  margin-bottom: 8px;
}

.empty-illustration {
  display: block;
  width: 100%;
  height: auto;
  animation: generate-empty-float 8s ease-in-out infinite;
  transform-origin: center center;
  filter: drop-shadow(0 18px 34px rgba(217, 238, 243, 0.28));
}

.empty-title {
  margin-top: 8px;
  font-size: 17px;
  font-weight: 700;
  color: var(--theme-title);
}

.empty-desc {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
}

/* --- History dialog --- */
.history-empty {
  text-align: center;
  padding: 32px 0;
  color: var(--text-secondary);
  font-size: 14px;
  animation: generate-fade-up var(--motion-duration-reveal-fast) var(--motion-ease-enter) both;
}

.history-list {
  max-height: 420px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  cursor: pointer;
  transition:
    background var(--motion-duration-micro) var(--motion-ease-soft),
    transform var(--motion-duration-micro) var(--motion-ease-soft),
    box-shadow var(--motion-duration-micro) var(--motion-ease-soft);

  &:hover {
    background: var(--theme-panel-bg-soft);
    transform: translateY(-1px);
    box-shadow: 0 10px 18px var(--theme-shadow-soft);
  }

  & + & {
    border-top: 1px solid var(--theme-border);
  }
}

.history-thumb {
  width: 52px;
  height: 52px;
  flex-shrink: 0;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);

  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: cover;
  }
}

.history-content {
  flex: 1;
  min-width: 0;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.history-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text);
  font-size: 11px;
  font-weight: 700;
}

.history-text {
  font-size: 13px;
  color: var(--theme-title);
  line-height: 1.6;
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.history-del {
  flex-shrink: 0;
  color: var(--text-muted) !important;
  margin-top: 2px;
  transition: transform var(--motion-duration-press) var(--motion-ease-soft), color var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    color: #d6574b !important;
    transform: scale(1.05);
  }
}

.generate-result-enter-active,
.generate-result-leave-active {
  transition:
    opacity var(--motion-duration-emphasis) var(--motion-ease-soft),
    transform var(--motion-duration-emphasis-plus) var(--motion-ease-enter);
  transition-delay: var(--generate-result-delay, 0ms);
  will-change: opacity, transform;
}

.generate-result-enter-from,
.generate-result-leave-to {
  opacity: 0;
  transform: translate3d(0, 22px, 0) scale(0.985);
}

.generate-result-move {
  transition: transform var(--motion-duration-reveal-fast) var(--motion-ease-enter);
  will-change: transform;
}

.history-item-enter-active,
.history-item-leave-active {
  transition:
    opacity var(--motion-duration-base) var(--motion-ease-soft),
    transform var(--motion-duration-emphasis) var(--motion-ease-enter);
  transition-delay: var(--history-item-delay, 0ms);
}

.history-item-enter-from,
.history-item-leave-to {
  opacity: 0;
  transform: translate3d(0, 12px, 0);
}

.history-item-move {
  transition: transform var(--motion-duration-hover-slow) var(--motion-ease-enter);
}

.generate-panel-slide-enter-active,
.generate-panel-slide-leave-active {
  transition:
    opacity var(--motion-duration-slide) var(--motion-ease-soft),
    transform var(--motion-duration-slide) var(--motion-ease-enter),
    filter var(--motion-duration-slide) var(--motion-ease-soft);
}

.generate-panel-slide-enter-from,
.generate-panel-slide-leave-to {
  opacity: 0;
  transform: translate3d(0, -12px, 0) scale(0.985);
  filter: blur(6px);
}

@media (prefers-reduced-motion: reduce) {
  .generate-page,
  .generate-workbench,
  .left-col,
  .result-panel,
  .result-empty,
  .history-empty {
    animation: none !important;
  }

  .config-section,
  .history-btn,
  .prompt-library-btn,
  .generate-config-panel .upload-thumb,
  .generate-config-panel .upload-thumb img,
  .generate-config-panel .upload-add,
  .generate-config-panel .flat-select,
  .generate-btn,
  .source-upload-empty,
  .reverse-preview-shell,
  .reverse-preview-image,
  .reverse-action-btn,
  .repaint-status-card,
  .canvas-remove-btn,
  .tool-btn,
  .result-card,
  .result-frame,
  .result-frame img,
  .empty-illustration,
  .icon-chip,
  .history-item,
  .history-del,
  .generate-result-enter-active,
  .generate-result-leave-active,
  .generate-result-move,
  .history-item-enter-active,
  .history-item-leave-active,
  .history-item-move,
  .config-panel-slide-enter-active,
  .config-panel-slide-leave-active,
  .generate-panel-slide-enter-active,
  .generate-panel-slide-leave-active,
  .mode-switch-btn,
  .result-config-expand-btn {
    transition: none !important;
  }
}

:deep(.generate-dropdown.ant-select-dropdown) {
  border-radius: 14px;
  padding: 6px;
  background: var(--theme-dropdown-bg);
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 18px 32px var(--theme-shadow-medium);
}

:deep(.generate-dropdown .ant-select-item) {
  border-radius: 10px;
}

:deep(.generate-dropdown .ant-select-item-option-active:not(.ant-select-item-option-disabled)) {
  background: var(--theme-dropdown-hover-bg);
}

:deep(.generate-dropdown .ant-select-item-option-selected:not(.ant-select-item-option-disabled)) {
  background: var(--theme-dropdown-selected-bg);
  color: var(--theme-dropdown-selected-text);
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 960px) {
  .generate-page {
    width: 100%;
    overflow-x: hidden;
    height: auto;
  }

  .generate-workbench {
    grid-template-columns: 1fr;
    width: 100%;
    max-width: 100%;
    min-width: 0;
    height: auto;
  }

  .left-col,
  .generate-mode-shell,
  .settings-panel,
  .work-panel {
    width: 100%;
    max-width: 100%;
    min-width: 0;
  }

  .left-col {
    min-width: var(--generate-config-min-width);
    max-width: 100%;
  }

  .result-panel {
    min-height: auto;
    height: auto;
    scroll-margin-top: 80px;
  }

  .result-body {
    overflow-y: visible;
    padding-right: 0;
  }

  .generate-mode-shell {
    min-height: unset;
  }

  .settings-panel,
  .generate-mode-shell {
    height: auto;
  }

  .settings-scroll {
    overflow-y: visible;
    padding: 0;
  }

  .generate-mode-switch {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: nowrap;
  }

  .mode-switch-btn.tool,
  .tool-trigger {
    width: auto;
    min-width: auto;
    padding: 0 10px;
    justify-content: space-between;
    gap: 8px;
  }

  .mode-switch-trigger-value,
  .mode-switch-trigger-arrow {
    display: inline-flex;
  }

  .generate-action-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  }

  .generate-action-row .generate-btn {
    width: 100%;
    min-width: 0;
  }

  .mode-switch-cluster:first-child {
    flex: 1 1 auto;
    min-width: 0;
  }

  .mode-switch-cluster:last-child {
    flex: 0 0 auto;
    margin-left: auto;
  }

  .mode-switch-group {
    flex-wrap: nowrap;
  }

  .config-collapse-btn,
  .result-config-expand-btn,
  .panel-hint-extra {
    display: none;
  }

  .result-retain-badge {
    flex: none;
    width: 100%;
    max-width: 100%;
    height: auto;
    min-height: 0;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: none;
    box-shadow: none;
    white-space: nowrap;
    line-height: 1.4;
    font-size: 11px;
    overflow-x: auto;
  }

  .result-retain-icon {
    display: inline-flex;
    flex: 0 0 auto;
    font-size: 14px;
  }

  .result-retain-badge > .result-retain-text {
    display: inline-flex;
    flex: 0 0 auto;
    flex-direction: row;
    align-items: center;
    min-width: 0;
    white-space: nowrap;
  }

  .result-retain-clause {
    display: inline;
    max-width: none;
    white-space: nowrap;
  }

  .result-tip-divider {
    display: inline;
    margin: 0 6px;
  }

  .result-retain-badge .result-tip-highlight {
    font-size: 13px;
    margin: 0 2px;
  }
}

@media (max-width: 640px) {
  .work-panel {
    padding: 16px;
    border-radius: 20px;
  }

  .generate-config-panel {
    padding: 15px;
  }

  .generate-config-panel .settings-footer {
    z-index: 1;
    margin-top: 8px;
    padding-top: 0;
  }

  .generate-link-tip {
    gap: 8px;
  }

  .generate-action-row .generate-btn-secondary {
    font-size: 13px;
    padding-inline: 8px;
  }

  .settings-row {
    flex-direction: column;
  }

  .settings-row-inline {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
    align-items: stretch;
    gap: 10px;
  }

  .settings-row-inline .setting-item-inline {
    min-width: 0;
    gap: 6px;
  }

  .settings-row-inline .setting-item-inline label {
    white-space: normal;
  }

  .custom-size-x {
    top: calc(1.4em + 6px);
    transform: translateX(calc(-50% - 5px));
  }

  .aspect-ratio-auto-row {
    gap: 8px;
  }

  .custom-size-bottom-row {
    flex-direction: row;
    align-items: center;
    gap: 12px;
  }

  .generate-config-panel .upload-thumb,
  .generate-config-panel .upload-add {
    width: 65px;
    height: 65px;
  }

  .result-head {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
  }

  .result-head-main {
    display: contents;
  }

  .result-head-main :deep(.history-filter-board) {
    grid-column: 1;
    grid-row: 1;
    width: min(148px, calc(100% - 8px));
  }

  .result-head-meta {
    grid-column: 2;
    grid-row: 1;
    align-self: center;
    justify-self: end;
    flex-wrap: nowrap;
    gap: 6px;
  }

  .result-retain-badge {
    grid-column: 1 / -1;
    grid-row: 2;
  }

  .result-head-center {
    width: 100%;
  }

  .result-canvas-entry-btn {
    width: 100%;
    min-height: 40px;
  }

  .generate-mode-switch {
    margin-bottom: 12px;
    gap: 10px;
  }

  .mode-switch-group {
    gap: 8px;
  }

  .mode-switch-group-primary {
    gap: 8px;
  }

  .mode-switch-group-primary .mode-switch-btn {
    min-width: 0;
    flex: 1 1 0;
  }

  .mode-switch-btn.tool {
    flex: 0 0 auto;
    min-width: auto;
  }

  .tool-trigger {
    height: 42px;
    min-height: 42px;
    padding: 0 10px;
  }

  .generate-tab-label {
    gap: 6px;
    min-height: 38px;
    padding: 0 11px;
    font-size: 14px;
  }

  .mode-switch-trigger-value {
    font-size: 12px;
  }
}
</style>

<style lang="scss">
.smart-cutout-entry-tooltip {
  max-width: none;
}

.smart-cutout-entry-tooltip .ant-tooltip-inner {
  box-sizing: border-box;
  width: 264px;
  padding: 10px 12px;
}

.smart-cutout-entry-tip {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.smart-cutout-entry-tip p {
  margin: 0;
  line-height: 1.5;
}

.smart-cutout-entry-tip-img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 6px;
}

.generate-dropdown.ant-select-dropdown {
  border-radius: 14px;
  padding: 6px;
  background: var(--theme-dropdown-bg);
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 18px 32px var(--theme-shadow-medium);
}

.generate-dropdown .ant-select-item {
  border-radius: 10px;
}

.generate-dropdown .ant-select-item-option-active:not(.ant-select-item-option-disabled) {
  background: var(--theme-dropdown-hover-bg) !important;
}

.generate-dropdown .ant-select-item-option-selected:not(.ant-select-item-option-disabled) {
  background: var(--theme-dropdown-selected-bg) !important;
  color: var(--theme-dropdown-selected-text) !important;
}

.generate-dropdown .ant-select-item-option-selected:not(.ant-select-item-option-disabled) .model-option-label,
.generate-dropdown .ant-select-item-option-selected:not(.ant-select-item-option-disabled) .ant-select-item-option-content {
  color: var(--theme-dropdown-selected-text) !important;
}

.generate-dropdown .ant-select-item-option-selected:not(.ant-select-item-option-disabled) .model-option-desc {
  color: var(--theme-dropdown-selected-text) !important;
  opacity: 0.78;
}

.generate-tool-dropdown .generate-tool-menu,
.generate-tool-dropdown .ant-dropdown-menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 176px;
  padding: 10px;
  border-radius: 16px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-dropdown-bg);
  box-shadow: 0 16px 28px var(--theme-shadow-soft);
}

.generate-tool-dropdown .generate-tool-menu .ant-menu-item,
.generate-tool-dropdown .ant-dropdown-menu-item {
  display: flex !important;
  align-items: center;
  width: 100%;
  min-height: 46px;
  margin: 0 !important;
  padding: 10px 14px !important;
  border-radius: 12px;
  background: transparent !important;
  color: var(--theme-title) !important;
  font-weight: 700;
  line-height: 1.2;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft);
}

.generate-tool-dropdown .generate-tool-menu .ant-menu-item::after,
.generate-tool-dropdown .ant-dropdown-menu-item::after {
  display: none !important;
}

.generate-tool-dropdown .generate-tool-menu .ant-menu-item + .ant-menu-item,
.generate-tool-dropdown .ant-dropdown-menu-item + .ant-dropdown-menu-item {
  margin-top: 0 !important;
}

.generate-tool-dropdown .generate-tool-menu .ant-menu-item:hover,
.generate-tool-dropdown .generate-tool-menu .ant-menu-item-active,
.generate-tool-dropdown .ant-dropdown-menu-item:hover,
.generate-tool-dropdown .ant-dropdown-menu-item-active {
  color: var(--theme-accent-text) !important;
  background: var(--theme-nav-hover-bg) !important;
  box-shadow: none;
  transform: none;
}

.generate-tool-dropdown .generate-tool-menu .ant-menu-item-selected,
.generate-tool-dropdown .generate-tool-menu .ant-menu-item-selected:hover,
.generate-tool-dropdown .ant-dropdown-menu-item-selected,
.generate-tool-dropdown .ant-dropdown-menu-item-selected:hover {
  color: var(--theme-dropdown-selected-text) !important;
  background: var(--theme-dropdown-selected-bg) !important;
  box-shadow: none;
}

.model-help-popover {
  z-index: 1300;
  max-width: calc(100vw - 40px);

  .ant-popover-inner {
    padding: 0;
    border-radius: 16px;
    background: rgba(12, 12, 12, 0.96);
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
  }

  .ant-popover-inner-content {
    padding: 12px 14px;
  }

  .ant-popover-arrow::before {
    background: rgba(12, 12, 12, 0.96);
  }

  .model-help-tip {
    width: min(620px, calc(100vw - 68px));
    color: #f5f5f5;
  }

  .batch-mode-tip {
    width: min(420px, calc(100vw - 68px));
  }

  .batch-mode-tip-title {
    margin-bottom: 10px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 800;
    line-height: 1.4;
  }

  .batch-mode-tip-list {
    margin: 0;
    padding-left: 18px;
    color: #f5f5f5;
    font-size: 13px;
    line-height: 1.65;
  }

  .batch-mode-tip-list li + li {
    margin-top: 8px;
  }

  .batch-mode-tip-note {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    color: rgba(245, 245, 245, 0.82);
    font-size: 12px;
    line-height: 1.6;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page {
  --config-title-color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .mode-switch-btn {
  color: var(--text-secondary);

  &:hover {
    color: var(--theme-title);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .mode-switch-group-primary .mode-switch-btn {
  border-color: var(--theme-control-border-strong);
  background: var(--theme-panel-bg);
  box-shadow: none;
  color: var(--theme-accent-text);

  &:hover,
  &:focus {
    color: var(--theme-accent-text-hover);
    border-color: var(--theme-border-strong);
    background: var(--theme-control-hover-bg);
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .mode-switch-group-primary .mode-switch-btn.active,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .mode-switch-group-primary .mode-switch-btn.active:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .mode-switch-group-primary .mode-switch-btn.active:focus {
  color: var(--theme-accent-contrast);
  border-color: transparent;
  background: var(--theme-accent);
  box-shadow: 0 14px 24px var(--theme-shadow-strong);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .mode-switch-btn.tool {
  border-color: var(--theme-panel-border);
  background: var(--theme-panel-bg-muted);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .mode-switch-btn.tool.active {
  border-color: var(--theme-accent);
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  box-shadow: 0 8px 16px var(--theme-shadow-medium);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .config-collapse-btn,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-config-expand-btn {
  color: var(--theme-accent-text);
  border-color: var(--theme-panel-border);
  background: var(--theme-panel-bg-muted);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .config-collapse-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .config-collapse-btn:focus-visible,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-config-expand-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-config-expand-btn:focus-visible {
  color: var(--theme-accent-text-hover);
  border-color: var(--theme-border-strong);
  background: var(--theme-control-hover-bg);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .settings-footer {
  background: linear-gradient(
    180deg,
    rgba(var(--theme-surface-strong-rgb), 0),
    rgba(var(--theme-surface-strong-rgb), 0.92) 28%,
    var(--theme-surface-strong)
  );
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .smart-cutout-panel .settings-size,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .smart-cutout-panel .settings-footer {
  background: transparent;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .history-btn,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .prompt-library-btn,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .asset-library-btn,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page :deep(.generate-style-trigger) {
  color: var(--text-secondary) !important;
  background: var(--theme-panel-bg-soft) !important;
  border-color: var(--theme-panel-border) !important;

  &:hover {
    color: var(--theme-title) !important;
    background: var(--theme-control-hover-bg) !important;
    border-color: var(--theme-border-strong) !important;
    box-shadow: 0 10px 20px var(--theme-shadow-soft);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .prompt-icon-btn,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page :deep(.generate-style-trigger) {
  color: var(--text-secondary);
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  box-shadow: none;

  &:hover,
  &:focus-visible {
    color: var(--theme-title);
    background: var(--theme-control-hover-bg);
    border-color: var(--theme-border-strong);
    box-shadow: none;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .prompt-optimize-status-text {
  color: var(--text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .prompt-optimize-cancel-btn {
  color: var(--text-secondary);
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);

  &:hover {
    color: var(--theme-title);
    background: var(--theme-control-hover-bg);
    border-color: var(--theme-border-strong);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-config-panel .prompt-input {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;

  &:focus,
  &:hover {
    box-shadow: none !important;
  }

  &.ant-input-textarea-show-count,
  :deep(.ant-input-textarea-show-count) {
    color: var(--theme-title) !important;
  }

  &.ant-input-textarea-show-count::after,
  :deep(.ant-input-textarea-show-count)::after,
  :deep(.ant-input-data-count) {
    color: var(--theme-title) !important;
  }

  :deep(textarea) {
    color: var(--theme-title) !important;
    caret-color: var(--theme-title);
    border: 1px solid var(--theme-control-border-strong) !important;
    background: var(--theme-field-bg, var(--theme-control-bg)) !important;
    outline: none !important;
    box-shadow: none;
  }

  :deep(textarea:hover),
  :deep(textarea:focus),
  :deep(textarea:focus-visible) {
    border: 1px solid var(--theme-control-border-strong) !important;
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg)) !important;
    outline: none !important;
    box-shadow: none !important;
    transform: none;
  }

  :deep(textarea::placeholder) {
    color: var(--text-muted);
  }
}

html[data-theme="midnight"] .generate-page .generate-config-panel .prompt-input {
  &.ant-input-textarea-show-count,
  &.ant-input-textarea-show-count::after,
  :deep(.ant-input-textarea-show-count),
  :deep(.ant-input-textarea-show-count)::after,
  :deep(.ant-input-data-count) {
    color: #ffffff !important;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .prompt-label-row label,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .setting-item label,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .field-block > label,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-panel-head h3,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-empty .empty-title {
  color: var(--theme-title) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .aspect-ratio-auto-label {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .aspect-ratio-auto-help {
  color: var(--text-muted);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .aspect-ratio-auto-help:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .aspect-ratio-auto-help:focus-visible {
  color: var(--theme-accent-text-hover);
  background: var(--theme-control-hover-bg);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-canvas-entry-btn {
  background: linear-gradient(135deg, var(--theme-accent-strong) 0%, var(--theme-accent) 100%);
  box-shadow:
    0 18px 34px var(--theme-shadow-strong),
    0 0 0 1px rgba(255, 255, 255, 0.14) inset;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .work-panel:not(.result-panel) {
  background: linear-gradient(180deg, var(--theme-panel-bg) 0%, var(--theme-panel-bg-soft) 100%);
  border-color: var(--theme-panel-border);
  box-shadow: 0 18px 45px var(--theme-shadow-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-panel,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-body,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-list {
  background: var(--theme-panel-bg);
  background-image: none;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .settings-panel.generate-config-panel {
  background: linear-gradient(
    180deg,
    rgba(var(--theme-surface-strong-rgb), 0.98) 0%,
    rgba(var(--theme-surface-strong-rgb), 0.94) 32%,
    var(--theme-panel-bg-soft) 100%
  );
  border-color: var(--theme-panel-border);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 18px 40px var(--theme-shadow-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .settings-panel.generate-config-panel .settings-footer {
  background: linear-gradient(
    180deg,
    rgba(var(--theme-surface-strong-rgb), 0),
    rgba(var(--theme-surface-strong-rgb), 0.9) 26%,
    var(--theme-panel-bg-soft)
  );
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .panel-hint,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .source-upload-desc,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-result-placeholder,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .repaint-status-desc,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .mask-tip,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-tip-line,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-retain-badge,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .history-text,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-list-footnote,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-empty .empty-desc,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .frame-state {
  color: var(--text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-config-panel .upload-thumb {
  border-color: var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  box-shadow: 0 8px 18px var(--theme-shadow-soft);

  &:hover {
    border-color: var(--theme-border-strong);
    box-shadow: 0 14px 24px var(--theme-shadow-medium);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-config-panel .upload-thumb-mask {
  background: rgba(var(--theme-page-base-rgb), 0.78);
  color: var(--text-secondary);

  &.error {
    background: rgba(185, 56, 42, 0.18);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-config-panel .upload-add,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .source-upload-empty {
  border-color: var(--theme-panel-border-strong);
  background: var(--theme-field-bg, var(--theme-panel-bg-soft));
  color: var(--text-secondary);
  box-shadow: 0 10px 22px var(--theme-shadow-soft);

  &:hover {
    border-color: var(--theme-border-strong);
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg));
    box-shadow: 0 14px 24px var(--theme-shadow-medium);
  }
}

html[data-theme="midnight"] .generate-page .generate-config-panel .upload-add,
html[data-theme="midnight"] .generate-page .source-upload-empty {
  color: #ffffff;
}

html[data-theme="midnight"] .generate-page .generate-config-panel .upload-add-icon,
html[data-theme="midnight"] .generate-page .source-upload-icon {
  color: var(--theme-accent) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-config-panel .flat-select {
  background: var(--theme-control-bg);
  border-color: var(--theme-control-border);
  box-shadow: none;

  &:hover {
    border-color: var(--theme-border-strong);
    box-shadow: 0 12px 22px var(--theme-shadow-soft);
  }

  &:focus-within {
    border-color: var(--theme-border-accent);
    box-shadow: 0 0 0 3px var(--theme-focus-ring);
  }

  :deep(.ant-select-selector) {
    color: var(--theme-title);
  }

  :deep(.ant-select-arrow),
  :deep(.ant-select-selection-placeholder) {
    color: var(--text-muted);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .model-option-label {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .model-option-desc {
  color: var(--text-secondary);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-retain-badge {
  background: var(--theme-panel-bg) !important;
  border: 1px solid var(--theme-panel-border) !important;
  box-shadow: none !important;
}

@media (max-width: 960px) {
  html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-retain-badge {
    background: none !important;
    border: 0 !important;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-retain-icon {
  color: var(--theme-icon) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-retain-badge .result-tip-highlight {
  color: #4ade80;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-btn,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-action-btn-primary {
  background: var(--theme-control-active) !important;
  color: var(--theme-accent-contrast) !important;
  border-color: var(--theme-control-active) !important;
  box-shadow: 0 14px 24px var(--theme-shadow-strong) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-btn:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-btn:focus,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-action-btn-primary:hover,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-action-btn-primary:focus {
  background: var(--theme-accent-strong) !important;
  box-shadow: 0 16px 28px var(--theme-shadow-strong) !important;
}

html[data-theme="midnight"] .generate-page .generate-btn,
html[data-theme="midnight"] .generate-page .reverse-action-btn-primary {
  color: var(--theme-action-contrast) !important;
}

html[data-theme="midnight"] .generate-page .generate-btn:hover,
html[data-theme="midnight"] .generate-page .generate-btn:focus,
html[data-theme="midnight"] .generate-page .reverse-action-btn-primary:hover,
html[data-theme="midnight"] .generate-page .reverse-action-btn-primary:focus {
  background: var(--theme-action-hover) !important;
}

html[data-theme="midnight"] .generate-page .aspect-ratio-auto-row .aspect-ratio-auto-switch.ant-switch {
  background: var(--theme-control-track) !important;
  box-shadow: inset 0 0 0 1px var(--theme-border-strong) !important;
}

html[data-theme="midnight"] .generate-page .aspect-ratio-auto-row .aspect-ratio-auto-switch.ant-switch .ant-switch-handle::before {
  background: #ffffff !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .generate-btn:disabled {
  background: var(--theme-control-hover-bg) !important;
  color: var(--text-muted) !important;
  box-shadow: none !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .source-upload-icon,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .repaint-status-uploading {
  color: var(--theme-accent);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .source-upload-title,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .repaint-status-title {
  color: var(--theme-title);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-preview-shell,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-result-card {
  border-color: var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-frame {
  border-color: var(--theme-panel-border) !important;
  background: var(--theme-surface-strong) !important;
  box-shadow: 0 12px 28px var(--theme-shadow-soft) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-frame.pending {
  background: var(--theme-panel-bg) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-frame.failed,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .failed-image,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .frame-state,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .frame-state.error {
  background: var(--theme-panel-bg-soft) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-card:hover .result-frame.clickable {
  border-color: var(--theme-border-strong) !important;
  box-shadow: 0 18px 30px var(--theme-shadow-medium) !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-empty {
  background: transparent !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-body {
  scrollbar-color: rgba(113, 113, 122, 0.42) transparent;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-body::-webkit-scrollbar-thumb {
  background: rgba(113, 113, 122, 0.42);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-body:hover::-webkit-scrollbar-thumb {
  background: rgba(82, 82, 91, 0.56);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-preview-shell:hover {
  box-shadow: 0 18px 30px var(--theme-shadow-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-action-btn-secondary {
  color: var(--theme-accent-text) !important;
  background: var(--theme-panel-bg-strong) !important;
  border-color: var(--theme-panel-border-strong) !important;

  &:hover,
  &:focus {
    color: var(--theme-accent-text-hover) !important;
    background: var(--theme-control-hover-bg) !important;
    border-color: var(--theme-border-strong) !important;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .reverse-result-placeholder,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .repaint-status-card {
  border-color: var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .repaint-status-card.ready {
  background: var(--theme-control-hover-bg);
  border-color: var(--theme-border-strong);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .repaint-status-card:hover {
  box-shadow: 0 14px 24px var(--theme-shadow-soft);
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .brush-preview {
  background: rgba(52, 54, 61, 0.5);
  border-color: var(--theme-border-strong);
}

.generate-tool-dropdown .generate-tool-menu .ant-menu-item .anticon,
.generate-tool-dropdown .ant-dropdown-menu-item .anticon {
  font-size: 16px;
  color: currentColor;
}

.generate-tool-dropdown .generate-tool-menu .ant-menu-item-selected .anticon,
.generate-tool-dropdown .generate-tool-menu .ant-menu-item-selected span,
.generate-tool-dropdown .generate-tool-menu .ant-menu-item-selected .generate-tool-menu-item-label,
.generate-tool-dropdown .ant-dropdown-menu-item-selected .anticon,
.generate-tool-dropdown .ant-dropdown-menu-item-selected span,
.generate-tool-dropdown .ant-dropdown-menu-item-selected .generate-tool-menu-item-label {
  color: inherit !important;
}

.generate-page .result-panel,
.generate-page .result-body,
.generate-page .result-list {
  background: var(--theme-panel-bg) !important;
  background-image: none !important;
}

.generate-page .result-card {
  background: transparent !important;
}

.generate-page .result-frame:not(.pending):not(.failed) {
  border: 1px dashed var(--theme-panel-border) !important;
  background: #ffffff !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .result-frame:not(.pending):not(.failed) {
  background: var(--theme-surface-strong) !important;
}

.hd-preview-loading {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
</style>
