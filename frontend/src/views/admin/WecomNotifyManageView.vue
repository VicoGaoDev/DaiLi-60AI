<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import dayjs from "dayjs";
import { message, Modal } from "ant-design-vue";
import {
  DeleteOutlined,
  EditOutlined,
  NotificationOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
} from "@ant-design/icons-vue";
import {
  createWecomChannel,
  createWecomRule,
  deleteWecomChannel,
  deleteWecomRule,
  listWecomChannels,
  listWecomEventCatalog,
  listWecomRules,
  testWecomChannel,
  testWecomRule,
  updateWecomChannel,
  updateWecomRule,
} from "@/api/admin";
import type {
  AdminWecomNotifyRule,
  AdminWecomWebhookChannel,
  WecomEventCatalogItem,
  WecomEventField,
  WecomEventVariable,
} from "@/types";

const loading = ref(false);
const catalog = ref<WecomEventCatalogItem[]>([]);
const channels = ref<AdminWecomWebhookChannel[]>([]);
const rules = ref<AdminWecomNotifyRule[]>([]);

const channelModalOpen = ref(false);
const channelSaving = ref(false);
const editingChannelId = ref<string | null>(null);
const testingChannelId = ref("");
const togglingChannelId = ref("");
const channelForm = reactive({
  name: "",
  webhook_url: "",
  is_enabled: false,
  remark: "",
});

const ruleModalOpen = ref(false);
const ruleSaving = ref(false);
const editingRuleId = ref<string | null>(null);
const togglingRuleId = ref("");
const testingRuleId = ref("");
const ruleForm = reactive({
  name: "",
  channel_id: "",
  event_key: "",
  is_enabled: true,
  min_amount_yuan: undefined as number | undefined,
  include_gift: true,
  order_types: [] as string[],
  template_markdown: "",
});

const channelColumns = [
  { title: "名称", dataIndex: "name", width: 150 },
  { title: "Webhook", dataIndex: "webhook_url", width: 360 },
  { title: "规则数", dataIndex: "rule_count", width: 88 },
  { title: "开关", dataIndex: "is_enabled", width: 96 },
  { title: "更新时间", dataIndex: "updated_at", width: 170 },
  { title: "操作", key: "actions", width: 132 },
];

const ruleColumns = [
  { title: "规则名称", dataIndex: "name", width: 160 },
  { title: "场景", dataIndex: "event_label", width: 160 },
  { title: "通道", dataIndex: "channel_name", width: 140 },
  { title: "条件", dataIndex: "conditions", width: 220 },
  { title: "模版", dataIndex: "template_markdown", width: 280 },
  { title: "开关", dataIndex: "is_enabled", width: 96 },
  { title: "操作", key: "actions", width: 132 },
];

const selectedEvent = computed(() => catalog.value.find((item) => item.event_key === ruleForm.event_key) || null);
const selectedFields = computed<WecomEventField[]>(() => selectedEvent.value?.fields || []);
const selectedVariables = computed<WecomEventVariable[]>(() => selectedEvent.value?.variables || []);

function formatTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function conditionText(rule: AdminWecomNotifyRule) {
  const event = catalog.value.find((item) => item.event_key === rule.event_key);
  const conditions = rule.conditions || {};
  const parts: string[] = [];
  (event?.fields || []).forEach((field) => {
    const value = conditions[field.key];
    if (value === undefined || value === null || value === "") return;
    if (field.type === "boolean") {
      parts.push(`${field.label}：${value ? "是" : "否"}`);
      return;
    }
    if (field.type === "multi_select" && Array.isArray(value)) {
      const labels = value.map((item) => field.options?.find((option) => option.value === item)?.label || String(item));
      if (labels.length) parts.push(`${field.label}：${labels.join("、")}`);
      return;
    }
    parts.push(`${field.label}：${String(value)}`);
  });
  return parts.join("；") || "无条件";
}

function templateSummary(rule: AdminWecomNotifyRule) {
  const text = (rule.template_markdown || "").trim();
  if (!text) return "默认模版";
  const firstLine = text.split("\n").find((line) => line.trim()) || text;
  return firstLine.length > 80 ? `${firstLine.slice(0, 80)}...` : firstLine;
}

