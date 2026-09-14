<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import {
  DownOutlined,
  MoreOutlined,
  PlusOutlined,
  SwapOutlined,
} from "@ant-design/icons-vue";
import {
  createVideoExternalApiConfig,
  createVideoExternalApiSceneBinding,
  deleteVideoExternalApiConfig,
  deleteVideoExternalApiSceneBinding,
  listVideoExternalApiConfigs,
  listVideoExternalApiSceneBindings,
  testVideoExternalApiConfig,
  updateVideoExternalApiConfig,
  updateVideoExternalApiConfigStatus,
  updateVideoExternalApiSceneBinding,
  updateVideoExternalApiSceneBindingMeta,
  updateVideoExternalApiSceneBindingStatus,
} from "@/api/admin";
import {
  parseAdminConfigTemplate,
  stringifyAdminConfigTemplate,
} from "@/lib/adminConfigTemplate";
import type {
  ExternalApiConfigStatus,
  ExternalApiRequestFormat,
  VideoExternalApiConfig,
  VideoExternalApiConfigPayload,
  VideoExternalApiConfigTestResult,
  VideoExternalApiSceneBinding,
  VideoExternalApiSceneBindingCreatePayload,
  VideoExternalApiSceneBindingMetaPayload,
  VideoGenerationMode,
} from "@/types";

type VideoCreditBillingMode = VideoExternalApiSceneBinding["credit_billing_mode"];
type ConfigUsageRole = "primary" | "backup";
type VideoSceneGroupKey = VideoGenerationMode | "mixed";
type ConfigUsageScene = {
  scene_key: string;
  scene_label: string;
  display_name: string;
  availability_label: string;
  roles: ConfigUsageRole[];
};

const DEFAULT_DURATION_OPTIONS_JSON = JSON.stringify([
  { label: "5 秒", value: "5" },
  { label: "10 秒", value: "10" },
], null, 2);
const DEFAULT_ASPECT_RATIO_OPTIONS_JSON = JSON.stringify([
  { label: "16:9", value: "16:9" },
  { label: "9:16", value: "9:16" },
  { label: "1:1", value: "1:1" },
], null, 2);
const DEFAULT_RESOLUTION_OPTIONS_JSON = JSON.stringify([
  { label: "540P", value: "540p" },
  { label: "720P", value: "720p" },
  { label: "1080P", value: "1080p" },
], null, 2);
const DEFAULT_RESOLUTION_MAPPING_JSON = JSON.stringify({}, null, 2);
const DEFAULT_RESOLUTION_CREDIT_COSTS_JSON = JSON.stringify({}, null, 2);
const DEFAULT_SUBMIT_SUCCESS_STATUSES_JSON = JSON.stringify([200, 201, 202], null, 2);
const DEFAULT_RESULT_SUCCESS_VALUES_JSON = JSON.stringify(["success", "succeeded", "completed"], null, 2);
const DEFAULT_RESULT_FAILED_VALUES_JSON = JSON.stringify(["failed", "error", "cancelled"], null, 2);
const DEFAULT_CREDIT_BILLING_MODE: VideoCreditBillingMode = "fixed";
const DEFAULT_AVAILABILITY_MODES: VideoGenerationMode[] = ["text_to_video", "image_to_video"];
const DEFAULT_PER_SECOND_CREDIT_COST = 1;

const configs = ref<VideoExternalApiConfig[]>([]);
const sceneBindings = ref<VideoExternalApiSceneBinding[]>([]);
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const bindingSavingKey = ref("");
const bindingCreating = ref(false);
const sceneMetaSaving = ref(false);
const modalOpen = ref(false);
const sceneModalOpen = ref(false);
const sceneMetaModalOpen = ref(false);
const copyModalOpen = ref(false);
const copyEditingKey = ref("");
const copyForm = reactive({
  display_name: "",
  subtitle: "",
});
const editingId = ref<number | null>(null);
const sceneEditingKey = ref("");
const isCopyMode = ref(false);
const isSceneCopyMode = ref(false);
const configGroupFilter = ref("all");
const configRequestFormatFilter = ref<"all" | ExternalApiRequestFormat>("all");
const configNameFilter = ref("");
const expandedConfigGroups = ref<string[]>([]);
const bindingGroupFilter = ref("all");
const bindingAvailabilityFilter = ref<"all" | VideoGenerationMode>("all");
const bindingNameFilter = ref("");
const configImportJson = ref("");
const sceneImportJson = ref("");

const VIDEO_SCENE_GROUP_ORDER: VideoSceneGroupKey[] = [
  "text_to_video",
  "image_to_video",
  "first_last_frame",
  "mixed",
];

const bindingColumns = [
  { title: "场景", key: "scene", width: 196, ellipsis: true },
  { title: "主接口", key: "bind", width: 400, ellipsis: true },
  { title: "互换", key: "swap", width: 64 },
  { title: "备用接口", key: "backup", width: 400, ellipsis: true },
  { title: "积分", key: "credit", width: 248 },
  { title: "排序", key: "sort", width: 72 },
  { title: "", key: "action", width: 56 },
];

const form = reactive<VideoExternalApiConfigPayload>({
  name: "",
  description: "",
  group_name: "默认",
  request_url: "",
  request_format: "json",
  headers_json: '{\n  "Content-Type": "application/json"\n}',
  payload_json: "{\n\n}",
  response_json: "{\n\n}",
  result_video_url_field: "",
  result_video_base64_field: "",
  result_cover_url_field: "",
  call_mode: "async",
  submit_success_statuses_json: DEFAULT_SUBMIT_SUCCESS_STATUSES_JSON,
  poll_url: "",
  poll_method: "GET",
  poll_headers_json: "{\n\n}",
  poll_payload_json: "{\n\n}",
  task_id_field: "",
  result_status_field: "",
  result_success_values_json: DEFAULT_RESULT_SUCCESS_VALUES_JSON,
  result_failed_values_json: DEFAULT_RESULT_FAILED_VALUES_JSON,
  result_error_field: "",
  poll_result_video_url_field: "",
  poll_result_video_base64_field: "",
  poll_result_cover_url_field: "",
  poll_interval_seconds: 5,
  poll_timeout_seconds: 600,
  status: "enabled",
});

const sceneForm = reactive<VideoExternalApiSceneBindingCreatePayload>({
  scene_key: "",
  scene_label: "",
  scene_description: "",
  sort_order: 100,
  hide_aspect_ratio: false,
  hide_duration: false,
  hide_resolution: false,
  availability_mode: "both",
  availability_modes: [...DEFAULT_AVAILABILITY_MODES],
  max_reference_images: 1,
  api_config_id: null,
  backup_api_config_id: null,
  display_name: "",
  subtitle: "",
  credit_billing_mode: DEFAULT_CREDIT_BILLING_MODE,
  credit_cost: 10,
  per_second_credit_cost: DEFAULT_PER_SECOND_CREDIT_COST,
  aspect_ratio_options_json: DEFAULT_ASPECT_RATIO_OPTIONS_JSON,
  duration_options_json: DEFAULT_DURATION_OPTIONS_JSON,
  resolution_options_json: DEFAULT_RESOLUTION_OPTIONS_JSON,
  resolution_mapping_json: DEFAULT_RESOLUTION_MAPPING_JSON,
  resolution_credit_costs_json: DEFAULT_RESOLUTION_CREDIT_COSTS_JSON,
  status: "enabled",
});

const sceneMetaForm = reactive<VideoExternalApiSceneBindingMetaPayload>({
  scene_key: "",
  scene_label: "",
  scene_description: "",
  sort_order: 100,
  hide_aspect_ratio: false,
  hide_duration: false,
  hide_resolution: false,
  availability_mode: "both",
  availability_modes: [...DEFAULT_AVAILABILITY_MODES],
  max_reference_images: 1,
  credit_billing_mode: DEFAULT_CREDIT_BILLING_MODE,
  credit_cost: 10,
  per_second_credit_cost: DEFAULT_PER_SECOND_CREDIT_COST,
  aspect_ratio_options_json: DEFAULT_ASPECT_RATIO_OPTIONS_JSON,
  duration_options_json: DEFAULT_DURATION_OPTIONS_JSON,
  resolution_options_json: DEFAULT_RESOLUTION_OPTIONS_JSON,
  resolution_mapping_json: DEFAULT_RESOLUTION_MAPPING_JSON,
  resolution_credit_costs_json: DEFAULT_RESOLUTION_CREDIT_COSTS_JSON,
});

const modalTitle = computed(() => {
  if (editingId.value) return "编辑视频接口配置";
  if (isCopyMode.value) return "复制新增视频接口配置";
  return "新增视频接口配置";
});
const sceneModalTitle = computed(() => (isSceneCopyMode.value ? "复制新增视频场景" : "新增视频场景"));
const groupOptions = computed(() => {
  const groups = Array.from(new Set(configs.value.map((item) => item.group_name || "未分组").filter(Boolean)));
  return groups.sort((a, b) => a.localeCompare(b, "zh-CN"));
});
const filteredConfigs = computed(() => configs.value.filter((item) => {
  if (configGroupFilter.value !== "all" && item.group_name !== configGroupFilter.value) return false;
  if (configRequestFormatFilter.value !== "all" && item.request_format !== configRequestFormatFilter.value) return false;
  if (!matchesNameFilter(configNameFilter.value, item.name, item.description)) return false;
  return true;
}));
const filteredSceneBindings = computed(() => sceneBindings.value.filter((item) => {
  if (bindingGroupFilter.value !== "all" && (item.api_group_name || "未分组") !== bindingGroupFilter.value) return false;
  if (bindingAvailabilityFilter.value !== "all") {
    const modes = normalizeAvailabilityModes(item.availability_modes, item.availability_mode);
    if (!modes.includes(bindingAvailabilityFilter.value)) return false;
  }
  if (!matchesNameFilter(
    bindingNameFilter.value,
    item.scene_label,
    item.scene_key,
    item.display_name,
    item.scene_description,
    item.api_config_name,
  )) return false;
  return true;
}));
const groupedConfigs = computed(() => {
  const map = new Map<string, VideoExternalApiConfig[]>();
  for (const item of filteredConfigs.value) {
    const key = item.group_name || "未分组";
    const list = map.get(key) ?? [];
    list.push(item);
    map.set(key, list);
  }
  return Array.from(map.entries())
    .sort(([a, aItems], [b, bItems]) => {
      const countDiff = bItems.length - aItems.length;
      if (countDiff !== 0) return countDiff;
      return a.localeCompare(b, "zh-CN");
    })
    .map(([group, items]) => ({
      group,
      items: [...items].sort((a, b) => {
        if (a.status !== b.status) return a.status === "enabled" ? -1 : 1;
        return a.name.localeCompare(b.name, "zh-CN");
      }),
    }));
});
const allConfigGroupsExpanded = computed(() => (
  groupedConfigs.value.length > 0
  && groupedConfigs.value.every((block) => expandedConfigGroups.value.includes(block.group))
));

function isConfigGroupExpanded(group: string) {
  return expandedConfigGroups.value.includes(group);
}

function toggleConfigGroup(group: string) {
  expandedConfigGroups.value = isConfigGroupExpanded(group)
    ? expandedConfigGroups.value.filter((item) => item !== group)
    : [...expandedConfigGroups.value, group];
}

function toggleAllConfigGroups() {
  expandedConfigGroups.value = allConfigGroupsExpanded.value
    ? []
    : groupedConfigs.value.map((block) => block.group);
}

const configUsageMap = computed(() => {
  const map = new Map<number, ConfigUsageScene[]>();
  const appendUsage = (configId: number | null | undefined, binding: VideoExternalApiSceneBinding, role: ConfigUsageRole) => {
    if (!configId) return;
    const list = map.get(configId) ?? [];
    const existing = list.find((item) => item.scene_key === binding.scene_key);
    if (existing) {
      if (!existing.roles.includes(role)) existing.roles.push(role);
    } else {
      list.push({
        scene_key: binding.scene_key,
        scene_label: binding.scene_label,
        display_name: binding.display_name,
        availability_label: availabilityModesLabel(binding.availability_modes, binding.availability_mode),
        roles: [role],
      });
    }
    map.set(configId, list);
  };
  for (const binding of sceneBindings.value) {
    appendUsage(binding.api_config_id, binding, "primary");
    appendUsage(binding.backup_api_config_id, binding, "backup");
  }
  return map;
});
const groupedSceneBindings = computed(() => {
  const map = new Map<VideoSceneGroupKey, VideoExternalApiSceneBinding[]>();
  for (const item of filteredSceneBindings.value) {
    const key = videoSceneGroupKey(item);
    const list = map.get(key) ?? [];
    list.push(item);
    map.set(key, list);
  }
  const knownTypes = VIDEO_SCENE_GROUP_ORDER.filter((sceneType) => map.has(sceneType));
  const extraTypes = Array.from(map.keys()).filter((sceneType) => !VIDEO_SCENE_GROUP_ORDER.includes(sceneType));
  return [...knownTypes, ...extraTypes].map((sceneType) => ({
    sceneType,
    items: [...(map.get(sceneType) || [])].sort((a, b) => {
      const sortDiff = Number(a.sort_order || 0) - Number(b.sort_order || 0);
      if (sortDiff !== 0) return sortDiff;
      return a.scene_label.localeCompare(b.scene_label, "zh-CN");
    }),
  }));
});
const bindingOptionGroups = computed(() => {
  const map = new Map<string, Array<{ label: string; value: number }>>();
  for (const item of configs.value.filter((config) => config.status === "enabled")) {
    const group = item.group_name || "未分组";
    const list = map.get(group) ?? [];
    list.push({ label: item.name, value: item.id });
    map.set(group, list);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b, "zh-CN"))
    .map(([group, options]) => ({
      group,
      options: options.sort((a, b) => a.label.localeCompare(b.label, "zh-CN")),
    }));
});

