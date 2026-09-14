<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { message } from "ant-design-vue";
import {
  CopyOutlined,
  LockOutlined,
  UploadOutlined,
  UserOutlined,
} from "@ant-design/icons-vue";
import { changePassword, getMe, updateProfile, uploadAvatar } from "@/api/auth";
import { getAvatarImageSrc } from "@/api/images";
import { formatAccountContact, maskPhone } from "@/lib/authAccount";
import { useAuthStore } from "@/stores/auth";
import ProfileAccountBind from "@/components/auth/ProfileAccountBind.vue";

const auth = useAuthStore();

const loadingProfile = ref(false);
const avatarUploading = ref(false);
const avatarInput = ref<HTMLInputElement | null>(null);
const usernameLoading = ref(false);
const showPasswordForm = ref(false);
const usernameForm = ref({
  username: "",
});
const pwdLoading = ref(false);
const pwdForm = ref({
  oldPassword: "",
  newPassword: "",
  confirmPassword: "",
});

const avatarUrl = computed(() => getAvatarImageSrc(auth.user?.avatar_url || ""));
const avatarFallback = computed(() => auth.user?.username?.charAt(0)?.toUpperCase() || "U");
const avatarPreviewVisible = ref(false);
const avatarCachedSrc = ref("");
const avatarImgRef = ref<HTMLImageElement | null>(null);
const avatarLoadFailed = ref(false);

function rememberAvatarSrc(image?: HTMLImageElement | null) {
  const loadedSrc = image?.currentSrc || image?.src || "";
  if (!loadedSrc) return;
  avatarCachedSrc.value = loadedSrc;
}

function cacheLoadedAvatar(event: Event) {
  rememberAvatarSrc(event.target as HTMLImageElement);
}

function handleAvatarLoadError() {
  avatarLoadFailed.value = true;
  avatarCachedSrc.value = "";
  avatarPreviewVisible.value = false;
}

function openAvatarPreview() {
  if (!avatarCachedSrc.value) return;
  avatarPreviewVisible.value = true;
}

function closeAvatarPreview() {
  avatarPreviewVisible.value = false;
}
const roleLabel = computed(() => {
  if (auth.user?.role === "superadmin") return "超级管理员";
  if (auth.user?.role === "admin") return "管理员";
  return "积分用户";
});

async function syncProfile() {
  if (!auth.isLoggedIn) return;
  loadingProfile.value = true;
  try {
    auth.updateUser(await getMe());
  } catch {
    message.error("获取个人信息失败");
  } finally {
    loadingProfile.value = false;
  }
}

function triggerAvatarSelect() {
  avatarInput.value?.click();
}

async function handleAvatarChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  avatarUploading.value = true;
  try {
    const nextUser = await uploadAvatar(file);
    auth.updateUser(nextUser);
    message.success("头像上传成功");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "头像上传失败");
  } finally {
    avatarUploading.value = false;
    input.value = "";
  }
}

async function handleUpdateUsername() {
  const nextUsername = usernameForm.value.username.trim();
  if (!nextUsername) {
    message.warning("请输入用户名");
    return;
  }
  if (nextUsername === (auth.user?.username || "")) {
    message.info("用户名未变化");
    return;
  }
  usernameLoading.value = true;
  try {
    const nextUser = await updateProfile({ username: nextUsername });
    auth.updateUser(nextUser);
    usernameForm.value.username = nextUser.username;
    message.success("用户名修改成功");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "用户名修改失败");
  } finally {
    usernameLoading.value = false;
  }
}

async function handleChangePwd() {
  if ((auth.user?.password_set !== false && !pwdForm.value.oldPassword) || !pwdForm.value.newPassword) {
    message.warning("请填写完整");
    return;
  }
  if (pwdForm.value.newPassword !== pwdForm.value.confirmPassword) {
    message.warning("两次密码不一致");
    return;
  }
  pwdLoading.value = true;
  try {
    await changePassword(
      auth.user?.password_set === false ? undefined : pwdForm.value.oldPassword,
      pwdForm.value.newPassword,
    );
    if (auth.user) {
      auth.updateUser({ ...auth.user, password_set: true });
    }
    pwdForm.value = {
      oldPassword: "",
      newPassword: "",
      confirmPassword: "",
    };
    message.success("密码修改成功");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "修改失败");
  } finally {
    pwdLoading.value = false;
  }
}