function defaultTemplateFor(eventKey: string) {
  return catalog.value.find((item) => item.event_key === eventKey)?.default_template || "";
}

async function load() {
  loading.value = true;
  try {
    const [nextCatalog, nextChannels, nextRules] = await Promise.all([
      listWecomEventCatalog(),
      listWecomChannels(),
      listWecomRules(),
    ]);
    catalog.value = nextCatalog;
    channels.value = nextChannels;
    rules.value = nextRules;
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取企微通知配置失败");
  } finally {
    loading.value = false;
  }
}

function resetChannelForm() {
  editingChannelId.value = null;
  channelForm.name = "";
  channelForm.webhook_url = "";
  channelForm.is_enabled = false;
  channelForm.remark = "";
}

function openCreateChannel() {
  resetChannelForm();
  channelModalOpen.value = true;
}

function openEditChannel(item: AdminWecomWebhookChannel) {
  editingChannelId.value = item.id;
  channelForm.name = item.name;
  channelForm.webhook_url = item.webhook_url;
  channelForm.is_enabled = item.is_enabled;
  channelForm.remark = item.remark;
  channelModalOpen.value = true;
}

async function handleSaveChannel() {
  if (!channelForm.name.trim()) {
    message.warning("请填写通道名称");
    return;
  }
  channelSaving.value = true;
  try {
    if (editingChannelId.value) {
      await updateWecomChannel(editingChannelId.value, { ...channelForm });
      message.success("通道已保存");
    } else {
      await createWecomChannel({ ...channelForm });
      message.success("通道已创建");
    }
    channelModalOpen.value = false;
    resetChannelForm();
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "保存通道失败");
  } finally {
    channelSaving.value = false;
  }
}

async function handleToggleChannel(item: AdminWecomWebhookChannel, checked: boolean) {
  togglingChannelId.value = item.id;
  try {
    await updateWecomChannel(item.id, { is_enabled: checked });
    message.success(checked ? `${item.name}已开启` : `${item.name}已关闭`);
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "更新通道开关失败");
  } finally {
    togglingChannelId.value = "";
  }
}

function channelToggleHandler(item: AdminWecomWebhookChannel) {
  return (checked: boolean | string | number) => {
    void handleToggleChannel(item, Boolean(checked));
  };
}

async function handleTestChannel(item: AdminWecomWebhookChannel) {
  testingChannelId.value = item.id;
  try {
    await testWecomChannel(item.id);
    message.success("测试消息已发送，请到对应企业微信群查看");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "测试发送失败");
  } finally {
    testingChannelId.value = "";
  }
}

function handleDeleteChannel(item: AdminWecomWebhookChannel) {
  Modal.confirm({
    title: `删除通道「${item.name}」？`,
    content: item.rule_count > 0 ? "该通道下还有触发规则，请先删除规则。" : "删除后不可恢复。",
    centered: true,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      await deleteWecomChannel(item.id);
      message.success("通道已删除");
      await load();
    },
  });
}

function resetRuleForm() {
  editingRuleId.value = null;
  ruleForm.name = "";
  ruleForm.channel_id = channels.value[0]?.id || "";
  ruleForm.event_key = catalog.value[0]?.event_key || "";
  ruleForm.is_enabled = true;
  ruleForm.min_amount_yuan = undefined;
  ruleForm.include_gift = true;
  ruleForm.order_types = [];
  ruleForm.template_markdown = defaultTemplateFor(ruleForm.event_key);
}

function applyRuleConditions(eventKey: string, conditions: Record<string, unknown>) {
  ruleForm.min_amount_yuan = eventKey === "payment_success" && conditions.min_amount_yuan != null
    ? Number(conditions.min_amount_yuan)
    : undefined;
  ruleForm.include_gift = eventKey !== "redeem_success" || conditions.include_gift !== false;
  ruleForm.order_types = eventKey === "offline_order" && Array.isArray(conditions.order_types)
    ? conditions.order_types.map((item) => String(item))
    : [];
}