function videoSceneGroupKey(record: VideoExternalApiSceneBinding): VideoSceneGroupKey {
  const modes = normalizeAvailabilityModes(record.availability_modes, record.availability_mode);
  if (modes.length === 1) return modes[0];
  return "mixed";
}

function videoSceneGroupLabel(sceneType: VideoSceneGroupKey) {
  if (sceneType === "mixed") return "多模式";
  return availabilityModeItemLabel(sceneType);
}

function configCardName(item: VideoExternalApiConfig) {
  const name = (item.name || "").trim() || "未命名接口";
  const group = (item.group_name || "").trim();
  if (!group || group === "未分组") return name;
  const prefixes = [`${group}-`, `${group} `];
  for (const prefix of prefixes) {
    if (name.startsWith(prefix) && name.length > prefix.length) {
      return name.slice(prefix.length).replace(/^[-_\s]+/, "") || name;
    }
  }
  return name;
}

function configUsageScenes(configId: number) {
  return configUsageMap.value.get(configId) || [];
}

function configUsageCount(configId: number) {
  return configUsageScenes(configId).length;
}

function configUsageLabel(configId: number) {
  const count = configUsageCount(configId);
  return count > 0 ? `${count} 个场景使用` : "未被场景使用";
}

function configUsageRoleLabel(roles: ConfigUsageRole[]) {
  return roles.map((role) => (role === "primary" ? "主接口" : "备用接口")).join(" / ");
}

function configUsageSceneName(scene: ConfigUsageScene) {
  return scene.display_name.trim() || scene.scene_label.trim() || scene.scene_key;
}

function callModeLabel(callMode: VideoExternalApiConfig["call_mode"]) {
  return callMode === "async" ? "异步" : "同步";
}

function normalizeAvailabilityModes(
  modes: VideoGenerationMode[] | null | undefined,
  legacyMode?: VideoExternalApiSceneBinding["availability_mode"] | null,
): VideoGenerationMode[] {
  const normalized = (modes || []).filter((item, index, arr) => arr.indexOf(item) === index);
  if (normalized.length) return normalized;
  if (legacyMode === "text_to_video") return ["text_to_video"] as VideoGenerationMode[];
  if (legacyMode === "image_to_video") return ["image_to_video"] as VideoGenerationMode[];
  return [...DEFAULT_AVAILABILITY_MODES];
}

function legacyAvailabilityModeFromModes(modes: VideoGenerationMode[]): VideoExternalApiSceneBinding["availability_mode"] {
  const hasText = modes.includes("text_to_video");
  const hasImage = modes.includes("image_to_video");
  if (hasText && hasImage) return "both";
  if (hasText) return "text_to_video";
  return "image_to_video";
}

function availabilityModeItemLabel(mode: VideoGenerationMode) {
  if (mode === "text_to_video") return "文生视频";
  if (mode === "image_to_video") return "图生视频";
  return "首尾帧";
}

function availabilityModesLabel(modes: VideoGenerationMode[] | null | undefined, legacyMode?: VideoExternalApiSceneBinding["availability_mode"] | null) {
  return normalizeAvailabilityModes(modes, legacyMode).map(availabilityModeItemLabel).join(" / ");
}

function matchesNameFilter(keyword: string, ...fields: Array<string | null | undefined>) {
  const normalized = keyword.trim().toLowerCase();
  if (!normalized) return true;
  return fields.some((field) => (field || "").toLowerCase().includes(normalized));
}

function normalizeStringValue(value: unknown, fallback = "") {
  return typeof value === "string" ? value : (value == null ? fallback : String(value));
}

function normalizeNumberValue(value: unknown, fallback = 0) {
  const normalized = Number(value);
  return Number.isFinite(normalized) ? normalized : fallback;
}

