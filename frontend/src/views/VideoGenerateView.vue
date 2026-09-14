<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { message, Modal } from "ant-design-vue";
import { consumeVideoGenerateDraft } from "@/lib/videoGenerateDraft";
import {
  CloseOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  ExclamationCircleFilled,
  EyeOutlined,
  FontSizeOutlined,
  MessageOutlined,
  MoreOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  VideoCameraOutlined,
  ExpandOutlined,
} from "@ant-design/icons-vue";
import AspectRatioPicker from "@/components/generate/AspectRatioPicker.vue";
import OptionGridPicker from "@/components/generate/OptionGridPicker.vue";
import PromptInterceptionTip from "@/components/generate/PromptInterceptionTip.vue";
import UpdateLogEntryButton from "@/components/update-log/UpdateLogEntryButton.vue";
import { getMe } from "@/api/auth";
import { isSupportedImageUploadFile } from "@/api/upload";
import ImageSourceActionSheet from "@/components/generate/ImageSourceActionSheet.vue";
import { createUserPrompt } from "@/api/userPrompts";
import { getVideoTaskScenes } from "@/api/videoConfig";
import { useImageSourcePicker } from "@/composables/useImageSourcePicker";
import { useUserAssets } from "@/composables/useUserAssets";
import { triggerDirectDownload } from "@/lib/directDownload";
import {
  PROMPT_INTERCEPTION_TIP_FOOTNOTE,
  PROMPT_INTERCEPTION_TIP_SECTIONS,
} from "@/lib/promptInterceptionTip";
import { buildQuickSavePromptTitle, imageUrlToFile } from "@/lib/userLibraryQuickSave";
import { createVideoTask, deleteVideoTask, getVideoTasks } from "@/api/videoTasks";
import { useAuthStore } from "@/stores/auth";
import type { SceneOptionItem, UserAsset, UserPrompt, VideoTaskResult, VideoTaskSceneConfig } from "@/types";

type VideoGenerateMode = "textGenerate" | "imageToVideo" | "firstLastFrame";
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

const route = useRoute();
const auth = useAuthStore();
const UserAssetPicker = defineAsyncComponent(() => import("@/components/assets/UserAssetPicker.vue"));
const FeedbackDialog = defineAsyncComponent(() => import("@/components/feedback/FeedbackDialog.vue"));
const UserPromptLibraryModal = defineAsyncComponent(() => import("@/components/prompts/UserPromptLibraryModal.vue"));
const PromptExpandDialog = defineAsyncComponent(() => import("@/components/generate/PromptExpandDialog.vue"));
const VideoTaskDetailDialog = defineAsyncComponent(() => import("@/components/video/VideoTaskDetailDialog.vue"));
const DEFAULT_MAX_VIDEO_REFERENCE_IMAGES = 1;
const MAX_IMAGE_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024;
const MAX_IMAGE_UPLOAD_SIZE_TEXT = "20MB";
const DEFAULT_DURATION_SECONDS = "3";
const DEFAULT_VIDEO_TASK_COUNT = 1;
const VIDEO_TASK_COUNT_MARKS: Record<number, string> = {
  1: "1",
  2: "2",
  3: "3",
  4: "4",
};
const RESULT_COLUMN_OPTIONS = [2, 3] as const;
type ResultColumnOption = typeof RESULT_COLUMN_OPTIONS[number];
const DEFAULT_RESULT_COLUMN_COUNT: ResultColumnOption = 2;
const FIRST_LAST_FRAME_SLOTS = [0, 1] as const;
const loading = ref(false);
const submitting = ref(false);
const taskPollingInFlight = ref(false);
const generateMode = ref<VideoGenerateMode>("imageToVideo");
const selectedModel = ref("");
const selectedAspectRatio = ref("");
const selectedDuration = ref("");
const selectedResolution = ref("");
const selectedTaskCount = ref<number>(DEFAULT_VIDEO_TASK_COUNT);
const prompt = ref("");
const lastSavedPromptText = ref("");
const taskScenes = ref<VideoTaskSceneConfig[]>([]);
const videoTasks = ref<VideoTaskResult[]>([]);
const failureRefundRemainingCount = ref<number | null>(null);
const taskPollTimer = ref<ReturnType<typeof setInterval> | null>(null);
const referenceItems = ref<UploadPreviewItem[]>([]);
const firstLastFrameItems = ref<[UploadPreviewItem | null, UploadPreviewItem | null]>([null, null]);
const assetPickerOpen = ref(false);
const assetPickerFrameSlot = ref<0 | 1 | null>(null);
const quickSavingReferenceIds = ref<string[]>([]);
const quickSavingPromptKeys = ref<string[]>([]);
const promptLibraryVisible = ref(false);
const promptExpandOpen = ref(false);
const detailOpen = ref(false);
const detailTask = ref<VideoTaskResult | null>(null);
const feedbackDialogOpen = ref(false);
const feedbackTarget = ref<VideoTaskResult | null>(null);
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
const referencePickerOpening = ref(false);
const referenceDragActive = ref(false);
const frameDragActive = ref<0 | 1 | null>(null);
const viewportWidth = ref(typeof window === "undefined" ? 1200 : window.innerWidth);
const preferredResultColumnCount = ref<ResultColumnOption>(DEFAULT_RESULT_COLUMN_COUNT);
const playingVideoTaskIds = ref<Set<string>>(new Set());
const videoPlayerRefs = new Map<string, HTMLVideoElement>();
const { uploadFiles: uploadUserAssetFiles } = useUserAssets();

function isImageUploadTooLarge(file: File) {
  return file.size > MAX_IMAGE_UPLOAD_SIZE_BYTES;
}

function isReferenceImageFile(file: File) {
  return isSupportedImageUploadFile(file);
}

function isSceneAvailableForGenerateMode(scene: VideoTaskSceneConfig, mode: VideoGenerateMode) {
  const availabilityModes = scene.availability_modes?.length
    ? scene.availability_modes
    : (
      scene.availability_mode === "text_to_video"
        ? ["text_to_video"]
        : (scene.availability_mode === "image_to_video" ? ["image_to_video"] : ["text_to_video", "image_to_video"])
    );
  return availabilityModes.includes(getGenerationModeValue(mode));
}

const selectedScene = computed(
  () => filteredTaskScenes.value.find((item) => item.scene_key === selectedModel.value) || null,
);
const filteredTaskScenes = computed(() => (
  taskScenes.value.filter((item) => isSceneAvailableForGenerateMode(item, generateMode.value))
));
const durationOptions = computed<SceneOptionItem[]>(() => (
  selectedScene.value?.duration_options?.length
    ? selectedScene.value.duration_options
    : []
));
const aspectRatioOptions = computed<SceneOptionItem[]>(() => (
  selectedScene.value?.aspect_ratio_options?.length
    ? selectedScene.value.aspect_ratio_options
    : []
));
const resolutionOptions = computed<SceneOptionItem[]>(() => (
  selectedScene.value?.resolution_options?.length
    ? selectedScene.value.resolution_options
    : []
));
const hideAspectRatio = computed(() => !!selectedScene.value?.hide_aspect_ratio);
const hideDuration = computed(() => !!selectedScene.value?.hide_duration);
const hideResolution = computed(() => !!selectedScene.value?.hide_resolution);
const selectedCreditCost = computed(() => {
  const scene = selectedScene.value;
  if (!scene) return 0;
  if (scene.credit_billing_mode === "per_second") {
    return Number(selectedDuration.value || 0) * Number(scene.per_second_credit_cost || 0);
  }
  const resolutionKey = selectedResolution.value.trim();
  if (resolutionKey && scene.resolution_credit_costs?.[resolutionKey] != null) {
    return Number(scene.resolution_credit_costs[resolutionKey] || 0);
  }
  return Number(scene.credit_cost || 0);
});
const totalSelectedCreditCost = computed(() => selectedTaskCount.value * selectedCreditCost.value);
const generateButtonText = computed(() => `开始生成视频 · ${totalSelectedCreditCost.value} 积分`);
const activeTaskIds = computed(() => (
  videoTasks.value
    .filter((task) => ["pending", "queued", "processing"].includes(task.status))
    .map((task) => task.id)
));
const maxReferenceImages = computed(() => {
  if (generateMode.value === "firstLastFrame") return 2;
  if (generateMode.value !== "imageToVideo") return 0;
  if (!selectedScene.value) return DEFAULT_MAX_VIDEO_REFERENCE_IMAGES;
  return Math.max(0, Number(selectedScene.value.max_reference_images || 0));
});
const referenceUrls = computed(() => (
  getCurrentReferenceItems()
    .filter((item) => item.status === "success" && item.remoteUrl)
    .map((item) => item.remoteUrl)
));
const uploading = computed(() => getCurrentReferenceItems().some((item) => item.status === "uploading"));
let filePickerRecoveryTimer: number | null = null;
const promptPlaceholder = computed(() => (
  generateMode.value === "firstLastFrame"
    ? "描述首帧到尾帧之间的主体动作、镜头运动和画面变化..."
    : generateMode.value === "imageToVideo"
    ? "描述参考画面的主体动作、镜头运动、转场方式和最终视频氛围..."
    : "描述您想要生成的视频内容、镜头运动、主体动作和场景氛围..."
));
const VIDEO_PROMPT_INTERCEPTION_TIP_SECTIONS = [
  {
    title: "视频参考图额外提示",
    items: [
      "真人支持还不够好，参考图如果有真人，拦截或生成出错的概率会更高。",
    ],
  },
  ...PROMPT_INTERCEPTION_TIP_SECTIONS,
];
const VIDEO_PROMPT_INTERCEPTION_TIP_FOOTNOTE = `${PROMPT_INTERCEPTION_TIP_FOOTNOTE} 若视频任务涉及真人参考图，建议优先改用非真人素材，或先简化提示词后再试。`;
const emptyStateTitle = computed(() => (
  generateMode.value === "firstLastFrame"
    ? "还没有首尾帧任务"
    : (generateMode.value === "imageToVideo" ? "还没有图生视频任务" : "还没有文生视频任务")
));
const emptyStateDescription = computed(() => (
  generateMode.value === "firstLastFrame"
    ? "上传首帧和尾帧并提交任务后，右侧会显示排队、生成和结果状态。"
    : generateMode.value === "imageToVideo"
    ? "在左侧切换到图生视频并提交任务后，右侧会显示排队、生成和结果状态。"
    : "在左侧输入提示词并提交任务后，右侧会显示排队、生成和结果状态。"
));
const resultColumnCount = computed(() => {
  if (viewportWidth.value <= 768) return 1;
  if (viewportWidth.value <= 1180) return Math.min(2, preferredResultColumnCount.value);
  return preferredResultColumnCount.value;
});
const resultListStyle = computed(() => ({
  gridTemplateColumns: `repeat(${resultColumnCount.value}, minmax(0, 1fr))`,
}));
const detailModelOptions = computed(() => (
  taskScenes.value.map((scene) => ({
    label: scene.display_name || scene.scene_label || scene.scene_key,
    value: scene.scene_key,
  }))
));

