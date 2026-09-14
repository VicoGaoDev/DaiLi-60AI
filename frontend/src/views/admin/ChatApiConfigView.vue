<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import { DeleteOutlined, DownOutlined, MoreOutlined, PlusOutlined, SwapOutlined } from "@ant-design/icons-vue";
import { getPreviewImageSrc } from "@/api/images";
import { isImageUploadTooLarge, MAX_IMAGE_UPLOAD_SIZE_TEXT, uploadReferenceImage } from "@/api/upload";
import {
  createChatExternalApiConfig,
  createChatExternalApiSceneBinding,
  deleteChatExternalApiConfig,
  deleteChatExternalApiSceneBinding,
  listChatExternalApiConfigs,
  listChatExternalApiSceneBindings,
  testChatExternalApiConfig,
  updateChatExternalApiConfig,
  updateChatExternalApiConfigStatus,
  updateChatExternalApiSceneBinding,
  updateChatExternalApiSceneBindingMeta,
  updateChatExternalApiSceneBindingStatus,
} from "@/api/admin";
import {
  parseAdminConfigTemplate,
  stringifyAdminConfigTemplate,
} from "@/lib/adminConfigTemplate";
import type {
  ChatExternalApiConfig,
  ChatExternalApiConfigPayload,
  ChatExternalApiSceneBinding,
  ChatExternalApiSceneBindingCreatePayload,
  ChatExternalApiSceneBindingMetaPayload,
  ChatStarterPrompt,
  ExternalApiConfigStatus,
} from "@/types";

type ConfigUsageRole = "primary" | "backup";
type ConfigUsageScene = {
  scene_key: string;
  scene_label: string;
  display_name: string;
  roles: ConfigUsageRole[];
};

const MAX_STARTER_PROMPTS = 6;
const DEFAULT_STARTER_PROMPTS: ChatStarterPrompt[] = [
  {
    tag: "生图",
    text: "怎么样才能让 AI 生图更准确、更好看？有哪些关键方法和常见坑？",
  },
  {
    tag: "生图",
    text: "我想做电商产品图，白底运动鞋怎么拍出质感和卖点？",
  },
  {
    tag: "生图",
    text: "有一张人像照片，想改成赛博朋克风格，该怎么操作更稳？",
  },
  {
    tag: "生视频",
    text: "怎么样才能让 AI 生视频更稳、更自然？有哪些关键方法和常见坑？",
  },
];

function cloneStarterPrompts(items?: ChatStarterPrompt[] | null): ChatStarterPrompt[] {
  return (items || [])
    .slice(0, MAX_STARTER_PROMPTS)
    .map((item) => ({
      tag: String(item?.tag || "").trim(),
      text: String(item?.text || "").trim(),
      image_url: String(item?.image_url || "").trim(),
    }))
    .filter((item) => item.text);
}

function normalizeStarterPromptsInput(items?: ChatStarterPrompt[] | null): ChatStarterPrompt[] {
  return (items || []).slice(0, MAX_STARTER_PROMPTS).map((item) => ({
    tag: String(item?.tag || ""),
    text: String(item?.text || ""),
    image_url: String(item?.image_url || ""),
  }));
}

const DEFAULT_HEADERS_JSON = JSON.stringify(
  {
    Authorization: "Bearer {{api_key}}",
    "Content-Type": "application/json",
  },
  null,
  2,
);
const DEFAULT_PAYLOAD_JSON = JSON.stringify(
  {
    model: "gpt-4o-mini",
    messages: "{{messages}}",
  },
  null,
  2,
);
const DEFAULT_RESPONSE_JSON = JSON.stringify(
  {
    choices: [{ message: { content: "示例回复" } }],
  },
  null,
  2,
);
const EMPTY_BACKUP_API_OPTION = "__none__";

const configs = ref<ChatExternalApiConfig[]>([]);
const sceneBindings = ref<ChatExternalApiSceneBinding[]>([]);
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const bindingCreating = ref(false);
const sceneMetaSaving = ref(false);
const bindingSavingKey = ref("");
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
const configNameFilter = ref("");
const expandedConfigGroups = ref<string[]>([]);
const bindingGroupFilter = ref("all");
const bindingNameFilter = ref("");
const configImportJson = ref("");
const sceneImportJson = ref("");

const form = reactive<ChatExternalApiConfigPayload>({
  name: "",
  description: "",
  group_name: "默认",
  request_url: "",
  request_format: "json",
  headers_json: DEFAULT_HEADERS_JSON,
  payload_json: DEFAULT_PAYLOAD_JSON,
  response_json: DEFAULT_RESPONSE_JSON,
  result_text_field: "choices.0.message.content",
  result_error_field: "error.message",
  call_mode: "sync",
  submit_success_statuses_json: JSON.stringify([200, 201, 202], null, 2),
  status: "enabled",
});

const sceneForm = reactive<ChatExternalApiSceneBindingCreatePayload>({
  scene_key: "",
  scene_label: "",
  scene_description: "",
  sort_order: 100,
  api_config_id: null,
  backup_api_config_id: null,
  display_name: "",
  subtitle: "",
  credit_cost: 1,
  system_prompt: "",
  context_message_limit: 10,
  opening_greeting: "",
  starter_prompts: cloneStarterPrompts(DEFAULT_STARTER_PROMPTS),
  status: "enabled",
});

const sceneMetaForm = reactive<ChatExternalApiSceneBindingMetaPayload>({
  scene_key: "",
  scene_label: "",
  scene_description: "",
  sort_order: 100,
  credit_cost: 1,
  system_prompt: "",
  context_message_limit: 10,
  opening_greeting: "",
  starter_prompts: [],
});