function normalizeBooleanValue(value: unknown, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function normalizeNullableNumberValue(value: unknown) {
  if (value == null || value === "") return null;
  const normalized = Number(value);
  return Number.isFinite(normalized) ? normalized : null;
}

function normalizeJsonFieldValue(value: unknown, fallback: string) {
  if (typeof value === "string" && value.trim()) return value;
  if (value && typeof value === "object") return JSON.stringify(value, null, 2);
  return fallback;
}

function normalizeAvailabilityModesValue(value: unknown) {
  if (!Array.isArray(value)) return [...DEFAULT_AVAILABILITY_MODES];
  const normalized = value
    .map((item) => String(item || "").trim())
    .filter((item): item is VideoGenerationMode => (
      item === "text_to_video" || item === "image_to_video" || item === "first_last_frame"
    ));
  return normalized.length ? normalized.filter((item, index, arr) => arr.indexOf(item) === index) : [...DEFAULT_AVAILABILITY_MODES];
}

function formatRequestError(err: any) {
  return err?.response?.data?.detail || err?.message || "请求失败，请稍后重试";
}

function resetForm() {
  editingId.value = null;
  isCopyMode.value = false;
  configImportJson.value = "";
  form.name = "";
  form.description = "";
  form.group_name = "默认";
  form.request_url = "";
  form.request_format = "json";
  form.headers_json = '{\n  "Content-Type": "application/json"\n}';
  form.payload_json = "{\n\n}";
  form.response_json = "{\n\n}";
  form.result_video_url_field = "";
  form.result_video_base64_field = "";
  form.result_cover_url_field = "";
  form.call_mode = "async";
  form.submit_success_statuses_json = DEFAULT_SUBMIT_SUCCESS_STATUSES_JSON;
  form.poll_url = "";
  form.poll_method = "GET";
  form.poll_headers_json = "{\n\n}";
  form.poll_payload_json = "{\n\n}";
  form.task_id_field = "";
  form.result_status_field = "";
  form.result_success_values_json = DEFAULT_RESULT_SUCCESS_VALUES_JSON;
  form.result_failed_values_json = DEFAULT_RESULT_FAILED_VALUES_JSON;
  form.result_error_field = "";
  form.poll_result_video_url_field = "";
  form.poll_result_video_base64_field = "";
  form.poll_result_cover_url_field = "";
  form.poll_interval_seconds = 5;
  form.poll_timeout_seconds = 600;
  form.status = "enabled";
}

function fillForm(item: VideoExternalApiConfig) {
  editingId.value = item.id;
  isCopyMode.value = false;
  configImportJson.value = "";
  form.name = item.name;
  form.description = item.description || "";
  form.group_name = item.group_name || "默认";
  form.request_url = item.request_url;
  form.request_format = item.request_format || "json";
  form.headers_json = item.headers_json;
  form.payload_json = item.payload_json;
  form.response_json = item.response_json || "{\n\n}";
  form.result_video_url_field = item.result_video_url_field || "";
  form.result_video_base64_field = item.result_video_base64_field || "";
  form.result_cover_url_field = item.result_cover_url_field || "";
  form.call_mode = "async";
  form.submit_success_statuses_json = item.submit_success_statuses_json || DEFAULT_SUBMIT_SUCCESS_STATUSES_JSON;
  form.poll_url = item.poll_url || "";
  form.poll_method = item.poll_method || "GET";
  form.poll_headers_json = item.poll_headers_json || "{\n\n}";
  form.poll_payload_json = item.poll_payload_json || "{\n\n}";
  form.task_id_field = item.task_id_field || "";
  form.result_status_field = item.result_status_field || "";
  form.result_success_values_json = item.result_success_values_json || DEFAULT_RESULT_SUCCESS_VALUES_JSON;
  form.result_failed_values_json = item.result_failed_values_json || DEFAULT_RESULT_FAILED_VALUES_JSON;
  form.result_error_field = item.result_error_field || "";
  form.poll_result_video_url_field = item.poll_result_video_url_field || "";
  form.poll_result_video_base64_field = item.poll_result_video_base64_field || "";
  form.poll_result_cover_url_field = item.poll_result_cover_url_field || "";
  form.poll_interval_seconds = Number(item.poll_interval_seconds || 5);
  form.poll_timeout_seconds = Number(item.poll_timeout_seconds || 600);
  form.status = item.status;
}

function buildCopiedName(sourceName: string) {
  const trimmed = sourceName.trim() || "未命名接口";
  const existingNames = new Set(configs.value.map((item) => item.name.trim()));
  const baseName = `${trimmed}（副本）`;
  if (!existingNames.has(baseName)) return baseName;
  let index = 2;
  while (existingNames.has(`${trimmed}（副本${index}）`)) index += 1;
  return `${trimmed}（副本${index}）`;
}

const EMPTY_BACKUP_API_OPTION = "__none__";

function toBackupApiSelectValue(value: number | null | undefined) {
  return value ?? EMPTY_BACKUP_API_OPTION;
}

function fromBackupApiSelectValue(value: number | string | null | undefined) {
  return value == null || value === EMPTY_BACKUP_API_OPTION ? null : Number(value);
}

function resetSceneForm() {
  isSceneCopyMode.value = false;
  sceneImportJson.value = "";
  sceneForm.scene_key = "";
  sceneForm.scene_label = "";
  sceneForm.scene_description = "";
  sceneForm.sort_order = Math.max(100, ...sceneBindings.value.map((item) => Number(item.sort_order || 0) + 10), 100);
  sceneForm.hide_aspect_ratio = false;
  sceneForm.hide_duration = false;
  sceneForm.hide_resolution = false;
  sceneForm.availability_mode = "both";
  sceneForm.availability_modes = [...DEFAULT_AVAILABILITY_MODES];
  sceneForm.max_reference_images = 1;
  sceneForm.api_config_id = null;
  sceneForm.backup_api_config_id = null;
  sceneForm.display_name = "";
  sceneForm.subtitle = "";
  sceneForm.credit_billing_mode = DEFAULT_CREDIT_BILLING_MODE;
  sceneForm.credit_cost = 10;
  sceneForm.per_second_credit_cost = DEFAULT_PER_SECOND_CREDIT_COST;
  sceneForm.aspect_ratio_options_json = DEFAULT_ASPECT_RATIO_OPTIONS_JSON;
  sceneForm.duration_options_json = DEFAULT_DURATION_OPTIONS_JSON;
  sceneForm.resolution_options_json = DEFAULT_RESOLUTION_OPTIONS_JSON;
  sceneForm.resolution_mapping_json = DEFAULT_RESOLUTION_MAPPING_JSON;
  sceneForm.resolution_credit_costs_json = DEFAULT_RESOLUTION_CREDIT_COSTS_JSON;
  sceneForm.status = "enabled";
}

function buildCopiedSceneLabel(sourceLabel: string) {
  const trimmed = sourceLabel.trim() || "未命名场景";
  const existingLabels = new Set(sceneBindings.value.map((item) => item.scene_label.trim()));
  const baseLabel = `${trimmed}（副本）`;
  if (!existingLabels.has(baseLabel)) return baseLabel;
  let index = 2;
  while (existingLabels.has(`${trimmed}（副本${index}）`)) index += 1;
  return `${trimmed}（副本${index}）`;
}

function buildCopiedSceneKey(sourceKey: string) {
  const normalized = sourceKey.trim().toLowerCase() || "video_scene";
  const existingKeys = new Set(sceneBindings.value.map((item) => item.scene_key.trim().toLowerCase()));
  const baseKey = `${normalized}_copy`;
  if (!existingKeys.has(baseKey)) return baseKey;
  let index = 2;
  while (existingKeys.has(`${normalized}_copy_${index}`)) index += 1;
  return `${normalized}_copy_${index}`;
}

function fillSceneMetaForm(record: VideoExternalApiSceneBinding) {
  sceneEditingKey.value = record.scene_key;
  sceneImportJson.value = "";
  sceneMetaForm.scene_key = record.scene_key;
  sceneMetaForm.scene_label = record.scene_label || "";
  sceneMetaForm.scene_description = record.scene_description || "";
  sceneMetaForm.sort_order = Number(record.sort_order || 0);
  sceneMetaForm.hide_aspect_ratio = !!record.hide_aspect_ratio;
  sceneMetaForm.hide_duration = !!record.hide_duration;
  sceneMetaForm.hide_resolution = !!record.hide_resolution;
  sceneMetaForm.availability_modes = normalizeAvailabilityModes(record.availability_modes, record.availability_mode);
  sceneMetaForm.availability_mode = legacyAvailabilityModeFromModes(sceneMetaForm.availability_modes);
  sceneMetaForm.max_reference_images = Number(record.max_reference_images || 0);
  sceneMetaForm.credit_billing_mode = record.credit_billing_mode || DEFAULT_CREDIT_BILLING_MODE;
  sceneMetaForm.credit_cost = Number(record.credit_cost || 0);
  sceneMetaForm.per_second_credit_cost = Number(record.per_second_credit_cost || 0);
  sceneMetaForm.aspect_ratio_options_json = record.aspect_ratio_options_json || DEFAULT_ASPECT_RATIO_OPTIONS_JSON;
  sceneMetaForm.duration_options_json = record.duration_options_json || DEFAULT_DURATION_OPTIONS_JSON;
  sceneMetaForm.resolution_options_json = record.resolution_options_json || DEFAULT_RESOLUTION_OPTIONS_JSON;
  sceneMetaForm.resolution_mapping_json = record.resolution_mapping_json || DEFAULT_RESOLUTION_MAPPING_JSON;
  sceneMetaForm.resolution_credit_costs_json = record.resolution_credit_costs_json || DEFAULT_RESOLUTION_CREDIT_COSTS_JSON;
}

async function load() {
  loading.value = true;
  try {
    const [configRows, bindingRows] = await Promise.all([
      listVideoExternalApiConfigs(),
      listVideoExternalApiSceneBindings(),
    ]);
    configs.value = configRows;
    sceneBindings.value = bindingRows;
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "获取视频接口管理数据失败");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  modalOpen.value = true;
}

function openEdit(item: VideoExternalApiConfig) {
  fillForm(item);
  modalOpen.value = true;
}

function openCopy(item: VideoExternalApiConfig) {
  resetForm();
  isCopyMode.value = true;
  form.name = buildCopiedName(item.name);
  form.description = item.description || "";
  form.group_name = item.group_name || "默认";
  form.request_url = item.request_url;
  form.request_format = item.request_format || "json";
  form.headers_json = item.headers_json;
  form.payload_json = item.payload_json;
  form.response_json = item.response_json || "{\n\n}";
  form.result_video_url_field = item.result_video_url_field || "";
  form.result_video_base64_field = item.result_video_base64_field || "";
  form.result_cover_url_field = item.result_cover_url_field || "";
  form.call_mode = "async";
  form.submit_success_statuses_json = item.submit_success_statuses_json || DEFAULT_SUBMIT_SUCCESS_STATUSES_JSON;
  form.poll_url = item.poll_url || "";
  form.poll_method = item.poll_method || "GET";
  form.poll_headers_json = item.poll_headers_json || "{\n\n}";
  form.poll_payload_json = item.poll_payload_json || "{\n\n}";
  form.task_id_field = item.task_id_field || "";
  form.result_status_field = item.result_status_field || "";
  form.result_success_values_json = item.result_success_values_json || DEFAULT_RESULT_SUCCESS_VALUES_JSON;
  form.result_failed_values_json = item.result_failed_values_json || DEFAULT_RESULT_FAILED_VALUES_JSON;
  form.result_error_field = item.result_error_field || "";
  form.poll_result_video_url_field = item.poll_result_video_url_field || "";
  form.poll_result_video_base64_field = item.poll_result_video_base64_field || "";
  form.poll_result_cover_url_field = item.poll_result_cover_url_field || "";
  form.poll_interval_seconds = Number(item.poll_interval_seconds || 5);
  form.poll_timeout_seconds = Number(item.poll_timeout_seconds || 600);
  form.status = item.status;
  modalOpen.value = true;
}

function buildConfigTemplateData(item: VideoExternalApiConfig): VideoExternalApiConfigPayload {
  return {
    name: item.name,
    description: item.description || "",
    group_name: item.group_name || "默认",
    request_url: item.request_url,
    request_format: item.request_format || "json",
    headers_json: item.headers_json,
    payload_json: item.payload_json,
    response_json: item.response_json || "{\n\n}",
    result_video_url_field: item.result_video_url_field || "",
    result_video_base64_field: item.result_video_base64_field || "",
    result_cover_url_field: item.result_cover_url_field || "",
    call_mode: "async",
    submit_success_statuses_json: item.submit_success_statuses_json || DEFAULT_SUBMIT_SUCCESS_STATUSES_JSON,
    poll_url: item.poll_url || "",
    poll_method: item.poll_method || "GET",
    poll_headers_json: item.poll_headers_json || "{\n\n}",
    poll_payload_json: item.poll_payload_json || "{\n\n}",
    task_id_field: item.task_id_field || "",
    result_status_field: item.result_status_field || "",
    result_success_values_json: item.result_success_values_json || DEFAULT_RESULT_SUCCESS_VALUES_JSON,
    result_failed_values_json: item.result_failed_values_json || DEFAULT_RESULT_FAILED_VALUES_JSON,
    result_error_field: item.result_error_field || "",
    poll_result_video_url_field: item.poll_result_video_url_field || "",
    poll_result_video_base64_field: item.poll_result_video_base64_field || "",
    poll_result_cover_url_field: item.poll_result_cover_url_field || "",
    poll_interval_seconds: Number(item.poll_interval_seconds || 5),
    poll_timeout_seconds: Number(item.poll_timeout_seconds || 600),
    status: item.status,
  };
}

function buildSceneTemplateData(record: VideoExternalApiSceneBinding): VideoExternalApiSceneBindingCreatePayload {
  const availabilityModes = normalizeAvailabilityModes(record.availability_modes, record.availability_mode);
  return {
    scene_key: record.scene_key,
    scene_label: record.scene_label,
    scene_description: record.scene_description || "",
    sort_order: Number(record.sort_order || 0),
    hide_aspect_ratio: !!record.hide_aspect_ratio,
    hide_duration: !!record.hide_duration,
    hide_resolution: !!record.hide_resolution,
    availability_mode: legacyAvailabilityModeFromModes(availabilityModes),
    availability_modes: availabilityModes,
    max_reference_images: Number(record.max_reference_images || 0),
    api_config_id: record.api_config_id ?? null,
    backup_api_config_id: record.backup_api_config_id ?? null,
    display_name: record.display_name || "",
    subtitle: record.subtitle || "",
    credit_billing_mode: record.credit_billing_mode || DEFAULT_CREDIT_BILLING_MODE,
    credit_cost: Number(record.credit_cost || 0),
    per_second_credit_cost: Number(record.per_second_credit_cost || 0),
    aspect_ratio_options_json: record.aspect_ratio_options_json || DEFAULT_ASPECT_RATIO_OPTIONS_JSON,
    duration_options_json: record.duration_options_json || DEFAULT_DURATION_OPTIONS_JSON,
    resolution_options_json: record.resolution_options_json || DEFAULT_RESOLUTION_OPTIONS_JSON,
    resolution_mapping_json: record.resolution_mapping_json || DEFAULT_RESOLUTION_MAPPING_JSON,
    resolution_credit_costs_json: record.resolution_credit_costs_json || DEFAULT_RESOLUTION_CREDIT_COSTS_JSON,
    status: record.status,
  };
}

async function copyTemplateJson(text: string, successText: string) {
  try {
    await navigator.clipboard.writeText(text);
    message.success(successText);
  } catch {
    message.error("复制失败，请检查剪贴板权限");
  }
}

function handleCopyConfigJson(item: VideoExternalApiConfig) {
  const template = stringifyAdminConfigTemplate("video-api-config", buildConfigTemplateData(item));
  copyTemplateJson(template, "视频接口配置 JSON 已复制");
}

function handleCopySceneJson(record: VideoExternalApiSceneBinding) {
  const template = stringifyAdminConfigTemplate("video-scene-binding", buildSceneTemplateData(record));
  copyTemplateJson(template, "视频场景绑定 JSON 已复制");
}

function applyImportedConfigData(data: Record<string, unknown>) {
  form.name = normalizeStringValue(data.name, form.name);
  form.description = normalizeStringValue(data.description, form.description);
  form.group_name = normalizeStringValue(data.group_name, form.group_name || "默认");
  form.request_url = normalizeStringValue(data.request_url, form.request_url);
  form.request_format = data.request_format === "multipart" ? "multipart" : "json";
  form.headers_json = normalizeJsonFieldValue(data.headers_json, form.headers_json);
  form.payload_json = normalizeJsonFieldValue(data.payload_json, form.payload_json);
  form.response_json = normalizeJsonFieldValue(data.response_json, form.response_json);
  form.result_video_url_field = normalizeStringValue(data.result_video_url_field, form.result_video_url_field);
  form.result_video_base64_field = normalizeStringValue(data.result_video_base64_field, form.result_video_base64_field);
  form.result_cover_url_field = normalizeStringValue(data.result_cover_url_field, form.result_cover_url_field);
  form.call_mode = "async";
  form.submit_success_statuses_json = normalizeJsonFieldValue(data.submit_success_statuses_json, form.submit_success_statuses_json);
  form.poll_url = normalizeStringValue(data.poll_url, form.poll_url);
  form.poll_method = data.poll_method === "POST" ? "POST" : "GET";
  form.poll_headers_json = normalizeJsonFieldValue(data.poll_headers_json, form.poll_headers_json);
  form.poll_payload_json = normalizeJsonFieldValue(data.poll_payload_json, form.poll_payload_json);
  form.task_id_field = normalizeStringValue(data.task_id_field, form.task_id_field);
  form.result_status_field = normalizeStringValue(data.result_status_field, form.result_status_field);
  form.result_success_values_json = normalizeJsonFieldValue(data.result_success_values_json, form.result_success_values_json);
  form.result_failed_values_json = normalizeJsonFieldValue(data.result_failed_values_json, form.result_failed_values_json);
  form.result_error_field = normalizeStringValue(data.result_error_field, form.result_error_field);
  form.poll_result_video_url_field = normalizeStringValue(data.poll_result_video_url_field, form.poll_result_video_url_field);
  form.poll_result_video_base64_field = normalizeStringValue(data.poll_result_video_base64_field, form.poll_result_video_base64_field);
  form.poll_result_cover_url_field = normalizeStringValue(data.poll_result_cover_url_field, form.poll_result_cover_url_field);
  form.poll_interval_seconds = normalizeNumberValue(data.poll_interval_seconds, form.poll_interval_seconds);
  form.poll_timeout_seconds = normalizeNumberValue(data.poll_timeout_seconds, form.poll_timeout_seconds);
  form.status = data.status === "disabled" ? "disabled" : "enabled";
}

function handleApplyConfigImportJson() {
  if (!configImportJson.value.trim()) {
    message.warning("请先粘贴视频接口配置 JSON");
    return;
  }
  try {
    const parsed = parseAdminConfigTemplate(configImportJson.value);
    if (parsed.kind !== "video-api-config") {
      message.warning("这段 JSON 不是视频接口配置模板");
      return;
    }
    applyImportedConfigData(parsed.data);
    message.success("已识别并回填视频接口配置");
  } catch (err: any) {
    message.error(err?.message || "识别视频接口配置 JSON 失败");
  }
}

function applyImportedSceneData(data: Record<string, unknown>) {
  const availabilityModes = normalizeAvailabilityModesValue(data.availability_modes);
  sceneForm.scene_key = normalizeStringValue(data.scene_key, sceneForm.scene_key);
  sceneForm.scene_label = normalizeStringValue(data.scene_label, sceneForm.scene_label);
  sceneForm.scene_description = normalizeStringValue(data.scene_description, sceneForm.scene_description);
  sceneForm.sort_order = normalizeNumberValue(data.sort_order, sceneForm.sort_order);
  sceneForm.hide_aspect_ratio = normalizeBooleanValue(data.hide_aspect_ratio, sceneForm.hide_aspect_ratio);
  sceneForm.hide_duration = normalizeBooleanValue(data.hide_duration, sceneForm.hide_duration);
  sceneForm.hide_resolution = normalizeBooleanValue(data.hide_resolution, sceneForm.hide_resolution);
  sceneForm.availability_modes = availabilityModes;
  sceneForm.availability_mode = legacyAvailabilityModeFromModes(availabilityModes);
  sceneForm.max_reference_images = normalizeNumberValue(data.max_reference_images, sceneForm.max_reference_images);
  sceneForm.api_config_id = normalizeNullableNumberValue(data.api_config_id);
  sceneForm.backup_api_config_id = normalizeNullableNumberValue(data.backup_api_config_id);
  sceneForm.display_name = normalizeStringValue(data.display_name, sceneForm.display_name);
  sceneForm.subtitle = normalizeStringValue(data.subtitle, sceneForm.subtitle);
  sceneForm.credit_billing_mode = data.credit_billing_mode === "per_second" ? "per_second" : "fixed";
  sceneForm.credit_cost = normalizeNumberValue(data.credit_cost, sceneForm.credit_cost);
  sceneForm.per_second_credit_cost = normalizeNumberValue(data.per_second_credit_cost, sceneForm.per_second_credit_cost);
  sceneForm.aspect_ratio_options_json = normalizeJsonFieldValue(data.aspect_ratio_options_json, sceneForm.aspect_ratio_options_json);
  sceneForm.duration_options_json = normalizeJsonFieldValue(data.duration_options_json, sceneForm.duration_options_json);
  sceneForm.resolution_options_json = normalizeJsonFieldValue(data.resolution_options_json, sceneForm.resolution_options_json);
  sceneForm.resolution_mapping_json = normalizeJsonFieldValue(data.resolution_mapping_json, sceneForm.resolution_mapping_json);
  sceneForm.resolution_credit_costs_json = normalizeJsonFieldValue(data.resolution_credit_costs_json, sceneForm.resolution_credit_costs_json);
  sceneForm.status = data.status === "disabled" ? "disabled" : "enabled";
}

function handleApplySceneImportJson() {
  if (!sceneImportJson.value.trim()) {
    message.warning("请先粘贴视频场景绑定 JSON");
    return;
  }
  try {
    const parsed = parseAdminConfigTemplate(sceneImportJson.value);
    if (parsed.kind !== "video-scene-binding") {
      message.warning("这段 JSON 不是视频场景绑定模板");
      return;
    }
    applyImportedSceneData(parsed.data);
    message.success("已识别并回填视频场景绑定");
  } catch (err: any) {
    message.error(err?.message || "识别视频场景绑定 JSON 失败");
  }
}

function openCreateScene() {
  resetSceneForm();
  sceneModalOpen.value = true;
}

function openCopyScene(record: VideoExternalApiSceneBinding) {
  resetSceneForm();
  isSceneCopyMode.value = true;
  sceneForm.scene_key = buildCopiedSceneKey(record.scene_key);
  sceneForm.scene_label = buildCopiedSceneLabel(record.scene_label);
  sceneForm.scene_description = record.scene_description || "";
  sceneForm.sort_order = Number(record.sort_order || 0) + 10;
  sceneForm.hide_aspect_ratio = !!record.hide_aspect_ratio;
  sceneForm.hide_duration = !!record.hide_duration;
  sceneForm.hide_resolution = !!record.hide_resolution;
  sceneForm.availability_modes = normalizeAvailabilityModes(record.availability_modes, record.availability_mode);
  sceneForm.availability_mode = legacyAvailabilityModeFromModes(sceneForm.availability_modes);
  sceneForm.max_reference_images = Number(record.max_reference_images || 0);
  sceneForm.api_config_id = record.api_config_id ?? null;
  sceneForm.backup_api_config_id = record.backup_api_config_id ?? null;
  sceneForm.display_name = record.display_name || "";
  sceneForm.subtitle = record.subtitle || "";
  sceneForm.credit_billing_mode = record.credit_billing_mode || DEFAULT_CREDIT_BILLING_MODE;
  sceneForm.credit_cost = Number(record.credit_cost || 0);
  sceneForm.per_second_credit_cost = Number(record.per_second_credit_cost || 0);
  sceneForm.aspect_ratio_options_json = record.aspect_ratio_options_json || DEFAULT_ASPECT_RATIO_OPTIONS_JSON;
  sceneForm.duration_options_json = record.duration_options_json || DEFAULT_DURATION_OPTIONS_JSON;
  sceneForm.resolution_options_json = record.resolution_options_json || DEFAULT_RESOLUTION_OPTIONS_JSON;
  sceneForm.resolution_mapping_json = record.resolution_mapping_json || DEFAULT_RESOLUTION_MAPPING_JSON;
  sceneForm.resolution_credit_costs_json = record.resolution_credit_costs_json || DEFAULT_RESOLUTION_CREDIT_COSTS_JSON;
  sceneForm.status = record.status;
  sceneModalOpen.value = true;
}

function openEditSceneMeta(record: VideoExternalApiSceneBinding) {
  fillSceneMetaForm(record);
  sceneMetaModalOpen.value = true;
}

function isSceneUnbound(record: VideoExternalApiSceneBinding) {
  return !record.api_config_id;
}

function sceneRowClassName(record: VideoExternalApiSceneBinding) {
  return isSceneUnbound(record) ? "is-unbound-scene" : "";
}

function openEditCopy(record: VideoExternalApiSceneBinding) {
  copyEditingKey.value = record.scene_key;
  copyForm.display_name = record.display_name || "";
  copyForm.subtitle = record.subtitle || "";
  copyModalOpen.value = true;
}

async function handleSaveCopy() {
  const record = sceneBindings.value.find((item) => item.scene_key === copyEditingKey.value);
  if (!record) return;
  await handleBindingChange(record.scene_key, buildBindingPayload(record, {
    display_name: copyForm.display_name,
    subtitle: copyForm.subtitle,
  }));
  copyModalOpen.value = false;
}

function canSwapBinding(record: VideoExternalApiSceneBinding) {
  const primaryId = record.api_config_id ?? null;
  const backupId = record.backup_api_config_id ?? null;
  return primaryId !== backupId && (primaryId != null || backupId != null);
}

function handleSwapBinding(record: VideoExternalApiSceneBinding) {
  if (!canSwapBinding(record)) {
    message.warning("请先绑定主接口或备用接口后再互换");
    return;
  }
  void handleBindingChange(record.scene_key, buildBindingPayload(record, {
    api_config_id: record.backup_api_config_id ?? null,
    backup_api_config_id: record.api_config_id ?? null,
  }));
}

function validateIntegerListJson(raw: string, label: string) {
  try {
    const parsed = JSON.parse(raw || "[]");
    if (!Array.isArray(parsed)) {
      message.warning(`${label}必须是 JSON 数组`);
      return false;
    }
    for (const [index, item] of parsed.entries()) {
      const value = Number(item);
      if (!Number.isInteger(value) || value < 100 || value > 599) {
        message.warning(`${label}第 ${index + 1} 项必须是合法 HTTP 状态码整数`);
        return false;
      }
    }
    return true;
  } catch {
    message.warning(`${label}不是合法的 JSON`);
    return false;
  }
}

function validateStringListJson(raw: string, label: string) {
  try {
    const parsed = JSON.parse(raw || "[]");
    if (!Array.isArray(parsed)) {
      message.warning(`${label}必须是 JSON 数组`);
      return false;
    }
    for (const [index, item] of parsed.entries()) {
      if (!String(item ?? "").trim()) {
        message.warning(`${label}第 ${index + 1} 项不能为空`);
        return false;
      }
    }
    return true;
  } catch {
    message.warning(`${label}不是合法的 JSON`);
    return false;
  }
}

function validateSceneOptionsJson(raw: string, label: string) {
  try {
    const parsed = JSON.parse(raw || "[]");
    if (!Array.isArray(parsed)) {
      message.warning(`${label}必须是 JSON 数组`);
      return false;
    }
    for (const [index, item] of parsed.entries()) {
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        message.warning(`${label}第 ${index + 1} 项必须是对象`);
        return false;
      }
      const labelValue = String((item as any).label ?? "").trim();
      const value = String((item as any).value ?? "").trim();
      if (!labelValue || !value) {
        message.warning(`${label}第 ${index + 1} 项的 label/value 不能为空`);
        return false;
      }
    }
    return true;
  } catch {
    message.warning(`${label}不是合法的 JSON`);
    return false;
  }
}