async function copyBusinessId() {
  const value = auth.user?.business_id;
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    message.success("Business ID 已复制");
  } catch {
    message.error("复制失败");
  }
}

onMounted(() => {
  syncProfile();
});

watch(
  () => auth.user?.username,
  (value) => {
    usernameForm.value.username = value || "";
  },
  { immediate: true }
);

watch(avatarUrl, async (value, previous) => {
  if (value === previous) return;
  avatarLoadFailed.value = false;
  avatarCachedSrc.value = "";
  avatarPreviewVisible.value = false;
  if (!value) return;
  await nextTick();
  const image = avatarImgRef.value;
  if (image?.complete) rememberAvatarSrc(image);
});
</script>

<template>
  <div class="profile-page warm-page motion-page-enter">
    <div class="profile-topbar">
      <div class="profile-topbar-main">
        <div class="profile-topbar-icon">
          <UserOutlined />
        </div>
        <div class="profile-topbar-copy">
          <h1 class="profile-topbar-title">个人主页</h1>
          <p class="warm-page-desc">查看账号基础信息，并在这里统一管理头像、绑定方式和密码。</p>
        </div>
      </div>
    </div>

    <a-spin :spinning="loadingProfile">
      <div class="profile-layout">
        <section class="profile-summary warm-card motion-card-lift">
          <div class="profile-summary-main">
            <button
              v-if="avatarUrl && !avatarLoadFailed"
              type="button"
              class="profile-avatar profile-avatar-button is-previewable"
              @click="openAvatarPreview"
            >
              <img ref="avatarImgRef" :src="avatarUrl" alt="" @load="cacheLoadedAvatar" @error="handleAvatarLoadError" />
            </button>
            <a-avatar v-else :size="92" class="profile-avatar">
              {{ avatarFallback }}
            </a-avatar>
            <div class="profile-summary-copy">
              <div class="profile-name-row">
                <h2>{{ auth.user?.username || "未登录用户" }}</h2>
                <span class="profile-role-badge">{{ roleLabel }}</span>
              </div>
              <div class="profile-email">{{ formatAccountContact(auth.user) }}</div>
              <div v-if="auth.user?.email && auth.user?.phone" class="profile-email">
                {{ maskPhone(auth.user.phone) }}
              </div>
              <div class="profile-business-id">
                <span>{{ auth.user?.business_id || "-" }}</span>
                <a-button
                  v-if="auth.user?.business_id"
                  class="profile-copy-btn"
                  type="text"
                  @click="copyBusinessId"
                >
                  <template #icon><CopyOutlined /></template>
                  复制
                </a-button>
              </div>
            </div>
          </div>

          <div class="profile-stats">
            <div class="profile-stat-card">
              <span>当前积分</span>
              <strong>{{ auth.user?.credits ?? 0 }}</strong>
            </div>
            <div class="profile-stat-card">
              <span>账户角色</span>
              <strong>{{ roleLabel }}</strong>
            </div>
          </div>
        </section>

        <section class="profile-actions">
          <div class="profile-action-card warm-card motion-card-lift">
            <div class="profile-settings-stack">
              <div class="profile-setting-block">
                <div class="profile-setting-row">
                  <div class="profile-setting-info">
                    <h4>编辑用户名</h4>
                    <span>支持 2-20 个字符，修改后会同步更新导航栏显示。</span>
                  </div>
                  <div class="profile-setting-controls profile-setting-controls-username">
                    <a-input
                      v-model:value="usernameForm.username"
                      :maxlength="20"
                      placeholder="请输入新的用户名"
                      @press-enter="handleUpdateUsername"
                    />
                    <a-button
                      type="primary"
                      class="warm-primary-btn"
                      :loading="usernameLoading"
                      @click="handleUpdateUsername"
                    >
                      <template #icon><UserOutlined /></template>
                      {{ usernameLoading ? "保存中..." : "保存用户名" }}
                    </a-button>
                  </div>
                </div>
              </div>

              <div class="profile-setting-block">
                <div class="profile-setting-row">
                  <div class="profile-setting-info">
                    <h4>上传头像</h4>
                    <span>支持 JPG / PNG / WEBP / GIF，图片最大 1MB。</span>
                  </div>
                  <div class="profile-setting-controls profile-setting-controls-avatar">
                    <a-avatar :size="56" class="profile-avatar profile-avatar-small" :src="avatarUrl || undefined">
                      {{ avatarFallback }}
                    </a-avatar>
                    <input
                      ref="avatarInput"
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      hidden
                      @change="handleAvatarChange"
                    />
                    <a-button
                      type="primary"
                      class="warm-primary-btn"
                      :loading="avatarUploading"
                      @click="triggerAvatarSelect"
                    >
                      <template #icon><UploadOutlined /></template>
                      {{ avatarUploading ? "上传中..." : "选择头像" }}
                    </a-button>
                  </div>
                </div>
              </div>

              <ProfileAccountBind />

              <div class="profile-setting-block">
                <div class="profile-setting-row">
                  <div class="profile-setting-info">
                    <h4>{{ auth.user?.password_set === false ? "设置密码" : "修改密码" }}</h4>
                    <span>
                      {{ auth.user?.password_set === false
                        ? "设置密码后可用用户名、邮箱或手机号登录。"
                        : "建议定期更新密码，提升账号安全性。" }}
                    </span>
                  </div>
                  <a-button class="profile-toggle-btn" @click="showPasswordForm = !showPasswordForm">
                    <template #icon><LockOutlined /></template>
                    {{ showPasswordForm ? "收起" : (auth.user?.password_set === false ? "设置密码" : "修改密码") }}
                  </a-button>
                </div>
                <a-form v-if="showPasswordForm" layout="vertical" class="profile-password-form">
                  <a-form-item v-if="auth.user?.password_set !== false" label="原密码">
                    <a-input-password v-model:value="pwdForm.oldPassword" placeholder="请输入原密码" />
                  </a-form-item>
                  <a-form-item label="新密码">
                    <a-input-password v-model:value="pwdForm.newPassword" placeholder="至少 6 位" />
                  </a-form-item>
                  <a-form-item label="确认新密码" style="margin-bottom: 0">
                    <a-input-password
                      v-model:value="pwdForm.confirmPassword"
                      placeholder="请再次输入"
                      @press-enter="handleChangePwd"
                    />
                  </a-form-item>
                  <div class="profile-password-actions">
                    <a-button type="primary" class="warm-primary-btn" :loading="pwdLoading" @click="handleChangePwd">
                      <template #icon><LockOutlined /></template>
                      {{ pwdLoading ? "提交中..." : "确认修改" }}
                    </a-button>
                  </div>
                </a-form>
              </div>
            </div>
          </div>
        </section>
      </div>
    </a-spin>

    <Teleport to="body">
      <div
        v-show="avatarPreviewVisible"
        class="profile-avatar-preview-mask"
        @click="closeAvatarPreview"
      >
        <img
          v-if="avatarCachedSrc"
          :src="avatarCachedSrc"
          alt=""
          @click.stop
        />
      </div>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
