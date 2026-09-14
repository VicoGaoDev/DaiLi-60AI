<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { message, Modal } from "ant-design-vue";
import { DeleteOutlined, SaveOutlined, SettingOutlined, UploadOutlined } from "@ant-design/icons-vue";
import { deleteAdminConfig, getAdminConfig, setAdminConfig } from "@/api/admin";
import { uploadReferenceImage } from "@/api/upload";
import { contentLooksLikeHtml } from "@/lib/htmlContent";

const contactQrImage = ref("");
const announcementEnabled = ref(false);
const announcementContent = ref("");
const loading = ref(false);
const saving = ref(false);
const qrUploading = ref(false);
const qrInput = ref<HTMLInputElement | null>(null);

const hasConfig = computed(() => (
  Boolean(contactQrImage.value.trim() || announcementEnabled.value || announcementContent.value.trim())
));
const announcementLooksLikeHtml = computed(() => contentLooksLikeHtml(announcementContent.value));

onMounted(async () => {
  loading.value = true;
  try {
    const res = await getAdminConfig();
    if (res) {
      contactQrImage.value = res.contact_qr_image || "";
      announcementEnabled.value = !!res.announcement_enabled;
      announcementContent.value = res.announcement_content || "";
    }
  } catch {
    // no config yet
  } finally {
    loading.value = false;
  }
});

async function handleSave() {
  if (!hasConfig.value) {
    message.warning("请至少配置一项内容");
    return;
  }
  saving.value = true;
  try {
    await setAdminConfig({
      contact_qr_image: contactQrImage.value,
      announcement_enabled: announcementEnabled.value,
      announcement_content: announcementContent.value.trim(),
    });
    message.success("配置保存成功");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

function handleDelete() {
  Modal.confirm({
    title: "确认删除",
    content: "删除后联系二维码与系统公告配置将被清空。",
    okText: "确认删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await deleteAdminConfig();
        contactQrImage.value = "";
        announcementEnabled.value = false;
        announcementContent.value = "";
        message.success("配置已删除");
      } catch (err: any) {
        message.error(err.response?.data?.detail || "删除失败");
      }
    },
  });
}

function triggerQrUpload() {
  qrInput.value?.click();
}

async function handleQrUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  qrUploading.value = true;
  try {
    const res = await uploadReferenceImage(file, "contact_qr");
    contactQrImage.value = res.url;
    message.success("二维码上传成功");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "二维码上传失败");
  } finally {
    qrUploading.value = false;
    input.value = "";
  }
}
</script>

<template>
  <div class="general-settings-page warm-page motion-page-enter">
    <div class="warm-page-header motion-fade-up" style="--motion-delay: 40ms">
      <div class="warm-page-heading">
        <div class="warm-page-icon">
          <SettingOutlined />
        </div>
        <div>
          <div class="warm-page-title">通用设置</div>
          <div class="warm-page-desc">管理联系二维码与系统公告，面向全站用户生效。</div>
        </div>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div class="settings-card warm-card motion-fade-up motion-card-lift" style="--motion-delay: 120ms">
        <div class="settings-footer">
          <a-button type="primary" class="warm-primary-btn" :loading="saving" @click="handleSave">
            <template #icon><SaveOutlined /></template>
            保存
          </a-button>
          <a-button class="warm-danger-btn" :disabled="!hasConfig" @click="handleDelete">
            <template #icon><DeleteOutlined /></template>
            删除
          </a-button>
        </div>

        <div class="qr-section">
          <div class="settings-label">联系二维码</div>
          <div class="qr-card">
            <div v-if="contactQrImage" class="qr-preview">
              <img :src="contactQrImage" alt="contact qr code" />
            </div>
            <div v-else class="qr-placeholder">暂未上传联系二维码</div>

            <div class="qr-actions">
              <input
                ref="qrInput"
                type="file"
                accept="image/*"
                style="display: none"
                @change="handleQrUpload"
              />
              <a-button class="config-secondary-btn" :loading="qrUploading" @click="triggerQrUpload">
                <template #icon><UploadOutlined /></template>
                {{ contactQrImage ? "重新上传" : "上传二维码" }}
              </a-button>
            </div>
          </div>
        </div>

        <div class="announcement-section">
          <div class="settings-label">系统公告</div>
          <a-switch
            v-model:checked="announcementEnabled"
            class="warm-switch"
            checked-children="开启"
            un-checked-children="关闭"
          />
          <div class="announcement-hint">
            支持 HTML。可用标题、加粗、列表、链接和换行。不写标签时，仍按纯文本换行展示。
          </div>
          <a-textarea
            v-model:value="announcementContent"
            class="announcement-textarea warm-textarea"
            :rows="8"
            :maxlength="5000"
            show-count
            placeholder="可直接写文字，或填 HTML。例如：&#10;<p><strong>【2026-08-25】</strong></p>&#10;<p>生图页新增风格设置和摄像机参数，欢迎试用。</p>"
          />
          <div v-if="announcementContent.trim()" class="announcement-preview-label">预览</div>
          <div
            v-if="announcementContent.trim()"
            class="announcement-preview"
            :class="{ 'is-html': announcementLooksLikeHtml }"
            v-html="announcementContent"
          />
        </div>
      </div>
    </a-spin>
  </div>
