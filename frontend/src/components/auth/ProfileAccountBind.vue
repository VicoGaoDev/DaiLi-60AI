<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { message } from "ant-design-vue";
import { bindEmail, bindPhone, checkRegistrationEmail, checkRegistrationPhone } from "@/api/auth";
import {
  CODE_RESEND_SECONDS,
  getBlockedRegistrationEmailReason,
  isValidEmail,
  isValidPhone,
  maskEmail,
  maskPhone,
  normalizePhone,
} from "@/lib/authAccount";
import { loadCloudbaseAuth } from "@/lib/cloudbaseLazy";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const emailForm = reactive({
  email: "",
  verificationCode: "",
  verificationId: "",
});
const phoneForm = reactive({
  phone: "",
  verificationCode: "",
  verificationId: "",
});
const emailLoading = ref(false);
const emailCodeLoading = ref(false);
const emailCountdown = ref(0);
const phoneLoading = ref(false);
const phoneCodeLoading = ref(false);
const phoneCountdown = ref(0);
let emailTimer: number | null = null;
let phoneTimer: number | null = null;

function startCountdown(target: "email" | "phone") {
  const counter = target === "email" ? emailCountdown : phoneCountdown;
  if (target === "email" && emailTimer) window.clearInterval(emailTimer);
  if (target === "phone" && phoneTimer) window.clearInterval(phoneTimer);
  counter.value = CODE_RESEND_SECONDS;
  const timer = window.setInterval(() => {
    counter.value -= 1;
    if (counter.value <= 0) {
      window.clearInterval(timer);
      if (target === "email") emailTimer = null;
      else phoneTimer = null;
    }
  }, 1000);
  if (target === "email") emailTimer = timer;
  else phoneTimer = timer;
}

watch(
  () => emailForm.email,
  () => {
    emailForm.verificationId = "";
  },
);

watch(
  () => phoneForm.phone,
  () => {
    phoneForm.verificationId = "";
  },
);

async function handleSendEmailCode() {
  if (!isValidEmail(emailForm.email)) {
    message.warning("邮箱格式不正确");
    return;
  }
  const blockedReason = getBlockedRegistrationEmailReason(emailForm.email);
  if (blockedReason) {
    message.warning(blockedReason);
    return;
  }
  emailCodeLoading.value = true;
  const email = emailForm.email.trim().toLowerCase();
  try {
    await checkRegistrationEmail(email);
    if (emailForm.email.trim().toLowerCase() !== email) return;
    const { sendBindEmailCode } = await loadCloudbaseAuth();
    const verificationId = await sendBindEmailCode(email);
    if (emailForm.email.trim().toLowerCase() !== email) return;
    emailForm.verificationId = verificationId;
    startCountdown("email");
    message.success("验证码已发送，请检查邮箱");
  } catch (err: any) {
    emailForm.verificationId = "";
    message.error(err.response?.data?.detail || err.message || "验证码发送失败");
  } finally {
    emailCodeLoading.value = false;
  }
}

async function handleBindEmail() {
  if (!isValidEmail(emailForm.email)) {
    message.warning("邮箱格式不正确");
    return;
  }
  const blockedReason = getBlockedRegistrationEmailReason(emailForm.email);
  if (blockedReason) {
    message.warning(blockedReason);
    return;
  }
  if (!/^\d{6}$/.test(emailForm.verificationCode.trim())) {
    message.warning("请输入正确的 6 位验证码");
    return;
  }
  if (!emailForm.verificationId) {
    message.warning("请先获取邮箱验证码");
    return;
  }
  emailLoading.value = true;
  try {
    const nextUser = await bindEmail({
      email: emailForm.email.trim(),
      verificationCode: emailForm.verificationCode.trim(),
      verificationId: emailForm.verificationId,
    });
    auth.updateUser(nextUser);
    emailForm.email = "";
    emailForm.verificationCode = "";
    emailForm.verificationId = "";
    message.success("邮箱绑定成功");
  } catch (err: any) {
    message.error(err.response?.data?.detail || err.message || "绑定失败");
  } finally {
    emailLoading.value = false;
  }
}

async function handleSendPhoneCode() {
  if (!isValidPhone(phoneForm.phone)) {
    message.warning("请输入正确的手机号");
    return;
  }
  phoneCodeLoading.value = true;
  const phone = normalizePhone(phoneForm.phone);
  try {
    await checkRegistrationPhone(phone);
    if (normalizePhone(phoneForm.phone) !== phone) return;
    const { sendBindPhoneCode } = await loadCloudbaseAuth();
    const verificationId = await sendBindPhoneCode(phone);
    if (normalizePhone(phoneForm.phone) !== phone) return;
    phoneForm.verificationId = verificationId;
    startCountdown("phone");
    message.success("验证码已发送，请查收短信");
  } catch (err: any) {
    phoneForm.verificationId = "";
    message.error(err.response?.data?.detail || err.message || "验证码发送失败");
  } finally {
    phoneCodeLoading.value = false;
  }
}