function formatRequestError(err: any) {
  return err?.response?.data?.detail || err?.message || "请求失败，请稍后重试";
}

function getGenerationModeValue(mode: VideoGenerateMode): VideoTaskResult["generation_mode"] {
  if (mode === "firstLastFrame") return "first_last_frame";
  if (mode === "imageToVideo") return "image_to_video";
  return "text_to_video";
}

function getGenerateModeFromTask(task: Pick<VideoTaskResult, "generation_mode" | "reference_images">): VideoGenerateMode {
  if (task.generation_mode === "first_last_frame") return "firstLastFrame";
  if (task.generation_mode === "image_to_video") return "imageToVideo";
  if (task.generation_mode === "text_to_video") return "textGenerate";
  return task.reference_images?.length ? "imageToVideo" : "textGenerate";
}

function getCurrentReferenceItems() {
  return generateMode.value === "firstLastFrame"
    ? firstLastFrameItems.value.filter((item): item is UploadPreviewItem => !!item)
    : referenceItems.value;
}

function updateViewportWidth() {
  if (typeof window === "undefined") return;
  viewportWidth.value = window.innerWidth;
}

function revokeObjectUrl(url?: string) {
  if (!url || !url.startsWith("blob:")) return;
  URL.revokeObjectURL(url);
}

function getReferencePreviewUrl(item: UploadPreviewItem) {
  return item.remoteUrl || item.localUrl;
}

function getFrameReferencePreviewUrl(slot: 0 | 1) {
  const item = firstLastFrameItems.value[slot];
  return item ? getReferencePreviewUrl(item) : "";
}

function getFrameReferenceStatus(slot: 0 | 1) {
  return firstLastFrameItems.value[slot]?.status || "success";
}

function updateReferenceItem(id: string, patch: Partial<UploadPreviewItem>) {
  const index = referenceItems.value.findIndex((item) => item.id === id);
  if (index !== -1) {
    referenceItems.value[index] = {
      ...referenceItems.value[index],
      ...patch,
    };
    return;
  }
  const frameIndex = firstLastFrameItems.value.findIndex((item) => item?.id === id);
  if (frameIndex === -1) return;
  const current = firstLastFrameItems.value[frameIndex];
  if (!current) return;
  const next = [...firstLastFrameItems.value] as [UploadPreviewItem | null, UploadPreviewItem | null];
  next[frameIndex] = {
    ...current,
    ...patch,
  };
  firstLastFrameItems.value = next;
}