.profile-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.profile-topbar,
.profile-summary,
.profile-action-card {
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 16px 28px var(--theme-shadow-soft);
}

.profile-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-radius: 22px;
  background: var(--theme-modal-bg);
}

.profile-topbar-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.profile-topbar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(180deg, var(--theme-brand-bg-start), var(--theme-brand-bg-end));
  color: var(--theme-accent-contrast);
  font-size: 18px;
  box-shadow: 0 10px 18px var(--theme-brand-shadow);
}

.profile-topbar-copy {
  min-width: 0;
}

.profile-topbar-title {
  margin: 0;
  color: var(--theme-title);
  font-size: 24px;
  line-height: 1.2;
  font-weight: 800;
}

.profile-topbar .warm-page-desc {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.profile-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.profile-summary,
.profile-action-card {
  border-radius: 24px;
  background: var(--theme-modal-bg);
  padding: 18px;
}

.profile-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.profile-summary-main {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.profile-avatar {
  flex: 0 0 auto;
  background: linear-gradient(180deg, var(--theme-brand-bg-start), var(--theme-brand-bg-end));
  color: var(--theme-accent-contrast);
  font-size: 30px;
  font-weight: 700;
  box-shadow: 0 16px 28px var(--theme-brand-shadow);
}

.profile-avatar-button {
  width: 92px;
  height: 92px;
  padding: 0;
  border: 0;
  overflow: hidden;
  border-radius: 50%;

  img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
}

.profile-avatar.is-previewable {
  cursor: zoom-in;
}

.profile-avatar-small {
  font-size: 26px;
}

.profile-avatar-preview-mask {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  cursor: zoom-out;

  img {
    max-width: min(80vw, 520px);
    max-height: 80vh;
    border-radius: 16px;
    box-shadow: 0 24px 48px rgba(0, 0, 0, 0.28);
  }
}

.profile-summary-copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.profile-name-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;

  h2 {
    margin: 0;
    color: var(--theme-title);
    font-size: 24px;
    line-height: 1.2;
    font-weight: 800;
  }
}

.profile-role-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: var(--theme-pill-bg);
  color: var(--theme-pill-text);
  font-size: 12px;
  font-weight: 700;
}