function validateResolutionMappingJson(raw: string, label: string) {
  try {
    const parsed = JSON.parse(raw || "{}");
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      message.warning(`${label}必须是 JSON 对象`);
      return false;
    }
    return true;
  } catch {
    message.warning(`${label}不是合法的 JSON`);
    return false;
  }
}

function validateResolutionCreditCostsJson(raw: string, label: string) {
  try {
    const parsed = JSON.parse(raw || "{}");
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      message.warning(`${label}必须是 JSON 对象`);
      return false;
    }
    for (const [key, value] of Object.entries(parsed)) {
      if (!String(key).trim()) {
        message.warning(`${label}存在空键`);
        return false;
      }
      const numberValue = Number(value);
      if (!Number.isInteger(numberValue) || numberValue < 0) {
        message.warning(`${label}中的 ${key} 必须是大于等于 0 的整数`);
        return false;
      }
    }
    return true;
  } catch {
    message.warning(`${label}不是合法的 JSON`);
    return false;
  }
}

function validateJsonFields() {
  try {
    const headers = JSON.parse(form.headers_json);
    if (!headers || Array.isArray(headers) || typeof headers !== "object") {
      message.warning("Header JSON 必须是对象");
      return false;
    }
  } catch {
    message.warning("Header JSON 不是合法的 JSON");
    return false;
  }

  try {
    JSON.parse(form.payload_json);
  } catch {
    message.warning("请求 JSON 不是合法的 JSON");
    return false;
  }

  try {
    JSON.parse(form.response_json);
  } catch {
    message.warning("响应 JSON 不是合法的 JSON");
    return false;
  }

  if (!form.poll_url.trim()) {
    message.warning("异步接口必须填写轮询地址");
    return false;
  }
  if (!form.task_id_field.trim()) {
    message.warning("异步接口必须填写第三方任务 ID 字段路径");
    return false;
  }
  if (!form.result_status_field.trim()) {
    message.warning("异步接口必须填写结果状态字段路径");
    return false;
  }
  if (!form.poll_result_video_url_field.trim()) {
    message.warning("异步接口必须填写轮询结果视频 URL 路径");
    return false;
  }

  try {
    const pollHeaders = JSON.parse(form.poll_headers_json);
    if (!pollHeaders || Array.isArray(pollHeaders) || typeof pollHeaders !== "object") {
      message.warning("轮询 Header JSON 必须是对象");
      return false;
    }
  } catch {
    message.warning("轮询 Header JSON 不是合法的 JSON");
    return false;
  }

  try {
    JSON.parse(form.poll_payload_json);
  } catch {
    message.warning("轮询请求 JSON 不是合法的 JSON");
    return false;
  }

  if (!validateIntegerListJson(form.submit_success_statuses_json, "提交成功状态码 JSON")) return false;
  if (!validateStringListJson(form.result_success_values_json, "成功状态值 JSON")) return false;
  if (!validateStringListJson(form.result_failed_values_json, "失败状态值 JSON")) return false;
  if (Number(form.poll_interval_seconds || 0) <= 0) {
    message.warning("轮询间隔必须大于 0 秒");
    return false;
  }
  if (Number(form.poll_timeout_seconds || 0) <= 0) {
    message.warning("轮询超时必须大于 0 秒");
    return false;
  }
  return true;
}

function buildPayload(): VideoExternalApiConfigPayload {
  return {
    name: form.name.trim(),
    description: form.description.trim(),
    group_name: form.group_name.trim() || "默认",
    request_url: form.request_url.trim(),
    request_format: form.request_format,
    headers_json: form.headers_json,
    payload_json: form.payload_json,
    response_json: form.response_json,
    result_video_url_field: form.result_video_url_field.trim(),
    result_video_base64_field: form.result_video_base64_field.trim(),
    result_cover_url_field: form.result_cover_url_field.trim(),
    call_mode: "async",
    submit_success_statuses_json: form.submit_success_statuses_json,
    poll_url: form.poll_url.trim(),
    poll_method: form.poll_method,
    poll_headers_json: form.poll_headers_json,
    poll_payload_json: form.poll_payload_json,
    task_id_field: form.task_id_field.trim(),
    result_status_field: form.result_status_field.trim(),
    result_success_values_json: form.result_success_values_json,
    result_failed_values_json: form.result_failed_values_json,
    result_error_field: form.result_error_field.trim(),
    poll_result_video_url_field: form.poll_result_video_url_field.trim(),
    poll_result_video_base64_field: form.poll_result_video_base64_field.trim(),
    poll_result_cover_url_field: form.poll_result_cover_url_field.trim(),
    poll_interval_seconds: Number(form.poll_interval_seconds || 5),
    poll_timeout_seconds: Number(form.poll_timeout_seconds || 600),
    status: form.status,
  };
}