function buildRuleConditions() {
  const conditions: Record<string, unknown> = {};
  if (ruleForm.event_key === "payment_success" && ruleForm.min_amount_yuan != null && ruleForm.min_amount_yuan !== ("" as unknown as number)) {
    conditions.min_amount_yuan = Number(ruleForm.min_amount_yuan);
  }
  if (ruleForm.event_key === "redeem_success" && ruleForm.include_gift === false) {
    conditions.include_gift = false;
  }
  if (ruleForm.event_key === "offline_order" && ruleForm.order_types.length) {
    conditions.order_types = [...ruleForm.order_types];
  }
  return conditions;
}

function openCreateRule() {
  resetRuleForm();
  ruleModalOpen.value = true;
}

function handleRuleEventChange(value: string) {
  ruleForm.event_key = value;
  applyRuleConditions(value, {});
  ruleForm.template_markdown = defaultTemplateFor(value);
}

function insertTemplateVariable(key: string) {
  const token = `{{${key}}}`;
  ruleForm.template_markdown = ruleForm.template_markdown
    ? `${ruleForm.template_markdown}${ruleForm.template_markdown.endsWith("\n") ? "" : "\n"}${token}`
    : token;
}

function variableToken(key: string) {
  return `{{${key}}}`;
}

function openEditRule(item: AdminWecomNotifyRule) {
  editingRuleId.value = item.id;
  ruleForm.name = item.name;
  ruleForm.channel_id = item.channel_id;
  ruleForm.event_key = item.event_key;
  ruleForm.is_enabled = item.is_enabled;
  applyRuleConditions(item.event_key, item.conditions || {});
  ruleForm.template_markdown = item.template_markdown || defaultTemplateFor(item.event_key);
  ruleModalOpen.value = true;
}

async function handleSaveRule() {
  if (!ruleForm.channel_id) {
    message.warning("请选择通道");
    return;
  }
  if (!ruleForm.event_key) {
    message.warning("请选择触发场景");
    return;
  }
  ruleSaving.value = true;
  try {
    const payload = {
      channel_id: ruleForm.channel_id,
      event_key: ruleForm.event_key,
      name: ruleForm.name.trim(),
      is_enabled: ruleForm.is_enabled,
      conditions: buildRuleConditions(),
      template_markdown: ruleForm.template_markdown,
    };
    if (editingRuleId.value) {
      await updateWecomRule(editingRuleId.value, payload);
      message.success("规则已保存");
    } else {
      await createWecomRule(payload);
      message.success("规则已创建");
    }
    ruleModalOpen.value = false;
    resetRuleForm();
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "保存规则失败");
  } finally {
    ruleSaving.value = false;
  }
}

async function handleToggleRule(item: AdminWecomNotifyRule, checked: boolean) {
  togglingRuleId.value = item.id;
  try {
    await updateWecomRule(item.id, { is_enabled: checked });
    message.success(checked ? `${item.name}已开启` : `${item.name}已关闭`);
    await load();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "更新规则开关失败");
  } finally {
    togglingRuleId.value = "";
  }
}

function ruleToggleHandler(item: AdminWecomNotifyRule) {
  return (checked: boolean | string | number) => {
    void handleToggleRule(item, Boolean(checked));
  };
}

async function handleTestRule(item: AdminWecomNotifyRule) {
  testingRuleId.value = item.id;
  try {
    await testWecomRule(item.id);
    message.success("规则测试消息已发送，请到对应企业微信群查看");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "规则测试发送失败");
  } finally {
    testingRuleId.value = "";
  }
}