.profile-email {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.profile-business-id {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  max-width: 100%;
  padding: 8px 10px;
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  color: var(--theme-title);
  font-size: 13px;
  line-height: 1.5;

  span {
    min-width: 0;
    word-break: break-all;
  }
}

.profile-copy-btn {
  color: var(--theme-link);
  border-radius: 10px;
}

.profile-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(160px, 1fr));
  gap: 12px;
  min-width: min(360px, 100%);
}

.profile-stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--theme-summary-bg);
  border: 1px solid var(--theme-panel-border);

  span {
    color: var(--text-secondary);
    font-size: 12px;
    line-height: 1.5;
  }

  strong {
    color: var(--theme-title);
    font-size: 24px;
    line-height: 1.1;
    font-weight: 800;
  }
}

.profile-section-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 14px;

  h3 {
    margin: 0;
    color: var(--theme-title);
    font-size: 18px;
    line-height: 1.2;
    font-weight: 800;
  }

  span {
    color: var(--text-secondary);
    font-size: 13px;
    line-height: 1.6;
  }
}

.profile-actions {
  display: block;
}

.profile-settings-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.profile-setting-block {
  padding-top: 14px;
  border-top: 1px solid var(--theme-border);
}

.profile-setting-block:first-child {
  padding-top: 0;
  border-top: none;
}

.profile-setting-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 14px;

  h4 {
    margin: 0;
    color: var(--theme-title);
    font-size: 16px;
    line-height: 1.2;
    font-weight: 800;
  }

  span {
    color: var(--text-secondary);
    font-size: 13px;
    line-height: 1.6;
  }
}

.profile-setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.profile-setting-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;

  h4 {
    margin: 0;
    color: var(--theme-title);
    font-size: 16px;
    line-height: 1.2;
    font-weight: 800;
  }

  span {
    color: var(--text-secondary);
    font-size: 13px;
    line-height: 1.6;
  }
}

.profile-setting-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex: 0 0 auto;
}

.profile-setting-controls-username {
  min-width: min(420px, 100%);

  :deep(.ant-input) {
    min-width: 220px;
  }
}

.profile-toggle-btn {
  height: 36px;
  padding-inline: 14px;
  border-radius: 12px;
  border-color: var(--theme-panel-border-strong);
  background: var(--theme-panel-bg-strong);
  color: var(--theme-accent-text);
  font-weight: 700;
}

.profile-avatar-panel {
  display: contents;
}

.profile-password-form {
  margin-top: 14px;
}

.profile-password-actions {
  display: flex;
  justify-content: flex-start;
  margin-top: 16px;
}

@media (max-width: 980px) {
  .profile-summary {
    flex-direction: column;
    align-items: flex-start;
  }

  .profile-stats {
    width: 100%;
    min-width: 0;
  }
}

@media (max-width: 640px) {
  .profile-page {
    gap: 12px;
  }

  .profile-topbar,
  .profile-summary,
  .profile-action-card {
    padding: 14px;
    border-radius: 20px;
  }

  .profile-summary-main,
  .profile-setting-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .profile-setting-controls,
  .profile-setting-controls-username {
    width: 100%;
  }

  .profile-setting-controls {
    justify-content: flex-start;
  }

  .profile-setting-controls-username {
    :deep(.ant-input) {
      min-width: 0;
      width: 100%;
    }
  }

  .profile-stats {
    grid-template-columns: 1fr;
  }
}
</style>
