<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import {
  CloudUploadOutlined,
  CopyOutlined,
  DeleteOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  SaveOutlined,
} from "@ant-design/icons-vue";
import { deleteCosConfig, getCosConfig, setCosConfig } from "@/api/admin";

const cosSecretId = ref("");
const cosSecretKey = ref("");
const cosBucket = ref("");
const cosRegion = ref("");
const cosUploadDomain = ref("");
const cosPublicBaseUrl = ref("");
const hasConfig = ref(false);
const loading = ref(false);
const saving = ref(false);
const cosSecretIdVisible = ref(false);
const cosSecretKeyVisible = ref(false);

const maskedCosSecretId = computed(() => {
  if (!cosSecretId.value) return "";
  const k = cosSecretId.value;
  if (k.length <= 8) return "••••••••";
  return k.slice(0, 4) + "••••••••" + k.slice(-4);
});

const maskedCosSecretKey = computed(() => {
  if (!cosSecretKey.value) return "";
  const k = cosSecretKey.value;
  if (k.length <= 8) return "••••••••";
  return k.slice(0, 4) + "••••••••" + k.slice(-4);
});

onMounted(async () => {
  loading.value = true;
  try {
    const res = await getCosConfig();
    if (res) {
      cosSecretId.value = res.cos_secret_id || "";
      cosSecretKey.value = res.cos_secret_key || "";
      cosBucket.value = res.cos_bucket || "";
      cosRegion.value = res.cos_region || "";
      cosUploadDomain.value = res.cos_upload_domain || "";
      cosPublicBaseUrl.value = res.cos_public_base_url || "";
      hasConfig.value = Boolean(
        res.cos_secret_id
        || res.cos_secret_key
        || res.cos_bucket
        || res.cos_region
        || res.cos_upload_domain
        || res.cos_public_base_url,
      );
    }
  } catch (err: any) {
    message.error(err.response?.data?.detail || "获取 COS 配置失败");
  } finally {
    loading.value = false;
  }
});

async function handleSave() {
  if (
    !cosSecretId.value.trim()
    && !cosSecretKey.value.trim()
    && !cosBucket.value.trim()
    && !cosRegion.value.trim()
    && !cosUploadDomain.value.trim()
    && !cosPublicBaseUrl.value.trim()
  ) {
    message.warning("请至少配置一项内容");
    return;
  }
  saving.value = true;
  try {
    await setCosConfig({
      cos_secret_id: cosSecretId.value.trim(),
      cos_secret_key: cosSecretKey.value.trim(),
      cos_bucket: cosBucket.value.trim(),
      cos_region: cosRegion.value.trim(),
      cos_upload_domain: cosUploadDomain.value.trim(),
      cos_public_base_url: cosPublicBaseUrl.value.trim(),
    });
    hasConfig.value = true;
    message.success("COS 配置保存成功");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

function handleDelete() {
  Modal.confirm({
    title: "确认清空 COS 配置",
    content: "清空后参考图上传与结果图存储将无法继续写入腾讯云 COS。",
    okText: "确认清空",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await deleteCosConfig();
        cosSecretId.value = "";
        cosSecretKey.value = "";
        cosBucket.value = "";
        cosRegion.value = "";
        cosUploadDomain.value = "";
        cosPublicBaseUrl.value = "";
        hasConfig.value = false;
        cosSecretIdVisible.value = false;
        cosSecretKeyVisible.value = false;
        message.success("COS 配置已清空");
      } catch (err: any) {
        message.error(err.response?.data?.detail || "清空失败");
      }
    },
  });
}

function copyText(value: string) {
  if (!value) return;
  navigator.clipboard.writeText(value).then(() => {
    message.success("已复制到剪贴板");
  });
}
</script>