function triggerUpload(frameSlot: 0 | 1 | null = null) {
  if (frameSlot === null && referenceItems.value.length >= maxReferenceImages.value) {
    message.warning(`当前最多上传 ${maxReferenceImages.value} 张参考图`);
    return;
  }
  assetPickerFrameSlot.value = frameSlot;
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

function clearFilePickerRecoveryTimer() {
  if (filePickerRecoveryTimer != null) {
    window.clearTimeout(filePickerRecoveryTimer);
    filePickerRecoveryTimer = null;
  }
}

function scheduleFilePickerRecovery(delay = 8000) {
  clearFilePickerRecoveryTimer();
  filePickerRecoveryTimer = window.setTimeout(() => {
    clearReferencePickerOpening();
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

function setFrameReferenceItem(slot: 0 | 1, item: UploadPreviewItem | null) {
  const current = firstLastFrameItems.value[slot];
  if (current?.objectUrl && current.objectUrl !== item?.objectUrl) {
    revokeObjectUrl(current.objectUrl);
  }
  const next = [...firstLastFrameItems.value] as [UploadPreviewItem | null, UploadPreviewItem | null];
  next[slot] = item;
  firstLastFrameItems.value = next;
}

function isSavingReferenceToLibrary(itemId: string) {
  return quickSavingReferenceIds.value.includes(itemId);
}

function canQuickSaveReferenceItem(item: UploadPreviewItem | null | undefined) {
  return !!item && item.status === "success" && !!item.objectUrl && !item.savedToAsset;
}

function isQuickSavePromptPending(promptKey: string) {
  return quickSavingPromptKeys.value.includes(promptKey);
}

function canQuickSavePrompt(content: string, lastSavedContent: string) {
  const normalized = content.trim();
  return !!normalized && normalized !== lastSavedContent.trim();
}

function markPromptQuickSaved(value: string) {
  lastSavedPromptText.value = value;
}

async function ensureLibraryAuth(kind: "asset" | "prompt") {
  if (auth.isLoggedIn) return true;
  message.warning(kind === "asset" ? "请先登录后使用我的素材" : "请先登录后使用我的提示词");
  return false;
}

async function saveReferenceItemToLibrary(item: UploadPreviewItem) {
  if (!(await ensureLibraryAuth("asset"))) return;
  if (!canQuickSaveReferenceItem(item)) return;
  if (isSavingReferenceToLibrary(item.id)) return;
  quickSavingReferenceIds.value = [...quickSavingReferenceIds.value, item.id];
  try {
    const file = await imageUrlToFile(item.objectUrl || item.localUrl, {
      fileName: item.fileName,
      fallbackPrefix: "video-reference",
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

function confirmSaveFrameReferenceItem(slot: 0 | 1) {
  const item = firstLastFrameItems.value[slot];
  if (item) {
    confirmSaveReferenceItem(item);
  }
}

async function savePromptToLibrary(content: string, promptKey: string, onSaved: (value: string) => void) {
  const normalized = content.trim();
  if (!normalized) return;
  if (!(await ensureLibraryAuth("prompt"))) return;
  if (isQuickSavePromptPending(promptKey)) return;
  quickSavingPromptKeys.value = [...quickSavingPromptKeys.value, promptKey];
  try {
    const title = buildQuickSavePromptTitle(normalized);
    await createUserPrompt({ title, content: normalized });
    onSaved(normalized);
    message.success("已加入我的提示词");
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "加入我的提示词失败");
  } finally {
    quickSavingPromptKeys.value = quickSavingPromptKeys.value.filter((key) => key !== promptKey);
  }
}

function confirmSavePromptToLibrary(content: string, promptKey: string, onSaved: (value: string) => void) {
  const normalized = content.trim();
  if (!normalized) return;
  const title = buildQuickSavePromptTitle(normalized);
  Modal.confirm({
    title: "加入我的提示词",
    content: `确认将当前提示词加入我的提示词吗？将使用“${title}”作为默认标题。`,
    centered: true,
    okText: "确认加入",
    cancelText: "取消",
    async onOk() {
      await savePromptToLibrary(normalized, promptKey, onSaved);
    },
  });
}

function addLibraryAssetToReference(asset: UserAsset) {
  if (generateMode.value === "firstLastFrame" && assetPickerFrameSlot.value !== null) {
    return addLibraryAssetToFrameSlot(asset, assetPickerFrameSlot.value);
  }
  if (referenceItems.value.some((item) => item.remoteUrl === asset.image_url)) {
    message.info("这张素材已在参考图中");
    return false;
  }
  if (referenceItems.value.length >= maxReferenceImages.value) {
    message.warning(`当前最多上传 ${maxReferenceImages.value} 张参考图`);
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
  return true;
}

function addLibraryAssetToFrameSlot(asset: UserAsset, slot: 0 | 1) {
  const duplicatedSlot = firstLastFrameItems.value.findIndex((item, index) => index !== slot && item?.remoteUrl === asset.image_url);
  if (duplicatedSlot !== -1) {
    message.info("首帧和尾帧不能使用同一张图片");
    return false;
  }
  setFrameReferenceItem(slot, {
    id: `frame-asset-${asset.id}-${Date.now()}`,
    localUrl: asset.thumb_url || asset.image_url,
    remoteUrl: asset.image_url,
    status: "success",
    fileName: asset.file_name,
    savedToAsset: true,
  });
  return true;
}

function addLibraryAssetsToReference(assets: UserAsset[]) {
  if (generateMode.value === "firstLastFrame") {
    const startSlot = assetPickerFrameSlot.value ?? 0;
    const availableSlots = [0, 1].slice(startSlot).filter((slot) => !firstLastFrameItems.value[slot]) as Array<0 | 1>;
    if (!availableSlots.length) {
      message.warning("首帧和尾帧均已选择图片");
      return false;
    }
    let added = 0;
    for (const asset of assets) {
      const slot = availableSlots.shift();
      if (slot === undefined) break;
      if (addLibraryAssetToFrameSlot(asset, slot)) added += 1;
    }
    return added > 0;
  }
  const limit = maxReferenceImages.value;
  if (limit <= 0) {
    message.warning("当前场景不支持参考图");
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
        ? `当前最多上传 ${limit} 张参考图，还可添加 ${remainingSlots} 张，已选 ${uniqueAssets.length} 张`
        : `当前最多上传 ${limit} 张参考图`,
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
  if (uniqueAssets.length < assets.length) {
    message.success(`已添加 ${uniqueAssets.length} 张参考图，其余素材已在参考图中`);
  }
  return true;
}

async function handlePickUserAsset(asset: UserAsset) {
  if (addLibraryAssetToReference(asset)) {
    assetPickerOpen.value = false;
    assetPickerFrameSlot.value = null;
  }
}

async function handlePickUserAssets(assets: UserAsset[]) {
  if (addLibraryAssetsToReference(assets)) {
    assetPickerOpen.value = false;
    assetPickerFrameSlot.value = null;
  }
}

function openAssetPicker() {
  assetPickerFrameSlot.value = null;
  if (!auth.isLoggedIn) {
    message.warning("请先登录后使用我的素材");
    return;
  }
  assetPickerOpen.value = true;
}

function openFrameAssetPicker(slot: 0 | 1) {
  assetPickerFrameSlot.value = slot;
  openAssetPicker();
  assetPickerFrameSlot.value = slot;
}

function openPromptLibrary() {
  if (!auth.isLoggedIn) {
    message.warning("请先登录后使用我的提示词");
    return;
  }
  promptLibraryVisible.value = true;
}

function useLibraryPrompt(item: UserPrompt) {
  const content = (item.content || "").trim();
  if (!content) {
    message.warning("该提示词内容为空");
    return;
  }
  prompt.value = content;
  message.success("已回填到编辑区");
}

function applyExpandedPrompt(value: string) {
  prompt.value = value;
}

function hasVideoStarted(taskId: string) {
  return playingVideoTaskIds.value.has(taskId);
}

function setVideoPlayerRef(taskId: string, el: unknown) {
  if (el instanceof HTMLVideoElement) {
    videoPlayerRefs.set(taskId, el);
    return;
  }
  videoPlayerRefs.delete(taskId);
}

function markVideoStarted(taskId: string) {
  if (playingVideoTaskIds.value.has(taskId)) return;
  const next = new Set(playingVideoTaskIds.value);
  next.add(taskId);
  playingVideoTaskIds.value = next;
}

async function handlePlayVideo(taskId: string) {
  const video = videoPlayerRefs.get(taskId);
  if (!video) return;
  markVideoStarted(taskId);
  try {
    await video.play();
  } catch {
    message.warning("视频暂时无法播放，请稍后重试");
  }
}

async function processReferenceFiles(files: File[], frameSlot: 0 | 1 | null = null) {
  const imageFiles = files.filter((file) => isReferenceImageFile(file));
  if (!imageFiles.length) {
    if (files.length) {
      message.warning("仅支持上传图片文件");
    }
    return;
  }

  if (frameSlot !== null) {
    const file = imageFiles[0];
    if (!file) return;
    if (imageFiles.length > 1) {
      message.warning("首帧和尾帧每次只能上传 1 张图片");
    }
    if (isImageUploadTooLarge(file)) {
      message.warning(`单张参考图不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    const item: UploadPreviewItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      localUrl: objectUrl,
      remoteUrl: "",
      status: "uploading",
      objectUrl,
      fileName: file.name,
      savedToAsset: false,
    };
    setFrameReferenceItem(frameSlot, item);
    try {
      const { uploadReferenceImage } = await import("@/api/upload");
      const uploaded = await uploadReferenceImage(file, "ref");
      updateReferenceItem(item.id, {
        remoteUrl: uploaded.url,
        status: "success",
      });
    } catch (err: any) {
      updateReferenceItem(item.id, { status: "failed" });
      message.error(err?.message || "参考图上传失败");
    }
    return;
  }

  const remainingSlots = Math.max(0, maxReferenceImages.value - referenceItems.value.length);
  if (!remainingSlots) {
    message.warning(`当前最多上传 ${maxReferenceImages.value} 张参考图`);
    return;
  }

  const acceptedFiles = imageFiles.slice(0, remainingSlots);
  if (acceptedFiles.length < imageFiles.length) {
    message.warning(`当前最多上传 ${maxReferenceImages.value} 张参考图`);
  }

  const { uploadReferenceImage } = await import("@/api/upload");

  for (const file of acceptedFiles) {
    if (isImageUploadTooLarge(file)) {
      message.warning(`单张参考图不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
      continue;
    }

    const objectUrl = URL.createObjectURL(file);
    const item: UploadPreviewItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      localUrl: objectUrl,
      remoteUrl: "",
      status: "uploading",
      objectUrl,
      fileName: file.name,
      savedToAsset: false,
    };
    referenceItems.value.push(item);

    try {
      const uploaded = await uploadReferenceImage(file, "ref");
      updateReferenceItem(item.id, {
        remoteUrl: uploaded.url,
        status: "success",
      });
    } catch (err: any) {
      updateReferenceItem(item.id, { status: "failed" });
      message.error(err?.message || "参考图上传失败");
    }
  }
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  const frameSlot = assetPickerFrameSlot.value;
  assetPickerFrameSlot.value = null;
  clearReferencePickerOpening();
  clearFilePickerRecoveryTimer();
  input.value = "";
  if (!files.length) return;
  await processReferenceFiles(files, frameSlot);
}

function removeReference(index: number) {
  const item = referenceItems.value[index];
  if (item) revokeObjectUrl(item.objectUrl);
  referenceItems.value.splice(index, 1);
}

function removeFrameReference(slot: 0 | 1) {
  setFrameReferenceItem(slot, null);
}

function handleReferenceDragOver(event: DragEvent) {
  event.preventDefault();
  if (!maxReferenceImages.value) return;
  referenceDragActive.value = true;
}

function handleReferenceDragLeave(event: DragEvent) {
  event.preventDefault();
  const nextTarget = event.relatedTarget as Node | null;
  if (nextTarget && (event.currentTarget as HTMLElement | null)?.contains(nextTarget)) return;
  referenceDragActive.value = false;
}

async function handleReferenceDrop(event: DragEvent) {
  event.preventDefault();
  referenceDragActive.value = false;
  const files = Array.from(event.dataTransfer?.files || []).filter((file) => file.type.startsWith("image/"));
  if (!files.length) return;
  await processReferenceFiles(files);
}

function handleFrameDragOver(event: DragEvent, slot: 0 | 1) {
  event.preventDefault();
  frameDragActive.value = slot;
}

function handleFrameDragLeave(event: DragEvent, slot: 0 | 1) {
  event.preventDefault();
  const nextTarget = event.relatedTarget as Node | null;
  if (nextTarget && (event.currentTarget as HTMLElement | null)?.contains(nextTarget)) return;
  if (frameDragActive.value === slot) frameDragActive.value = null;
}

async function handleFrameDrop(event: DragEvent, slot: 0 | 1) {
  event.preventDefault();
  frameDragActive.value = null;
  const files = Array.from(event.dataTransfer?.files || []).filter((file) => file.type.startsWith("image/"));
  if (!files.length) return;
  await processReferenceFiles(files, slot);
}

function ensureSceneDefaults() {
  if (!filteredTaskScenes.value.length) {
    selectedModel.value = "";
    return;
  }
  if (!selectedModel.value || !filteredTaskScenes.value.some((item) => item.scene_key === selectedModel.value)) {
    selectedModel.value = filteredTaskScenes.value[0].scene_key;
  }
  const scene = selectedScene.value;
  if (!scene) return;
  if (!selectedAspectRatio.value || !scene.aspect_ratio_options.some((item) => item.value === selectedAspectRatio.value)) {
    selectedAspectRatio.value = scene.aspect_ratio_options[0]?.value || "";
  }
  if (!selectedDuration.value || !scene.duration_options.some((item) => item.value === selectedDuration.value)) {
    const preferredDuration = scene.duration_options.find((item) => item.value === DEFAULT_DURATION_SECONDS);
    selectedDuration.value = preferredDuration?.value || scene.duration_options[0]?.value || "";
  }
  if (!selectedResolution.value || !scene.resolution_options.some((item) => item.value === selectedResolution.value)) {
    selectedResolution.value = scene.resolution_options[0]?.value || "";
  }
}

async function loadSceneConfigs() {
  loading.value = true;
  try {
    taskScenes.value = await getVideoTaskScenes();
    ensureSceneDefaults();
  } catch (err: any) {
    message.error(formatRequestError(err));
  } finally {
    loading.value = false;
  }
}

async function loadRecentTasks() {
  if (!auth.isLoggedIn) {
    videoTasks.value = [];
    stopTaskPolling();
    return;
  }
  try {
    videoTasks.value = await getVideoTasks([], 20);
    videoTasks.value.forEach((task) => {
      if (typeof task.failure_refund_remaining_count === "number" && task.failure_refund_remaining_count >= 0) {
        failureRefundRemainingCount.value = task.failure_refund_remaining_count;
      }
    });
    if (activeTaskIds.value.length) {
      startTaskPolling();
    }
  } catch (err: any) {
    message.error(formatRequestError(err));
  }
}

function updateTaskFromRemote(remoteTask: VideoTaskResult) {
  if (typeof remoteTask.failure_refund_remaining_count === "number" && remoteTask.failure_refund_remaining_count >= 0) {
    failureRefundRemainingCount.value = remoteTask.failure_refund_remaining_count;
  }
  const currentIndex = videoTasks.value.findIndex((item) => item.id === remoteTask.id);
  if (currentIndex >= 0) {
    const cloned = videoTasks.value.slice();
    cloned[currentIndex] = remoteTask;
    videoTasks.value = cloned;
    return;
  }
  videoTasks.value = [remoteTask, ...videoTasks.value];
}

function buildVideoTaskPlaceholder(task: VideoTaskResult): VideoTaskResult {
  return {
    id: task.id,
    model: task.model,
    source: task.source || "web",
    generation_mode: task.generation_mode || "text_to_video",
    prompt: task.prompt,
    duration_seconds: task.duration_seconds,
    aspect_ratio: task.aspect_ratio,
    resolution: task.resolution,
    reference_images: [...(task.reference_images || [])],
    credit_cost: task.credit_cost,
    failure_refund_remaining_count: null,
    status: "queued",
    created_at: new Date().toISOString(),
    videos: [{
      id: -Date.now(),
      video_url: "",
      cover_url: "",
      status: "pending",
      error_message: "",
    }],
    api_attempts: [],
  };
}

async function submitVideoTaskFromPayload(task: Pick<VideoTaskResult, "model" | "generation_mode" | "prompt" | "duration_seconds" | "aspect_ratio" | "resolution" | "reference_images" | "source" | "credit_cost">) {
  const response = await createVideoTask({
    model: task.model,
    generation_mode: task.generation_mode,
    prompt: task.prompt.trim(),
    duration_seconds: Number(task.duration_seconds || 0),
    aspect_ratio: task.aspect_ratio || "",
    resolution: task.resolution || "",
    reference_images: task.reference_images || [],
    source: "web",
  });
  const placeholder = buildVideoTaskPlaceholder({
    ...task,
    id: response.task_id,
    status: "queued",
    created_at: new Date().toISOString(),
    videos: [],
    api_attempts: [],
  } as VideoTaskResult);
  videoTasks.value = [placeholder, ...videoTasks.value.filter((item) => item.id !== placeholder.id)];
  startTaskPolling();
  void pollActiveTasks();
  getMe().then((user) => auth.updateUser(user)).catch(() => {});
}

function replaceReferenceItems(urls: string[]) {
  if (generateMode.value === "firstLastFrame") {
    firstLastFrameItems.value.forEach((item) => revokeObjectUrl(item?.objectUrl));
    const restored = urls.slice(0, 2).map((url, index) => ({
      id: `restored-frame-${index}-${Date.now()}`,
      localUrl: url,
      remoteUrl: url,
      status: "success" as const,
    }));
    firstLastFrameItems.value = [restored[0] || null, restored[1] || null];
    return;
  }
  referenceItems.value.forEach((item) => revokeObjectUrl(item.objectUrl));
  referenceItems.value = urls.map((url, index) => ({
    id: `restored-${index}-${Date.now()}`,
    localUrl: url,
    remoteUrl: url,
    status: "success" as const,
  }));
}

function promptSwitchToTextGenerate(messageText: string) {
  Modal.confirm({
    title: "当前为图生视频",
    content: messageText,
    centered: true,
    okText: "去文生视频",
    cancelText: "取消",
    onOk: () => {
      generateMode.value = "textGenerate";
    },
  });
}

function normalizeRouteVideoMode(value: unknown): VideoGenerateMode | null {
  const normalized = Array.isArray(value) ? value[0] : value;
  if (normalized === "textGenerate" || normalized === "imageToVideo" || normalized === "firstLastFrame") {
    return normalized;
  }
  return null;
}

function applyRouteVideoMode() {
  const nextMode = normalizeRouteVideoMode(route.query.mode);
  if (!nextMode) return;
  if (generateMode.value !== nextMode) {
    generateMode.value = nextMode;
  }
}

function applyIncomingVideoDraft() {
  const draft = consumeVideoGenerateDraft();
  if (!draft) return;
  generateMode.value = draft.mode;
  prompt.value = draft.prompt || "";
  selectedModel.value = draft.model || "";
  selectedAspectRatio.value = draft.aspect_ratio || "";
  selectedDuration.value = draft.duration_seconds ? String(draft.duration_seconds) : "";
  selectedResolution.value = draft.resolution || "";
  selectedTaskCount.value = DEFAULT_VIDEO_TASK_COUNT;
  ensureSceneDefaults();
  replaceReferenceItems(
    draft.mode === "imageToVideo"
      ? draft.reference_images.slice(0, Math.max(1, maxReferenceImages.value || DEFAULT_MAX_VIDEO_REFERENCE_IMAGES))
      : draft.mode === "firstLastFrame"
        ? draft.reference_images.slice(0, 2)
      : [],
  );
  message.success("已回填到视频生成页，可继续编辑后提交");
}

async function pollActiveTasks() {
  if (!activeTaskIds.value.length || taskPollingInFlight.value) return;
  taskPollingInFlight.value = true;
  try {
    const results = await getVideoTasks(activeTaskIds.value);
    results.forEach(updateTaskFromRemote);
    if (!results.some((task) => ["pending", "queued", "processing"].includes(task.status))) {
      stopTaskPolling();
    }
  } catch {
    // Polling failures are transient; keep the timer running.
  } finally {
    taskPollingInFlight.value = false;
  }
}

function stopTaskPolling() {
  if (taskPollTimer.value) {
    clearInterval(taskPollTimer.value);
    taskPollTimer.value = null;
  }
}

function startTaskPolling() {
  if (taskPollTimer.value || !activeTaskIds.value.length) return;
  taskPollTimer.value = setInterval(() => {
    void pollActiveTasks();
  }, 5000);
}

async function handleSubmit() {
  if (!selectedModel.value) {
    message.warning("请先选择视频模型");
    return;
  }
  if (!prompt.value.trim()) {
    message.warning("请输入视频提示词");
    return;
  }
  if (!hideDuration.value && !selectedDuration.value) {
    message.warning("请选择视频秒数");
    return;
  }
  if (!hideAspectRatio.value && !selectedAspectRatio.value) {
    message.warning("请选择宽高比");
    return;
  }
  if (!hideResolution.value && !selectedResolution.value) {
    message.warning("请选择分辨率");
    return;
  }
  if (generateMode.value === "imageToVideo") {
    if (maxReferenceImages.value <= 0) {
      promptSwitchToTextGenerate("当前模型不支持参考图。若没有参考图，请切换到文生视频发起任务。");
      return;
    }
    if (!referenceUrls.value.length) {
      promptSwitchToTextGenerate("图生视频必须先上传参考图。若你现在没有参考图，请切换到文生视频发起任务。");
      return;
    }
  }
  if (generateMode.value === "firstLastFrame") {
    if (referenceUrls.value.length !== 2) {
      message.warning("首尾帧视频必须上传首帧和尾帧两张图片");
      return;
    }
  }

  const taskCount = Math.min(Math.max(Number(selectedTaskCount.value || 1), 1), 4);
  const payload = {
    model: selectedModel.value,
    generation_mode: getGenerationModeValue(generateMode.value),
    prompt: prompt.value.trim(),
    duration_seconds: Number(selectedDuration.value || 0),
    aspect_ratio: hideAspectRatio.value ? "" : selectedAspectRatio.value,
    resolution: hideResolution.value ? "" : selectedResolution.value,
    reference_images: generateMode.value === "textGenerate" ? [] : [...referenceUrls.value],
    source: "web" as const,
    credit_cost: selectedCreditCost.value,
  };

  let submittedCount = 0;
  submitting.value = true;
  try {
    for (let index = 0; index < taskCount; index += 1) {
      await submitVideoTaskFromPayload(payload);
      submittedCount += 1;
    }
    message.success(submittedCount > 1 ? `已提交 ${submittedCount} 个视频任务` : "视频任务已提交");
  } catch (err: any) {
    const detail = formatRequestError(err);
    message.error(
      submittedCount > 0
        ? `已提交 ${submittedCount} 个视频任务，后续提交失败：${detail}`
        : detail,
    );
  } finally {
    submitting.value = false;
  }
}

function getVideoStatusLabel(status: VideoTaskResult["status"]) {
  if (status === "queued") return "排队中";
  if (status === "processing") return "生成中";
  if (status === "success") return "已完成";
  if (status === "failed") return "失败";
  return "待处理";
}

function getVideoTaskSceneLabel(task: VideoTaskResult) {
  const matchedScene = taskScenes.value.find((item) => item.scene_key === task.model);
  return matchedScene?.display_name || matchedScene?.scene_label || task.model;
}

function getSceneOptionLabel(scene: VideoTaskSceneConfig) {
  return (scene.display_name || scene.scene_label || scene.scene_key).trim();
}

function getSceneOptionSubtitle(scene: VideoTaskSceneConfig) {
  return (scene.subtitle || scene.scene_description || "").trim();
}

function getVideoTaskModeLabel(task: VideoTaskResult) {
  const mode = getGenerateModeFromTask(task);
  if (mode === "firstLastFrame") return "首尾帧";
  if (mode === "imageToVideo") return "图生视频";
  return "文生视频";
}

function getVideoTaskSpecLabel(task: VideoTaskResult) {
  return [
    getVideoTaskModeLabel(task),
    task.resolution || "",
    task.duration_seconds ? `${task.duration_seconds}秒` : "",
  ].filter(Boolean).join("/");
}

function handleRecreateTask(task: VideoTaskResult) {
  const restoredReferenceImages = [...(task.reference_images || [])];
  generateMode.value = getGenerateModeFromTask(task);
  selectedModel.value = task.model || "";
  prompt.value = task.prompt || "";
  selectedAspectRatio.value = task.aspect_ratio || "";
  selectedDuration.value = task.duration_seconds ? String(task.duration_seconds) : "";
  selectedResolution.value = task.resolution || "";
  replaceReferenceItems(restoredReferenceImages);
  message.success("已回填到左侧编辑区，请确认后重新提交");
}

function openVideoTaskDetail(task: VideoTaskResult) {
  detailTask.value = task;
  detailOpen.value = true;
}

function openFeedbackDialog(task: VideoTaskResult) {
  feedbackTarget.value = task;
  feedbackDialogOpen.value = true;
}

const detailTaskIndex = computed(() => {
  if (!detailOpen.value || !detailTask.value) return -1;
  return videoTasks.value.findIndex((item) => item.id === detailTask.value?.id);
});

const hasDetailPrev = computed(() => detailTaskIndex.value > 0);
const hasDetailNext = computed(() => (
  detailTaskIndex.value >= 0
  && detailTaskIndex.value < videoTasks.value.length - 1
));

function navigateVideoTaskDetail(delta: -1 | 1) {
  const nextIndex = detailTaskIndex.value + delta;
  const nextTask = videoTasks.value[nextIndex];
  if (!nextTask) return;
  openVideoTaskDetail(nextTask);
}

function handleDetailReedit(task: VideoTaskResult) {
  detailOpen.value = false;
  handleRecreateTask(task);
}

function handleDownloadVideo(task: VideoTaskResult) {
  if (!task.videos[0]?.video_url) {
    message.warning("当前没有可下载的原视频");
    return;
  }
  try {
    triggerDirectDownload(task.videos[0]?.video_url || "", `${task.id}.${task.videos[0]?.video_format || "mp4"}`);
  } catch {
    message.error("原视频下载失败");
  }
}

function handleDeleteTask(task: VideoTaskResult) {
  Modal.confirm({
    title: "删除该视频任务？",
    content: "删除后将从当前任务列表中移除，且无法恢复。",
    centered: true,
    okButtonProps: { danger: true },
    onOk: async () => {
      try {
        await deleteVideoTask(task.id);
        videoTasks.value = videoTasks.value.filter((item) => item.id !== task.id);
        videoPlayerRefs.delete(task.id);
        if (playingVideoTaskIds.value.has(task.id)) {
          const next = new Set(playingVideoTaskIds.value);
          next.delete(task.id);
          playingVideoTaskIds.value = next;
        }
        if (detailTask.value?.id === task.id) {
          detailOpen.value = false;
          detailTask.value = null;
        }
        message.success("视频任务已删除");
      } catch (err: any) {
        message.error(formatRequestError(err));
      }
    },
  });
}

watch(selectedScene, () => {
  ensureSceneDefaults();
});

watch(generateMode, () => {
  ensureSceneDefaults();
});

watch(
  () => route.query.mode,
  () => {
    applyRouteVideoMode();
  },
);

watch(videoTasks, (tasks) => {
  if (!detailOpen.value || !detailTask.value) return;
  const latest = tasks.find((item) => item.id === detailTask.value?.id);
  if (latest) {
    if (detailTask.value.status === "success" && latest.status === "success") return;
    detailTask.value = latest;
  }
});

watch(
  () => maxReferenceImages.value,
  (limit) => {
    if (generateMode.value !== "imageToVideo" || limit <= 0 || referenceItems.value.length <= limit) return;
    const removedItems = referenceItems.value.slice(limit);
    removedItems.forEach((item) => revokeObjectUrl(item.objectUrl));
    referenceItems.value = referenceItems.value.slice(0, limit);
    message.warning(`当前模型最多支持 ${limit} 张参考图，已自动保留前 ${limit} 张`);
  },
);

watch(activeTaskIds, (ids) => {
  if (ids.length) {
    startTaskPolling();
  } else {
    stopTaskPolling();
  }
});

watch(() => auth.isLoggedIn, () => {
  void loadRecentTasks();
});

onMounted(() => {
  updateViewportWidth();
  if (typeof window !== "undefined") {
    window.addEventListener("resize", updateViewportWidth);
    window.addEventListener("focus", handleFilePickerFocusReturn);
    document.addEventListener("visibilitychange", handleDocumentVisibilityChange);
  }
  void loadSceneConfigs().then(() => {
    applyRouteVideoMode();
    applyIncomingVideoDraft();
  });
  void loadRecentTasks();
});

onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("resize", updateViewportWidth);
    window.removeEventListener("focus", handleFilePickerFocusReturn);
    document.removeEventListener("visibilitychange", handleDocumentVisibilityChange);
  }
  clearFilePickerRecoveryTimer();
  stopTaskPolling();
  referenceItems.value.forEach((item) => revokeObjectUrl(item.objectUrl));
  firstLastFrameItems.value.forEach((item) => revokeObjectUrl(item?.objectUrl));
});
</script>

<template>
  <div class="generate-page">
    <div class="generate-workbench">
      <div class="left-col">
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
                    <span>文生视频</span>
                  </span>
                </button>
                <button
                  type="button"
                  class="mode-switch-btn"
                  :class="{ active: generateMode === 'imageToVideo' }"
                  @click="generateMode = 'imageToVideo'"
                >
                  <span class="generate-tab-label">
                    <PictureOutlined />
                    <span>图生视频</span>
                  </span>
                </button>
                <button
                  type="button"
                  class="mode-switch-btn"
                  :class="{ active: generateMode === 'firstLastFrame' }"
                  @click="generateMode = 'firstLastFrame'"
                >
                  <span class="generate-tab-label">
                    <PictureOutlined />
                    <span>首尾帧</span>
                  </span>
                </button>
              </div>
            </div>
          </div>
          <transition name="generate-panel-slide" mode="out-in">
            <section :key="generateMode" class="work-panel settings-panel generate-config-panel">
              <div class="settings-scroll">
                <template v-if="loading">
                  <a-skeleton active :paragraph="{ rows: 8 }" />
                </template>
                <template v-else>
                  <div class="settings-row model-row config-section">
                    <div class="setting-item setting-item-full">
                      <label>选择模型</label>
                      <div class="model-select-wrap">
                        <a-select
                          v-model:value="selectedModel"
                          :bordered="false"
                          class="flat-select"
                          option-label-prop="label"
                          popup-class-name="video-generate-dropdown"
                          :placeholder="generateMode === 'firstLastFrame' ? '请选择首尾帧模型' : (generateMode === 'imageToVideo' ? '请选择图生视频模型' : '请选择文生视频模型')"
                        >
                          <a-select-option
                            v-for="scene in filteredTaskScenes"
                            :key="scene.scene_key"
                            :value="scene.scene_key"
                            :label="getSceneOptionLabel(scene)"
                          >
                            <div class="scene-option">
                              <div class="scene-option-title">{{ getSceneOptionLabel(scene) }}</div>
                              <div v-if="getSceneOptionSubtitle(scene)" class="scene-option-desc">
                                {{ getSceneOptionSubtitle(scene) }}
                              </div>
                            </div>
                          </a-select-option>
                        </a-select>
                        <span v-if="filteredTaskScenes.length" class="model-count-hint">共 {{ filteredTaskScenes.length }} 个模型</span>
                      </div>
                    </div>
                  </div>

                  <div
                    v-if="generateMode === 'imageToVideo'"
                    class="field-block ref-upload-block config-section"
                    :class="{ 'is-reference-drag-over': referenceDragActive }"
                    @dragover="handleReferenceDragOver"
                    @dragleave="handleReferenceDragLeave"
                    @drop="handleReferenceDrop"
                  >
                    <div class="panel-head">
                      <div class="panel-head-main">
                        <h3>参考图</h3>
                        <span class="panel-hint">(最多 {{ maxReferenceImages }} 张，支持拖拽上传)</span>
                      </div>
                      <div class="panel-head-actions">
                        <a-button type="text" class="asset-library-btn" @click.stop="openAssetPicker">我的素材</a-button>
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
                      >
                        <img :src="getReferencePreviewUrl(item)" alt="参考图" />
                        <div v-if="item.status !== 'success'" class="upload-thumb-mask" :class="{ error: item.status === 'failed' }">
                          <a-spin v-if="item.status === 'uploading'" />
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
                        class="upload-add"
                        @click="triggerUpload()"
                      >
                        <a-spin v-if="referencePickerOpening" />
                        <template v-else>
                          <CloudUploadOutlined class="upload-add-icon" style="font-size: 22px" />
                          <span>{{ referenceDragActive ? "松开上传" : "拖拽或点击" }}</span>
                        </template>
                      </div>
                    </div>
                  </div>

                  <div
                    v-if="generateMode === 'firstLastFrame'"
                    class="field-block ref-upload-block config-section"
                  >
                    <div class="panel-head">
                      <h3>首尾帧</h3>
                      <div class="panel-head-actions">
                        <span class="panel-hint">首帧和尾帧各 1 张，支持拖拽上传</span>
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

                    <div class="frame-upload-grid">
                      <div
                        v-for="slot in FIRST_LAST_FRAME_SLOTS"
                        :key="slot"
                        class="frame-upload-card"
                        :class="{ 'is-reference-drag-over': frameDragActive === slot }"
                        @dragover="handleFrameDragOver($event, slot)"
                        @dragleave="handleFrameDragLeave($event, slot)"
                        @drop="handleFrameDrop($event, slot)"
                      >
                        <div v-if="firstLastFrameItems[slot]" class="upload-thumb frame-upload-thumb">
                          <img :src="getFrameReferencePreviewUrl(slot)" :alt="slot === 0 ? '首帧' : '尾帧'" />
                          <div v-if="getFrameReferenceStatus(slot) !== 'success'" class="upload-thumb-mask" :class="{ error: getFrameReferenceStatus(slot) === 'failed' }">
                            <a-spin v-if="getFrameReferenceStatus(slot) === 'uploading'" />
                            <span v-else>上传失败</span>
                          </div>
                          <a-tooltip v-if="canQuickSaveReferenceItem(firstLastFrameItems[slot])" title="加入我的素材">
                            <button
                              type="button"
                              class="thumb-save"
                              :aria-label="slot === 0 ? '将首帧加入我的素材' : '将尾帧加入我的素材'"
                              :disabled="isSavingReferenceToLibrary(firstLastFrameItems[slot]?.id || '')"
                              @click.stop="confirmSaveFrameReferenceItem(slot)"
                            >
                              <PlusOutlined />
                            </button>
                          </a-tooltip>
                          <button
                            type="button"
                            class="thumb-remove"
                            :aria-label="slot === 0 ? '删除首帧' : '删除尾帧'"
                            @click.stop="removeFrameReference(slot)"
                          >
                            <CloseOutlined />
                          </button>
                        </div>
                        <div
                          v-else
                          class="upload-add frame-upload-add"
                          @click="triggerUpload(slot)"
                        >
                          <a-spin v-if="referencePickerOpening" />
                          <template v-else>
                            <CloudUploadOutlined class="upload-add-icon" style="font-size: 22px" />
                            <span>{{ frameDragActive === slot ? "松开上传" : `上传${slot === 0 ? "首帧" : "尾帧"}` }}</span>
                          </template>
                        </div>
                        <a-button type="text" class="asset-library-btn frame-asset-btn" @click.stop="openFrameAssetPicker(slot)">
                          我的素材
                        </a-button>
                      </div>
                    </div>
                  </div>

                  <div class="prompt-block config-section">
                    <div class="prompt-label-row">
                      <div class="prompt-label-main">
                        <label>提示词</label>
                        <a-tooltip v-if="canQuickSavePrompt(prompt, lastSavedPromptText)" title="加入我的提示词">
                          <button
                            type="button"
                            class="prompt-quick-save-btn"
                            aria-label="加入我的提示词"
                            :disabled="isQuickSavePromptPending('video-prompt')"
                            @click="confirmSavePromptToLibrary(prompt, 'video-prompt', markPromptQuickSaved)"
                          >
                            <PlusOutlined />
                          </button>
                        </a-tooltip>
                      </div>
                      <div class="prompt-label-actions">
                        <PromptInterceptionTip
                          :sections="VIDEO_PROMPT_INTERCEPTION_TIP_SECTIONS"
                          :footnote="VIDEO_PROMPT_INTERCEPTION_TIP_FOOTNOTE"
                        />
                        <a-button type="text" class="prompt-library-btn" @click="openPromptLibrary">我的提示词</a-button>
                      </div>
                    </div>
                    <div class="prompt-input-wrap">
                      <a-textarea
                        v-model:value="prompt"
                        :rows="5"
                        :maxlength="5000"
                        allow-clear
                        show-count
                        :placeholder="promptPlaceholder"
                        class="prompt-input"
                      />
                      <a-tooltip title="放大编辑">
                        <span class="prompt-expand-btn-wrap">
                          <button
                            type="button"
                            class="prompt-expand-btn"
                            aria-label="放大编辑"
                            @click="promptExpandOpen = true"
                          >
                            <ExpandOutlined />
                          </button>
                        </span>
                      </a-tooltip>
                    </div>
                  </div>

                  <div class="settings-row settings-row-inline config-section compact-config-section">
                    <div v-if="!hideAspectRatio && aspectRatioOptions.length" class="setting-item setting-item-inline">
                      <label>宽高比</label>
                      <AspectRatioPicker v-model="selectedAspectRatio" :options="aspectRatioOptions" />
                    </div>
                    <div v-if="!hideResolution && resolutionOptions.length" class="setting-item setting-item-inline">
                      <label>分辨率</label>
                      <OptionGridPicker
                        v-model:model-value="selectedResolution"
                        :options="resolutionOptions"
                        panel-title="选择分辨率"
                        placeholder="选择分辨率"
                      />
                    </div>
                    <div v-if="!hideDuration && durationOptions.length" class="setting-item setting-item-inline">
                      <label>秒数</label>
                      <OptionGridPicker
                        v-model:model-value="selectedDuration"
                        :options="durationOptions"
                        panel-title="选择秒数"
                        placeholder="选择秒数"
                      />
                    </div>
                  </div>

                  <div class="settings-row config-section">
                    <div class="setting-item setting-item-full">
                      <label>生成数量</label>
                      <div class="task-count-slider-wrap">
                        <a-slider
                          v-model:value="selectedTaskCount"
                          :min="1"
                          :max="4"
                          :step="1"
                          :marks="VIDEO_TASK_COUNT_MARKS"
                          class="task-count-slider"
                        />
                      </div>
                    </div>
                  </div>
                </template>
              </div>

              <div class="settings-footer">
                <a-button
                  type="primary"
                  block
                  size="large"
                  class="generate-btn"
                  :loading="submitting"
                  @click="handleSubmit"
                >
                  <template #icon><ThunderboltOutlined /></template>
                  {{ generateButtonText }}
                </a-button>
              </div>
            </section>
          </transition>
        </div>
      </div>

      <section class="work-panel result-panel">
        <div class="result-head">
          <div class="result-head-main">
            <div class="result-tips">
              <div class="result-tip-line">
                每日前 <span class="result-tip-highlight">20</span> 次失败任务不扣积分
                <span v-if="failureRefundRemainingCount !== null">（剩余{{ failureRefundRemainingCount }}次）</span>
              </div>
            </div>
          </div>
          <div class="result-head-meta">
            <UpdateLogEntryButton />
            <a-select
              v-model:value="preferredResultColumnCount"
              class="result-column-select"
              placeholder="卡片列数"
            >
              <a-select-option
                v-for="columnCount in RESULT_COLUMN_OPTIONS"
                :key="columnCount"
                :value="columnCount"
              >
                {{ columnCount }} 列
              </a-select-option>
            </a-select>
            <div class="result-retain-badge">
              <ExclamationCircleFilled class="result-retain-icon" />
              <span>服务器只保留视频3天</span>
            </div>
          </div>
        </div>

        <div class="result-body">
          <div v-if="videoTasks.length" class="video-task-list" :style="resultListStyle">
            <article
              v-for="task in videoTasks"
              :key="task.id"
              class="video-task-card is-clickable"
              @click="openVideoTaskDetail(task)"
            >
              <div class="video-task-head">
                <div class="video-task-head-main">
                  <div class="video-task-meta">
                    <span
                      v-if="getVideoTaskSceneLabel(task)"
                      class="video-task-model-tag"
                      :title="getVideoTaskSceneLabel(task)"
                    >
                      {{ getVideoTaskSceneLabel(task) }}
                    </span>
                    <span
                      v-if="getVideoTaskSpecLabel(task)"
                      :title="getVideoTaskSpecLabel(task)"
                    >
                      {{ getVideoTaskSpecLabel(task) }}
                    </span>
                    <span
                      v-if="['pending', 'queued', 'processing'].includes(task.status)"
                      class="video-task-status"
                      :class="`is-${task.status}`"
                    >
                      {{ getVideoStatusLabel(task.status) }}
                    </span>
                  </div>
                </div>
                <div class="video-task-head-side">
                  <div class="video-task-actions" @click.stop>
                    <a-tooltip title="查看详情">
                      <a-button
                        shape="circle"
                        class="video-task-action-btn"
                        @click.stop="openVideoTaskDetail(task)"
                      >
                        <template #icon><EyeOutlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-tooltip title="回填参数">
                      <a-button
                        shape="circle"
                        class="video-task-action-btn"
                        @click.stop="handleRecreateTask(task)"
                      >
                        <template #icon><ReloadOutlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-dropdown :trigger="['click']">
                      <a-button shape="circle" class="video-task-action-btn" @click.stop>
                        <template #icon><MoreOutlined /></template>
                      </a-button>
                      <template #overlay>
                        <a-menu>
                          <a-menu-item
                            :disabled="!task.videos[0]?.video_url"
                            @click="handleDownloadVideo(task)"
                          >
                            <span class="video-task-menu-item">
                              <DownloadOutlined />
                              <span>下载原视频</span>
                            </span>
                          </a-menu-item>
                          <a-menu-item @click="openFeedbackDialog(task)">
                            <span class="video-task-menu-item">
                              <MessageOutlined />
                              <span>反馈</span>
                            </span>
                          </a-menu-item>
                          <a-menu-item danger @click="handleDeleteTask(task)">
                            <span class="video-task-menu-item">
                              <DeleteOutlined />
                              <span>删除任务</span>
                            </span>
                          </a-menu-item>
                        </a-menu>
                      </template>
                    </a-dropdown>
                  </div>
                </div>
              </div>

              <div class="video-task-prompt">{{ task.prompt }}</div>

              <div class="video-result-box">
                <template v-if="['pending', 'queued', 'processing'].includes(task.status)">
                  <a-spin />
                  <div class="video-result-hint">视频生成中，请稍候...</div>
                </template>

                <template v-else-if="task.status === 'success' && task.videos[0]?.video_url">
                  <div class="video-result-player-shell" :class="{ 'is-started': hasVideoStarted(task.id) }">
                    <video
                      :ref="(el) => setVideoPlayerRef(task.id, el)"
                      class="video-result-player"
                      :poster="task.videos[0].cover_url || undefined"
                      :src="task.videos[0].video_url"
                      :controls="hasVideoStarted(task.id)"
                      playsinline
                      preload="metadata"
                      @play="markVideoStarted(task.id)"
                      @click.stop
                    />
                    <button
                      v-if="!hasVideoStarted(task.id)"
                      type="button"
                      class="video-result-play-btn"
                      aria-label="播放视频"
                      @click.stop="handlePlayVideo(task.id)"
                    >
                      <svg class="video-result-play-icon" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M7.2 6.4c0-.9 1-1.45 1.75-1l8.1 4.7c.8.45.8 1.55 0 2l-8.1 4.7c-.75.45-1.75-.1-1.75-1V6.4Z" />
                      </svg>
                    </button>
                  </div>
                </template>

                <template v-else>
                  <div class="video-result-error">{{ task.error_message || task.videos[0]?.error_message || "生成视频失败，请反馈给我们处理" }}</div>
                </template>
              </div>
            </article>
          </div>

          <div v-else class="result-empty">
            <transition name="generate-panel-slide" mode="out-in">
              <div :key="generateMode" class="result-empty-copy">
                <div class="empty-illustration-shell">
                  <VideoCameraOutlined class="empty-video-icon" />
                </div>
                <div class="empty-title">{{ emptyStateTitle }}</div>
                <div class="empty-desc">{{ emptyStateDescription }}</div>
              </div>
            </transition>
          </div>
        </div>
      </section>
    </div>
    <UserAssetPicker
      v-if="assetPickerOpen"
      v-model:open="assetPickerOpen"
      title="我的素材"
      @select-asset="handlePickUserAsset"
      @select-assets="handlePickUserAssets"
    />
    <UserPromptLibraryModal
      v-if="promptLibraryVisible"
      v-model:open="promptLibraryVisible"
      @select-prompt="useLibraryPrompt"
    />
    <PromptExpandDialog
      v-model:open="promptExpandOpen"
      :value="prompt"
      draft-key="video-prompt"
      :maxlength="5000"
      :placeholder="promptPlaceholder"
      @confirm="applyExpandedPrompt"
    />
    <FeedbackDialog
      v-if="feedbackDialogOpen"
      v-model:open="feedbackDialogOpen"
      title="视频任务反馈"
      :task-id="feedbackTarget?.id"
      :model="feedbackTarget?.model"
      :prompt="feedbackTarget?.prompt"
      :created-at="feedbackTarget?.created_at"
      feedback-type="video_task"
    />
    <VideoTaskDetailDialog
      v-if="detailOpen"
      v-model:open="detailOpen"
      :item="detailTask"
      :model-options="detailModelOptions"
      :has-prev="hasDetailPrev"
      :has-next="hasDetailNext"
      compact
      @reedit="handleDetailReedit"
      @download="handleDownloadVideo"
      @navigate-prev="navigateVideoTaskDetail(-1)"
      @navigate-next="navigateVideoTaskDetail(1)"
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
}

:global(.app-layout-desktop-side-nav) .generate-page {
  min-height: calc(100dvh - 66px);
  height: calc(100dvh - 66px);
}

.generate-workbench {
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
}

.left-col {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  min-width: var(--generate-config-min-width);
  max-width: var(--generate-config-max-width);
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
}

.mode-switch-cluster {
  min-width: 0;
  display: flex;
  align-items: center;
}

.mode-switch-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mode-switch-group-primary {
  gap: 12px;
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

.generate-tab-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 18px;
  border-radius: 14px;
  font-weight: 700;
  white-space: nowrap;

  .anticon {
    font-size: 17px;
  }
}

.work-panel {
  box-sizing: border-box;
  min-width: 0;
  max-width: 100%;
  background: var(--theme-modal-bg);
  border: 1px solid var(--theme-panel-border);
  border-radius: 24px;
  box-shadow: 0 18px 45px var(--theme-shadow-soft);
  padding: 20px;
}

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
  border-color: var(--theme-panel-border);
  box-shadow:
    0 18px 36px var(--theme-shadow-soft),
    inset 0 1px 0 var(--theme-panel-inset);
}

.settings-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 10px 0 4px;
}

.settings-footer {
  position: relative;
  z-index: 3;
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 8px;
  background: linear-gradient(
    180deg,
    rgba(var(--theme-surface-strong-rgb), 0),
    rgba(var(--theme-surface-strong-rgb), 0.94) 28%,
    var(--theme-surface-strong)
  );
}

.config-section {
  position: relative;
  padding: 0 0 10px;
}

.compact-config-section {
  padding-top: 0;
  padding-bottom: 10px;
}

.settings-row {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.settings-row-inline {
  align-items: center;
  flex-direction: row;
  gap: 14px;
}

.setting-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.setting-item-full {
  width: 100%;

  label {
    color: var(--config-title-color);
    font-size: 15px;
    font-weight: 700;
    line-height: 1.4;
  }
}

.setting-item-inline {
  flex: 1 1 0;

  label {
    color: var(--config-title-color);
    font-size: 15px;
    font-weight: 700;
    line-height: 1.4;
  }
}

.setting-label-row,
.prompt-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: var(--config-title-gap);

  label {
    color: var(--config-title-color);
    font-size: 15px;
    font-weight: 700;
    line-height: 1.4;
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

.panel-hint {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  line-height: 1.5;
  text-align: right;
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

.field-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
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

.ref-upload-block {
  position: relative;
  border-radius: 18px;
  transition:
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    background var(--motion-duration-fast) var(--motion-ease-soft);
}

.ref-upload-block.is-reference-drag-over {
  background: color-mix(in srgb, var(--theme-accent) 8%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-accent) 28%, transparent);
}

.upload-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.upload-thumb {
  position: relative;
  width: 77px;
  height: 77px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  flex-shrink: 0;
  box-shadow: 0 8px 18px var(--theme-shadow-soft);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.upload-thumb-mask {
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
  cursor: pointer;
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

.upload-thumb:hover .thumb-save,
.upload-thumb:focus-within .thumb-save {
  opacity: 1;
  transform: scale(1);
}

.thumb-save:hover,
.thumb-save:focus-visible {
  background: rgba(0, 0, 0, 0.92);
}

.upload-add {
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

  &:hover {
    border-color: var(--theme-border-strong);
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg));
    transform: translateY(-2px);
    box-shadow:
      inset 0 1px 0 var(--theme-panel-inset),
      0 14px 24px var(--theme-shadow-medium);
  }
}

.upload-add-icon {
  color: currentColor;
}

.frame-upload-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.frame-upload-card {
  position: relative;
}

.frame-upload-thumb,
.frame-upload-add {
  width: 100%;
  height: auto;
  aspect-ratio: 1 / 1;
}

.frame-upload-card.is-reference-drag-over .frame-upload-thumb,
.frame-upload-card.is-reference-drag-over .frame-upload-add {
  background: color-mix(in srgb, var(--theme-accent) 8%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--theme-accent) 28%, transparent);
}

.frame-asset-btn {
  position: absolute;
  right: 12px;
  bottom: 12px;
  left: 12px;
  width: auto;
  z-index: 3;
  opacity: 0;
  pointer-events: none;
  transform: translateY(4px);
}

.frame-upload-card:hover .frame-asset-btn,
.frame-upload-card:focus-within .frame-asset-btn {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
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

.model-select-wrap {
  position: relative;
}

.model-count-hint {
  position: absolute;
  top: 50%;
  right: 36px;
  transform: translateY(-50%);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  pointer-events: none;
}

.flat-select {
  width: 100%;
  background: var(--theme-field-bg, var(--theme-control-bg));
  border: 1px solid var(--theme-control-border-strong);
  border-radius: 16px;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 8px 18px var(--theme-card-shadow);
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    border-color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover,
  &:focus-within {
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg));
  }

  :deep(.ant-select-selector) {
    height: 52px !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 128px 0 14px !important;
  }

  :deep(.ant-select-selection-item) {
    line-height: 52px !important;
    font-weight: 700;
    color: var(--theme-title);
  }

  :deep(.ant-select-selection-placeholder) {
    line-height: 52px !important;
  }
}

.task-count-slider-wrap {
  width: 100%;
  padding: 0 10px;
  box-sizing: border-box;
}

.task-count-slider {
  margin: 4px 0 22px;

  :deep(.ant-slider-rail) {
    height: 8px;
    background: color-mix(in srgb, var(--theme-accent) 18%, transparent);
    border-radius: 999px;
  }

  :deep(.ant-slider-track) {
    height: 8px;
    background: linear-gradient(90deg, var(--theme-progress) 0%, color-mix(in srgb, var(--theme-progress) 70%, var(--theme-accent)) 100%);
    border-radius: 999px;
  }

  :deep(.ant-slider-dot) {
    width: 12px;
    height: 12px;
    margin-inline-start: 0;
    inset-block-start: 50%;
    transform: translate(-50%, -50%);
    background: var(--theme-surface-strong);
    border: 2px solid color-mix(in srgb, var(--theme-accent) 45%, transparent);
    box-shadow: 0 1px 4px var(--theme-shadow-soft);
  }

  :deep(.ant-slider-dot-active) {
    border-color: var(--theme-accent);
  }

  :deep(.ant-slider-handle) {
    width: 18px;
    height: 18px;
    inset-block-start: -5px;
  }

  :deep(.ant-slider-handle)::after {
    width: 18px;
    height: 18px;
    inset-inline-start: 0;
    inset-block-start: 0;
    box-sizing: border-box;
    background: linear-gradient(180deg, var(--theme-accent-strong) 0%, var(--theme-accent) 100%);
    border: 2px solid var(--theme-surface-strong);
    box-shadow:
      0 4px 14px var(--theme-shadow-medium),
      inset 0 1px 0 var(--theme-panel-inset);
  }

  :deep(.ant-slider-mark-text) {
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 600;
  }
}

.scene-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 0;
}

.scene-option-title {
  font-weight: 700;
  color: var(--theme-title);
  line-height: 1.35;
}

.scene-option-desc {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
  white-space: normal;
}

.prompt-input {
  border: none !important;
  background: transparent !important;

  &.ant-input-textarea-show-count,
  :deep(.ant-input-textarea-show-count) {
    color: var(--theme-title) !important;
  }

  &.ant-input-textarea-show-count::after,
  :deep(.ant-input-textarea-show-count)::after,
  :deep(.ant-input-data-count) {
    color: var(--theme-title) !important;
  }

  :deep(.ant-input) {
    border: 1px solid var(--theme-control-border-strong) !important;
    border-radius: 18px;
    background: var(--theme-field-bg, var(--theme-control-bg)) !important;
    outline: none !important;
    box-shadow: inset 0 1px 0 var(--theme-panel-inset);
    color: var(--theme-title);
    line-height: 1.7;
    padding: 14px 16px 44px;
    transition: background var(--motion-duration-fast) var(--motion-ease-soft);
  }

  :deep(.ant-input:hover),
  :deep(.ant-input:focus),
  :deep(.ant-input:focus-visible) {
    border: 1px solid var(--theme-control-border-strong) !important;
    background: var(--theme-field-hover-bg, var(--theme-control-hover-bg)) !important;
    outline: none !important;
    box-shadow: inset 0 1px 0 var(--theme-panel-inset) !important;
    transform: none;
  }
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

.generate-btn {
  margin-top: 10px;
  height: 48px;
  border-radius: 16px;
  font-size: 15px;
  font-weight: 700;
  background: var(--theme-accent) !important;
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

.result-panel {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--theme-panel-bg);
}

.result-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px 12px;
}

.result-head-main {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.result-tips {
  display: flex;
  flex-direction: column;
  gap: 4px;
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
  flex-wrap: wrap;
  justify-content: flex-end;
}

.result-column-select {
  width: 96px;
}

.result-retain-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 30px;
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

.result-retain-icon {
  color: #e25555;
  font-size: 13px;
}

.result-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 14px;
  padding-right: 4px;
  display: flex;
  flex-direction: column;
}

.video-task-list {
  display: grid;
  gap: 16px;
  margin-top: 2px;
  align-items: start;
}

.video-task-card {
  border: 1px dashed var(--theme-panel-border);
  border-radius: 20px;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  padding: 16px;
  box-shadow: 0 14px 24px var(--theme-shadow-soft);
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  height: 100%;
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    box-shadow var(--motion-duration-hover) var(--motion-ease-soft),
    border-color var(--motion-duration-hover) var(--motion-ease-soft);

  &.is-clickable {
    cursor: pointer;
  }

  &.is-clickable:hover {
    transform: translateY(-4px);
    border-color: var(--theme-border-strong);
    box-shadow: 0 16px 28px var(--theme-shadow-medium);
  }

  &.is-clickable:active {
    transform: scale(0.992);
  }
}

.video-task-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.video-task-head-main {
  min-width: 0;
  flex: 1;
}

.video-task-head-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.video-task-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.video-task-action-btn {
  border-color: var(--theme-panel-border-strong) !important;
  background: rgba(var(--theme-surface-strong-rgb), 0.82) !important;
  color: var(--theme-accent-text) !important;
  box-shadow: none !important;
}

.video-task-action-btn:hover,
.video-task-action-btn:focus {
  border-color: var(--theme-border-strong) !important;
  background: rgba(var(--theme-page-base-rgb), 0.96) !important;
  color: var(--theme-accent-text-hover) !important;
}

.video-task-menu-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.video-task-model-tag {
  font-weight: 700;
  color: var(--theme-title);
}

.video-task-meta {
  display: flex;
  gap: 8px;
  color: var(--text-muted);
  font-size: 12px;
  flex-wrap: wrap;
}

.video-task-meta > span {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(var(--theme-surface-strong-rgb), 0.72);
  border: 1px solid var(--theme-panel-border);
  line-height: 1;
  white-space: nowrap;
}

.video-task-status {
  font-weight: 700;
}

.video-task-status.is-success {
  color: #1d7a49;
  background: #edf9f1;
  border-color: #b8e4c8;
}

.video-task-status.is-failed {
  color: #c9483d;
  background: #fff1ef;
  border-color: #efb5ae;
}

.video-task-status.is-pending,
.video-task-status.is-queued,
.video-task-status.is-processing {
  color: #8a5d20;
  background: #fff1d7;
  border-color: #f1d29a;
}

.video-task-prompt {
  color: var(--theme-title);
  line-height: 1.6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.video-result-box {
  margin-top: auto;
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 18px;
  background: rgba(var(--theme-surface-strong-rgb), 0.58);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 10px;
  overflow: hidden;
}

.video-result-hint,
.video-result-error {
  color: var(--text-secondary);
  text-align: center;
  padding: 0 12px;
}

.video-result-player-shell {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 14px;
  overflow: hidden;
  background: #000;
}

.video-result-player {
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  border-radius: 14px;
  background: #000;
  object-fit: contain;
  display: block;
}

.video-result-play-btn {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(48, 48, 48, 0.58);
  transform: translate(-50%, -50%);
  cursor: pointer;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-press) var(--motion-ease-soft);

  &:hover {
    background: rgba(36, 36, 36, 0.7);
  }

  &:active {
    transform: translate(-50%, -50%) scale(0.96);
  }
}

.video-result-play-icon {
  width: 34px;
  height: 34px;
  margin: 0;
  fill: #fff;
}

.result-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--theme-link);
  font-weight: 700;
  text-decoration: none;

  &:hover {
    color: var(--theme-link-hover);
    text-decoration: underline;
  }
}