async function handleSave() {
  if (!form.name.trim()) {
    message.warning("请输入配置名称");
    return;
  }
  if (!form.request_url.trim()) {
    message.warning("请输入请求地址");
    return;
  }
  if (!validateJsonFields()) return;

  saving.value = true;
  try {
    const payload = buildPayload();
    if (editingId.value) {
      await updateVideoExternalApiConfig(editingId.value, payload);
      message.success("视频接口配置更新成功");
    } else {
      await createVideoExternalApiConfig(payload);
      message.success("视频接口配置创建成功");
    }
    modalOpen.value = false;
    resetForm();
    await load();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function handleTestConnection() {
  if (!form.name.trim()) {
    message.warning("请先填写配置名称");
    return;
  }
  if (!form.request_url.trim()) {
    message.warning("请先填写请求地址");
    return;
  }
  if (!validateJsonFields()) return;

  testing.value = true;
  try {
    const result = await testVideoExternalApiConfig(buildPayload());
    showTestResult(result);
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "测试连接失败");
  } finally {
    testing.value = false;
  }
}

function showTestResult(result: VideoExternalApiConfigTestResult) {
  Modal.info({
    title: result.success ? "测试连接成功" : "测试连接失败",
    width: 760,
    centered: true,
    okText: "知道了",
    content: [
      `请求地址：${result.request_url}`,
      `状态码：${result.status_code ?? "-"}`,
      "",
      "响应摘要：",
      result.response_preview || "(空响应)",
    ].join("\n"),
  });
}

function handleToggleStatus(item: VideoExternalApiConfig) {
  const nextStatus: ExternalApiConfigStatus = item.status === "enabled" ? "disabled" : "enabled";
  Modal.confirm({
    title: nextStatus === "enabled" ? "启用该视频接口配置？" : "停用该视频接口配置？",
    centered: true,
    onOk: async () => {
      try {
        await updateVideoExternalApiConfigStatus(item.id, nextStatus);
        message.success(nextStatus === "enabled" ? "已启用" : "已停用");
        await load();
      } catch (err: any) {
        message.error(formatRequestError(err));
      }
    },
  });
}

function handleDeleteConfig(item: VideoExternalApiConfig) {
  Modal.confirm({
    title: "删除该视频接口配置？",
    content: "删除后会同时解除所有引用它的视频场景绑定，场景会保留但变成未绑定状态。",
    centered: true,
    okButtonProps: { danger: true },
    onOk: async () => {
      try {
        await deleteVideoExternalApiConfig(item.id);
        message.success("视频接口配置已删除");
        await load();
      } catch (err: any) {
        Modal.warning({
          title: "无法删除该接口",
          content: formatRequestError(err),
          centered: true,
        });
      }
    },
  });
}

async function handleBindingChange(
  sceneKey: VideoExternalApiSceneBinding["scene_key"],
  payload: {
    api_config_id: number | null;
    backup_api_config_id: number | null;
    credit_billing_mode: VideoCreditBillingMode;
    credit_cost: number;
    per_second_credit_cost: number;
    display_name: string;
    subtitle: string;
    status: ExternalApiConfigStatus;
  },
) {
  bindingSavingKey.value = sceneKey;
  try {
    await updateVideoExternalApiSceneBinding(sceneKey, payload);
    message.success("视频场景绑定已更新");
    await load();
  } catch (err: any) {
    message.error(formatRequestError(err));
  } finally {
    bindingSavingKey.value = "";
  }
}

function buildBindingPayload(record: VideoExternalApiSceneBinding, overrides: Partial<{
  api_config_id: number | null;
  backup_api_config_id: number | null;
  credit_billing_mode: VideoCreditBillingMode;
  credit_cost: number;
  per_second_credit_cost: number;
  display_name: string;
  subtitle: string;
  status: ExternalApiConfigStatus;
}> = {}) {
  return {
    api_config_id: overrides.api_config_id !== undefined ? overrides.api_config_id : (record.api_config_id ?? null),
    backup_api_config_id: overrides.backup_api_config_id !== undefined ? overrides.backup_api_config_id : (record.backup_api_config_id ?? null),
    credit_billing_mode: overrides.credit_billing_mode ?? record.credit_billing_mode ?? DEFAULT_CREDIT_BILLING_MODE,
    credit_cost: overrides.credit_cost ?? record.credit_cost,
    per_second_credit_cost: overrides.per_second_credit_cost ?? record.per_second_credit_cost,
    display_name: overrides.display_name ?? record.display_name ?? "",
    subtitle: overrides.subtitle ?? record.subtitle ?? "",
    status: overrides.status ?? record.status,
  };
}

async function handleCreateScene() {
  if (!sceneForm.scene_key.trim()) {
    message.warning("请输入场景标识");
    return;
  }
  if (!sceneForm.scene_label.trim()) {
    message.warning("请输入场景名称");
    return;
  }
  if (!sceneForm.availability_modes.length) {
    message.warning("请至少选择一个可用范围");
    return;
  }
  if (!validateSceneOptionsJson(sceneForm.aspect_ratio_options_json, "宽高比选项 JSON")) return;
  if (!validateSceneOptionsJson(sceneForm.duration_options_json, "秒数选项 JSON")) return;
  if (!validateSceneOptionsJson(sceneForm.resolution_options_json, "分辨率选项 JSON")) return;
  if (!validateResolutionMappingJson(sceneForm.resolution_mapping_json, "分辨率映射 JSON")) return;
  if (!validateResolutionCreditCostsJson(sceneForm.resolution_credit_costs_json, "分辨率积分 JSON")) return;

  bindingCreating.value = true;
  try {
    await createVideoExternalApiSceneBinding({
      scene_key: sceneForm.scene_key.trim().toLowerCase(),
      scene_label: sceneForm.scene_label.trim(),
      scene_description: sceneForm.scene_description.trim(),
      sort_order: Number(sceneForm.sort_order || 0),
      hide_aspect_ratio: !!sceneForm.hide_aspect_ratio,
      hide_duration: !!sceneForm.hide_duration,
      hide_resolution: !!sceneForm.hide_resolution,
      availability_mode: legacyAvailabilityModeFromModes(sceneForm.availability_modes),
      availability_modes: [...sceneForm.availability_modes],
      max_reference_images: Number(sceneForm.max_reference_images || 0),
      api_config_id: sceneForm.api_config_id ?? null,
      backup_api_config_id: sceneForm.backup_api_config_id ?? null,
      display_name: sceneForm.display_name.trim(),
      subtitle: sceneForm.subtitle.trim(),
      credit_billing_mode: sceneForm.credit_billing_mode,
      credit_cost: Number(sceneForm.credit_cost || 0),
      per_second_credit_cost: Number(sceneForm.per_second_credit_cost || 0),
      aspect_ratio_options_json: sceneForm.aspect_ratio_options_json,
      duration_options_json: sceneForm.duration_options_json,
      resolution_options_json: sceneForm.resolution_options_json,
      resolution_mapping_json: sceneForm.resolution_mapping_json,
      resolution_credit_costs_json: sceneForm.resolution_credit_costs_json,
      status: sceneForm.status,
    });
    message.success("视频场景创建成功");
    sceneModalOpen.value = false;
    resetSceneForm();
    await load();
  } catch (err: any) {
    message.error(formatRequestError(err));
  } finally {
    bindingCreating.value = false;
  }
}

async function handleSaveSceneMeta() {
  if (!sceneEditingKey.value) return;
  if (!sceneMetaForm.scene_key.trim()) {
    message.warning("请输入场景标识");
    return;
  }
  if (!sceneMetaForm.scene_label.trim()) {
    message.warning("请输入场景名称");
    return;
  }
  if (!sceneMetaForm.availability_modes.length) {
    message.warning("请至少选择一个可用范围");
    return;
  }
  if (!validateSceneOptionsJson(sceneMetaForm.aspect_ratio_options_json, "宽高比选项 JSON")) return;
  if (!validateSceneOptionsJson(sceneMetaForm.duration_options_json, "秒数选项 JSON")) return;
  if (!validateSceneOptionsJson(sceneMetaForm.resolution_options_json, "分辨率选项 JSON")) return;
  if (!validateResolutionMappingJson(sceneMetaForm.resolution_mapping_json, "分辨率映射 JSON")) return;
  if (!validateResolutionCreditCostsJson(sceneMetaForm.resolution_credit_costs_json, "分辨率积分 JSON")) return;

  sceneMetaSaving.value = true;
  try {
    await updateVideoExternalApiSceneBindingMeta(sceneEditingKey.value, {
      scene_key: sceneMetaForm.scene_key.trim().toLowerCase(),
      scene_label: sceneMetaForm.scene_label.trim(),
      scene_description: sceneMetaForm.scene_description.trim(),
      sort_order: Number(sceneMetaForm.sort_order || 0),
      hide_aspect_ratio: !!sceneMetaForm.hide_aspect_ratio,
      hide_duration: !!sceneMetaForm.hide_duration,
      hide_resolution: !!sceneMetaForm.hide_resolution,
      availability_mode: legacyAvailabilityModeFromModes(sceneMetaForm.availability_modes),
      availability_modes: [...sceneMetaForm.availability_modes],
      max_reference_images: Number(sceneMetaForm.max_reference_images || 0),
      credit_billing_mode: sceneMetaForm.credit_billing_mode,
      credit_cost: Number(sceneMetaForm.credit_cost || 0),
      per_second_credit_cost: Number(sceneMetaForm.per_second_credit_cost || 0),
      aspect_ratio_options_json: sceneMetaForm.aspect_ratio_options_json,
      duration_options_json: sceneMetaForm.duration_options_json,
      resolution_options_json: sceneMetaForm.resolution_options_json,
      resolution_mapping_json: sceneMetaForm.resolution_mapping_json,
      resolution_credit_costs_json: sceneMetaForm.resolution_credit_costs_json,
    });
    message.success("视频场景基础信息已更新");
    sceneMetaModalOpen.value = false;
    sceneEditingKey.value = "";
    await load();
  } catch (err: any) {
    message.error(formatRequestError(err));
  } finally {
    sceneMetaSaving.value = false;
  }
}

function handleToggleSceneStatus(record: VideoExternalApiSceneBinding) {
  const nextStatus: ExternalApiConfigStatus = record.status === "enabled" ? "disabled" : "enabled";
  Modal.confirm({
    title: nextStatus === "enabled" ? "启用该视频场景？" : "停用该视频场景？",
    centered: true,
    onOk: async () => {
      try {
        await updateVideoExternalApiSceneBindingStatus(record.scene_key, nextStatus);
        message.success(nextStatus === "enabled" ? "场景已启用" : "场景已停用");
        await load();
      } catch (err: any) {
        message.error(formatRequestError(err));
      }
    },
  });
}

function handleDeleteScene(record: VideoExternalApiSceneBinding) {
  Modal.confirm({
    title: "删除该视频场景？",
    content: "删除后将不再出现在视频生成页的模型选择中，且无法恢复。",
    centered: true,
    okButtonProps: { danger: true },
    onOk: async () => {
      try {
        await deleteVideoExternalApiSceneBinding(record.scene_key);
        message.success("视频场景已删除");
        await load();
      } catch (err: any) {
        message.error(formatRequestError(err));
      }
    },
  });
}

onMounted(load);
</script>

<template>
  <div class="page warm-page motion-page-enter">
    <a-space direction="vertical" :size="16" style="width: 100%">
      <a-card title="接口配置" class="warm-card api-card motion-fade-up motion-card-lift" style="--motion-delay: 40ms">
        <template #extra>
          <a-space wrap>
            <a-button class="api-secondary-btn" @click="toggleAllConfigGroups">
              {{ allConfigGroupsExpanded ? "全部折叠" : "全部展开" }}
            </a-button>
            <a-input v-model:value="configNameFilter" class="warm-input" allow-clear placeholder="按名称筛选" style="width: 180px" />
            <a-select
              v-model:value="configGroupFilter"
              class="warm-select"
              show-search
              option-filter-prop="label"
              placeholder="筛选分组"
              style="width: 180px"
            >
              <a-select-option value="all" label="全部分组">全部分组</a-select-option>
              <a-select-option v-for="group in groupOptions" :key="group" :value="group" :label="group">
                {{ group }}
              </a-select-option>
            </a-select>
            <a-select
              v-model:value="configRequestFormatFilter"
              class="warm-select"
              show-search
              option-filter-prop="label"
              placeholder="筛选请求格式"
              style="width: 180px"
            >
              <a-select-option value="all" label="全部格式">全部格式</a-select-option>
              <a-select-option value="json" label="JSON">JSON</a-select-option>
              <a-select-option value="multipart" label="Multipart Form">Multipart Form</a-select-option>
            </a-select>
            <a-button type="primary" class="api-primary-btn" :icon="h(PlusOutlined)" @click="openCreate">
              新增接口
            </a-button>
          </a-space>
        </template>

        <a-spin :spinning="loading">
          <a-empty v-if="!groupedConfigs.length" description="没有匹配的接口" />
          <div v-else class="api-config-groups">
            <section v-for="block in groupedConfigs" :key="block.group" class="api-config-group">
              <button
                type="button"
                class="api-config-group-title"
                :class="{ 'is-expanded': isConfigGroupExpanded(block.group) }"
                @click="toggleConfigGroup(block.group)"
              >
                <DownOutlined class="api-config-group-arrow" />
                <span>{{ block.group }}</span>
                <span class="api-config-group-count">{{ block.items.length }} 个接口</span>
              </button>
              <div class="api-config-group-body" :class="{ 'is-expanded': isConfigGroupExpanded(block.group) }">
              <div class="api-config-group-body-inner">
              <div class="api-config-grid">
                <article
                  v-for="item in block.items"
                  :key="item.id"
                  class="api-config-tile"
                  :class="{
                    'is-used': configUsageCount(item.id) > 0,
                    'is-unused': configUsageCount(item.id) === 0,
                    'is-disabled': item.status !== 'enabled',
                  }"
                  @click="openEdit(item)"
                >
                  <div class="api-config-tile-top">
                    <div class="api-config-tile-name" :title="item.name">{{ configCardName(item) }}</div>
                    <a-dropdown trigger="click" overlay-class-name="api-more-dropdown" @click.stop>
                      <button type="button" class="api-config-more-btn" @click.stop>
                        <MoreOutlined />
                      </button>
                      <template #overlay>
                        <a-menu>
                          <a-menu-item key="edit" @click="openEdit(item)">编辑</a-menu-item>
                          <a-menu-item key="copy" @click="openCopy(item)">复制新增</a-menu-item>
                          <a-menu-item key="copy-json" @click="handleCopyConfigJson(item)">复制 JSON</a-menu-item>
                          <a-menu-divider />
                          <a-menu-item key="toggle" @click="handleToggleStatus(item)">
                            {{ item.status === "enabled" ? "停用" : "启用" }}
                          </a-menu-item>
                          <a-menu-item key="delete" danger @click="handleDeleteConfig(item)">删除</a-menu-item>
                        </a-menu>
                      </template>
                    </a-dropdown>
                  </div>
                  <div class="api-config-tile-tags">
                    <a-tag class="api-tag" :class="item.status === 'enabled' ? 'api-tag-enabled' : 'api-tag-disabled'">
                      {{ item.status === "enabled" ? "启用" : "停用" }}
                    </a-tag>
                    <a-tag class="api-tag" :class="item.call_mode === 'async' ? 'api-tag-async' : 'api-tag-sync'">
                      {{ callModeLabel(item.call_mode) }}
                    </a-tag>
                    <a-tag class="api-tag" :class="item.request_format === 'multipart' ? 'api-tag-form' : 'api-tag-json'">
                      {{ item.request_format === "multipart" ? "Form" : "JSON" }}
                    </a-tag>
                  </div>
                  <a-popover
                    v-if="configUsageCount(item.id)"
                    trigger="click"
                    placement="bottomLeft"
                    overlay-class-name="api-config-usage-popover"
                  >
                    <template #title>使用该接口的场景</template>
                    <template #content>
                      <div class="api-config-usage-list">
                        <div
                          v-for="scene in configUsageScenes(item.id)"
                          :key="scene.scene_key"
                          class="api-config-usage-item"
                        >
                          <div class="api-config-usage-name">{{ configUsageSceneName(scene) }}</div>
                          <div class="api-config-usage-desc">
                            {{ scene.availability_label }} · {{ configUsageRoleLabel(scene.roles) }}
                          </div>
                        </div>
                      </div>
                    </template>
                    <span class="api-config-tile-meta is-clickable" @click.stop>
                      {{ configUsageLabel(item.id) }}
                    </span>
                  </a-popover>
                  <div v-else class="api-config-tile-meta is-unused">
                    {{ configUsageLabel(item.id) }}
                  </div>
                </article>
              </div>
              </div>
              </div>
            </section>
          </div>
        </a-spin>
      </a-card>

      <a-card title="场景绑定" class="warm-card warm-table-card api-card motion-fade-up motion-card-lift" style="--motion-delay: 200ms">
        <template #extra>
          <a-space wrap>
            <a-input v-model:value="bindingNameFilter" class="warm-input" allow-clear placeholder="按名称筛选" style="width: 180px" />
            <a-select
              v-model:value="bindingGroupFilter"
              class="warm-select"
              show-search
              option-filter-prop="label"
              placeholder="主接口分组"
              style="width: 180px"
            >
              <a-select-option value="all" label="全部主接口分组">全部主接口分组</a-select-option>
              <a-select-option v-for="group in groupOptions" :key="group" :value="group" :label="group">
                {{ group }}
              </a-select-option>
            </a-select>
            <a-select
              v-model:value="bindingAvailabilityFilter"
              class="warm-select"
              show-search
              option-filter-prop="label"
              placeholder="筛选可用范围"
              style="width: 180px"
            >
              <a-select-option value="all" label="全部范围">全部范围</a-select-option>
              <a-select-option value="text_to_video" label="文生视频">文生视频</a-select-option>
              <a-select-option value="image_to_video" label="图生视频">图生视频</a-select-option>
              <a-select-option value="first_last_frame" label="首尾帧">首尾帧</a-select-option>
            </a-select>
            <a-button type="primary" class="api-primary-btn" :icon="h(PlusOutlined)" @click="openCreateScene">
              新增场景
            </a-button>
          </a-space>
        </template>

        <a-alert
          class="warm-alert"
          type="info"
          show-icon
          message="按可用范围分组。主接口分组只过滤列表，不会限制可选接口。显示文案请用行内菜单编辑。"
          style="margin-bottom: 16px"
        />

        <a-spin :spinning="loading">
          <a-empty v-if="!groupedSceneBindings.length" description="没有匹配的场景" />
          <div v-else class="scene-binding-groups">
            <section v-for="block in groupedSceneBindings" :key="block.sceneType" class="scene-binding-group">
              <div class="api-config-group-title">
                <span>{{ videoSceneGroupLabel(block.sceneType) }}</span>
                <span class="api-config-group-count">{{ block.items.length }} 个场景</span>
              </div>
              <a-table
                row-key="scene_key"
                :columns="bindingColumns"
                :data-source="block.items"
                :pagination="false"
                table-layout="fixed"
                :scroll="{ x: 1436 }"
                :row-class-name="sceneRowClassName"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'scene'">
                    <div class="scene-title">{{ record.scene_label }}</div>
                    <div v-if="record.display_name" class="scene-desc">展示名：{{ record.display_name }}</div>
                    <div v-else-if="record.scene_description" class="scene-desc">{{ record.scene_description }}</div>
                    <a-space size="small" style="margin-top: 6px">
                      <a-tag v-if="record.is_builtin" class="api-tag api-tag-muted">内置</a-tag>
                      <a-tag class="api-tag" :class="record.status === 'enabled' ? 'api-tag-enabled' : 'api-tag-disabled'">
                        {{ record.status === "enabled" ? "启用" : "停用" }}
                      </a-tag>
                      <a-tag v-if="isSceneUnbound(record)" class="api-tag api-tag-form">未绑定</a-tag>
                    </a-space>
                  </template>
                  <template v-else-if="column.key === 'bind'">
                    <div class="binding-api-cell">
                      <a-select
                        :value="record.api_config_id ?? undefined"
                        class="warm-select"
                        popup-class-name="binding-api-select-dropdown"
                        allow-clear
                        show-search
                        option-filter-prop="label"
                        placeholder="请选择主接口"
                        :loading="bindingSavingKey === record.scene_key"
                        @change="(value: number | undefined) => handleBindingChange(record.scene_key, buildBindingPayload(record, { api_config_id: value ?? null }))"
                      >
                        <a-select-opt-group v-for="group in bindingOptionGroups" :key="group.group" :label="group.group">
                          <a-select-option
                            v-for="option in group.options"
                            :key="option.value"
                            :value="option.value"
                            :label="option.label"
                          >
                            {{ option.label }}
                          </a-select-option>
                        </a-select-opt-group>
                      </a-select>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'swap'">
                    <div class="binding-swap-cell">
                      <a-tooltip title="互换主备接口">
                        <a-button
                          size="small"
                          class="api-secondary-btn api-icon-btn"
                          :icon="h(SwapOutlined)"
                          :disabled="!canSwapBinding(record) || bindingSavingKey === record.scene_key"
                          :loading="bindingSavingKey === record.scene_key"
                          @click="handleSwapBinding(record)"
                        />
                      </a-tooltip>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'backup'">
                    <div class="binding-api-cell">
                      <a-select
                        :value="toBackupApiSelectValue(record.backup_api_config_id)"
                        class="warm-select"
                        popup-class-name="binding-api-select-dropdown"
                        allow-clear
                        show-search
                        option-filter-prop="label"
                        placeholder="请选择备用接口"
                        :loading="bindingSavingKey === record.scene_key"
                        @change="(value: number | string | undefined) => handleBindingChange(record.scene_key, buildBindingPayload(record, { backup_api_config_id: fromBackupApiSelectValue(value) }))"
                      >
                        <a-select-option :value="EMPTY_BACKUP_API_OPTION" label="无">无</a-select-option>
                        <a-select-opt-group v-for="group in bindingOptionGroups" :key="group.group" :label="group.group">
                          <a-select-option
                            v-for="option in group.options"
                            :key="option.value"
                            :value="option.value"
                            :label="option.label"
                          >
                            {{ option.label }}
                          </a-select-option>
                        </a-select-opt-group>
                      </a-select>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'credit'">
                    <div class="binding-credit-cell">
                      <a-select
                        :value="record.credit_billing_mode"
                        class="warm-select binding-credit-mode"
                        :disabled="bindingSavingKey === record.scene_key"
                        @change="(value: VideoCreditBillingMode) => handleBindingChange(record.scene_key, buildBindingPayload(record, { credit_billing_mode: value }))"
                      >
                        <a-select-option value="fixed">固定</a-select-option>
                        <a-select-option value="per_second">按秒</a-select-option>
                      </a-select>
                      <a-input-number
                        :value="record.credit_billing_mode === 'per_second' ? record.per_second_credit_cost : record.credit_cost"
                        class="warm-input-number"
                        :min="0"
                        :precision="0"
                        :disabled="bindingSavingKey === record.scene_key"
                        @change="(value: number | null) => handleBindingChange(
                          record.scene_key,
                          buildBindingPayload(
                            record,
                            record.credit_billing_mode === 'per_second'
                              ? { per_second_credit_cost: Number(value ?? 0) }
                              : { credit_cost: Number(value ?? 0) },
                          ),
                        )"
                      />
                      <span class="credit-unit">{{ record.credit_billing_mode === "per_second" ? "积分/秒" : "积分" }}</span>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'sort'">
                    <span class="binding-sort-value">{{ record.sort_order ?? 0 }}</span>
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-dropdown trigger="click" overlay-class-name="api-more-dropdown">
                      <button type="button" class="api-config-more-btn">
                        <MoreOutlined />
                      </button>
                      <template #overlay>
                        <a-menu>
                          <a-menu-item key="copy-text" @click="openEditCopy(record)">编辑文案</a-menu-item>
                          <a-menu-item key="copy-scene" @click="openCopyScene(record)">复制新增</a-menu-item>
                          <a-menu-item key="copy-json" @click="handleCopySceneJson(record)">复制 JSON</a-menu-item>
                          <template v-if="!record.is_builtin">
                            <a-menu-divider />
                            <a-menu-item key="edit" @click="openEditSceneMeta(record)">编辑</a-menu-item>
                            <a-menu-item key="toggle" @click="handleToggleSceneStatus(record)">
                              {{ record.status === "enabled" ? "停用" : "启用" }}
                            </a-menu-item>
                            <a-menu-item key="delete" danger @click="handleDeleteScene(record)">删除</a-menu-item>
                          </template>
                        </a-menu>
                      </template>
                    </a-dropdown>
                  </template>
                </template>
              </a-table>
            </section>
          </div>
        </a-spin>
      </a-card>

      <a-card title="占位符用法" class="warm-card api-card motion-fade-up motion-card-lift" style="--motion-delay: 200ms">
        <a-collapse class="warm-collapse">
          <a-collapse-panel key="common" header="通用占位符">
            <div class="doc-block">
              <div>可用于 Header JSON、请求 JSON、轮询地址或轮询请求 JSON：</div>
              <pre v-pre>{{ api_key }}</pre>
              <pre v-pre>{{ bearer_token }}</pre>
              <pre v-pre>{{ prompt }}</pre>
              <pre v-pre>{{ aspect_ratio }}</pre>
              <pre v-pre>{{ duration_seconds }}</pre>
              <pre v-pre>{{ resolution }}</pre>
              <pre v-pre>{{ mapped_resolution }}</pre>
              <pre v-pre>{{ provider_task_id }}</pre>
              <pre v-pre>{{ task_id }}</pre>
            </div>
          </a-collapse-panel>
          <a-collapse-panel key="video" header="视频生成相关">
            <div class="doc-block">
              <div>用于图生视频或需要带参考图的视频接口：</div>
              <pre v-pre>{{ reference_image_1 }}</pre>
              <pre v-pre>{{ reference_image_1_url }}</pre>
              <pre v-pre>{{ reference_image_1_base64 }}</pre>
              <pre v-pre>{{ reference_image_1_mime_type }}</pre>
              <pre v-pre>{{ reference_image_1_data_url }}</pre>
              <pre v-pre>{{ reference_image_count }}</pre>
              <div class="scene-desc" style="margin-top: 8px">首尾帧模式可使用别名：</div>
              <pre v-pre>{{ first_frame_image_url }}</pre>
              <pre v-pre>{{ last_frame_image_url }}</pre>
              <pre v-pre>{{ first_frame_image_data_url }}</pre>
              <pre v-pre>{{ last_frame_image_data_url }}</pre>
              <div class="scene-desc" style="margin-top: 8px">
                每个视频场景可单独配置最大参考图张数。前端会按场景限制上传数量，并回填
                <code v-pre>{{ reference_image_1 }}</code>
                到
                <code v-pre>{{ reference_image_N }}</code>
                ，以及对应的
                <code v-pre>{{ reference_image_1_url }}</code>
                /
                <code v-pre>{{ reference_image_1_base64 }}</code>
                /
                <code v-pre>{{ reference_image_1_data_url }}</code>
                变体。纯文生视频场景可填 `0`。
              </div>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </a-card>
    </a-space>

    <a-modal v-model:open="sceneModalOpen" :title="sceneModalTitle" :mask-closable="false" :width="720" @ok="handleCreateScene">
      <a-form layout="vertical">
        <a-form-item label="粘贴视频场景绑定 JSON 回填">
          <a-textarea
            v-model:value="sceneImportJson"
            :rows="6"
            allow-clear
            class="warm-input"
            placeholder="粘贴从“复制 JSON”得到的视频场景绑定模板，可自动识别并回填下面的字段"
          />
          <div style="display: flex; justify-content: flex-end; margin-top: 8px">
            <a-button class="api-secondary-btn" @click="handleApplySceneImportJson">识别并回填</a-button>
          </div>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="场景标识" required>
              <a-input v-model:value="sceneForm.scene_key" class="warm-input" placeholder="例如：kling_v11" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="排序值">
              <a-input-number v-model:value="sceneForm.sort_order" class="warm-input-number" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="场景名称" required>
              <a-input v-model:value="sceneForm.scene_label" class="warm-input" placeholder="例如：Kling V1.1" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="计费方式">
              <a-radio-group v-model:value="sceneForm.credit_billing_mode" class="warm-radio-group" button-style="solid">
                <a-radio-button value="fixed">固定计费</a-radio-button>
                <a-radio-button value="per_second">按秒计费</a-radio-button>
              </a-radio-group>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item :label="sceneForm.credit_billing_mode === 'per_second' ? '每秒积分' : '一次性积分'">
              <a-input-number
                v-if="sceneForm.credit_billing_mode === 'per_second'"
                v-model:value="sceneForm.per_second_credit_cost"
                class="warm-input-number"
                :min="0"
                style="width: 100%"
              />
              <a-input-number
                v-else
                v-model:value="sceneForm.credit_cost"
                class="warm-input-number"
                :min="0"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="计费说明">
              <div class="scene-desc">
                {{ sceneForm.credit_billing_mode === "per_second" ? "提交任务时按 秒数 x 每秒积分 扣费。" : "提交任务时按固定积分扣费；如果配置了分辨率积分 JSON，则优先使用分辨率对应值。" }}
              </div>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="场景描述">
          <a-input v-model:value="sceneForm.scene_description" class="warm-input" placeholder="例如：高质量文生视频模型" />
        </a-form-item>
        <a-form-item label="可用范围">
          <a-select v-model:value="sceneForm.availability_modes" class="warm-select" mode="multiple" placeholder="请选择可用范围">
            <a-select-option value="text_to_video">文生视频</a-select-option>
            <a-select-option value="image_to_video">图生视频</a-select-option>
            <a-select-option value="first_last_frame">首尾帧</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="默认绑定接口">
          <a-select
            v-model:value="sceneForm.api_config_id"
            class="warm-select"
            popup-class-name="binding-api-select-dropdown"
            allow-clear
            show-search
            option-filter-prop="label"
            placeholder="可选，创建后也可在列表中再绑定"
          >
            <a-select-opt-group v-for="group in bindingOptionGroups" :key="group.group" :label="group.group">
              <a-select-option
                v-for="option in group.options"
                :key="option.value"
                :value="option.value"
                :label="option.label"
              >
                {{ option.label }}
              </a-select-option>
            </a-select-opt-group>
          </a-select>
        </a-form-item>
        <a-form-item label="备用接口">
          <a-select
            :value="toBackupApiSelectValue(sceneForm.backup_api_config_id)"
            class="warm-select"
            popup-class-name="binding-api-select-dropdown"
            allow-clear
            show-search
            option-filter-prop="label"
            placeholder="可选，主接口失败时自动切换"
            @update:value="(value: number | string | undefined) => { sceneForm.backup_api_config_id = fromBackupApiSelectValue(value); }"
          >
            <a-select-option :value="EMPTY_BACKUP_API_OPTION" label="无">无</a-select-option>
            <a-select-opt-group v-for="group in bindingOptionGroups" :key="group.group" :label="group.group">
              <a-select-option
                v-for="option in group.options"
                :key="option.value"
                :value="option.value"
                :label="option.label"
              >
                {{ option.label }}
              </a-select-option>
            </a-select-opt-group>
          </a-select>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="显示名称">
              <a-input v-model:value="sceneForm.display_name" class="warm-input" placeholder="为空则使用场景名称" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="副标题">
              <a-input v-model:value="sceneForm.subtitle" class="warm-input" placeholder="为空则使用场景描述" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="最大参考图张数">
          <a-input-number v-model:value="sceneForm.max_reference_images" class="warm-input-number" :min="0" :max="6" style="width: 100%" />
          <div class="scene-desc" style="margin-top: 6px">
            图生视频时前端最多允许上传这么多张参考图；纯文生视频可填 `0`。系统上限为 6 张。
          </div>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="隐藏宽高比">
              <a-switch v-model:checked="sceneForm.hide_aspect_ratio" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="隐藏秒数">
              <a-switch v-model:checked="sceneForm.hide_duration" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="隐藏分辨率">
              <a-switch v-model:checked="sceneForm.hide_resolution" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="宽高比选项 JSON">
          <a-textarea v-model:value="sceneForm.aspect_ratio_options_json" class="warm-textarea" :rows="6" placeholder='[{"label":"16:9","value":"16:9"}]' />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `label/value` 数组；`value` 会映射到请求里的 <code v-pre>{{ aspect_ratio }}</code> 占位符。
          </div>
        </a-form-item>
        <a-form-item label="秒数选项 JSON">
          <a-textarea v-model:value="sceneForm.duration_options_json" class="warm-textarea" :rows="6" placeholder='[{"label":"5 秒","value":"5"}]' />
        </a-form-item>
        <a-form-item label="分辨率选项 JSON">
          <a-textarea v-model:value="sceneForm.resolution_options_json" class="warm-textarea" :rows="6" placeholder='[{"label":"1080P","value":"1080p"}]' />
        </a-form-item>
        <a-form-item label="分辨率映射 JSON">
          <a-textarea v-model:value="sceneForm.resolution_mapping_json" class="warm-textarea" :rows="8" placeholder='{"1080p":"1920x1080"}' />
        </a-form-item>
        <a-form-item label="分辨率积分 JSON">
          <a-textarea v-model:value="sceneForm.resolution_credit_costs_json" class="warm-textarea" :rows="5" placeholder='{"540p":10,"720p":20,"1080p":30}' />
        </a-form-item>
        <div v-if="sceneForm.credit_billing_mode === 'per_second'" class="scene-desc" style="margin-top: -8px">
          按秒计费模式下，分辨率积分 JSON 不参与扣费计算，仅固定计费模式会使用。
        </div>
      </a-form>
      <template #footer>
        <a-space>
          <a-button class="api-secondary-btn" @click="sceneModalOpen = false">取消</a-button>
          <a-button type="primary" class="api-primary-btn" :loading="bindingCreating" @click="handleCreateScene">创建</a-button>
        </a-space>
      </template>
    </a-modal>

    <a-modal v-model:open="sceneMetaModalOpen" title="编辑视频场景基础信息" :mask-closable="false" :width="720" @ok="handleSaveSceneMeta">
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="场景标识" required>
              <a-input v-model:value="sceneMetaForm.scene_key" class="warm-input" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="场景名称" required>
              <a-input v-model:value="sceneMetaForm.scene_label" class="warm-input" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="排序值">
              <a-input-number v-model:value="sceneMetaForm.sort_order" class="warm-input-number" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="最大参考图张数">
              <a-input-number v-model:value="sceneMetaForm.max_reference_images" class="warm-input-number" :min="0" :max="6" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item label="场景描述">
              <a-input v-model:value="sceneMetaForm.scene_description" class="warm-input" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="可用范围">
          <a-select v-model:value="sceneMetaForm.availability_modes" class="warm-select" mode="multiple" placeholder="请选择可用范围">
            <a-select-option value="text_to_video">文生视频</a-select-option>
            <a-select-option value="image_to_video">图生视频</a-select-option>
            <a-select-option value="first_last_frame">首尾帧</a-select-option>
          </a-select>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="计费方式">
              <a-radio-group v-model:value="sceneMetaForm.credit_billing_mode" class="warm-radio-group" button-style="solid">
                <a-radio-button value="fixed">固定计费</a-radio-button>
                <a-radio-button value="per_second">按秒计费</a-radio-button>
              </a-radio-group>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="sceneMetaForm.credit_billing_mode === 'per_second' ? '每秒积分' : '一次性积分'">
              <a-input-number
                v-if="sceneMetaForm.credit_billing_mode === 'per_second'"
                v-model:value="sceneMetaForm.per_second_credit_cost"
                class="warm-input-number"
                :min="0"
                style="width: 100%"
              />
              <a-input-number
                v-else
                v-model:value="sceneMetaForm.credit_cost"
                class="warm-input-number"
                :min="0"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="隐藏宽高比">
              <a-switch v-model:checked="sceneMetaForm.hide_aspect_ratio" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="隐藏秒数">
              <a-switch v-model:checked="sceneMetaForm.hide_duration" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="隐藏分辨率">
              <a-switch v-model:checked="sceneMetaForm.hide_resolution" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="宽高比选项 JSON">
          <a-textarea v-model:value="sceneMetaForm.aspect_ratio_options_json" class="warm-textarea" :rows="6" />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `label/value` 数组；`value` 会映射到请求里的 <code v-pre>{{ aspect_ratio }}</code> 占位符。
          </div>
        </a-form-item>
        <a-form-item label="秒数选项 JSON">
          <a-textarea v-model:value="sceneMetaForm.duration_options_json" class="warm-textarea" :rows="6" />
        </a-form-item>
        <a-form-item label="分辨率选项 JSON">
          <a-textarea v-model:value="sceneMetaForm.resolution_options_json" class="warm-textarea" :rows="6" />
        </a-form-item>
        <a-form-item label="分辨率映射 JSON">
          <a-textarea v-model:value="sceneMetaForm.resolution_mapping_json" class="warm-textarea" :rows="8" />
        </a-form-item>
        <a-form-item label="分辨率积分 JSON">
          <a-textarea v-model:value="sceneMetaForm.resolution_credit_costs_json" class="warm-textarea" :rows="5" />
        </a-form-item>
        <div v-if="sceneMetaForm.credit_billing_mode === 'per_second'" class="scene-desc" style="margin-top: -8px">
          按秒计费模式下，分辨率积分 JSON 不参与扣费计算，仅固定计费模式会使用。
        </div>
      </a-form>
      <template #footer>
        <a-space>
          <a-button class="api-secondary-btn" @click="sceneMetaModalOpen = false">取消</a-button>
          <a-button type="primary" class="api-primary-btn" :loading="sceneMetaSaving" @click="handleSaveSceneMeta">保存</a-button>
        </a-space>
      </template>
    </a-modal>

    <a-modal
      v-model:open="copyModalOpen"
      title="编辑展示文案"
      :mask-closable="false"
      :width="480"
    >
      <a-form layout="vertical">
        <a-form-item label="显示名称">
          <a-input v-model:value="copyForm.display_name" class="warm-input" placeholder="为空则使用场景名称" />
        </a-form-item>
        <a-form-item label="副标题">
          <a-input v-model:value="copyForm.subtitle" class="warm-input" placeholder="为空则使用场景描述" />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space>
          <a-button class="api-secondary-btn" @click="copyModalOpen = false">取消</a-button>
          <a-button
            type="primary"
            class="api-primary-btn"
            :loading="bindingSavingKey === copyEditingKey"
            @click="handleSaveCopy"
          >
            保存
          </a-button>
        </a-space>
      </template>
    </a-modal>

    <a-modal v-model:open="modalOpen" :title="modalTitle" :mask-closable="false" :width="920" @ok="handleSave">
      <a-form layout="vertical">
        <a-form-item v-if="!editingId" label="粘贴视频接口配置 JSON 回填">
          <a-textarea
            v-model:value="configImportJson"
            :rows="6"
            allow-clear
            class="warm-input"
            placeholder="粘贴从“复制 JSON”得到的视频接口配置模板，可自动识别并回填下面的字段"
          />
          <div style="display: flex; justify-content: flex-end; margin-top: 8px">
            <a-button class="api-secondary-btn" @click="handleApplyConfigImportJson">识别并回填</a-button>
          </div>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="配置名称" required>
              <a-input v-model:value="form.name" class="warm-input" placeholder="例如：Kling 主接口" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="接口分组">
              <a-input v-model:value="form.group_name" class="warm-input" placeholder="例如：Kling / Hailuo / Runway" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-input v-model:value="form.description" class="warm-input" placeholder="可选，用于备注该视频接口用途" />
        </a-form-item>
        <a-form-item label="请求地址" required>
          <a-input v-model:value="form.request_url" class="warm-input" placeholder="https://example.com/api" />
        </a-form-item>
        <a-form-item label="调用方式" required>
          <a-radio-group v-model:value="form.call_mode" class="warm-radio-group" button-style="solid">
            <a-radio-button value="async">异步轮询</a-radio-button>
          </a-radio-group>
          <div class="scene-desc" style="margin-top: 6px">视频接口统一按“提交第三方 taskId -> 服务端轮询结果”路线执行。</div>
        </a-form-item>
        <a-form-item label="请求格式" required>
          <a-radio-group v-model:value="form.request_format" class="warm-radio-group" button-style="solid">
            <a-radio-button value="json">JSON</a-radio-button>
            <a-radio-button value="multipart">Multipart Form</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-form-item label="Header JSON" required>
          <a-textarea v-model:value="form.headers_json" class="warm-textarea" :rows="7" />
        </a-form-item>
        <a-form-item label="请求 JSON" required>
          <a-textarea v-model:value="form.payload_json" class="warm-textarea" :rows="12" />
        </a-form-item>
        <a-form-item label="响应 JSON" required>
          <a-textarea v-model:value="form.response_json" class="warm-textarea" :rows="10" />
        </a-form-item>

        <a-divider orientation="left">异步轮询配置</a-divider>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="提交成功状态码 JSON" required>
              <a-textarea v-model:value="form.submit_success_statuses_json" class="warm-textarea" :rows="4" placeholder='[200, 201, 202]' />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="轮询方法" required>
              <a-radio-group v-model:value="form.poll_method" class="warm-radio-group" button-style="solid">
                <a-radio-button value="GET">GET</a-radio-button>
                <a-radio-button value="POST">POST</a-radio-button>
              </a-radio-group>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="轮询地址" required>
          <a-input v-model:value="form.poll_url" class="warm-input" placeholder="https://example.com/tasks/{{ provider_task_id }}" />
        </a-form-item>
        <a-form-item label="轮询 Header JSON" required>
          <a-textarea v-model:value="form.poll_headers_json" class="warm-textarea" :rows="6" />
        </a-form-item>
        <a-form-item label="轮询请求 JSON">
          <a-textarea v-model:value="form.poll_payload_json" class="warm-textarea" :rows="8" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="第三方任务 ID 字段路径" required>
              <a-input v-model:value="form.task_id_field" class="warm-input" placeholder="例如：data.task_id" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="结果状态字段路径" required>
              <a-input v-model:value="form.result_status_field" class="warm-input" placeholder="例如：data.status" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="成功状态值 JSON" required>
              <a-textarea v-model:value="form.result_success_values_json" class="warm-textarea" :rows="4" placeholder='["success", "completed"]' />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="失败状态值 JSON" required>
              <a-textarea v-model:value="form.result_failed_values_json" class="warm-textarea" :rows="4" placeholder='["failed", "error", "cancelled"]' />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="轮询结果视频 URL 字段路径" required>
              <a-input v-model:value="form.poll_result_video_url_field" class="warm-input" placeholder="例如：data.result.video_url" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="轮询结果封面 URL 字段路径">
              <a-input v-model:value="form.poll_result_cover_url_field" class="warm-input" placeholder="例如：data.result.cover_url" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="轮询结果视频 Base64 字段路径">
              <a-input v-model:value="form.poll_result_video_base64_field" class="warm-input" placeholder="通常留空，仅兼容特殊供应商" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="提交响应视频 URL 字段路径">
              <a-input v-model:value="form.result_video_url_field" class="warm-input" placeholder="通常留空，仅少数接口会在提交响应中直接返回" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="提交响应封面 URL 字段路径">
          <a-input v-model:value="form.result_cover_url_field" class="warm-input" placeholder="通常留空，仅少数接口会在提交响应中直接返回" />
        </a-form-item>
        <a-form-item label="结果错误信息字段路径">
          <a-input v-model:value="form.result_error_field" class="warm-input" placeholder="例如：data.error.message" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="轮询间隔（秒）" required>
              <a-input-number v-model:value="form.poll_interval_seconds" class="warm-input-number" :min="1" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="轮询超时（秒）" required>
              <a-input-number v-model:value="form.poll_timeout_seconds" class="warm-input-number" :min="1" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="状态">
          <a-radio-group v-model:value="form.status" class="warm-radio-group" button-style="solid">
            <a-radio-button value="enabled">启用</a-radio-button>
            <a-radio-button value="disabled">停用</a-radio-button>
          </a-radio-group>
        </a-form-item>
      </a-form>
      <template #footer>
        <a-space>
          <a-button class="api-secondary-btn" @click="modalOpen = false">取消</a-button>
          <a-button class="api-secondary-btn" :loading="testing" @click="handleTestConnection">测试连接</a-button>
          <a-button type="primary" class="api-primary-btn" :loading="saving" @click="handleSave">保存</a-button>
        </a-space>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.page {
  padding: 4px;
}