<template>
  <div class="cos-page warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <CloudUploadOutlined />
        </div>
        <div>
          <div class="warm-page-title">COS 配置</div>
          <div class="warm-page-desc">仅超级管理员可访问，用于管理腾讯云 COS 存储与上传凭证配置。</div>
        </div>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div class="cos-card warm-card motion-fade-up motion-card-lift" style="--motion-delay: 140ms">
        <div class="field-stack">
          <div>
            <div class="field-label">Bucket</div>
            <a-input v-model:value="cosBucket" size="large" placeholder="如：vicoimagetencent-1257893314" class="plain-input" />
          </div>

          <div>
            <div class="field-label">Region</div>
            <a-input v-model:value="cosRegion" size="large" placeholder="如：ap-guangzhou" class="plain-input" />
          </div>

          <div>
            <div class="field-label">上传域名（可选）</div>
            <a-input
              v-model:value="cosUploadDomain"
              size="large"
              placeholder="仅后端服务上传使用；留空则默认使用 Bucket 标准域名"
              class="plain-input"
            />
            <div class="field-hint">
              该域名只用于后端服务调用 COS SDK 上传/删除文件。前端浏览器直传会走下方“访问域名”。
            </div>
          </div>

          <div>
            <div class="field-label">访问域名（可选）</div>
            <a-input
              v-model:value="cosPublicBaseUrl"
              size="large"
              placeholder="留空则默认使用 COS 公网域名，也可填写 CDN 域名"
              class="plain-input"
            />
            <div class="field-hint">
              浏览器直传 COS 与最终落库返回给前端的 URL 都会使用这个域名。
            </div>
          </div>

          <div>
            <div class="field-label">SecretId</div>
            <div class="secret-row">
              <a-input
                v-if="cosSecretIdVisible"
                v-model:value="cosSecretId"
                size="large"
                placeholder="请输入 COS SecretId"
                class="secret-input"
              />
              <div v-else class="secret-masked" @click="cosSecretIdVisible = true">
                {{ cosSecretId ? maskedCosSecretId : "暂未配置" }}
              </div>
              <div class="secret-actions">
                <a-button
                  type="text"
                  class="cos-icon-btn"
                  @click="cosSecretIdVisible = !cosSecretIdVisible"
                  :title="cosSecretIdVisible ? '隐藏' : '显示'"
                >
                  <template #icon>
                    <EyeInvisibleOutlined v-if="cosSecretIdVisible" />
                    <EyeOutlined v-else />
                  </template>
                </a-button>
                <a-button type="text" class="cos-icon-btn" @click="copyText(cosSecretId)" :disabled="!cosSecretId" title="复制">
                  <template #icon><CopyOutlined /></template>
                </a-button>
              </div>
            </div>
          </div>

          <div>
            <div class="field-label">SecretKey</div>
            <div class="secret-row">
              <a-input
                v-if="cosSecretKeyVisible"
                v-model:value="cosSecretKey"
                size="large"
                placeholder="请输入 COS SecretKey"
                class="secret-input"
              />
              <div v-else class="secret-masked" @click="cosSecretKeyVisible = true">
                {{ cosSecretKey ? maskedCosSecretKey : "暂未配置" }}
              </div>
              <div class="secret-actions">
                <a-button
                  type="text"
                  class="cos-icon-btn"
                  @click="cosSecretKeyVisible = !cosSecretKeyVisible"
                  :title="cosSecretKeyVisible ? '隐藏' : '显示'"
                >
                  <template #icon>
                    <EyeInvisibleOutlined v-if="cosSecretKeyVisible" />
                    <EyeOutlined v-else />
                  </template>
                </a-button>
                <a-button type="text" class="cos-icon-btn" @click="copyText(cosSecretKey)" :disabled="!cosSecretKey" title="复制">
                  <template #icon><CopyOutlined /></template>
                </a-button>
              </div>
            </div>
          </div>
        </div>

        <div class="cos-footer">
          <a-button type="primary" class="warm-primary-btn" :loading="saving" @click="handleSave">
            <template #icon><SaveOutlined /></template>
            保存
          </a-button>
          <a-button class="warm-danger-btn" :disabled="!hasConfig" @click="handleDelete">
            <template #icon><DeleteOutlined /></template>
            清空
          </a-button>
        </div>
      </div>
    </a-spin>
  </div>
</template>

<style scoped lang="scss">
.cos-page {
  max-width: 820px;
}

.cos-card {
  padding: 32px;
}

.field-stack {
  display: grid;
  gap: 18px;
}

.field-label {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.plain-input {
  :deep(.ant-input) {
    border-radius: 16px;
    border-color: var(--theme-control-border);
    background: var(--theme-control-bg);
  }
}

.field-hint {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
}

.secret-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.secret-input {
  flex: 1;
  font-family: "SF Mono", "Consolas", "Monaco", monospace;

  :deep(.ant-input) {
    border-radius: 16px;
    border-color: var(--theme-control-border);
    background: var(--theme-control-bg);
  }
}

.secret-masked {
  flex: 1;
  min-height: 48px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  border-radius: 16px;
  font-family: "SF Mono", "Consolas", "Monaco", monospace;
  font-size: 14px;
  color: var(--theme-title);
  letter-spacing: 1px;
  cursor: pointer;
}

.secret-actions {
  display: flex;
  gap: 6px;
}

.cos-icon-btn {
  width: 40px;
  height: 40px;
  border-radius: 14px !important;
  background: var(--theme-panel-bg-strong) !important;
  border: 1px solid var(--theme-panel-border-strong) !important;
  color: var(--theme-accent-text) !important;
}

.cos-icon-btn:hover,
.cos-icon-btn:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
}

.cos-footer {
  display: flex;
  gap: 12px;
  margin-top: 28px;
}
</style>