</template>

<style scoped lang="scss">
.general-settings-page {
  max-width: 820px;
}

.settings-card {
  padding: 32px;
}

.settings-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--theme-subtitle);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.settings-footer {
  display: flex;
  gap: 12px;
  margin-bottom: 28px;
}

.config-secondary-btn {
  border-color: var(--theme-panel-border-strong) !important;
  background: var(--theme-panel-bg-strong) !important;
  color: var(--theme-accent-text) !important;
  border-radius: 12px !important;
  font-weight: 600;
}

.config-secondary-btn:hover,
.config-secondary-btn:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
}

.qr-section {
  margin-top: 0;
}

.qr-card {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 18px 20px;
  border-radius: 20px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
}

.qr-preview {
  width: 144px;
  height: 144px;
  flex: 0 0 144px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  overflow: hidden;
  background: var(--theme-empty-bg);
  border: 1px solid var(--theme-border);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
}

.qr-placeholder {
  width: 144px;
  height: 144px;
  flex: 0 0 144px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  text-align: center;
  border-radius: 18px;
  background: var(--theme-control-bg);
  border: 1px dashed var(--theme-empty-border);
  color: var(--text-secondary);
  line-height: 1.6;
}

.qr-actions {
  display: flex;
  align-items: center;
}

.announcement-section {
  margin-top: 28px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.announcement-hint {
  color: var(--theme-muted-text);
  font-size: 13px;
  line-height: 1.6;
}

.announcement-textarea {
  :deep(textarea) {
    border-radius: 16px;
    border-color: var(--theme-control-border);
    background: var(--theme-control-bg);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 13px;
    line-height: 1.7;
  }
}

.announcement-preview-label {
  margin-top: 4px;
  font-size: 12px;
  font-weight: 700;
  color: var(--theme-subtitle);
  letter-spacing: 0.06em;
}

.announcement-preview {
  max-height: 280px;
  overflow: auto;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  color: var(--theme-text);
  font-size: 14px;
  line-height: 1.85;
  white-space: pre-wrap;
  word-break: break-word;

  &.is-html {
    white-space: normal;
  }

  &.is-html :deep(p) {
    margin: 0 0 10px;
  }

  &.is-html :deep(h1),
  &.is-html :deep(h2),
  &.is-html :deep(h3),
  &.is-html :deep(h4) {
    margin: 14px 0 8px;
    color: var(--theme-heading);
    line-height: 1.35;
  }

  &.is-html :deep(ul),
  &.is-html :deep(ol) {
    margin: 0 0 10px 20px;
    padding-left: 16px;
  }

  &.is-html :deep(a) {
    color: var(--theme-accent-text);
  }

  &.is-html :deep(strong),
  &.is-html :deep(b) {
    color: var(--theme-title);
  }
}
</style>
