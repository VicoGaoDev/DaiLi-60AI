<script setup lang="ts">
import { computed, h, onMounted, reactive, ref, watch } from "vue";
import { message, Modal } from "ant-design-vue";
import {
  DownOutlined,
  MoreOutlined,
  PlusOutlined,
  SwapOutlined,
} from "@ant-design/icons-vue";
import {
  createExternalApiConfig,
  createExternalApiSceneBinding,
  deleteExternalApiConfig,
  deleteExternalApiSceneBinding,
  listExternalApiConfigs,
  listExternalApiSceneBindings,
  testExternalApiConfig,
  updateExternalApiConfig,
  updateExternalApiConfigStatus,
  updateExternalApiSceneBinding,
  updateExternalApiSceneBindingMeta,
  updateExternalApiSceneBindingStatus,
} from "@/api/admin";
import {
  parseAdminConfigTemplate,
  stringifyAdminConfigTemplate,
} from "@/lib/adminConfigTemplate";
import type {
  ExternalApiCallMode,
  ExternalApiConfig,
  ExternalApiConfigPayload,
  ExternalApiConfigTestResult,
  ExternalApiRequestFormat,
  ExternalApiSceneBinding,
  ExternalApiSceneBindingCreatePayload,
  ExternalApiSceneBindingMetaPayload,
  ExternalApiSceneType,
} from "@/types";

type ConfigUsageRole = "primary" | "backup";

type ConfigUsageScene = {
  scene_key: string;
  scene_label: string;
  scene_type: ExternalApiSceneType;
  display_name: string;
  roles: ConfigUsageRole[];
};

const DEFAULT_ASPECT_RATIO_OPTIONS_JSON = JSON.stringify([
  { label: "■  1:1", value: "1:1" },
  { label: "▮  2:3", value: "2:3" },
  { label: "▬  3:2", value: "3:2" },
  { label: "▮  3:4", value: "3:4" },
  { label: "▬  4:3", value: "4:3" },
  { label: "▮  9:16", value: "9:16" },
  { label: "▬  16:9", value: "16:9" },
], null, 2);

const DEFAULT_IMAGE_SIZE_OPTIONS_JSON = JSON.stringify([
  { label: "1K", value: "1K" },
  { label: "2K", value: "2K" },
  { label: "4K", value: "4K" },
], null, 2);

const DEFAULT_CUSTOM_SIZE_OPTIONS_JSON = JSON.stringify([
  { label: "1024 x 1024", value: "1024x1024" },
  { label: "1152 x 896", value: "1152x896" },
  { label: "896 x 1152", value: "896x1152" },
  { label: "1280 x 720", value: "1280x720" },
], null, 2);
const DEFAULT_RESOLUTION_MAPPING_JSON = JSON.stringify({}, null, 2);
const DEFAULT_RESOLUTION_CREDIT_COSTS_JSON = JSON.stringify({}, null, 2);
const DEFAULT_IMAGE_EDIT_MAX_REFERENCE_IMAGES = 6;
const DEFAULT_SUBMIT_SUCCESS_STATUSES_JSON = JSON.stringify([200, 201, 202], null, 2);
const DEFAULT_RESULT_SUCCESS_VALUES_JSON = JSON.stringify(["success", "succeeded", "completed"], null, 2);
const DEFAULT_RESULT_FAILED_VALUES_JSON = JSON.stringify(["failed", "error", "cancelled"], null, 2);

const configs = ref<ExternalApiConfig[]>([]);
const sceneBindings = ref<ExternalApiSceneBinding[]>([]);
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
const bindingSceneTypeFilter = ref<"all" | ExternalApiSceneType>("all");
const bindingNameFilter = ref("");
const configImportJson = ref("");
const sceneImportJson = ref("");

const SCENE_TYPE_ORDER: ExternalApiSceneType[] = [
  "generate",
  "image_edit",
  "prompt_reverse",
  "prompt_optimize",
  "inpaint",
  "smart_cutout",
];

const bindingColumns = [
  { title: "场景", key: "scene", width: 196, ellipsis: true },
  { title: "主接口", key: "bind", width: 400, ellipsis: true },
  { title: "互换", key: "swap", width: 64 },
  { title: "备用接口", key: "backup", width: 400, ellipsis: true },
  { title: "积分", key: "credit", width: 128 },
  { title: "排序", key: "sort", width: 72 },
  { title: "", key: "action", width: 56 },
];

const form = reactive<ExternalApiConfigPayload>({
  name: "",
  description: "",
  group_name: "默认",
  request_url: "",
  request_format: "json",
  headers_json: '{\n  "Content-Type": "application/json"\n}',
  payload_json: "{\n\n}",
  response_json: "{\n\n}",
  result_base64_field: "candidates.0.content.parts.0.inlineData.data",
  call_mode: "sync",
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
  poll_result_base64_field: "",
  poll_result_url_field: "",
  poll_interval_seconds: 5,
  poll_timeout_seconds: 600,
  status: "enabled",
});
const sceneForm = reactive<ExternalApiSceneBindingCreatePayload>({
  scene_key: "",
  scene_type: "generate",
  scene_label: "",
  scene_description: "",
  sort_order: 100,
  hide_aspect_ratio: false,
  hide_resolution: false,
  hide_custom_size: true,
  custom_size_min: 256,
  custom_size_max: 4096,
  custom_size_step: 8,
  api_config_id: null,
  backup_api_config_id: null,
  display_name: "",
  subtitle: "",
  credit_cost: 4,
  max_reference_images: 0,
  aspect_ratio_options_json: DEFAULT_ASPECT_RATIO_OPTIONS_JSON,
  image_size_options_json: DEFAULT_IMAGE_SIZE_OPTIONS_JSON,
  custom_size_options_json: DEFAULT_CUSTOM_SIZE_OPTIONS_JSON,
  resolution_mapping_json: DEFAULT_RESOLUTION_MAPPING_JSON,
  resolution_credit_costs_json: DEFAULT_RESOLUTION_CREDIT_COSTS_JSON,
});
const sceneMetaForm = reactive<ExternalApiSceneBindingMetaPayload>({
  scene_key: "",
  scene_label: "",
  scene_description: "",
  sort_order: 0,
  hide_aspect_ratio: false,
  hide_resolution: false,
  hide_custom_size: true,
  custom_size_min: 256,
  custom_size_max: 4096,
  custom_size_step: 8,
  max_reference_images: 0,
  aspect_ratio_options_json: DEFAULT_ASPECT_RATIO_OPTIONS_JSON,
  image_size_options_json: DEFAULT_IMAGE_SIZE_OPTIONS_JSON,
  custom_size_options_json: DEFAULT_CUSTOM_SIZE_OPTIONS_JSON,
  resolution_mapping_json: DEFAULT_RESOLUTION_MAPPING_JSON,
  resolution_credit_costs_json: DEFAULT_RESOLUTION_CREDIT_COSTS_JSON,
});