const bindingColumns = [
  { title: "场景", key: "scene", width: 196, ellipsis: true },
  { title: "主接口", key: "bind", width: 400, ellipsis: true },
  { title: "互换", key: "swap", width: 64 },
  { title: "备用接口", key: "backup", width: 400, ellipsis: true },
  { title: "积分", key: "credit", width: 128 },
  { title: "排序", key: "sort", width: 72 },
  { title: "", key: "action", width: 56 },
];

const modalTitle = computed(() => {
  if (editingId.value) return "编辑对话接口配置";
  if (isCopyMode.value) return "复制新增对话接口配置";
  return "新增对话接口配置";
});
const sceneModalTitle = computed(() => (isSceneCopyMode.value ? "复制新增对话场景" : "新增对话场景"));
const groupOptions = computed(() => {
  const groups = Array.from(new Set(configs.value.map((item) => item.group_name || "未分组").filter(Boolean)));
  return groups.sort((a, b) => a.localeCompare(b, "zh-CN"));
});
const filteredConfigs = computed(() => configs.value.filter((item) => {
  if (configGroupFilter.value !== "all" && item.group_name !== configGroupFilter.value) return false;
  if (!matchesNameFilter(configNameFilter.value, item.name, item.description)) return false;
  return true;
}));
const filteredSceneBindings = computed(() => sceneBindings.value.filter((item) => {
  if (bindingGroupFilter.value !== "all" && (item.api_group_name || "未分组") !== bindingGroupFilter.value) return false;
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
  const map = new Map<string, ChatExternalApiConfig[]>();
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
  const appendUsage = (configId: number | null | undefined, binding: ChatExternalApiSceneBinding, role: ConfigUsageRole) => {
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
  const items = [...filteredSceneBindings.value].sort((a, b) => {
    const sortDiff = Number(a.sort_order || 0) - Number(b.sort_order || 0);
    if (sortDiff !== 0) return sortDiff;
    return a.scene_label.localeCompare(b.scene_label, "zh-CN");
  });
  return items.length ? [{ sceneType: "chat", items }] : [];
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

function configCardName(item: ChatExternalApiConfig) {
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

function toBackupApiSelectValue(value: number | null | undefined) {
  return value ?? EMPTY_BACKUP_API_OPTION;
}

function fromBackupApiSelectValue(value: number | string | null | undefined) {
  return value == null || value === EMPTY_BACKUP_API_OPTION ? null : Number(value);
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

function buildCopiedSceneKey(sourceKey: string) {
  const trimmed = (sourceKey || "chat_scene").trim().toLowerCase().replace(/\s+/g, "_");
  const existing = new Set(sceneBindings.value.map((item) => item.scene_key));
  const base = `${trimmed}_copy`;
  if (!existing.has(base)) return base;
  let index = 2;
  while (existing.has(`${trimmed}_copy_${index}`)) index += 1;
  return `${trimmed}_copy_${index}`;
}

function buildCopiedSceneLabel(sourceLabel: string) {
  const trimmed = sourceLabel.trim() || "未命名场景";
  const existing = new Set(sceneBindings.value.map((item) => item.scene_label.trim()));
  const base = `${trimmed}（副本）`;
  if (!existing.has(base)) return base;
  let index = 2;
  while (existing.has(`${trimmed}（副本${index}）`)) index += 1;
  return `${trimmed}（副本${index}）`;
}

async function loadData() {
  loading.value = true;
  try {
    const [configRows, bindingRows] = await Promise.all([
      listChatExternalApiConfigs(),
      listChatExternalApiSceneBindings(),
    ]);
    configs.value = configRows;
    sceneBindings.value = bindingRows;
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "加载对话接口配置失败");
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  isCopyMode.value = false;
  editingId.value = null;
  configImportJson.value = "";
  form.name = "";
  form.description = "";
  form.group_name = "默认";
  form.request_url = "";
  form.request_format = "json";
  form.headers_json = DEFAULT_HEADERS_JSON;
  form.payload_json = DEFAULT_PAYLOAD_JSON;
  form.response_json = DEFAULT_RESPONSE_JSON;
  form.result_text_field = "choices.0.message.content";
  form.result_error_field = "error.message";
  form.call_mode = "sync";
  form.submit_success_statuses_json = JSON.stringify([200, 201, 202], null, 2);
  form.status = "enabled";
}

function fillForm(record: ChatExternalApiConfig) {
  isCopyMode.value = false;
  editingId.value = record.id;
  configImportJson.value = "";
  Object.assign(form, {
    name: record.name,
    description: record.description,
    group_name: record.group_name,
    request_url: record.request_url,
    request_format: "json",
    headers_json: record.headers_json,
    payload_json: record.payload_json,
    response_json: record.response_json,
    result_text_field: record.result_text_field,
    result_error_field: record.result_error_field,
    call_mode: "sync",
    submit_success_statuses_json: record.submit_success_statuses_json,
    status: record.status,
  });
}

function openCreate() {
  resetForm();
  modalOpen.value = true;
}

function openEdit(record: ChatExternalApiConfig) {
  fillForm(record);
  modalOpen.value = true;
}

function openCopy(record: ChatExternalApiConfig) {
  resetForm();
  isCopyMode.value = true;
  form.name = buildCopiedName(record.name);
  form.description = record.description || "";
  form.group_name = record.group_name || "默认";
  form.request_url = record.request_url;
  form.headers_json = record.headers_json;
  form.payload_json = record.payload_json;
  form.response_json = record.response_json || DEFAULT_RESPONSE_JSON;
  form.result_text_field = record.result_text_field || "choices.0.message.content";
  form.result_error_field = record.result_error_field || "error.message";
  form.submit_success_statuses_json = record.submit_success_statuses_json || JSON.stringify([200, 201, 202], null, 2);
  form.status = record.status;
  modalOpen.value = true;
}

function resetSceneForm() {
  isSceneCopyMode.value = false;
  sceneImportJson.value = "";
  sceneForm.scene_key = "";
  sceneForm.scene_label = "";
  sceneForm.scene_description = "";
  sceneForm.sort_order = Math.max(100, ...sceneBindings.value.map((item) => Number(item.sort_order || 0) + 10), 100);
  sceneForm.api_config_id = null;
  sceneForm.backup_api_config_id = null;
  sceneForm.display_name = "";
  sceneForm.subtitle = "";
  sceneForm.credit_cost = 1;
  sceneForm.system_prompt = "";
  sceneForm.context_message_limit = 10;
  sceneForm.opening_greeting = "";
  sceneForm.starter_prompts = cloneStarterPrompts(DEFAULT_STARTER_PROMPTS);
  sceneForm.status = "enabled";
}

function addStarterPrompt(target: { starter_prompts: ChatStarterPrompt[] }) {
  if (target.starter_prompts.length >= MAX_STARTER_PROMPTS) {
    message.warning(`最多添加 ${MAX_STARTER_PROMPTS} 条内置问题`);
    return;
  }
  target.starter_prompts.push({ tag: "", text: "", image_url: "" });
}

const starterImageInputRef = ref<HTMLInputElement | null>(null);
const starterImageUploadingKey = ref("");
const starterImageTarget = ref<{ list: ChatStarterPrompt[]; index: number } | null>(null);

function starterImageKey(list: ChatStarterPrompt[], index: number) {
  return list === sceneMetaForm.starter_prompts ? `meta-${index}` : `scene-${index}`;
}

function triggerStarterImageUpload(list: ChatStarterPrompt[], index: number) {
  starterImageTarget.value = { list, index };
  starterImageInputRef.value?.click();
}

function clearStarterImage(list: ChatStarterPrompt[], index: number) {
  if (!list[index]) return;
  list[index].image_url = "";
}

async function handleStarterImageChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  const target = starterImageTarget.value;
  input.value = "";
  starterImageTarget.value = null;
  if (!file || !target || !target.list[target.index]) return;
  if (!file.type.startsWith("image/")) {
    message.warning("仅支持上传图片");
    return;
  }
  if (isImageUploadTooLarge(file)) {
    message.warning(`图片不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
    return;
  }
  const uploadKey = starterImageKey(target.list, target.index);
  starterImageUploadingKey.value = uploadKey;
  try {
    const uploaded = await uploadReferenceImage(file, "chat");
    if (target.list[target.index]) {
      target.list[target.index].image_url = uploaded.url;
    }
    message.success("图片已上传");
  } catch (err: any) {
    message.error(err?.response?.data?.detail || err?.message || "图片上传失败");
  } finally {
    if (starterImageUploadingKey.value === uploadKey) {
      starterImageUploadingKey.value = "";
    }
  }
}

function removeStarterPrompt(target: { starter_prompts: ChatStarterPrompt[] }, index: number) {
  target.starter_prompts.splice(index, 1);
}

function sanitizeStarterPrompts(items: ChatStarterPrompt[]): ChatStarterPrompt[] {
  const cleaned = cloneStarterPrompts(items);
  if (cleaned.length > MAX_STARTER_PROMPTS) {
    throw new Error(`内置问题最多 ${MAX_STARTER_PROMPTS} 条`);
  }
  return cleaned;
}

function openCreateScene() {
  resetSceneForm();
  sceneModalOpen.value = true;
}

function openCopyScene(record: ChatExternalApiSceneBinding) {
  resetSceneForm();
  isSceneCopyMode.value = true;
  sceneForm.scene_key = buildCopiedSceneKey(record.scene_key);
  sceneForm.scene_label = buildCopiedSceneLabel(record.scene_label);
  sceneForm.scene_description = record.scene_description || "";
  sceneForm.sort_order = Number(record.sort_order || 0) + 10;
  sceneForm.api_config_id = record.api_config_id ?? null;
  sceneForm.backup_api_config_id = record.backup_api_config_id ?? null;
  sceneForm.display_name = record.display_name || "";
  sceneForm.subtitle = record.subtitle || "";
  sceneForm.credit_cost = Number(record.credit_cost || 0);
  sceneForm.system_prompt = record.system_prompt || "";
  sceneForm.context_message_limit = Number(record.context_message_limit || 10);
  sceneForm.opening_greeting = record.opening_greeting || "";
  sceneForm.starter_prompts = normalizeStarterPromptsInput(record.starter_prompts);
  sceneForm.status = record.status;
  sceneModalOpen.value = true;
}

function buildConfigTemplateData(item: ChatExternalApiConfig): ChatExternalApiConfigPayload {
  return {
    name: item.name,
    description: item.description || "",
    group_name: item.group_name || "默认",
    request_url: item.request_url,
    request_format: "json",
    headers_json: item.headers_json,
    payload_json: item.payload_json,
    response_json: item.response_json || DEFAULT_RESPONSE_JSON,
    result_text_field: item.result_text_field || "choices.0.message.content",
    result_error_field: item.result_error_field || "error.message",
    call_mode: "sync",
    submit_success_statuses_json: item.submit_success_statuses_json || JSON.stringify([200, 201, 202], null, 2),
    status: item.status,
  };
}

function buildSceneTemplateData(record: ChatExternalApiSceneBinding): ChatExternalApiSceneBindingCreatePayload {
  return {
    scene_key: record.scene_key,
    scene_label: record.scene_label,
    scene_description: record.scene_description || "",
    sort_order: Number(record.sort_order || 0),
    api_config_id: record.api_config_id ?? null,
    backup_api_config_id: record.backup_api_config_id ?? null,
    display_name: record.display_name || "",
    subtitle: record.subtitle || "",
    credit_cost: Number(record.credit_cost || 0),
    system_prompt: record.system_prompt || "",
    context_message_limit: Number(record.context_message_limit || 10),
    opening_greeting: record.opening_greeting || "",
    starter_prompts: cloneStarterPrompts(record.starter_prompts),
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

function handleCopyConfigJson(item: ChatExternalApiConfig) {
  const template = stringifyAdminConfigTemplate("chat-api-config", buildConfigTemplateData(item));
  copyTemplateJson(template, "对话接口配置 JSON 已复制");
}

function handleCopySceneJson(record: ChatExternalApiSceneBinding) {
  const template = stringifyAdminConfigTemplate("chat-scene-binding", buildSceneTemplateData(record));
  copyTemplateJson(template, "对话场景绑定 JSON 已复制");
}

function applyImportedConfigData(data: Record<string, unknown>) {
  form.name = normalizeStringValue(data.name, form.name);
  form.description = normalizeStringValue(data.description, form.description);
  form.group_name = normalizeStringValue(data.group_name, form.group_name || "默认");
  form.request_url = normalizeStringValue(data.request_url, form.request_url);
  form.request_format = "json";
  form.headers_json = normalizeJsonFieldValue(data.headers_json, form.headers_json);
  form.payload_json = normalizeJsonFieldValue(data.payload_json, form.payload_json);
  form.response_json = normalizeJsonFieldValue(data.response_json, form.response_json);
  form.result_text_field = normalizeStringValue(data.result_text_field, form.result_text_field);
  form.result_error_field = normalizeStringValue(data.result_error_field, form.result_error_field);
  form.call_mode = "sync";
  form.submit_success_statuses_json = normalizeJsonFieldValue(
    data.submit_success_statuses_json,
    form.submit_success_statuses_json,
  );
  form.status = data.status === "disabled" ? "disabled" : "enabled";
}

function handleApplyConfigImportJson() {
  if (!configImportJson.value.trim()) {
    message.warning("请先粘贴对话接口配置 JSON");
    return;
  }
  try {
    const parsed = parseAdminConfigTemplate(configImportJson.value);
    if (parsed.kind !== "chat-api-config") {
      message.warning("这段 JSON 不是对话接口配置模板");
      return;
    }
    applyImportedConfigData(parsed.data);
    message.success("已识别并回填对话接口配置");
  } catch (err: any) {
    message.error(err?.message || "识别对话接口配置 JSON 失败");
  }
}

function applyImportedSceneData(data: Record<string, unknown>) {
  sceneForm.scene_key = normalizeStringValue(data.scene_key, sceneForm.scene_key);
  sceneForm.scene_label = normalizeStringValue(data.scene_label, sceneForm.scene_label);
  sceneForm.scene_description = normalizeStringValue(data.scene_description, sceneForm.scene_description);
  sceneForm.sort_order = normalizeNumberValue(data.sort_order, sceneForm.sort_order);
  sceneForm.api_config_id = normalizeNullableNumberValue(data.api_config_id);
  sceneForm.backup_api_config_id = normalizeNullableNumberValue(data.backup_api_config_id);
  sceneForm.display_name = normalizeStringValue(data.display_name, sceneForm.display_name);
  sceneForm.subtitle = normalizeStringValue(data.subtitle, sceneForm.subtitle);
  sceneForm.credit_cost = normalizeNumberValue(data.credit_cost, sceneForm.credit_cost);
  sceneForm.system_prompt = normalizeStringValue(data.system_prompt, sceneForm.system_prompt);
  sceneForm.context_message_limit = normalizeNumberValue(
    data.context_message_limit,
    sceneForm.context_message_limit,
  );
  sceneForm.opening_greeting = normalizeStringValue(data.opening_greeting, sceneForm.opening_greeting);
  if (Array.isArray(data.starter_prompts)) {
    sceneForm.starter_prompts = normalizeStarterPromptsInput(data.starter_prompts as ChatStarterPrompt[]);
  }
  sceneForm.status = data.status === "disabled" ? "disabled" : "enabled";
}

function handleApplySceneImportJson() {
  if (!sceneImportJson.value.trim()) {
    message.warning("请先粘贴对话场景绑定 JSON");
    return;
  }
  try {
    const parsed = parseAdminConfigTemplate(sceneImportJson.value);
    if (parsed.kind !== "chat-scene-binding") {
      message.warning("这段 JSON 不是对话场景绑定模板");
      return;
    }
    applyImportedSceneData(parsed.data);
    message.success("已识别并回填对话场景绑定");
  } catch (err: any) {
    message.error(err?.message || "识别对话场景绑定 JSON 失败");
  }
}

async function handleSave() {
  if (!form.name.trim() || !form.request_url.trim() || !form.result_text_field.trim()) {
    message.warning("请填写名称、请求地址和回复文本字段路径");
    return;
  }
  saving.value = true;
  try {
    if (editingId.value) {
      await updateChatExternalApiConfig(editingId.value, { ...form });
      message.success("对话接口已更新");
    } else {
      await createChatExternalApiConfig({ ...form });
      message.success("对话接口已创建");
    }
    modalOpen.value = false;
    await loadData();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function handleTest() {
  testing.value = true;
  try {
    const result = await testChatExternalApiConfig({ ...form });
    if (result.success) {
      message.success(`测试成功：${result.extracted_text || "已解析到文本"}`);
    } else {
      message.warning(`测试未通过（HTTP ${result.status_code ?? "-"}）`);
    }
    Modal.info({
      title: "测试结果",
      width: 720,
      content: `URL: ${result.request_url}\n状态码: ${result.status_code ?? "-"}\n提取文本: ${result.extracted_text || "(空)"}\n\n响应预览:\n${result.response_preview}`,
    });
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "测试失败");
  } finally {
    testing.value = false;
  }
}

function handleToggleConfigStatus(record: ChatExternalApiConfig) {
  const nextStatus: ExternalApiConfigStatus = record.status === "enabled" ? "disabled" : "enabled";
  Modal.confirm({
    title: nextStatus === "enabled" ? "启用该接口？" : "停用该接口？",
    onOk: async () => {
      await updateChatExternalApiConfigStatus(record.id, nextStatus);
      message.success("状态已更新");
      await loadData();
    },
  });
}

function handleDeleteConfig(record: ChatExternalApiConfig) {
  Modal.confirm({
    title: "删除对话接口",
    content: `确认删除「${record.name}」？绑定该接口的场景会清空主/备接口。`,
    okType: "danger",
    onOk: async () => {
      try {
        await deleteChatExternalApiConfig(record.id);
        message.success("已删除");
        await loadData();
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

async function handleCreateScene() {
  if (!sceneForm.scene_key.trim() || !sceneForm.scene_label.trim()) {
    message.warning("请填写场景标识和场景名称");
    return;
  }
  if (!sceneForm.api_config_id) {
    message.warning("请绑定主接口");
    return;
  }
  bindingCreating.value = true;
  try {
    const starter_prompts = sanitizeStarterPrompts(sceneForm.starter_prompts);
    await createChatExternalApiSceneBinding({ ...sceneForm, starter_prompts });
    message.success("对话场景已创建");
    sceneModalOpen.value = false;
    await loadData();
  } catch (err: any) {
    message.error(err?.message || err?.response?.data?.detail || "创建场景失败");
  } finally {
    bindingCreating.value = false;
  }
}

function openEditSceneMeta(record: ChatExternalApiSceneBinding) {
  sceneEditingKey.value = record.scene_key;
  sceneMetaForm.scene_key = record.scene_key;
  sceneMetaForm.scene_label = record.scene_label;
  sceneMetaForm.scene_description = record.scene_description;
  sceneMetaForm.sort_order = record.sort_order;
  sceneMetaForm.credit_cost = record.credit_cost;
  sceneMetaForm.system_prompt = record.system_prompt;
  sceneMetaForm.context_message_limit = record.context_message_limit;
  sceneMetaForm.opening_greeting = record.opening_greeting;
  sceneMetaForm.starter_prompts = normalizeStarterPromptsInput(record.starter_prompts);
  sceneMetaModalOpen.value = true;
}

function isSceneUnbound(record: ChatExternalApiSceneBinding) {
  return !record.api_config_id;
}

function sceneRowClassName(record: ChatExternalApiSceneBinding) {
  return isSceneUnbound(record) ? "is-unbound-scene" : "";
}

function openEditCopy(record: ChatExternalApiSceneBinding) {
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

function canSwapBinding(record: ChatExternalApiSceneBinding) {
  const primaryId = record.api_config_id ?? null;
  const backupId = record.backup_api_config_id ?? null;
  return primaryId !== backupId && (primaryId != null || backupId != null);
}

function handleSwapBinding(record: ChatExternalApiSceneBinding) {
  if (!canSwapBinding(record)) {
    message.warning("请先绑定主接口或备用接口后再互换");
    return;
  }
  void handleBindingChange(record.scene_key, buildBindingPayload(record, {
    api_config_id: record.backup_api_config_id ?? null,
    backup_api_config_id: record.api_config_id ?? null,
  }));
}

async function handleSaveSceneMeta() {
  sceneMetaSaving.value = true;
  try {
    const starter_prompts = sanitizeStarterPrompts(sceneMetaForm.starter_prompts);
    await updateChatExternalApiSceneBindingMeta(sceneEditingKey.value, {
      ...sceneMetaForm,
      starter_prompts,
    });
    message.success("场景信息已更新");
    sceneMetaModalOpen.value = false;
    await loadData();
  } catch (err: any) {
    message.error(err?.message || err?.response?.data?.detail || "更新失败");
  } finally {
    sceneMetaSaving.value = false;
  }
}

function buildBindingPayload(
  record: ChatExternalApiSceneBinding,
  overrides: Partial<{
    api_config_id: number | null;
    backup_api_config_id: number | null;
    credit_cost: number;
    display_name: string;
    subtitle: string;
    status: ExternalApiConfigStatus;
  }> = {},
) {
  return {
    api_config_id: overrides.api_config_id !== undefined ? overrides.api_config_id : (record.api_config_id ?? null),
    backup_api_config_id: overrides.backup_api_config_id !== undefined
      ? overrides.backup_api_config_id
      : (record.backup_api_config_id ?? null),
    credit_cost: overrides.credit_cost ?? record.credit_cost,
    display_name: overrides.display_name ?? record.display_name ?? "",
    subtitle: overrides.subtitle ?? record.subtitle ?? "",
    status: overrides.status ?? record.status,
  };
}

async function handleBindingChange(
  sceneKey: string,
  payload: ReturnType<typeof buildBindingPayload>,
) {
  bindingSavingKey.value = sceneKey;
  try {
    await updateChatExternalApiSceneBinding(sceneKey, payload);
    message.success("对话场景绑定已更新");
    await loadData();
  } catch (err: any) {
    message.error(err?.response?.data?.detail || "保存绑定失败");
  } finally {
    bindingSavingKey.value = "";
  }
}

function handleToggleSceneStatus(record: ChatExternalApiSceneBinding) {
  const nextStatus: ExternalApiConfigStatus = record.status === "enabled" ? "disabled" : "enabled";
  Modal.confirm({
    title: nextStatus === "enabled" ? "启用该对话场景？" : "停用该对话场景？",
    onOk: async () => {
      await updateChatExternalApiSceneBindingStatus(record.scene_key, nextStatus);
      message.success("状态已更新");
      await loadData();
    },
  });
}

function handleDeleteScene(record: ChatExternalApiSceneBinding) {
  Modal.confirm({
    title: "删除对话场景",
    content: `确认删除「${record.scene_label}」？`,
    okType: "danger",
    onOk: async () => {
      await deleteChatExternalApiSceneBinding(record.scene_key);
      message.success("已删除");
      await loadData();
    },
  });
}

onMounted(loadData);
</script>

<template>
  <div class="page warm-page motion-page-enter">
    <input
      ref="starterImageInputRef"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/gif"
      hidden
      @change="handleStarterImageChange"
    />
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
                          <a-menu-item key="toggle" @click="handleToggleConfigStatus(item)">
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
                    <a-tag class="api-tag api-tag-sync">同步</a-tag>
                    <a-tag class="api-tag api-tag-json">JSON</a-tag>
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
                            对话 · {{ configUsageRoleLabel(scene.roles) }}
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
            <a-button type="primary" class="api-primary-btn" :icon="h(PlusOutlined)" @click="openCreateScene">
              新增场景
            </a-button>
          </a-space>
        </template>

        <a-alert
          class="warm-alert"
          type="info"
          show-icon
          message="主接口分组只过滤列表，不会限制可选接口。显示文案请用行内菜单编辑。"
          style="margin-bottom: 16px"
        />

        <a-spin :spinning="loading">
          <a-empty v-if="!groupedSceneBindings.length" description="没有匹配的场景" />
          <div v-else class="scene-binding-groups">
            <section v-for="block in groupedSceneBindings" :key="block.sceneType" class="scene-binding-group">
              <div class="api-config-group-title">
                <span>对话场景</span>
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
                      <a-tag class="api-tag" :class="record.status === 'enabled' ? 'api-tag-enabled' : 'api-tag-disabled'">
                        {{ record.status === "enabled" ? "启用" : "停用" }}
                      </a-tag>
                      <a-tag class="api-tag api-tag-group">上下文 {{ record.context_message_limit || 10 }}</a-tag>
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
                          <a-menu-item key="copy-scene" @click="openCopyScene(record)">复制新增</a-menu-item>
                          <a-menu-item key="copy-json" @click="handleCopySceneJson(record)">复制 JSON</a-menu-item>
                          <a-menu-divider />
                          <a-menu-item key="edit" @click="openEditSceneMeta(record)">编辑</a-menu-item>
                          <a-menu-item key="toggle" @click="handleToggleSceneStatus(record)">
                            {{ record.status === "enabled" ? "停用" : "启用" }}
                          </a-menu-item>
                          <a-menu-item key="delete" danger @click="handleDeleteScene(record)">删除</a-menu-item>
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
              <div>可用于 Header JSON、请求 JSON：</div>
              <pre v-pre>{{ api_key }}</pre>
              <pre v-pre>{{ bearer_token }}</pre>
              <pre v-pre>{{ system_prompt }}</pre>
              <pre v-pre>{{ user_message }}</pre>
            </div>
          </a-collapse-panel>
          <a-collapse-panel key="messages" header="对话消息数组">
            <div class="doc-block">
              <div>
                请求体里若要注入完整 OpenAI 风格 messages（含系统提示词 + 滑动窗口历史 + 当前用户消息），请写成整值占位：
              </div>
              <pre v-pre>"messages": "{{messages}}"</pre>
              <div class="scene-desc">
                注意必须是完整字符串值；不要写成数组字面量里的普通文本，否则无法替换为 JSON 数组。
              </div>
            </div>
          </a-collapse-panel>
          <a-collapse-panel key="stream" header="流式返回 stream">
            <div class="doc-block">
              <div>第三方支持 SSE 时，在请求 JSON 中显式加上布尔值：</div>
              <pre>"stream": true</pre>
              <div class="scene-desc">
                仅当值为 JSON 布尔 true 时，用户对话走端到端真流式；不写或 false 仍为一次性 JSON + 前端打字机。测试连接会强制 stream=false。
              </div>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </a-card>
    </a-space>

    <a-modal v-model:open="modalOpen" :title="modalTitle" :mask-closable="false" :width="920" @ok="handleSave">
      <a-form layout="vertical">
        <a-form-item v-if="!editingId" label="粘贴对话接口配置 JSON 回填">
          <a-textarea
            v-model:value="configImportJson"
            :rows="6"
            allow-clear
            class="warm-input"
            placeholder="粘贴从“复制 JSON”得到的对话接口配置模板，可自动识别并回填下面的字段"
          />
          <div style="display: flex; justify-content: flex-end; margin-top: 8px">
            <a-button class="api-secondary-btn" @click="handleApplyConfigImportJson">识别并回填</a-button>
          </div>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="配置名称" required>
              <a-input v-model:value="form.name" class="warm-input" placeholder="例如：OpenAI 兼容主接口" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="接口分组">
              <a-input v-model:value="form.group_name" class="warm-input" placeholder="例如：OpenAI / DeepSeek / 自建" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-input v-model:value="form.description" class="warm-input" placeholder="可选，用于备注该对话接口用途" />
        </a-form-item>
        <a-form-item label="请求地址" required>
          <a-input v-model:value="form.request_url" class="warm-input" placeholder="https://example.com/v1/chat/completions" />
        </a-form-item>
        <a-form-item label="Header JSON" required>
          <a-textarea v-model:value="form.headers_json" class="warm-textarea" :rows="6" />
          <div class="scene-desc" style="margin-top: 6px">
            可用 <code v-pre>{{ api_key }}</code> / <code v-pre>{{ bearer_token }}</code>。
          </div>
        </a-form-item>
        <a-form-item label="请求 JSON" required>
          <a-textarea v-model:value="form.payload_json" class="warm-textarea" :rows="10" />
          <div class="scene-desc" style="margin-top: 6px">
            `messages` 必须写成完整占位符：<code v-pre>"messages": "{{messages}}"</code>，才能保留 JSON 数组。
            需要真流式时在请求体里加上 <code>"stream": true</code>（JSON 布尔）；不写或 false 则仍走一次性 JSON。测试连接会强制非流式。
          </div>
        </a-form-item>
        <a-form-item label="响应 JSON 示例">
          <a-textarea
            v-model:value="form.response_json"
            class="warm-textarea"
            :rows="6"
            placeholder="粘贴一份成功响应示例，便于对照字段路径"
          />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="回复文本字段路径" required>
              <a-input v-model:value="form.result_text_field" class="warm-input" placeholder="例如：choices.0.message.content" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="错误字段路径">
              <a-input v-model:value="form.result_error_field" class="warm-input" placeholder="例如：error.message" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="提交成功状态码 JSON">
          <a-textarea
            v-model:value="form.submit_success_statuses_json"
            class="warm-textarea"
            :rows="3"
            placeholder='[200, 201, 202]'
          />
        </a-form-item>
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
          <a-button class="api-secondary-btn" :loading="testing" @click="handleTest">测试连接</a-button>
          <a-button type="primary" class="api-primary-btn" :loading="saving" @click="handleSave">保存</a-button>
        </a-space>
      </template>
    </a-modal>

    <a-modal v-model:open="sceneModalOpen" :title="sceneModalTitle" :mask-closable="false" :width="720" @ok="handleCreateScene">
      <a-form layout="vertical">
        <a-form-item label="粘贴对话场景绑定 JSON 回填">
          <a-textarea
            v-model:value="sceneImportJson"
            :rows="6"
            allow-clear
            class="warm-input"
            placeholder="粘贴从“复制 JSON”得到的对话场景绑定模板，可自动识别并回填下面的字段"
          />
          <div style="display: flex; justify-content: flex-end; margin-top: 8px">
            <a-button class="api-secondary-btn" @click="handleApplySceneImportJson">识别并回填</a-button>
          </div>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="场景标识" required>
              <a-input v-model:value="sceneForm.scene_key" class="warm-input" placeholder="例如：image_assistant" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="场景名称" required>
              <a-input v-model:value="sceneForm.scene_label" class="warm-input" placeholder="例如：生图助手" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-input v-model:value="sceneForm.scene_description" class="warm-input" placeholder="可选，用于后台备注该场景用途" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="显示名称">
              <a-input v-model:value="sceneForm.display_name" class="warm-input" placeholder="前台展示名，为空则用场景名称" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="副标题">
              <a-input v-model:value="sceneForm.subtitle" class="warm-input" placeholder="例如：擅长电商主图与风格改图" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="主接口" required>
              <a-select
                v-model:value="sceneForm.api_config_id"
                class="warm-select"
                popup-class-name="binding-api-select-dropdown"
                show-search
                option-filter-prop="label"
                placeholder="请选择主接口"
                style="width: 100%"
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
              <div class="scene-desc" style="margin-top: 6px">前台场景必须绑定启用中的主接口后才会出现。</div>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="备用接口">
              <a-select
                :value="toBackupApiSelectValue(sceneForm.backup_api_config_id)"
                class="warm-select"
                popup-class-name="binding-api-select-dropdown"
                allow-clear
                show-search
                option-filter-prop="label"
                placeholder="可选备用接口"
                style="width: 100%"
                @change="(value: number | string | undefined) => { sceneForm.backup_api_config_id = fromBackupApiSelectValue(value); }"
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
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="积分消耗">
              <a-input-number v-model:value="sceneForm.credit_cost" class="warm-input-number" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="上下文条数">
              <a-input-number v-model:value="sceneForm.context_message_limit" class="warm-input-number" :min="2" :max="200" style="width: 100%" />
              <div class="scene-desc" style="margin-top: 6px">每次请求携带的最近成功消息条数。</div>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="排序">
              <a-input-number v-model:value="sceneForm.sort_order" class="warm-input-number" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="系统提示词">
          <a-textarea
            v-model:value="sceneForm.system_prompt"
            class="warm-textarea"
            :rows="5"
            placeholder="设定助手角色、能力边界与输出格式"
          />
        </a-form-item>
        <a-form-item label="新会话欢迎语">
          <a-textarea
            v-model:value="sceneForm.opening_greeting"
            class="warm-textarea"
            :rows="3"
            placeholder="用户进入空会话时展示的欢迎文案"
          />
        </a-form-item>
        <a-form-item label="内置问题">
          <div class="starter-prompt-editor">
            <div class="scene-desc">空会话欢迎区展示，最多 {{ MAX_STARTER_PROMPTS }} 条；标签可选，问题必填，图片可选。</div>
            <div
              v-for="(item, index) in sceneForm.starter_prompts"
              :key="`scene-starter-${index}`"
              class="starter-prompt-row"
            >
              <button
                type="button"
                class="starter-prompt-image-btn"
                :disabled="starterImageUploadingKey === starterImageKey(sceneForm.starter_prompts, index)"
                @click="triggerStarterImageUpload(sceneForm.starter_prompts, index)"
              >
                <img v-if="item.image_url" :src="getPreviewImageSrc(item.image_url)" alt="" />
                <span v-else>{{ starterImageUploadingKey === starterImageKey(sceneForm.starter_prompts, index) ? "上传中" : "配图" }}</span>
              </button>
              <a-input v-model:value="item.tag" class="warm-input starter-prompt-tag-input" placeholder="标签，如生图" :maxlength="20" />
              <a-input v-model:value="item.text" class="warm-input starter-prompt-text-input" placeholder="问题内容" :maxlength="500" />
              <a-button
                v-if="item.image_url"
                class="api-secondary-btn"
                title="移除配图"
                @click="clearStarterImage(sceneForm.starter_prompts, index)"
              >
                去图
              </a-button>
              <a-button class="api-secondary-btn" @click="removeStarterPrompt(sceneForm, index)">
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </div>
            <a-button
              class="api-secondary-btn"
              :disabled="sceneForm.starter_prompts.length >= MAX_STARTER_PROMPTS"
              @click="addStarterPrompt(sceneForm)"
            >
              <template #icon><PlusOutlined /></template>
              添加问题
            </a-button>
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

    <a-modal v-model:open="sceneMetaModalOpen" title="编辑对话场景基础信息" :mask-closable="false" :width="720">
      <a-form layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="场景标识">
              <a-input v-model:value="sceneMetaForm.scene_key" class="warm-input" placeholder="例如：image_assistant" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="场景名称" required>
              <a-input v-model:value="sceneMetaForm.scene_label" class="warm-input" placeholder="例如：生图助手" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-input v-model:value="sceneMetaForm.scene_description" class="warm-input" placeholder="可选，用于后台备注该场景用途" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="积分消耗">
              <a-input-number v-model:value="sceneMetaForm.credit_cost" class="warm-input-number" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="上下文条数">
              <a-input-number v-model:value="sceneMetaForm.context_message_limit" class="warm-input-number" :min="2" :max="200" style="width: 100%" />
              <div class="scene-desc" style="margin-top: 6px">每次请求携带的最近成功消息条数。</div>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="排序">
              <a-input-number v-model:value="sceneMetaForm.sort_order" class="warm-input-number" :min="0" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="系统提示词">
          <a-textarea
            v-model:value="sceneMetaForm.system_prompt"
            class="warm-textarea"
            :rows="5"
            placeholder="设定助手角色、能力边界与输出格式"
          />
        </a-form-item>
        <a-form-item label="新会话欢迎语">
          <a-textarea
            v-model:value="sceneMetaForm.opening_greeting"
            class="warm-textarea"
            :rows="3"
            placeholder="用户进入空会话时展示的欢迎文案"
          />
        </a-form-item>
        <a-form-item label="内置问题">
          <div class="starter-prompt-editor">
            <div class="scene-desc">空会话欢迎区展示，最多 {{ MAX_STARTER_PROMPTS }} 条；标签可选，问题必填，图片可选。</div>
            <div
              v-for="(item, index) in sceneMetaForm.starter_prompts"
              :key="`meta-starter-${index}`"
              class="starter-prompt-row"
            >
              <button
                type="button"
                class="starter-prompt-image-btn"
                :disabled="starterImageUploadingKey === starterImageKey(sceneMetaForm.starter_prompts, index)"
                @click="triggerStarterImageUpload(sceneMetaForm.starter_prompts, index)"
              >
                <img v-if="item.image_url" :src="getPreviewImageSrc(item.image_url)" alt="" />
                <span v-else>{{ starterImageUploadingKey === starterImageKey(sceneMetaForm.starter_prompts, index) ? "上传中" : "配图" }}</span>
              </button>
              <a-input v-model:value="item.tag" class="warm-input starter-prompt-tag-input" placeholder="标签，如生图" :maxlength="20" />
              <a-input v-model:value="item.text" class="warm-input starter-prompt-text-input" placeholder="问题内容" :maxlength="500" />
              <a-button
                v-if="item.image_url"
                class="api-secondary-btn"
                title="移除配图"
                @click="clearStarterImage(sceneMetaForm.starter_prompts, index)"
              >
                去图
              </a-button>
              <a-button class="api-secondary-btn" @click="removeStarterPrompt(sceneMetaForm, index)">
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </div>
            <a-button
              class="api-secondary-btn"
              :disabled="sceneMetaForm.starter_prompts.length >= MAX_STARTER_PROMPTS"
              @click="addStarterPrompt(sceneMetaForm)"
            >
              <template #icon><PlusOutlined /></template>
              添加问题
            </a-button>
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
          <a-input v-model:value="copyForm.subtitle" class="warm-input" placeholder="为空则不展示" />
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

.credit-unit {
  flex: none;
  color: var(--text-secondary);
  white-space: nowrap;
}

.binding-sort-value {
  color: #5d4526;
  font-weight: 700;
}

.starter-prompt-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.starter-prompt-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.starter-prompt-image-btn {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  padding: 0;
  border: 1px dashed #e4c89a;
  border-radius: 10px;
  overflow: hidden;
  background: var(--theme-empty-bg);
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
}

.starter-prompt-image-btn img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.starter-prompt-image-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.starter-prompt-tag-input {
  width: 120px;
  flex-shrink: 0;
}

.starter-prompt-text-input {
  flex: 1;
  min-width: 0;
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