function handleDeleteRule(item: AdminWecomNotifyRule) {
  Modal.confirm({
    title: `删除规则「${item.name}」？`,
    content: "删除后该场景不再向对应通道发送。",
    centered: true,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      await deleteWecomRule(item.id);
      message.success("规则已删除");
      await load();
    },
  });
}

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <NotificationOutlined />
        </div>
        <div>
          <div class="warm-page-title">企微通知</div>
          <div class="warm-page-desc">管理企业微信通道，并为每个通道配置触发场景和条件。空条件表示该场景一律发送。</div>
        </div>
      </div>
      <div class="warm-page-actions">
        <a-button type="primary" class="warm-primary-btn" :loading="loading" @click="load">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>
    </div>

    <div class="warm-card warm-table-card motion-fade-up" style="--motion-delay: 100ms">
      <div class="section-header">
        <div class="section-title">通知通道</div>
        <a-button type="primary" class="warm-primary-btn" @click="openCreateChannel">
          <template #icon><PlusOutlined /></template>
          新增通道
        </a-button>
      </div>
      <a-table
        class="wecom-table"
        :columns="channelColumns"
        :data-source="channels"
        :loading="loading"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 1060 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'webhook_url'">
            <span class="mono-cell">{{ record.webhook_url || "未填写" }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'is_enabled'">
            <a-switch
              :checked="record.is_enabled"
              class="warm-switch"
              checked-children="开启"
              un-checked-children="关闭"
              :loading="togglingChannelId === record.id"
              @change="channelToggleHandler(record)($event)"
            />
          </template>
          <template v-else-if="column.dataIndex === 'updated_at'">
            {{ formatTime(record.updated_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space class="action-cell">
              <a-button type="link" size="small" title="编辑" aria-label="编辑" @click="openEditChannel(record)">
                <EditOutlined />
              </a-button>
              <a-button type="link" size="small" title="测试" aria-label="测试" :loading="testingChannelId === record.id" @click="handleTestChannel(record)">
                <SendOutlined />
              </a-button>
              <a-button type="link" size="small" title="删除" aria-label="删除" danger @click="handleDeleteChannel(record)">
                <DeleteOutlined />
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>

    <div class="warm-card warm-table-card motion-fade-up rules-card" style="--motion-delay: 160ms">
      <div class="section-header">
        <div class="section-title">触发规则</div>
        <a-button type="primary" class="warm-primary-btn" @click="openCreateRule">
          <template #icon><PlusOutlined /></template>
          新增规则
        </a-button>
      </div>
      <a-table
        class="wecom-table"
        :columns="ruleColumns"
        :data-source="rules"
        :loading="loading"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 1266 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'conditions'">
            <span class="condition-cell">{{ conditionText(record) }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'template_markdown'">
            <span class="template-cell">{{ templateSummary(record) }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'is_enabled'">
            <a-switch
              :checked="record.is_enabled"
              class="warm-switch"
              checked-children="开启"
              un-checked-children="关闭"
              :loading="togglingRuleId === record.id"
              @change="ruleToggleHandler(record)($event)"
            />
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space class="action-cell">
              <a-button type="link" size="small" title="编辑" aria-label="编辑" @click="openEditRule(record)">
                <EditOutlined />
              </a-button>
              <a-button type="link" size="small" title="测试" aria-label="测试" :loading="testingRuleId === record.id" @click="handleTestRule(record)">
                <SendOutlined />
              </a-button>
              <a-button type="link" size="small" title="删除" aria-label="删除" danger @click="handleDeleteRule(record)">
                <DeleteOutlined />
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>

    <a-modal
      v-model:open="channelModalOpen"
      :title="editingChannelId ? '编辑通道' : '新增通道'"
      :confirm-loading="channelSaving"
      ok-text="保存"
      cancel-text="取消"
      centered
      @ok="handleSaveChannel"
    >
      <a-form layout="vertical">
        <a-form-item label="通道名称" required>
          <a-input v-model:value="channelForm.name" maxlength="50" placeholder="例如：经营通知" />
        </a-form-item>
        <a-form-item label="Webhook 地址">
          <a-input v-model:value="channelForm.webhook_url" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" />
        </a-form-item>
        <a-form-item label="备注">
          <a-input v-model:value="channelForm.remark" maxlength="200" placeholder="用途说明" />
        </a-form-item>
        <a-form-item label="是否开启">
          <a-switch v-model:checked="channelForm.is_enabled" class="warm-switch" checked-children="开启" un-checked-children="关闭" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="ruleModalOpen"
      :title="editingRuleId ? '编辑规则' : '新增规则'"
      :confirm-loading="ruleSaving"
      ok-text="保存"
      cancel-text="取消"
      centered
      width="720px"
      @ok="handleSaveRule"
    >
      <a-form layout="vertical">
        <a-form-item label="规则名称">
          <a-input v-model:value="ruleForm.name" maxlength="80" placeholder="不填则使用场景名称" />
        </a-form-item>
        <a-form-item label="通道" required>
          <a-select v-model:value="ruleForm.channel_id" :options="channels.map((item) => ({ value: item.id, label: item.name }))" />
        </a-form-item>
        <a-form-item label="触发场景" required>
          <a-select
            v-model:value="ruleForm.event_key"
            :options="catalog.map((item) => ({ value: item.event_key, label: item.label }))"
            @change="handleRuleEventChange"
          />
        </a-form-item>
        <a-form-item v-for="field in selectedFields" :key="field.key" :label="field.label">
          <a-input-number
            v-if="field.type === 'number'"
            v-model:value="ruleForm.min_amount_yuan"
            :min="0"
            :precision="2"
            style="width: 100%"
            placeholder="不填表示不限制金额"
          />
          <a-switch
            v-else-if="field.type === 'boolean'"
            v-model:checked="ruleForm.include_gift"
            class="warm-switch"
            checked-children="包含"
            un-checked-children="不含"
          />
          <a-select
            v-else-if="field.type === 'multi_select'"
            v-model:value="ruleForm.order_types"
            mode="multiple"
            :options="field.options || []"
            placeholder="不选表示购买和退款都发送"
          />
        </a-form-item>
        <a-form-item label="发送内容模版" required>
          <a-textarea
            v-model:value="ruleForm.template_markdown"
            class="template-editor"
            :auto-size="{ minRows: 8, maxRows: 16 }"
            placeholder="支持 Markdown 和 {{变量名}}"
          />
          <div class="template-help">
            点击变量可追加到模版末尾；未填写模版时会使用当前场景默认模版。
          </div>
          <div v-if="selectedVariables.length" class="variable-list">
            <a-tag
              v-for="variable in selectedVariables"
              :key="variable.key"
              class="variable-tag"
              @click="insertTemplateVariable(variable.key)"
            >
              {{ variable.label }}：{{ variableToken(variable.key) }}
            </a-tag>
          </div>
        </a-form-item>
        <a-form-item label="是否开启">
          <a-switch v-model:checked="ruleForm.is_enabled" class="warm-switch" checked-children="开启" un-checked-children="关闭" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.warm-card {
  overflow: hidden;
  padding: 24px 28px 28px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--theme-title);
}

.rules-card {
  margin-top: 20px;
}

.mono-cell {
  display: block;
  max-width: 100%;
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.condition-cell {
  display: block;
  max-width: 100%;
  overflow: hidden;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-cell {
  display: block;
  max-width: 100%;
  overflow: hidden;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-cell {
  white-space: nowrap;
}

.template-editor {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

.template-help {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.variable-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.variable-tag {
  margin-inline-end: 0;
  cursor: pointer;
  user-select: none;
}

:deep(.wecom-table .ant-table-thead > tr > th),
:deep(.wecom-table .ant-table-tbody > tr > td) {
  padding: 10px 12px;
  white-space: nowrap;
}

:deep(.wecom-table .ant-table),
:deep(.wecom-table .ant-table-container),
:deep(.wecom-table .ant-table-content),
:deep(.wecom-table .ant-table-body) {
  background: transparent !important;
}

:deep(.wecom-table .ant-table-thead > tr > th) {
  background: var(--theme-table-head-bg) !important;
  border-bottom: 1px solid var(--theme-border) !important;
  color: var(--theme-title) !important;
}

:deep(.wecom-table .ant-table-tbody > tr > td) {
  background: var(--theme-table-row-bg) !important;
  border-bottom: 1px solid var(--theme-border) !important;
  color: var(--theme-text) !important;
}

:deep(.wecom-table .ant-table-tbody > tr:hover > td) {
  background: var(--theme-table-row-hover) !important;
}

:deep(.wecom-table .ant-table-placeholder > td) {
  background: var(--theme-panel-bg) !important;
  color: var(--text-secondary) !important;
}

:deep(.wecom-table .ant-table-content) {
  overflow-x: auto !important;
}

@media (max-width: 768px) {
  .warm-card {
    padding: 18px 18px 22px;
  }

  .section-header {
    align-items: flex-start;
  }
}
</style>
