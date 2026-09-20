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
const previewDialogOpen = ref(false);

const hasConfig = computed(() => (
  Boolean(contactQrImage.value.trim() || announcementEnabled.value || announcementContent.value.trim())
));
const announcementLooksLikeHtml = computed(() => contentLooksLikeHtml(announcementContent.value));
const announcementPreviewEmpty = computed(() => !announcementContent.value.trim());

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

function openAnnouncementPreview() {
  previewDialogOpen.value = true;
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
        <div class="settings-toolbar">
          <div>
            <div class="toolbar-title">内容配置</div>
            <div class="toolbar-desc">这里的修改会直接影响全站展示内容，保存后即时生效。</div>
          </div>
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
        </div>

        <section class="config-section qr-section">
          <div class="section-head">
            <div>
              <div class="settings-label">联系二维码</div>
              <div class="section-desc">用于站内“联系我们”等入口展示，建议上传清晰的正方形二维码。</div>
            </div>
            <a-tag class="section-status-tag">{{ contactQrImage ? "已上传" : "未上传" }}</a-tag>
          </div>
          <div class="qr-card">
            <div class="qr-visual">
              <div v-if="contactQrImage" class="qr-preview">
                <img :src="contactQrImage" alt="contact qr code" />
              </div>
              <div v-else class="qr-placeholder">暂未上传联系二维码</div>
            </div>
            <div class="qr-content">
              <div class="qr-meta-card">
                <div class="meta-title">展示建议</div>
                <div class="meta-list">
                  <div>建议比例：1:1 方图</div>
                  <div>建议内容：客服微信、社群二维码等</div>
                  <div>生效范围：前台联系入口与相关引导位</div>
                </div>
              </div>
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
        </section>

        <section class="config-section announcement-section">
          <div class="section-head announcement-head">
            <div>
              <div class="settings-label">系统公告</div>
              <div class="section-desc">支持纯文本和 HTML，适合发布版本更新、维护通知和活动说明。</div>
            </div>
            <div class="announcement-switch-wrap">
              <span class="switch-label">{{ announcementEnabled ? "已开启" : "已关闭" }}</span>
              <a-switch
                v-model:checked="announcementEnabled"
                class="warm-switch"
                checked-children="开启"
                un-checked-children="关闭"
              />
            </div>
          </div>
          <div class="announcement-hint">
            支持 HTML。可用标题、加粗、列表、链接和换行。不写标签时，仍按纯文本换行展示。
          </div>
          <div class="announcement-editor-panel">
            <div class="announcement-preview-label">编辑内容</div>
            <a-textarea
              v-model:value="announcementContent"
              class="announcement-textarea warm-textarea"
              :rows="10"
              :maxlength="5000"
              show-count
              placeholder="可直接写文字，或填 HTML。例如：&#10;<p><strong>【2026-08-25】</strong></p>&#10;<p>生图页新增风格设置和摄像机参数，欢迎试用。</p>"
            />
            <div class="announcement-actions">
              <div class="announcement-preview-tip">预览时会按前台公告样式展示。</div>
              <a-button class="config-secondary-btn" :disabled="announcementPreviewEmpty" @click="openAnnouncementPreview">
                查看模拟预览
              </a-button>
            </div>
          </div>
        </section>
      </div>
    </a-spin>

    <a-modal
      v-model:open="previewDialogOpen"
      title="公告模拟预览"
      width="720px"
      centered
      :footer="null"
    >
      <div class="announcement-dialog">
        <div class="announcement-dialog-head">
          <div>
            <div class="announcement-dialog-title">前台展示效果</div>
            <div class="announcement-dialog-subtitle">
              {{ announcementEnabled ? "当前公告处于开启状态" : "当前公告处于关闭状态，仅供预览内容样式" }}
            </div>
          </div>
          <a-tag class="section-status-tag">{{ announcementEnabled ? "已开启" : "未开启" }}</a-tag>
        </div>
        <div
          v-if="!announcementPreviewEmpty"
          class="announcement-preview announcement-dialog-preview"
          :class="{ 'is-html': announcementLooksLikeHtml }"
          v-html="announcementContent"
        />
        <div v-else class="announcement-empty announcement-dialog-empty">
          暂无公告内容，请先填写公告后再预览。
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style scoped lang="scss">
.general-settings-page {
  max-width: 980px;
  margin: 0 auto;
}

.settings-card {
  padding: 30px 32px 32px;
  max-width: 980px;
  margin: 0 auto;
}

.general-settings-page :deep(.warm-page-header) {
  max-width: 980px;
  margin-inline: auto;
}

.general-settings-page :deep(.warm-page-heading) {
  width: 100%;
}

.settings-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--theme-subtitle);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.settings-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 28px;
}