.api-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--theme-border);
  background: linear-gradient(180deg, rgba(255, 250, 240, 0.88), rgba(255, 255, 255, 0.22));
}

.api-card :deep(.ant-card-head-title) {
  color: #5d4526;
  font-weight: 700;
}

.api-card :deep(.ant-card-body) {
  padding: 20px;
}

.api-config-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.api-config-group + .api-config-group {
  padding-top: 20px;
  border-top: 1px solid var(--theme-border);
}

.api-config-group-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
  color: #5d4526;
  font-size: 16px;
  font-weight: 700;
}

button.api-config-group-title {
  align-items: center;
  width: 100%;
  margin-bottom: 0;
  padding: 0;
  border: 0;
  background: transparent;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}

button.api-config-group-title.is-expanded {
  margin-bottom: 12px;
}

.api-config-group-arrow {
  flex-shrink: 0;
  color: var(--text-secondary);
  font-size: 12px;
  transition: transform 0.2s ease;
}

button.api-config-group-title.is-expanded .api-config-group-arrow {
  transform: rotate(180deg);
}

.api-config-group-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.22s var(--motion-ease-enter, cubic-bezier(0.24, 0.72, 0.32, 1));
}

.api-config-group-body.is-expanded {
  grid-template-rows: 1fr;
}