async function handleBindPhone() {
  if (!isValidPhone(phoneForm.phone)) {
    message.warning("请输入正确的手机号");
    return;
  }
  if (!/^\d{6}$/.test(phoneForm.verificationCode.trim())) {
    message.warning("请输入正确的 6 位验证码");
    return;
  }
  if (!phoneForm.verificationId) {
    message.warning("请先获取短信验证码");
    return;
  }
  phoneLoading.value = true;
  try {
    const nextUser = await bindPhone({
      phone: normalizePhone(phoneForm.phone),
      verificationCode: phoneForm.verificationCode.trim(),
      verificationId: phoneForm.verificationId,
    });
    auth.updateUser(nextUser);
    phoneForm.phone = "";
    phoneForm.verificationCode = "";
    phoneForm.verificationId = "";
    message.success("手机号绑定成功，之后可用手机号 + 密码登录");
  } catch (err: any) {
    message.error(err.response?.data?.detail || err.message || "绑定失败");
  } finally {
    phoneLoading.value = false;
  }
}

function sendCodeLabel(loading: boolean, verificationId: string, countdown: number) {
  if (loading) return "发送中...";
  if (countdown > 0) return `${countdown}s`;
  return verificationId ? "重新发送" : "发送验证码";
}
</script>

<template>
  <div class="profile-setting-block">
    <div class="profile-setting-row">
      <div class="profile-setting-info">
        <h4>绑定邮箱</h4>
        <span v-if="auth.user?.email">已绑定 {{ maskEmail(auth.user.email) }}{{ auth.user.password_set ? "，可用于邮箱登录。" : "。设置密码后可用邮箱登录。" }}</span>
        <span v-else>绑定需邮箱验证码，且邮箱未被占用。第一期不支持换绑。</span>
      </div>
    </div>
    <a-form v-if="!auth.user?.email" layout="vertical" class="profile-bind-form">
      <a-form-item label="邮箱">
        <a-input v-model:value="emailForm.email" placeholder="请输入常用邮箱" :maxlength="255" />
      </a-form-item>
      <a-form-item label="验证码">
        <div class="profile-code-row">
          <a-input v-model:value="emailForm.verificationCode" placeholder="请输入 6 位验证码" :maxlength="6" />
          <a-button :loading="emailCodeLoading" :disabled="emailCountdown > 0" @click="handleSendEmailCode">
            {{ sendCodeLabel(emailCodeLoading, emailForm.verificationId, emailCountdown) }}
          </a-button>
        </div>
      </a-form-item>
      <a-button type="primary" class="warm-primary-btn" :loading="emailLoading" @click="handleBindEmail">
        绑定邮箱
      </a-button>
    </a-form>
  </div>

  <div class="profile-setting-block">
    <div class="profile-setting-row">
      <div class="profile-setting-info">
        <h4>绑定手机号</h4>
        <span v-if="auth.user?.phone">已绑定 {{ maskPhone(auth.user.phone) }}，可用于手机号 + 密码登录。</span>
        <span v-else>绑定后可用手机号 + 密码登录。第一期不支持换绑。</span>
      </div>
    </div>
    <a-form v-if="!auth.user?.phone" layout="vertical" class="profile-bind-form">
      <a-form-item label="手机号">
        <a-input v-model:value="phoneForm.phone" placeholder="请输入 11 位手机号" :maxlength="11" />
      </a-form-item>
      <a-form-item label="验证码">
        <div class="profile-code-row">
          <a-input v-model:value="phoneForm.verificationCode" placeholder="请输入 6 位验证码" :maxlength="6" />
          <a-button :loading="phoneCodeLoading" :disabled="phoneCountdown > 0" @click="handleSendPhoneCode">
            {{ sendCodeLabel(phoneCodeLoading, phoneForm.verificationId, phoneCountdown) }}
          </a-button>
        </div>
      </a-form-item>
      <a-button type="primary" class="warm-primary-btn" :loading="phoneLoading" @click="handleBindPhone">
        绑定手机号
      </a-button>
    </a-form>
  </div>
</template>

<style scoped lang="scss">
.profile-setting-block {
  padding-top: 14px;
  border-top: 1px solid var(--theme-border);
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

.profile-bind-form {
  margin-top: 12px;
}

.profile-code-row {
  display: flex;
  gap: 10px;

  > :first-child {
    flex: 1;
  }
}
</style>