const modalTitle = computed(() => {
  if (editingId.value) return "编辑接口配置";
  if (isCopyMode.value) return "复制新增接口配置";
  return "新增接口配置";
});
const sceneModalTitle = computed(() => (isSceneCopyMode.value ? "复制新增场景" : "新增场景"));
const isAsyncConfigForm = computed(() => form.call_mode === "async");
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
const groupedConfigs = computed(() => {
  const map = new Map<string, ExternalApiConfig[]>();
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
  const appendUsage = (configId: number | null | undefined, binding: ExternalApiSceneBinding, role: ConfigUsageRole) => {
    if (!configId) return;
    const list = map.get(configId) ?? [];
    const existing = list.find((item) => item.scene_key === binding.scene_key);
    if (existing) {
      if (!existing.roles.includes(role)) existing.roles.push(role);
    } else {
      list.push({
        scene_key: binding.scene_key,
        scene_label: binding.scene_label,
        scene_type: binding.scene_type,
        display_name: binding.display_name,
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
const filteredSceneBindings = computed(() => sceneBindings.value.filter((item) => {
  if (bindingGroupFilter.value !== "all" && (item.api_group_name || "未分组") !== bindingGroupFilter.value) return false;
  if (bindingSceneTypeFilter.value !== "all" && item.scene_type !== bindingSceneTypeFilter.value) return false;
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
const groupedSceneBindings = computed(() => {
  const map = new Map<ExternalApiSceneType, ExternalApiSceneBinding[]>();
  for (const item of filteredSceneBindings.value) {
    const list = map.get(item.scene_type) ?? [];
    list.push(item);
    map.set(item.scene_type, list);
  }
  const knownTypes = SCENE_TYPE_ORDER.filter((sceneType) => map.has(sceneType));
  const extraTypes = Array.from(map.keys()).filter((sceneType) => !SCENE_TYPE_ORDER.includes(sceneType));
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

function sceneTypeLabel(sceneType: ExternalApiSceneBinding["scene_type"]) {
  if (sceneType === "generate") return "文生图";
  if (sceneType === "image_edit") return "图编辑";
  if (sceneType === "inpaint") return "局部重绘";
  if (sceneType === "smart_cutout") return "智能抠图";
  if (sceneType === "prompt_reverse") return "提示词反推";
  if (sceneType === "prompt_optimize") return "提示词优化";
  return sceneType;
}

function configCardName(item: ExternalApiConfig) {
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

function callModeLabel(callMode: ExternalApiCallMode) {
  return callMode === "async" ? "异步" : "同步";
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
  form.result_base64_field = "candidates.0.content.parts.0.inlineData.data";
  form.call_mode = "sync";
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
  form.poll_result_base64_field = "";
  form.poll_result_url_field = "";
  form.poll_interval_seconds = 5;
  form.poll_timeout_seconds = 600;
  form.status = "enabled";
}

function fillForm(item: ExternalApiConfig) {
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
  form.result_base64_field = item.result_base64_field || "";
  form.call_mode = item.call_mode || "sync";
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
  form.poll_result_base64_field = item.poll_result_base64_field || "";
  form.poll_result_url_field = item.poll_result_url_field || "";
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
  while (existingNames.has(`${trimmed}（副本${index}）`)) {
    index += 1;
  }
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
  sceneForm.scene_type = "generate";
  sceneForm.scene_label = "";
  sceneForm.scene_description = "";
  sceneForm.sort_order = Math.max(100, ...sceneBindings.value.map((item) => Number(item.sort_order || 0) + 10), 100);
  sceneForm.hide_aspect_ratio = false;
  sceneForm.hide_resolution = false;
  sceneForm.hide_custom_size = true;
  sceneForm.custom_size_min = 256;
  sceneForm.custom_size_max = 4096;
  sceneForm.custom_size_step = 8;
  sceneForm.api_config_id = null;
  sceneForm.backup_api_config_id = null;
  sceneForm.display_name = "";
  sceneForm.subtitle = "";
  sceneForm.credit_cost = 4;
  sceneForm.max_reference_images = 0;
  sceneForm.aspect_ratio_options_json = DEFAULT_ASPECT_RATIO_OPTIONS_JSON;
  sceneForm.image_size_options_json = DEFAULT_IMAGE_SIZE_OPTIONS_JSON;
  sceneForm.custom_size_options_json = DEFAULT_CUSTOM_SIZE_OPTIONS_JSON;
  sceneForm.resolution_mapping_json = DEFAULT_RESOLUTION_MAPPING_JSON;
  sceneForm.resolution_credit_costs_json = DEFAULT_RESOLUTION_CREDIT_COSTS_JSON;
}

function buildCopiedSceneLabel(sourceLabel: string) {
  const trimmed = sourceLabel.trim() || "未命名场景";
  const existingLabels = new Set(sceneBindings.value.map((item) => item.scene_label.trim()));
  const baseLabel = `${trimmed}（副本）`;
  if (!existingLabels.has(baseLabel)) return baseLabel;

  let index = 2;
  while (existingLabels.has(`${trimmed}（副本${index}）`)) {
    index += 1;
  }
  return `${trimmed}（副本${index}）`;
}

function buildCopiedSceneKey(sourceKey: string) {
  const normalized = sourceKey.trim().toLowerCase() || "scene";
  const existingKeys = new Set(sceneBindings.value.map((item) => item.scene_key.trim().toLowerCase()));
  const baseKey = `${normalized}_copy`;
  if (!existingKeys.has(baseKey)) return baseKey;

  let index = 2;
  while (existingKeys.has(`${normalized}_copy_${index}`)) {
    index += 1;
  }
  return `${normalized}_copy_${index}`;
}

function isCopyableSceneType(
  sceneType: ExternalApiSceneType
): sceneType is Extract<ExternalApiSceneType, "generate" | "image_edit"> {
  return sceneType === "generate" || sceneType === "image_edit";
}

function canCopyScene(record: ExternalApiSceneBinding) {
  return isCopyableSceneType(record.scene_type);
}

function fillSceneMetaForm(record: ExternalApiSceneBinding) {
  sceneEditingKey.value = record.scene_key;
  sceneImportJson.value = "";
  sceneMetaForm.scene_key = record.scene_key;
  sceneMetaForm.scene_label = record.scene_label || "";
  sceneMetaForm.scene_description = record.scene_description || "";
  sceneMetaForm.sort_order = Number(record.sort_order || 0);
  sceneMetaForm.hide_aspect_ratio = !!record.hide_aspect_ratio;
  sceneMetaForm.hide_resolution = !!record.hide_resolution;
  sceneMetaForm.hide_custom_size = !!record.hide_custom_size;
  sceneMetaForm.custom_size_min = Number(record.custom_size_min || 256);
  sceneMetaForm.custom_size_max = Number(record.custom_size_max || 4096);
  sceneMetaForm.custom_size_step = Number(record.custom_size_step || 8);
  sceneMetaForm.max_reference_images = Number(record.max_reference_images || 0);
  sceneMetaForm.aspect_ratio_options_json = record.aspect_ratio_options_json || DEFAULT_ASPECT_RATIO_OPTIONS_JSON;
  sceneMetaForm.image_size_options_json = record.image_size_options_json || DEFAULT_IMAGE_SIZE_OPTIONS_JSON;
  sceneMetaForm.custom_size_options_json = record.custom_size_options_json || DEFAULT_CUSTOM_SIZE_OPTIONS_JSON;
  sceneMetaForm.resolution_mapping_json = record.resolution_mapping_json || DEFAULT_RESOLUTION_MAPPING_JSON;
  sceneMetaForm.resolution_credit_costs_json = record.resolution_credit_costs_json || DEFAULT_RESOLUTION_CREDIT_COSTS_JSON;
}

watch(
  () => sceneForm.scene_type,
  (sceneType, previousType) => {
    if (sceneType === previousType) return;
    if (sceneType === "image_edit" && Number(sceneForm.max_reference_images || 0) <= 0) {
      sceneForm.max_reference_images = DEFAULT_IMAGE_EDIT_MAX_REFERENCE_IMAGES;
    }
    if (sceneType === "generate" && Number(sceneForm.max_reference_images || 0) === DEFAULT_IMAGE_EDIT_MAX_REFERENCE_IMAGES) {
      sceneForm.max_reference_images = 0;
    }
  }
);

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
      const optionLabel = String((item as Record<string, unknown>).label ?? "").trim();
      const optionValue = String((item as Record<string, unknown>).value ?? "").trim();
      if (!optionLabel || !optionValue) {
        message.warning(`${label}第 ${index + 1} 项必须包含非空 label 和 value`);
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
    for (const [aspectRatio, resolutionMap] of Object.entries(parsed as Record<string, unknown>)) {
      if (!String(aspectRatio).trim()) {
        message.warning(`${label}的宽高比键不能为空`);
        return false;
      }
      if (!resolutionMap || Array.isArray(resolutionMap) || typeof resolutionMap !== "object") {
        message.warning(`${label}中 ${aspectRatio} 的值必须是对象`);
        return false;
      }
      for (const [imageSize, mappedResolution] of Object.entries(resolutionMap as Record<string, unknown>)) {
        if (!String(imageSize).trim() || !String(mappedResolution ?? "").trim()) {
          message.warning(`${label}中 ${aspectRatio} 的分辨率键和值不能为空`);
          return false;
        }
      }
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
    for (const [resolution, creditCost] of Object.entries(parsed as Record<string, unknown>)) {
      if (!String(resolution).trim()) {
        message.warning(`${label}的分辨率键不能为空`);
        return false;
      }
      if (typeof creditCost === "boolean" || !Number.isInteger(Number(creditCost))) {
        message.warning(`${label}中 ${resolution} 的积分消耗必须是整数`);
        return false;
      }
      if (Number(creditCost) < 0) {
        message.warning(`${label}中 ${resolution} 的积分消耗不能小于 0`);
        return false;
      }
    }
    return true;
  } catch {
    message.warning(`${label}不是合法的 JSON`);
    return false;
  }
}

async function load() {
  loading.value = true;
  try {
    const [configRows, bindingRows] = await Promise.all([
      listExternalApiConfigs(),
      listExternalApiSceneBindings(),
    ]);
    configs.value = configRows;
    sceneBindings.value = bindingRows;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取接口管理数据失败");
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function openCreate() {
  resetForm();
  modalOpen.value = true;
}

function openCreateScene() {
  resetSceneForm();
  sceneModalOpen.value = true;
}

function openCopyScene(record: ExternalApiSceneBinding) {
  if (!isCopyableSceneType(record.scene_type)) return;
  resetSceneForm();
  isSceneCopyMode.value = true;
  sceneForm.scene_key = buildCopiedSceneKey(record.scene_key);
  sceneForm.scene_type = record.scene_type;
  sceneForm.scene_label = buildCopiedSceneLabel(record.scene_label);
  sceneForm.scene_description = record.scene_description || "";
  sceneForm.sort_order = Number(record.sort_order || 0) + 10;
  sceneForm.hide_aspect_ratio = !!record.hide_aspect_ratio;
  sceneForm.hide_resolution = !!record.hide_resolution;
  sceneForm.hide_custom_size = !!record.hide_custom_size;
  sceneForm.custom_size_min = Number(record.custom_size_min || 256);
  sceneForm.custom_size_max = Number(record.custom_size_max || 4096);
  sceneForm.custom_size_step = Number(record.custom_size_step || 8);
  sceneForm.api_config_id = record.api_config_id ?? null;
  sceneForm.backup_api_config_id = record.backup_api_config_id ?? null;
  sceneForm.display_name = record.display_name || "";
  sceneForm.subtitle = record.subtitle || "";
  sceneForm.credit_cost = Number(record.credit_cost || 0);
  sceneForm.max_reference_images = Number(record.max_reference_images || 0);
  sceneForm.aspect_ratio_options_json = record.aspect_ratio_options_json || DEFAULT_ASPECT_RATIO_OPTIONS_JSON;
  sceneForm.image_size_options_json = record.image_size_options_json || DEFAULT_IMAGE_SIZE_OPTIONS_JSON;
  sceneForm.custom_size_options_json = record.custom_size_options_json || DEFAULT_CUSTOM_SIZE_OPTIONS_JSON;
  sceneForm.resolution_mapping_json = record.resolution_mapping_json || DEFAULT_RESOLUTION_MAPPING_JSON;
  sceneForm.resolution_credit_costs_json = record.resolution_credit_costs_json || DEFAULT_RESOLUTION_CREDIT_COSTS_JSON;
  sceneModalOpen.value = true;
}

function openEditSceneMeta(record: ExternalApiSceneBinding) {
  fillSceneMetaForm(record);
  sceneMetaModalOpen.value = true;
}

function isSceneUnbound(record: ExternalApiSceneBinding) {
  return !record.api_config_id;
}

function sceneRowClassName(record: ExternalApiSceneBinding) {
  return isSceneUnbound(record) ? "is-unbound-scene" : "";
}

function openEditCopy(record: ExternalApiSceneBinding) {
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

function openEdit(item: ExternalApiConfig) {
  fillForm(item);
  modalOpen.value = true;
}

function openCopy(item: ExternalApiConfig) {
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
  form.result_base64_field = item.result_base64_field || "";
  form.call_mode = item.call_mode || "sync";
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
  form.poll_result_base64_field = item.poll_result_base64_field || "";
  form.poll_result_url_field = item.poll_result_url_field || "";
  form.poll_interval_seconds = Number(item.poll_interval_seconds || 5);
  form.poll_timeout_seconds = Number(item.poll_timeout_seconds || 600);
  form.status = item.status;
  modalOpen.value = true;
}

function buildConfigTemplateData(item: ExternalApiConfig): ExternalApiConfigPayload {
  return {
    name: item.name,
    description: item.description || "",
    group_name: item.group_name || "默认",
    request_url: item.request_url,
    request_format: item.request_format || "json",
    headers_json: item.headers_json,
    payload_json: item.payload_json,
    response_json: item.response_json || "{\n\n}",
    result_base64_field: item.result_base64_field || "",
    call_mode: item.call_mode || "sync",
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
    poll_result_base64_field: item.poll_result_base64_field || "",
    poll_result_url_field: item.poll_result_url_field || "",
    poll_interval_seconds: Number(item.poll_interval_seconds || 5),
    poll_timeout_seconds: Number(item.poll_timeout_seconds || 600),
    status: item.status,
  };
}

function buildSceneTemplateData(record: ExternalApiSceneBinding): ExternalApiSceneBindingCreatePayload {
  if (!isCopyableSceneType(record.scene_type)) {
    throw new Error("当前场景类型暂不支持导出为新增模板");
  }
  return {
    scene_key: record.scene_key,
    scene_type: record.scene_type,
    scene_label: record.scene_label,
    scene_description: record.scene_description || "",
    sort_order: Number(record.sort_order || 0),
    hide_aspect_ratio: !!record.hide_aspect_ratio,
    hide_resolution: !!record.hide_resolution,
    hide_custom_size: !!record.hide_custom_size,
    custom_size_min: Number(record.custom_size_min || 256),
    custom_size_max: Number(record.custom_size_max || 4096),
    custom_size_step: Number(record.custom_size_step || 8),
    api_config_id: record.api_config_id ?? null,
    backup_api_config_id: record.backup_api_config_id ?? null,
    display_name: record.display_name || "",
    subtitle: record.subtitle || "",
    credit_cost: Number(record.credit_cost || 0),
    max_reference_images: Number(record.max_reference_images || 0),
    aspect_ratio_options_json: record.aspect_ratio_options_json || DEFAULT_ASPECT_RATIO_OPTIONS_JSON,
    image_size_options_json: record.image_size_options_json || DEFAULT_IMAGE_SIZE_OPTIONS_JSON,
    custom_size_options_json: record.custom_size_options_json || DEFAULT_CUSTOM_SIZE_OPTIONS_JSON,
    resolution_mapping_json: record.resolution_mapping_json || DEFAULT_RESOLUTION_MAPPING_JSON,
    resolution_credit_costs_json: record.resolution_credit_costs_json || DEFAULT_RESOLUTION_CREDIT_COSTS_JSON,
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

function handleCopyConfigJson(item: ExternalApiConfig) {
  const template = stringifyAdminConfigTemplate("image-api-config", buildConfigTemplateData(item));
  copyTemplateJson(template, "接口配置 JSON 已复制");
}

function handleCopySceneJson(record: ExternalApiSceneBinding) {
  if (!canCopyScene(record)) return;
  try {
    const template = stringifyAdminConfigTemplate("image-scene-binding", buildSceneTemplateData(record));
    copyTemplateJson(template, "场景绑定 JSON 已复制");
  } catch (err: any) {
    message.error(err?.message || "生成场景 JSON 失败");
  }
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
  form.result_base64_field = normalizeStringValue(data.result_base64_field, form.result_base64_field);
  form.call_mode = data.call_mode === "async" ? "async" : "sync";
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
  form.poll_result_base64_field = normalizeStringValue(data.poll_result_base64_field, form.poll_result_base64_field);
  form.poll_result_url_field = normalizeStringValue(data.poll_result_url_field, form.poll_result_url_field);
  form.poll_interval_seconds = normalizeNumberValue(data.poll_interval_seconds, form.poll_interval_seconds);
  form.poll_timeout_seconds = normalizeNumberValue(data.poll_timeout_seconds, form.poll_timeout_seconds);
  form.status = data.status === "disabled" ? "disabled" : "enabled";
}

function handleApplyConfigImportJson() {
  if (!configImportJson.value.trim()) {
    message.warning("请先粘贴接口配置 JSON");
    return;
  }
  try {
    const parsed = parseAdminConfigTemplate(configImportJson.value);
    if (parsed.kind !== "image-api-config") {
      message.warning("这段 JSON 不是生图接口配置模板");
      return;
    }
    applyImportedConfigData(parsed.data);
    message.success("已识别并回填接口配置");
  } catch (err: any) {
    message.error(err?.message || "识别接口配置 JSON 失败");
  }
}

function applyImportedSceneData(data: Record<string, unknown>) {
  const sceneType = data.scene_type;
  if (sceneType !== "generate" && sceneType !== "image_edit") {
    throw new Error("当前仅支持回填文生图或图编辑场景模板");
  }
  sceneForm.scene_key = normalizeStringValue(data.scene_key, sceneForm.scene_key);
  sceneForm.scene_type = sceneType;
  sceneForm.scene_label = normalizeStringValue(data.scene_label, sceneForm.scene_label);
  sceneForm.scene_description = normalizeStringValue(data.scene_description, sceneForm.scene_description);
  sceneForm.sort_order = normalizeNumberValue(data.sort_order, sceneForm.sort_order);
  sceneForm.hide_aspect_ratio = normalizeBooleanValue(data.hide_aspect_ratio, sceneForm.hide_aspect_ratio);
  sceneForm.hide_resolution = normalizeBooleanValue(data.hide_resolution, sceneForm.hide_resolution);
  sceneForm.hide_custom_size = normalizeBooleanValue(data.hide_custom_size, sceneForm.hide_custom_size);
  sceneForm.custom_size_min = normalizeNumberValue(data.custom_size_min, sceneForm.custom_size_min);
  sceneForm.custom_size_max = normalizeNumberValue(data.custom_size_max, sceneForm.custom_size_max);
  sceneForm.custom_size_step = normalizeNumberValue(data.custom_size_step, sceneForm.custom_size_step);
  sceneForm.api_config_id = normalizeNullableNumberValue(data.api_config_id);
  sceneForm.backup_api_config_id = normalizeNullableNumberValue(data.backup_api_config_id);
  sceneForm.display_name = normalizeStringValue(data.display_name, sceneForm.display_name);
  sceneForm.subtitle = normalizeStringValue(data.subtitle, sceneForm.subtitle);
  sceneForm.credit_cost = normalizeNumberValue(data.credit_cost, sceneForm.credit_cost);
  sceneForm.max_reference_images = normalizeNumberValue(data.max_reference_images, sceneForm.max_reference_images);
  sceneForm.aspect_ratio_options_json = normalizeJsonFieldValue(data.aspect_ratio_options_json, sceneForm.aspect_ratio_options_json);
  sceneForm.image_size_options_json = normalizeJsonFieldValue(data.image_size_options_json, sceneForm.image_size_options_json);
  sceneForm.custom_size_options_json = normalizeJsonFieldValue(data.custom_size_options_json, sceneForm.custom_size_options_json);
  sceneForm.resolution_mapping_json = normalizeJsonFieldValue(data.resolution_mapping_json, sceneForm.resolution_mapping_json);
  sceneForm.resolution_credit_costs_json = normalizeJsonFieldValue(data.resolution_credit_costs_json, sceneForm.resolution_credit_costs_json);
}

function handleApplySceneImportJson() {
  if (!sceneImportJson.value.trim()) {
    message.warning("请先粘贴场景绑定 JSON");
    return;
  }
  try {
    const parsed = parseAdminConfigTemplate(sceneImportJson.value);
    if (parsed.kind !== "image-scene-binding") {
      message.warning("这段 JSON 不是生图场景绑定模板");
      return;
    }
    applyImportedSceneData(parsed.data);
    message.success("已识别并回填场景绑定");
  } catch (err: any) {
    message.error(err?.message || "识别场景绑定 JSON 失败");
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

  if (form.call_mode === "async") {
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
    if (!form.poll_result_base64_field.trim() && !form.poll_result_url_field.trim()) {
      message.warning("异步接口至少需要填写轮询结果 Base64 路径或结果 URL 路径");
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
  }

  return true;
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

function buildPayload(): ExternalApiConfigPayload {
  return {
    name: form.name.trim(),
    description: form.description.trim(),
    group_name: form.group_name.trim() || "默认",
    request_url: form.request_url.trim(),
    request_format: form.request_format,
    headers_json: form.headers_json,
    payload_json: form.payload_json,
    response_json: form.response_json,
    result_base64_field: form.result_base64_field.trim(),
    call_mode: form.call_mode,
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
    poll_result_base64_field: form.poll_result_base64_field.trim(),
    poll_result_url_field: form.poll_result_url_field.trim(),
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
      await updateExternalApiConfig(editingId.value, payload);
      message.success("接口配置更新成功");
    } else {
      await createExternalApiConfig(payload);
      message.success("接口配置创建成功");
    }
    modalOpen.value = false;
    resetForm();
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "保存失败");
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
    const result = await testExternalApiConfig(buildPayload());
    showTestResult(result);
  } catch (err: any) {
    message.error(err.response?.data?.detail || "测试连接失败");
  } finally {
    testing.value = false;
  }
}

function showTestResult(result: ExternalApiConfigTestResult) {
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

function handleToggleStatus(item: ExternalApiConfig) {
  const nextStatus = item.status === "enabled" ? "disabled" : "enabled";
  Modal.confirm({
    title: nextStatus === "enabled" ? "启用该接口配置？" : "停用该接口配置？",
    centered: true,
    onOk: async () => {
      try {
        await updateExternalApiConfigStatus(item.id, nextStatus);
        message.success(nextStatus === "enabled" ? "已启用" : "已停用");
        await load();
      } catch (err: any) {
        message.error(err.response?.data?.detail || "更新状态失败");
      }
    },
  });
}

function handleDeleteConfig(item: ExternalApiConfig) {
  Modal.confirm({
    title: "删除该接口配置？",
    content: "删除后会同时解除所有引用它的场景绑定，场景会保留但变成未绑定状态。",
    centered: true,
    okButtonProps: { danger: true },
    onOk: async () => {
      try {
        await deleteExternalApiConfig(item.id);
        message.success("接口配置已删除");
        await load();
      } catch (err: any) {
        Modal.warning({
          title: "无法删除该接口",
          content: err.response?.data?.detail || "删除接口配置失败",
          centered: true,
        });
      }
    },
  });
}

async function handleBindingChange(
  sceneKey: ExternalApiSceneBinding["scene_key"],
  payload: {
    api_config_id: number | null;
    backup_api_config_id: number | null;
    credit_cost: number;
    resolution_credit_costs_json: string;
    display_name: string;
    subtitle: string;
  },
) {
  bindingSavingKey.value = sceneKey;
  try {
    await updateExternalApiSceneBinding(sceneKey, payload);
    message.success("场景绑定已更新");
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "更新绑定失败");
  } finally {
    bindingSavingKey.value = "";
  }
}

function canSwapBinding(record: ExternalApiSceneBinding) {
  const primaryId = record.api_config_id ?? null;
  const backupId = record.backup_api_config_id ?? null;
  return primaryId !== backupId && (primaryId != null || backupId != null);
}

function handleSwapBinding(record: ExternalApiSceneBinding) {
  if (!canSwapBinding(record)) {
    message.warning("请先绑定主接口或备用接口后再互换");
    return;
  }
  void handleBindingChange(record.scene_key, buildBindingPayload(record, {
    api_config_id: record.backup_api_config_id ?? null,
    backup_api_config_id: record.api_config_id ?? null,
  }));
}

function buildBindingPayload(record: ExternalApiSceneBinding, overrides: Partial<{
  api_config_id: number | null;
  backup_api_config_id: number | null;
  credit_cost: number;
  resolution_credit_costs_json: string;
  display_name: string;
  subtitle: string;
}> = {}) {
  return {
    api_config_id: overrides.api_config_id !== undefined ? overrides.api_config_id : (record.api_config_id ?? null),
    backup_api_config_id: overrides.backup_api_config_id !== undefined ? overrides.backup_api_config_id : (record.backup_api_config_id ?? null),
    credit_cost: overrides.credit_cost ?? record.credit_cost,
    resolution_credit_costs_json: overrides.resolution_credit_costs_json ?? record.resolution_credit_costs_json ?? DEFAULT_RESOLUTION_CREDIT_COSTS_JSON,
    display_name: overrides.display_name ?? record.display_name ?? "",
    subtitle: overrides.subtitle ?? record.subtitle ?? "",
  };
}

function validateCustomSizeLimits(form: { custom_size_min: number; custom_size_max: number; custom_size_step: number }) {
  const minimum = Number(form.custom_size_min);
  const maximum = Number(form.custom_size_max);
  const step = Number(form.custom_size_step);
  if (!Number.isInteger(minimum) || minimum <= 0 || !Number.isInteger(maximum) || maximum < minimum) {
    message.warning("自定义分辨率范围配置不正确");
    return false;
  }
  if (!Number.isInteger(step) || step <= 0) {
    message.warning("自定义分辨率步长必须是正整数");
    return false;
  }
  return true;
}

function setSceneSupportsCustomSize(checked: boolean) {
  sceneForm.hide_custom_size = !checked;
}

function setSceneMetaSupportsCustomSize(checked: boolean) {
  sceneMetaForm.hide_custom_size = !checked;
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
  if (!validateCustomSizeLimits(sceneForm)) return;
  if (!validateSceneOptionsJson(sceneForm.aspect_ratio_options_json, "宽高比选项 JSON")) return;
  if (!validateSceneOptionsJson(sceneForm.image_size_options_json, "生图质量选项 JSON")) return;
  if (!validateSceneOptionsJson(sceneForm.custom_size_options_json, "自定义分辨率选项 JSON")) return;
  if (!validateResolutionMappingJson(sceneForm.resolution_mapping_json, "分辨率映射 JSON")) return;
  if (!validateResolutionCreditCostsJson(sceneForm.resolution_credit_costs_json, "分辨率积分 JSON")) return;

  bindingCreating.value = true;
  try {
    await createExternalApiSceneBinding({
      scene_key: sceneForm.scene_key.trim().toLowerCase(),
      scene_type: sceneForm.scene_type,
      scene_label: sceneForm.scene_label.trim(),
      scene_description: sceneForm.scene_description.trim(),
      sort_order: Number(sceneForm.sort_order || 0),
      hide_aspect_ratio: !!sceneForm.hide_aspect_ratio,
      hide_resolution: !!sceneForm.hide_resolution,
      hide_custom_size: !!sceneForm.hide_custom_size,
      custom_size_min: Number(sceneForm.custom_size_min),
      custom_size_max: Number(sceneForm.custom_size_max),
      custom_size_step: Number(sceneForm.custom_size_step),
      api_config_id: sceneForm.api_config_id ?? null,
      backup_api_config_id: sceneForm.backup_api_config_id ?? null,
      display_name: sceneForm.display_name.trim(),
      subtitle: sceneForm.subtitle.trim(),
      credit_cost: Number(sceneForm.credit_cost || 0),
      max_reference_images: Number(sceneForm.max_reference_images || 0),
      aspect_ratio_options_json: sceneForm.aspect_ratio_options_json,
      image_size_options_json: sceneForm.image_size_options_json,
      custom_size_options_json: sceneForm.custom_size_options_json,
      resolution_mapping_json: sceneForm.resolution_mapping_json,
      resolution_credit_costs_json: sceneForm.resolution_credit_costs_json,
    });
    message.success("场景创建成功");
    sceneModalOpen.value = false;
    resetSceneForm();
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "创建场景失败");
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
  if (!validateCustomSizeLimits(sceneMetaForm)) return;
  if (!validateSceneOptionsJson(sceneMetaForm.aspect_ratio_options_json, "宽高比选项 JSON")) return;
  if (!validateSceneOptionsJson(sceneMetaForm.image_size_options_json, "生图质量选项 JSON")) return;
  if (!validateSceneOptionsJson(sceneMetaForm.custom_size_options_json, "自定义分辨率选项 JSON")) return;
  if (!validateResolutionMappingJson(sceneMetaForm.resolution_mapping_json, "分辨率映射 JSON")) return;
  if (!validateResolutionCreditCostsJson(sceneMetaForm.resolution_credit_costs_json, "分辨率积分 JSON")) return;

  sceneMetaSaving.value = true;
  try {
    await updateExternalApiSceneBindingMeta(sceneEditingKey.value, {
      scene_key: sceneMetaForm.scene_key.trim().toLowerCase(),
      scene_label: sceneMetaForm.scene_label.trim(),
      scene_description: sceneMetaForm.scene_description.trim(),
      sort_order: Number(sceneMetaForm.sort_order || 0),
      hide_aspect_ratio: !!sceneMetaForm.hide_aspect_ratio,
      hide_resolution: !!sceneMetaForm.hide_resolution,
      hide_custom_size: !!sceneMetaForm.hide_custom_size,
      custom_size_min: Number(sceneMetaForm.custom_size_min),
      custom_size_max: Number(sceneMetaForm.custom_size_max),
      custom_size_step: Number(sceneMetaForm.custom_size_step),
      max_reference_images: Number(sceneMetaForm.max_reference_images || 0),
      aspect_ratio_options_json: sceneMetaForm.aspect_ratio_options_json,
      image_size_options_json: sceneMetaForm.image_size_options_json,
      custom_size_options_json: sceneMetaForm.custom_size_options_json,
      resolution_mapping_json: sceneMetaForm.resolution_mapping_json,
      resolution_credit_costs_json: sceneMetaForm.resolution_credit_costs_json,
    });
    message.success("场景基础信息已更新");
    sceneMetaModalOpen.value = false;
    sceneEditingKey.value = "";
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "更新场景失败");
  } finally {
    sceneMetaSaving.value = false;
  }
}

function handleToggleSceneStatus(record: ExternalApiSceneBinding) {
  const nextStatus = record.status === "enabled" ? "disabled" : "enabled";
  Modal.confirm({
    title: nextStatus === "enabled" ? "启用该自定义场景？" : "停用该自定义场景？",
    centered: true,
    onOk: async () => {
      try {
        await updateExternalApiSceneBindingStatus(record.scene_key, nextStatus);
        message.success(nextStatus === "enabled" ? "场景已启用" : "场景已停用");
        await load();
      } catch (err: any) {
        message.error(err.response?.data?.detail || "更新场景状态失败");
      }
    },
  });
}

function handleDeleteScene(record: ExternalApiSceneBinding) {
  Modal.confirm({
    title: "删除该自定义场景？",
    content: "删除后将不再出现在模型选择中，且无法恢复。",
    centered: true,
    okButtonProps: { danger: true },
    onOk: async () => {
      try {
        await deleteExternalApiSceneBinding(record.scene_key);
        message.success("场景已删除");
        await load();
      } catch (err: any) {
        message.error(err.response?.data?.detail || "删除场景失败");
      }
    },
  });
}

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
            <a-input
              v-model:value="configNameFilter"
              class="warm-input"
              allow-clear
              placeholder="按名称筛选"
              style="width: 180px"
            />
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
                            {{ sceneTypeLabel(scene.scene_type) }} · {{ configUsageRoleLabel(scene.roles) }}
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
            <a-input
              v-model:value="bindingNameFilter"
              class="warm-input"
              allow-clear
              placeholder="按名称筛选"
              style="width: 180px"
            />
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
              v-model:value="bindingSceneTypeFilter"
              class="warm-select"
              show-search
              option-filter-prop="label"
              placeholder="筛选场景类型"
              style="width: 180px"
            >
              <a-select-option value="all" label="全部类型">全部类型</a-select-option>
              <a-select-option value="generate" label="文生图">文生图</a-select-option>
              <a-select-option value="image_edit" label="图编辑">图编辑</a-select-option>
              <a-select-option value="prompt_reverse" label="提示词反推">提示词反推</a-select-option>
              <a-select-option value="prompt_optimize" label="提示词优化">提示词优化</a-select-option>
              <a-select-option value="inpaint" label="局部重绘">局部重绘</a-select-option>
              <a-select-option value="smart_cutout" label="智能抠图">智能抠图</a-select-option>
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
          message="按场景类型分组。主接口分组只过滤列表，不会限制可选接口。显示文案请用行内菜单编辑。"
          style="margin-bottom: 16px"
        />

        <a-spin :spinning="loading">
          <a-empty v-if="!groupedSceneBindings.length" description="没有匹配的场景" />
          <div v-else class="scene-binding-groups">
            <section v-for="block in groupedSceneBindings" :key="block.sceneType" class="scene-binding-group">
              <div class="api-config-group-title">
                <span>{{ sceneTypeLabel(block.sceneType) }}</span>
                <span class="api-config-group-count">{{ block.items.length }} 个场景</span>
              </div>
              <a-table
                row-key="scene_key"
                :columns="bindingColumns"
                :data-source="block.items"
                :pagination="false"
                table-layout="fixed"
                :scroll="{ x: 1316 }"
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
                      <a-select-option :value="EMPTY_BACKUP_API_OPTION" label="无">
                        无
                      </a-select-option>
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
                      <a-input-number
                        :value="record.credit_cost"
                        class="warm-input-number"
                        :min="0"
                        :precision="0"
                        :disabled="bindingSavingKey === record.scene_key"
                        @change="(value: number | null) => handleBindingChange(record.scene_key, buildBindingPayload(record, { credit_cost: Number(value ?? 0) }))"
                      />
                      <span class="credit-unit">积分</span>
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
                          <a-menu-item v-if="canCopyScene(record)" key="copy-scene" @click="openCopyScene(record)">复制新增</a-menu-item>
                          <a-menu-item v-if="canCopyScene(record)" key="copy-json" @click="handleCopySceneJson(record)">复制 JSON</a-menu-item>
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

      <a-card title="占位符用法" class="warm-card api-card motion-fade-up motion-card-lift" style="--motion-delay: 280ms">
        <a-collapse class="warm-collapse">
          <a-collapse-panel key="common" header="通用占位符">
            <div class="doc-block">
              <div>可用于 Header JSON 或 请求 JSON：</div>
              <pre v-pre>{{ api_key }}</pre>
              <pre v-pre>{{ bearer_token }}</pre>
              <pre v-pre>{{ prompt }}</pre>
              <pre v-pre>{{ aspect_ratio }}</pre>
              <pre v-pre>{{ image_size }}</pre>
              <pre v-pre>{{ custom_size }}</pre>
              <pre v-pre>{{ mapped_resolution }}</pre>
              <pre v-pre>{{ resolved_resolution }}</pre>
              <pre v-pre>{{ mode }}</pre>
            </div>
          </a-collapse-panel>
          <a-collapse-panel key="image" header="图片生成相关">
            <div class="doc-block">
              <div>用于文生图或图编辑接口：</div>
              <pre v-pre>{{ contents_parts }}</pre>
              <pre v-pre>{{ generation_config }}</pre>
              <pre v-pre>{{ reference_image_1 }}</pre>
              <pre v-pre>{{ reference_image_1_url }}</pre>
              <pre v-pre>{{ reference_image_1_base64 }}</pre>
              <pre v-pre>{{ reference_image_1_mime_type }}</pre>
              <pre v-pre>{{ reference_image_1_data_url }}</pre>
              <pre v-pre>{{ reference_image_2 }}</pre>
              <pre v-pre>{{ reference_image_2_url }}</pre>
              <pre v-pre>{{ reference_image_3 }}</pre>
              <pre v-pre>{{ reference_image_3_url }}</pre>
              <pre v-pre>{{ source_image_url }}</pre>
              <pre v-pre>{{ reference_image_count }}</pre>
              <div class="scene-desc">
                图编辑场景会按“最大参考图张数”限制上传与请求回填数量。支持多少张，就会尝试回填多少个
                <code v-pre>{{ reference_image_N }}</code>
                占位符；超出的图片不会进入请求。旧模板仍可继续使用
                <code v-pre>{{ contents_parts }}</code>
                兼容现有 Gemini 风格请求体。
              </div>
              <div class="scene-desc" style="margin-top: 8px">
                当某个精确占位符不存在时，例如
                <code v-pre>{{ reference_image_6_base64 }}</code>
                ，系统会自动移除当前对象或数组项，适合按上传张数动态裁剪
                <code>image</code>
                列表。
              </div>
              <div class="scene-desc" style="margin-top: 8px">
                其中
                <code v-pre>{{ reference_image_1 }}</code>
                是内联对象，
                <code v-pre>{{ reference_image_1_url }}</code>
                是图片公网 URL，
                <code v-pre>{{ reference_image_1_base64 }}</code>
                是纯 base64，
                <code v-pre>{{ reference_image_1_data_url }}</code>
                是
                <code>data:image/...;base64,...</code>
                格式。若第三方接口要求传 URL，请使用
                <code v-pre>{{ reference_image_1_url }}</code>
                或
                <code v-pre>{{ source_image_url }}</code>
                ，不要使用
                <code v-pre>{{ reference_image_1 }}</code>
                /
                <code v-pre>{{ reference_image_1_data_url }}</code>
                。
              </div>
              <div class="scene-desc" style="margin-top: 8px">例如：</div>
              <pre v-pre>{
  "input": {
    "image": "{{ reference_image_1 }}",
    "style": "{{ reference_image_2 }}",
    "referenceCount": "{{ reference_image_count }}"
  }
}</pre>
              <pre v-pre>{
  "image": [
    {
      "b64_json": "{{ reference_image_1_base64 }}"
    }
  ]
}</pre>
              <pre v-pre>{
  "images": [
    "{{ reference_image_1_url }}?imageMogr2/format/webp",
    "{{ reference_image_2_url }}?imageMogr2/format/webp"
  ],
  "source": "{{ source_image_url }}"
}</pre>
              <div class="scene-desc">
                宽高比、生图质量、自定义分辨率选项请在场景表单中用 JSON 数组维护，系统会把对应 value 传入
                <code v-pre>{{ aspect_ratio }}</code>
                /
                <code v-pre>{{ image_size }}</code>
                /
                <code v-pre>{{ custom_size }}</code>
                。
              </div>
              <div class="scene-desc" style="margin-top: 8px">
                如果第三方只接受一个分辨率参数，可在场景表单维护“分辨率映射 JSON”，系统会按
                <code v-pre>{{ aspect_ratio }}</code>
                +
                <code v-pre>{{ image_size }}</code>
                输出
                <code v-pre>{{ mapped_resolution }}</code>
                。
              </div>
              <div class="scene-desc" style="margin-top: 8px">
                未开启自定义分辨率时继续使用 <code v-pre>{{ mapped_resolution }}</code> 即可，原有接口不用改。
                只有开启自定义后，才需要改成 <code v-pre>{{ resolved_resolution }}</code>（有手动宽高用手动宽高，否则回退映射分辨率）。
              </div>
            </div>
          </a-collapse-panel>
          <a-collapse-panel key="reverse" header="提示词反推相关">
            <div class="doc-block">
              <div>用于反推接口：</div>
              <pre v-pre>{{ image_data_url }}</pre>
              <pre v-pre>{{ prompt_reverse_text }}</pre>
            </div>
          </a-collapse-panel>
          <a-collapse-panel key="optimize" header="提示词优化相关">
            <div class="doc-block">
              <div>用于提示词优化接口：</div>
              <pre v-pre>{{ prompt }}</pre>
              <pre v-pre>{{ prompt_optimize_text }}</pre>
              <pre v-pre>{{ prompt_optimize_style_prompt }}</pre>
              <pre v-pre>{{ reference_images }}</pre>
              <pre v-pre>{{ reference_image_1_url }}</pre>
              <pre v-pre>{{ reference_image_1_data_url }}</pre>
              <pre v-pre>{{ reference_image_1_base64 }}</pre>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </a-card>
    </a-space>

    <a-modal
      v-model:open="sceneModalOpen"
      :title="sceneModalTitle"
      :mask-closable="false"
      :width="720"
      @ok="handleCreateScene"
    >
      <a-form layout="vertical">
        <a-form-item label="粘贴场景绑定 JSON 回填">
          <a-textarea
            v-model:value="sceneImportJson"
            :rows="6"
            allow-clear
            class="warm-input"
            placeholder="粘贴从“复制 JSON”得到的场景绑定模板，可自动识别并回填下面的字段"
          />
          <div style="display: flex; justify-content: flex-end; margin-top: 8px">
            <a-button class="api-secondary-btn" @click="handleApplySceneImportJson">识别并回填</a-button>
          </div>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="场景标识" required>
              <a-input v-model:value="sceneForm.scene_key" class="warm-input" placeholder="例如：banana_ultra" />
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
              <a-input v-model:value="sceneForm.scene_label" class="warm-input" placeholder="例如：80AI Ultra" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="消耗积分">
              <a-input-number v-model:value="sceneForm.credit_cost" class="warm-input-number" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="最大参考图张数">
          <a-input-number v-model:value="sceneForm.max_reference_images" class="warm-input-number" :min="0" style="width: 100%" />
          <div class="scene-desc" style="margin-top: 6px">
            仅图编辑场景生效；前端最多允许上传这么多张参考图，并回填对应数量的
            <code v-pre>{{ reference_image_1 }}</code>
            到
            <code v-pre>{{ reference_image_N }}</code>
            占位符，以及对应的
            <code v-pre>{{ reference_image_1_url }}</code>
            /
            <code v-pre>{{ reference_image_1_base64 }}</code>
            /
            <code v-pre>{{ reference_image_1_data_url }}</code>
            变体。文生图场景可填 `0`。
          </div>
        </a-form-item>

        <a-form-item label="场景类型" required>
          <a-radio-group v-model:value="sceneForm.scene_type" class="warm-radio-group" button-style="solid">
            <a-radio-button value="generate">文生图</a-radio-button>
            <a-radio-button value="image_edit">图编辑</a-radio-button>
          </a-radio-group>
        </a-form-item>

        <a-form-item label="场景描述">
          <a-input v-model:value="sceneForm.scene_description" class="warm-input" placeholder="例如：高质量增强版" />
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
            placeholder="可选，主接口 502/503/504 或缺少配置路径结果时自动切换"
            @update:value="(value: number | string | undefined) => { sceneForm.backup_api_config_id = fromBackupApiSelectValue(value); }"
          >
            <a-select-option :value="EMPTY_BACKUP_API_OPTION" label="无">
              无
            </a-select-option>
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

        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="隐藏宽高比">
              <a-switch v-model:checked="sceneForm.hide_aspect_ratio" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="隐藏分辨率">
              <a-switch v-model:checked="sceneForm.hide_resolution" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="支持自定义分辨率">
              <a-switch
                :checked="!sceneForm.hide_custom_size"
                @change="setSceneSupportsCustomSize"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row v-if="!sceneForm.hide_custom_size" :gutter="16">
          <a-col :span="8">
            <a-form-item label="最小宽高">
              <a-input-number v-model:value="sceneForm.custom_size_min" :min="1" :precision="0" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="最大宽高">
              <a-input-number v-model:value="sceneForm.custom_size_max" :min="sceneForm.custom_size_min" :precision="0" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="递增步长">
              <a-input-number v-model:value="sceneForm.custom_size_step" :min="1" :precision="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="宽高比选项 JSON">
          <a-textarea
            v-model:value="sceneForm.aspect_ratio_options_json"
            class="warm-textarea"
            :rows="8"
            placeholder='[{"label":"1:1","value":"1:1"}]'
          />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `label/value` 数组；`value` 会映射到请求里的 <code v-pre>{{ aspect_ratio }}</code> 占位符。
          </div>
        </a-form-item>

        <a-form-item label="生图质量选项 JSON">
          <a-textarea
            v-model:value="sceneForm.image_size_options_json"
            class="warm-textarea"
            :rows="6"
            placeholder='[{"label":"2K","value":"2K"}]'
          />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `label/value` 数组；`value` 会映射到请求里的 <code v-pre>{{ image_size }}</code> 占位符。
          </div>
        </a-form-item>

        <a-form-item label="旧版自定义分辨率选项 JSON（兼容）">
          <a-textarea
            v-model:value="sceneForm.custom_size_options_json"
            class="warm-textarea"
            :rows="6"
            placeholder='[{"label":"1024 x 1024","value":"1024x1024"}]'
          />
          <div class="scene-desc" style="margin-top: 6px">
            仅用于兼容旧入口；主生图页开启自定义分辨率后改为手动输入宽高。
          </div>
        </a-form-item>

        <a-form-item label="分辨率映射 JSON">
          <a-textarea
            v-model:value="sceneForm.resolution_mapping_json"
            class="warm-textarea"
            :rows="8"
            placeholder='{"1:1":{"2K":"2048x2048"},"3:4":{"2K":"1536x2048"}}'
          />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `宽高比 -> 生图质量 -> 第三方分辨率` 对象；匹配结果会映射到请求里的
            <code v-pre>{{ mapped_resolution }}</code>
            占位符。
          </div>
          <div class="scene-desc" style="margin-top: 6px">
            未开启自定义分辨率时继续使用 <code v-pre>{{ mapped_resolution }}</code> 即可，原有接口不用改。
            只有开启自定义后，才需要改成 <code v-pre>{{ resolved_resolution }}</code>（有手动宽高用手动宽高，否则回退映射分辨率）。
          </div>
        </a-form-item>

        <a-form-item label="分辨率积分 JSON">
          <a-textarea
            v-model:value="sceneForm.resolution_credit_costs_json"
            class="warm-textarea"
            :rows="5"
            placeholder='{"1K":2,"2K":4,"4K":8}'
          />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `生图质量 -> 单张积分` 对象；未配置的分辨率会使用上方“消耗积分”作为默认值。
          </div>
        </a-form-item>
      </a-form>

      <template #footer>
        <a-space>
          <a-button class="api-secondary-btn" @click="sceneModalOpen = false">取消</a-button>
          <a-button type="primary" class="api-primary-btn" :loading="bindingCreating" @click="handleCreateScene">创建</a-button>
        </a-space>
      </template>
    </a-modal>

    <a-modal
      v-model:open="sceneMetaModalOpen"
      title="编辑场景基础信息"
      :mask-closable="false"
      :width="720"
      @ok="handleSaveSceneMeta"
    >
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="场景标识" required>
              <a-input v-model:value="sceneMetaForm.scene_key" class="warm-input" placeholder="例如：banana_ultra" />
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
              <a-input-number v-model:value="sceneMetaForm.max_reference_images" class="warm-input-number" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="场景描述">
          <a-input v-model:value="sceneMetaForm.scene_description" class="warm-input" />
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="隐藏宽高比">
              <a-switch v-model:checked="sceneMetaForm.hide_aspect_ratio" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="隐藏分辨率">
              <a-switch v-model:checked="sceneMetaForm.hide_resolution" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="支持自定义分辨率">
              <a-switch
                :checked="!sceneMetaForm.hide_custom_size"
                @change="setSceneMetaSupportsCustomSize"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row v-if="!sceneMetaForm.hide_custom_size" :gutter="16">
          <a-col :span="8">
            <a-form-item label="最小宽高">
              <a-input-number v-model:value="sceneMetaForm.custom_size_min" :min="1" :precision="0" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="最大宽高">
              <a-input-number v-model:value="sceneMetaForm.custom_size_max" :min="sceneMetaForm.custom_size_min" :precision="0" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="递增步长">
              <a-input-number v-model:value="sceneMetaForm.custom_size_step" :min="1" :precision="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="宽高比选项 JSON">
          <a-textarea
            v-model:value="sceneMetaForm.aspect_ratio_options_json"
            class="warm-textarea"
            :rows="8"
            placeholder='[{"label":"1:1","value":"1:1"}]'
          />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `label/value` 数组；`value` 会映射到请求里的 <code v-pre>{{ aspect_ratio }}</code> 占位符。
          </div>
        </a-form-item>

        <a-form-item label="生图质量选项 JSON">
          <a-textarea
            v-model:value="sceneMetaForm.image_size_options_json"
            class="warm-textarea"
            :rows="6"
            placeholder='[{"label":"2K","value":"2K"}]'
          />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `label/value` 数组；`value` 会映射到请求里的 <code v-pre>{{ image_size }}</code> 占位符。
          </div>
        </a-form-item>

        <a-form-item label="旧版自定义分辨率选项 JSON（兼容）">
          <a-textarea
            v-model:value="sceneMetaForm.custom_size_options_json"
            class="warm-textarea"
            :rows="6"
            placeholder='[{"label":"1024 x 1024","value":"1024x1024"}]'
          />
          <div class="scene-desc" style="margin-top: 6px">
            仅用于兼容旧入口；主生图页开启自定义分辨率后改为手动输入宽高。
          </div>
        </a-form-item>

        <a-form-item label="分辨率映射 JSON">
          <a-textarea
            v-model:value="sceneMetaForm.resolution_mapping_json"
            class="warm-textarea"
            :rows="8"
            placeholder='{"1:1":{"2K":"2048x2048"},"3:4":{"2K":"1536x2048"}}'
          />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `宽高比 -> 生图质量 -> 第三方分辨率` 对象；匹配结果会映射到请求里的
            <code v-pre>{{ mapped_resolution }}</code>
            占位符。
          </div>
          <div class="scene-desc" style="margin-top: 6px">
            未开启自定义分辨率时继续使用 <code v-pre>{{ mapped_resolution }}</code> 即可，原有接口不用改。
            只有开启自定义后，才需要改成 <code v-pre>{{ resolved_resolution }}</code>（有手动宽高用手动宽高，否则回退映射分辨率）。
          </div>
        </a-form-item>

        <a-form-item label="分辨率积分 JSON">
          <a-textarea
            v-model:value="sceneMetaForm.resolution_credit_costs_json"
            class="warm-textarea"
            :rows="5"
            placeholder='{"1K":2,"2K":4,"4K":8}'
          />
          <div class="scene-desc" style="margin-top: 6px">
            使用 `生图质量 -> 单张积分` 对象；未配置的分辨率会使用场景默认积分。
          </div>
        </a-form-item>
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

    <a-modal
      v-model:open="modalOpen"
      :title="modalTitle"
      :mask-closable="false"
      :width="920"
      @ok="handleSave"
    >
      <a-form layout="vertical">
        <a-form-item v-if="!editingId" label="粘贴接口配置 JSON 回填">
          <a-textarea
            v-model:value="configImportJson"
            :rows="6"
            allow-clear
            class="warm-input"
            placeholder="粘贴从“复制 JSON”得到的接口配置模板，可自动识别并回填下面的字段"
          />
          <div style="display: flex; justify-content: flex-end; margin-top: 8px">
            <a-button class="api-secondary-btn" @click="handleApplyConfigImportJson">识别并回填</a-button>
          </div>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="配置名称" required>
              <a-input v-model:value="form.name" class="warm-input" placeholder="例如：80AI 主接口" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="接口分组">
              <a-input v-model:value="form.group_name" class="warm-input" placeholder="例如：80AI 系列 / 反推接口" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="描述">
          <a-input v-model:value="form.description" class="warm-input" placeholder="可选，用于备注该接口用途" />
        </a-form-item>

        <a-form-item label="请求地址" required>
          <a-input v-model:value="form.request_url" class="warm-input" placeholder="https://example.com/api" />
        </a-form-item>

        <a-form-item label="调用方式" required>
          <a-radio-group v-model:value="form.call_mode" class="warm-radio-group" button-style="solid">
            <a-radio-button value="sync">同步</a-radio-button>
            <a-radio-button value="async">异步</a-radio-button>
          </a-radio-group>
          <div class="scene-desc" style="margin-top: 6px">
            默认保留现有同步生图接口路线；只有选择异步时，才会提交第三方 taskId 并由服务端轮询结果。
          </div>
        </a-form-item>

        <a-form-item label="请求格式" required>
          <a-radio-group v-model:value="form.request_format" class="warm-radio-group" button-style="solid">
            <a-radio-button value="json">JSON</a-radio-button>
            <a-radio-button value="multipart">Multipart Form</a-radio-button>
          </a-radio-group>
          <div class="scene-desc" style="margin-top: 6px">
            选择 multipart 时会按表单方式发送，并自动忽略 Header JSON 中手写的 Content-Type。
          </div>
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

        <a-form-item v-if="form.call_mode === 'sync'" label="结果 Base64 字段路径">
          <a-input
            v-model:value="form.result_base64_field"
            class="warm-input"
            placeholder="例如：candidates.0.content.parts.0.inlineData.data"
          />
          <div class="scene-desc" style="margin-top: 6px">
            生图完成后会按此路径读取响应中的 base64，并保存为结果图；支持点号路径与数字索引。
          </div>
        </a-form-item>

        <template v-if="isAsyncConfigForm">
          <a-divider orientation="left">异步轮询配置</a-divider>

          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="提交成功状态码 JSON" required>
                <a-textarea
                  v-model:value="form.submit_success_statuses_json"
                  class="warm-textarea"
                  :rows="4"
                  placeholder='[200, 201, 202]'
                />
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
            <div class="scene-desc" style="margin-top: 6px">
              支持在轮询地址、Header JSON、轮询请求 JSON 中使用 <code v-pre>{{ provider_task_id }}</code> 占位符。
            </div>
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
                <a-textarea
                  v-model:value="form.result_success_values_json"
                  class="warm-textarea"
                  :rows="4"
                  placeholder='["success", "completed"]'
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="失败状态值 JSON" required>
                <a-textarea
                  v-model:value="form.result_failed_values_json"
                  class="warm-textarea"
                  :rows="4"
                  placeholder='["failed", "error", "cancelled"]'
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="轮询结果 Base64 字段路径">
                <a-input v-model:value="form.poll_result_base64_field" class="warm-input" placeholder="例如：data.result.image_base64" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="轮询结果图片 URL 字段路径">
                <a-input v-model:value="form.poll_result_url_field" class="warm-input" placeholder="例如：data.result.image_url" />
              </a-form-item>
            </a-col>
          </a-row>

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
        </template>

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

.doc-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-block pre {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--theme-panel-bg-soft);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
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

.credit-unit {
  flex: none;
  color: var(--text-secondary);
  white-space: nowrap;
}

.binding-sort-value {
  color: #5d4526;
  font-weight: 700;
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