.api-config-group-body-inner {
  min-height: 0;
  overflow: hidden;
}

.api-config-group-count {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.api-config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(196px, 1fr));
  gap: 10px;
}

.api-config-tile {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 96px;
  padding: 10px 10px 8px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 12px;
  background: var(--theme-panel-bg-soft);
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease, background 0.16s ease;
}

.api-config-tile.is-used {
  border-color: #1fba62;
  background: #7ee3a3;
}

.api-config-tile.is-unused {
  border-color: #ebd3a4;
  background: #fff8eb;
}

.api-config-tile:hover {
  transform: translateY(-1px);
}

.api-config-tile.is-used:hover {
  border-color: #12964c;
  box-shadow: 0 8px 20px rgba(18, 150, 76, 0.22);
}

.api-config-tile.is-unused:hover {
  border-color: #dfb56a;
  box-shadow: 0 8px 20px rgba(176, 126, 36, 0.1);
}

.api-config-tile.is-disabled,
.api-config-tile.is-used.is-disabled,
.api-config-tile.is-unused.is-disabled {
  opacity: 1;
  border-color: #b8b8b8;
  background: #d8d8d8;
  box-shadow: none;
}

.api-config-tile.is-disabled:hover,
.api-config-tile.is-used.is-disabled:hover,
.api-config-tile.is-unused.is-disabled:hover {
  border-color: #9e9e9e;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
}