.toolbar-title {
  color: var(--theme-title);
  font-size: 20px;
  font-weight: 800;
  line-height: 1.2;
}

.toolbar-desc {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.settings-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  flex-shrink: 0;
}

.config-section + .config-section {
  margin-top: 28px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.section-desc {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.section-status-tag {
  margin-inline-end: 0;
  padding: 6px 12px;
  border-radius: 999px;
  border-color: var(--theme-panel-border-strong);
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text);
  font-weight: 700;
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
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 20px;
  padding: 18px 20px;
  border-radius: 20px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
}

.qr-visual {
  display: flex;
  align-items: center;
  justify-content: center;
}

.qr-preview {
  width: 156px;
  height: 156px;
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
  width: 156px;
  height: 156px;
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

.qr-content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
}

.qr-meta-card {
  padding: 16px 18px;
  border-radius: 16px;
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-border);
}

.meta-title {
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 700;
}

.meta-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.qr-actions {
  display: flex;
  align-items: center;
}

.announcement-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.announcement-head {
  margin-bottom: 0;
}

.announcement-switch-wrap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
}

.switch-label {
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 700;
}

.announcement-hint {
  color: var(--theme-muted-text);
  font-size: 13px;
  line-height: 1.6;
}

.announcement-editor-panel {
  min-width: 0;
}

.announcement-textarea {
  :deep(textarea) {
    min-height: 320px;
    border-radius: 16px;
    border-color: var(--theme-control-border);
    background: var(--theme-control-bg);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 13px;
    line-height: 1.7;
  }
}

.announcement-preview-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--theme-subtitle);
  letter-spacing: 0.06em;
  margin-bottom: 10px;
}

.announcement-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 12px;
}

.announcement-preview-tip {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.announcement-preview {
  min-height: 320px;
  max-height: 420px;
  overflow-y: auto;
  overflow-x: hidden;
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

  &.is-html :deep(figure) {
    max-width: 100%;
    margin: 12px 0;
  }

  &.is-html :deep(img) {
    display: block;
    width: 100%;
    max-width: 100%;
    height: auto;
    border-radius: 14px;
    object-fit: contain;
  }

  &.is-html :deep(a) {
    color: var(--theme-accent-text);
  }

  &.is-html :deep(strong),
  &.is-html :deep(b) {
    color: var(--theme-title);
  }
}

.announcement-empty {
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  border-radius: 16px;
  border: 1px dashed var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  color: var(--text-secondary);
  text-align: center;
  line-height: 1.8;
}

.announcement-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.announcement-dialog-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.announcement-dialog-title {
  color: var(--theme-title);
  font-size: 18px;
  font-weight: 800;
  line-height: 1.2;
}

.announcement-dialog-subtitle {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.announcement-dialog-preview,
.announcement-dialog-empty {
  min-height: 240px;
}

@media (max-width: 960px) {
  .general-settings-page {
    max-width: 100%;
  }

  .settings-card {
    padding: 24px;
  }

  .settings-toolbar,
  .section-head {
    flex-direction: column;
  }

  .qr-card {
    grid-template-columns: 1fr;
  }

  .qr-visual {
    justify-content: flex-start;
  }

  .announcement-actions,
  .announcement-dialog-head {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 640px) {
  .settings-card {
    padding: 18px;
  }

  .qr-preview,
  .qr-placeholder {
    width: 132px;
    height: 132px;
  }

  .announcement-textarea :deep(textarea),
  .announcement-preview,
  .announcement-empty {
    min-height: 260px;
  }
}
</style>