.result-empty {
  flex: 1;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 20px 28px;
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

.empty-illustration-shell {
  width: min(100%, 220px);
  margin-bottom: 8px;
  display: flex;
  justify-content: center;
}

.empty-video-icon {
  font-size: 64px;
  color: #caa066;
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

.generate-panel-slide-enter-active,
.generate-panel-slide-leave-active {
  transition:
    opacity var(--motion-duration-slide) var(--motion-ease-soft),
    transform var(--motion-duration-slide) var(--motion-ease-soft);
}

.generate-panel-slide-enter-from,
.generate-panel-slide-leave-to {
  opacity: 0;
  transform: translate3d(0, -12px, 0) scale(0.985);
}

@media (min-width: 1200px) and (hover: hover) and (pointer: fine) {
  .generate-workbench {
    --generate-config-min-width: 340px;
    --generate-config-fluid-width: 28vw;
    --generate-config-max-width: 520px;
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
  }

  .result-body {
    overflow-y: visible;
    padding-right: 0;
  }

  .settings-scroll {
    overflow-y: visible;
    padding: 0;
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

  .settings-footer {
    z-index: 1;
    margin-top: 8px;
    padding-top: 0;
  }

  .settings-row {
    flex-direction: column;
  }

  .settings-row-inline {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .result-head {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .result-head-meta {
    align-self: flex-start;
    width: 100%;
    justify-content: space-between;
  }

  .result-column-select {
    width: 92px;
  }

  .video-task-list {
    grid-template-columns: 1fr !important;
  }

  .frame-upload-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style lang="scss">
.video-generate-dropdown.ant-select-dropdown {
  border-radius: 14px;
  padding: 6px;
  background: var(--theme-dropdown-bg);
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 18px 32px var(--theme-shadow-medium);
}

.video-generate-dropdown .ant-select-item {
  border-radius: 10px;
  min-height: auto;
  padding-top: 8px;
  padding-bottom: 8px;
}

.video-generate-dropdown .ant-select-item-option-content {
  white-space: normal;
  overflow: visible;
  text-overflow: unset;
}

.video-generate-dropdown .ant-select-item-option-active:not(.ant-select-item-option-disabled) {
  background: var(--theme-dropdown-hover-bg);
}

.video-generate-dropdown .ant-select-item-option-selected:not(.ant-select-item-option-disabled) {
  background: var(--theme-dropdown-selected-bg);
  color: var(--theme-dropdown-selected-text);
}

html[data-theme="midnight"] .generate-page .upload-add {
  color: #ffffff;
}

html[data-theme="midnight"] .generate-page .upload-add-icon {
  color: var(--theme-accent) !important;
}

html[data-theme="midnight"] .generate-page .prompt-input.ant-input-textarea-show-count::after,
html[data-theme="midnight"] .generate-page .prompt-input .ant-input-data-count {
  color: #ffffff !important;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .prompt-library-btn,
html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .asset-library-btn {
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
</style>