.api-config-tile.is-disabled .api-config-tile-name,
.api-config-tile.is-disabled .api-config-more-btn {
  color: #6b6b6b;
}

.api-config-tile.is-disabled .api-config-tile-meta,
.api-config-tile.is-disabled .api-config-tile-meta.is-unused {
  color: #7a7a7a;
}

.api-config-tile-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.api-config-tile-name {
  color: #5d4526;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
  word-break: break-word;
}

.api-config-more-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #5d4526;
  cursor: pointer;
}

.api-config-more-btn:hover {
  border-color: var(--theme-panel-border-strong);
  background: var(--theme-control-hover-bg);
  color: var(--theme-accent-text);
}

.api-config-tile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.api-config-tile-tags :deep(.ant-tag) {
  margin-inline-end: 0;
  padding-inline: 6px;
  line-height: 18px;
  font-size: 11px;
}

.api-config-tile-meta {
  margin-top: auto;
  color: #0d6b35;
  font-size: 11px;
  font-weight: 700;
}

.api-config-tile-meta.is-clickable {
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.api-config-tile-meta.is-unused {
  color: #b07e24;
}

.api-config-usage-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 220px;
  max-width: 280px;
}

.api-config-usage-item + .api-config-usage-item {
  padding-top: 10px;
  border-top: 1px solid var(--theme-border);
}

.api-config-usage-name {
  color: #5d4526;
  font-weight: 700;
}

.api-config-usage-desc {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 12px;
}

.api-primary-btn {
  border-color: var(--theme-accent) !important;
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  border-radius: 12px !important;
  font-weight: 600;
}

.api-primary-btn:hover,
.api-primary-btn:focus {
  border-color: var(--theme-accent-strong) !important;
  background: var(--theme-accent-strong) !important;
  color: var(--theme-accent-contrast) !important;
}

.api-secondary-btn {
  border-color: var(--theme-panel-border-strong) !important;
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
  border-radius: 12px !important;
  font-weight: 600;
}

.api-secondary-btn:hover,
.api-secondary-btn:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
}

.api-danger-btn {
  border-color: #efb5ae !important;
  background: #fff1ef !important;
  color: #d6574b !important;
  border-radius: 12px !important;
  font-weight: 600;
}

.api-danger-btn:hover,
.api-danger-btn:focus {
  border-color: #e28980 !important;
  background: #ffe5e1 !important;
  color: #c9483d !important;
}

.api-icon-btn {
  padding-inline: 10px;
}

.api-tag {
  border-radius: 999px;
  border-width: 1px;
  font-weight: 600;
}

.api-tag-group {
  color: var(--theme-accent-text);
  background: var(--theme-panel-bg-strong);
  border-color: var(--theme-panel-border-strong);
}

.api-tag-enabled {
  color: #2f7a45;
  background: #e7f6ec;
  border-color: #b7d6bf;
}

.api-tag-disabled {
  color: #8a5a55;
  background: #f6eceb;
  border-color: #e2c4c0;
}

.api-tag-sync {
  color: #2b6f86;
  background: #e7f4f8;
  border-color: #b5d4de;
}

.api-tag-async {
  color: #6b4ea3;
  background: #f1ebf8;
  border-color: #d2c4e8;
}

.api-tag-json {
  color: #5d4526;
  background: #f6efe4;
  border-color: #e2d3bb;
}

.api-tag-form {
  color: #8a5a1e;
  background: #fff3df;
  border-color: #ebd3a4;
}

.api-tag-muted {
  color: var(--text-secondary);
  background: var(--theme-panel-bg-soft);
  border-color: var(--theme-panel-border);
}

.scene-binding-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.scene-binding-group + .scene-binding-group {
  padding-top: 20px;
  border-top: 1px solid var(--theme-border);
}

.scene-binding-group :deep(.ant-table),
.scene-binding-group :deep(.ant-table-container),
.scene-binding-group :deep(.ant-table-content),
.scene-binding-group :deep(.ant-table-body),
.scene-binding-group :deep(.ant-table-header) {
  background: transparent;
}

.scene-binding-group :deep(.ant-table-tbody > tr.is-unbound-scene > td) {
  background: color-mix(in srgb, #f3d7a0 28%, var(--theme-table-row-bg));
}

.scene-binding-group :deep(.ant-table-tbody > tr.is-unbound-scene:hover > td) {
  background: color-mix(in srgb, #f3d7a0 38%, var(--theme-table-row-hover)) !important;
}

.scene-binding-group :deep(.ant-table-container table) {
  table-layout: fixed;
}

.scene-binding-group :deep(.ant-table-thead > tr > th:nth-child(1)),
.scene-binding-group :deep(.ant-table-tbody > tr > td:nth-child(1)) {
  width: 196px;
  max-width: 196px;
}

.scene-binding-group :deep(.ant-table-thead > tr > th:nth-child(2)),
.scene-binding-group :deep(.ant-table-tbody > tr > td:nth-child(2)),
.scene-binding-group :deep(.ant-table-thead > tr > th:nth-child(4)),
.scene-binding-group :deep(.ant-table-tbody > tr > td:nth-child(4)) {
  width: 400px;
  min-width: 400px;
  max-width: 400px;
}

.binding-api-cell {
  width: 100%;
}

.binding-api-cell :deep(.ant-select) {
  width: 100%;
}

.scene-title {
  color: #5d4526;
  font-weight: 600;
}

.scene-binding-group .scene-title,
.scene-binding-group .scene-desc {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scene-desc {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.binding-swap-cell {
  display: flex;
  align-items: center;
  justify-content: center;
}

.binding-credit-cell {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 6px;
  min-width: 0;
}

.binding-credit-cell :deep(.warm-input-number.ant-input-number) {
  width: 72px !important;
  min-width: 72px;
  flex: none;
}

.binding-credit-cell :deep(.binding-credit-mode.ant-select) {
  width: 80px !important;
  min-width: 80px;
  flex: none;
}

.credit-unit {
  flex: none;
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.binding-sort-value {
  color: #5d4526;
  font-weight: 700;
}

.doc-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-block pre {
  margin: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--theme-empty-bg);
  border: 1px solid var(--theme-panel-border);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>

<style>
.binding-api-select-dropdown .ant-select-item-group {
  margin-top: 2px;
  padding-top: 8px;
  color: #5d4526;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.4;
}

.binding-api-select-dropdown .ant-select-item-group:not(:first-child) {
  margin-top: 6px;
  border-top: 1px solid var(--theme-border, #ead9c0);
}

.api-more-dropdown .ant-dropdown-menu {
  min-width: 148px;
  padding: 6px;
  border: 1px solid var(--theme-panel-border, #ead9c0);
  border-radius: 12px;
  background: #fffaf2;
  box-shadow: 0 10px 28px rgba(93, 69, 38, 0.12);
}

.api-more-dropdown .ant-dropdown-menu-item {
  margin: 2px 0;
  padding: 7px 12px;
  border-radius: 8px;
  color: #5d4526;
  font-weight: 600;
}

.api-more-dropdown .ant-dropdown-menu-item:hover {
  background: var(--theme-control-hover-bg, #f6efe4);
  color: #5d4526;
}

.api-more-dropdown .ant-dropdown-menu-item-danger {
  color: #c9483d;
}

.api-more-dropdown .ant-dropdown-menu-item-danger:hover {
  background: #fff1ef;
  color: #c9483d;
}

.api-more-dropdown .ant-dropdown-menu-item-divider {
  margin: 4px 8px;
  background: var(--theme-border, #ead9c0);
}
</style>
