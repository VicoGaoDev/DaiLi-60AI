<script setup lang="ts">
import { computed, h, reactive, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { message, notification } from "ant-design-vue";
import {
  LockOutlined,
  MailOutlined,
  MobileOutlined,
  ThunderboltOutlined,
  UserAddOutlined,
  UserOutlined,
} from "@ant-design/icons-vue";
import {
  checkLoginEmail,
  checkLoginPhone,
  checkRegistrationEmail,
  checkRegistrationPhone,
  forgotPassword as apiForgotPassword,
  login as apiLogin,
  register as apiRegister,
  validatePromoCode,
} from "@/api/auth";
import { validateInviteCode } from "@/api/inviteRewards";
import { NEW_USER_TRIAL_CREDITS, PHONE_USER_TRIAL_CREDITS, PROMO_CODE_REWARD_CREDITS } from "@/lib/auth";
import {
  CODE_RESEND_SECONDS,
  getBlockedRegistrationEmailReason,
  isPhoneAccount,
  isValidEmail,
  isValidPhone,
  normalizePhone,
} from "@/lib/authAccount";
import { loadCloudbaseAuth, preloadCloudbaseAuth } from "@/lib/cloudbaseLazy";
import { useAuthStore } from "@/stores/auth";

const props = defineProps<{
  open: boolean;
  tab: "login" | "register";
  lockedPromoCode?: string;
  seedPromoCode?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:tab": ["login" | "register"];
  "logged-in": [];
  registered: [kind: "invite" | "promo" | "plain"];
  "invite-cleared": [];
}>();

const auth = useAuthStore();
const authInputPrefixStyle = { color: "var(--theme-input-prefix-color)" };

const registerChannel = ref<"email" | "phone">("phone");
const loginForm = reactive({ account: "", password: "" });
const loginLoading = ref(false);
const forgotPasswordDialogOpen = ref(false);
const forgotPasswordChannel = ref<"email" | "phone">("email");
const forgotPasswordForm = reactive({
  email: "",
  phone: "",
  verificationCode: "",
  verificationId: "",
  newPassword: "",
  confirmPassword: "",
});
const forgotPasswordLoading = ref(false);
const forgotPasswordCodeLoading = ref(false);
const forgotPasswordCountdown = ref(0);
let forgotPasswordTimer: number | null = null;
const registerForm = reactive({
  email: "",
  phone: "",
  verificationCode: "",
  verificationId: "",
  username: "",
  password: "",
  confirmPassword: "",
  promoCode: "",
  agreedTerms: false,
});
const registerLoading = ref(false);
const registerCodeLoading = ref(false);
const registerCountdown = ref(0);
let registerTimer: number | null = null;

const modalOpen = computed({
  get: () => props.open,
  set: (value) => emit("update:open", value),
});

const authTab = computed({
  get: () => props.tab,
  set: (value) => emit("update:tab", value),
});

function normalizeInviteCode(code?: string | null) {
  return (code || "").trim().toUpperCase().replace(/\s+/g, "");
}

function isPersonalInviteCodeValue(code?: string | null) {
  return /^U[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{7}$/.test(normalizeInviteCode(code));
}

function applyPromoCode() {
  const locked = normalizeInviteCode(props.lockedPromoCode);
  if (locked) {
    registerForm.promoCode = locked;
    return;
  }
  if (registerForm.promoCode.trim()) return;
  const seed = normalizeInviteCode(props.seedPromoCode);
  if (seed) registerForm.promoCode = seed;
}

function startRegisterCountdown() {
  if (registerTimer) window.clearInterval(registerTimer);
  registerCountdown.value = CODE_RESEND_SECONDS;
  registerTimer = window.setInterval(() => {
    registerCountdown.value -= 1;
    if (registerCountdown.value <= 0 && registerTimer) {
      window.clearInterval(registerTimer);
      registerTimer = null;
    }
  }, 1000);
}

function resetAuthForms() {
  loginForm.account = "";
  loginForm.password = "";
  registerChannel.value = "phone";
  registerForm.email = "";
  registerForm.phone = "";
  registerForm.verificationCode = "";
  registerForm.verificationId = "";
  registerForm.username = "";
  registerForm.password = "";
  registerForm.confirmPassword = "";
  registerForm.promoCode = "";
  registerForm.agreedTerms = false;
  registerCountdown.value = 0;
}

function resetForgotPasswordForm() {
  forgotPasswordChannel.value = "email";
  forgotPasswordForm.email = "";
  forgotPasswordForm.phone = "";
  forgotPasswordForm.verificationCode = "";
  forgotPasswordForm.verificationId = "";
  forgotPasswordForm.newPassword = "";
  forgotPasswordForm.confirmPassword = "";
  forgotPasswordCountdown.value = 0;
  if (forgotPasswordTimer) {
    window.clearInterval(forgotPasswordTimer);
    forgotPasswordTimer = null;
  }
}

function startForgotPasswordCountdown() {
  if (forgotPasswordTimer) window.clearInterval(forgotPasswordTimer);
  forgotPasswordCountdown.value = CODE_RESEND_SECONDS;
  forgotPasswordTimer = window.setInterval(() => {
    forgotPasswordCountdown.value -= 1;
    if (forgotPasswordCountdown.value <= 0 && forgotPasswordTimer) {
      window.clearInterval(forgotPasswordTimer);
      forgotPasswordTimer = null;
    }
  }, 1000);
}

function openForgotPasswordDialog() {
  const account = loginForm.account.trim();
  if (isPhoneAccount(account)) {
    forgotPasswordChannel.value = "phone";
    forgotPasswordForm.phone = normalizePhone(account);
  } else {
    forgotPasswordChannel.value = "email";
    forgotPasswordForm.email = account.includes("@") ? account : "";
  }
  forgotPasswordDialogOpen.value = true;
  emit("update:open", false);
}

watch(
  () => [props.open, props.tab, props.lockedPromoCode, props.seedPromoCode] as const,
  ([open, tab]) => {
    if (!open) return;
    if (tab === "register") {
      applyPromoCode();
      preloadCloudbaseAuth();
    }
  },
);

watch(
  () => registerForm.email,
  () => {
    if (registerChannel.value === "email") registerForm.verificationId = "";
  },
);

watch(
  () => registerForm.phone,
  () => {
    if (registerChannel.value === "phone") registerForm.verificationId = "";
  },
);

watch(registerChannel, () => {
  registerForm.verificationCode = "";
  registerForm.verificationId = "";
  registerCountdown.value = 0;
});

watch(forgotPasswordChannel, () => {
  forgotPasswordForm.verificationCode = "";
  forgotPasswordForm.verificationId = "";
  forgotPasswordCountdown.value = 0;
});

watch(
  () => forgotPasswordForm.email,
  () => {
    if (forgotPasswordChannel.value === "email") forgotPasswordForm.verificationId = "";
  },
);

watch(
  () => forgotPasswordForm.phone,
  () => {
    if (forgotPasswordChannel.value === "phone") forgotPasswordForm.verificationId = "";
  },
);

async function handleLoginSubmit() {
  if (!loginForm.account || !loginForm.password) {
    message.warning("请输入账号和密码");
    return;
  }
  loginLoading.value = true;
  try {
    const res = await apiLogin(loginForm.account, loginForm.password);
    auth.setAuth(res.token, res.user);
    message.success("登录成功");
    emit("update:open", false);
    resetAuthForms();
    emit("logged-in");
  } catch (err: any) {
    message.error(err.response?.data?.detail || "登录失败");
  } finally {
    loginLoading.value = false;
  }
}

async function handleSendForgotPasswordCode() {
  if (forgotPasswordChannel.value === "email") {
    if (!forgotPasswordForm.email) {
      message.warning("请输入邮箱");
      return;
    }
    if (!isValidEmail(forgotPasswordForm.email)) {
      message.warning("邮箱格式不正确");
      return;
    }
    forgotPasswordCodeLoading.value = true;
    const email = forgotPasswordForm.email.trim();
    try {
      await checkLoginEmail(email);
      if (forgotPasswordForm.email.trim() !== email) return;
      const { sendPasswordResetEmailCode } = await loadCloudbaseAuth();
      forgotPasswordForm.verificationId = await sendPasswordResetEmailCode(email);
      if (forgotPasswordForm.email.trim() !== email) return;
      startForgotPasswordCountdown();
      message.success("验证码已发送，请检查邮箱");
    } catch (err: any) {
      forgotPasswordForm.verificationId = "";
      message.error(err.response?.data?.detail || err.message || "验证码发送失败");
    } finally {
      forgotPasswordCodeLoading.value = false;
    }
    return;
  }

  if (!isValidPhone(forgotPasswordForm.phone)) {
    message.warning("请输入正确的手机号");
    return;
  }
  forgotPasswordCodeLoading.value = true;
  const phone = normalizePhone(forgotPasswordForm.phone);
  try {
    await checkLoginPhone(phone);
    if (normalizePhone(forgotPasswordForm.phone) !== phone) return;
    const { sendPasswordResetPhoneCode } = await loadCloudbaseAuth();
    const verificationId = await sendPasswordResetPhoneCode(phone);
    if (normalizePhone(forgotPasswordForm.phone) !== phone) return;
    forgotPasswordForm.verificationId = verificationId;
    startForgotPasswordCountdown();
    message.success("验证码已发送，请查收短信");
  } catch (err: any) {
    forgotPasswordForm.verificationId = "";
    message.error(err.response?.data?.detail || err.message || "验证码发送失败");
  } finally {
    forgotPasswordCodeLoading.value = false;
  }
}

async function handleForgotPasswordSubmit() {
  const isPhoneReset = forgotPasswordChannel.value === "phone";
  const accountReady = isPhoneReset ? forgotPasswordForm.phone : forgotPasswordForm.email;
  if (!accountReady || !forgotPasswordForm.verificationCode || !forgotPasswordForm.newPassword) {
    message.warning("请完整填写找回密码信息");
    return;
  }
  if (isPhoneReset) {
    if (!isValidPhone(forgotPasswordForm.phone)) {
      message.warning("请输入正确的手机号");
      return;
    }
  } else if (!isValidEmail(forgotPasswordForm.email)) {
    message.warning("邮箱格式不正确");
    return;
  }
  if (!/^\d{6}$/.test(forgotPasswordForm.verificationCode.trim())) {
    message.warning("请输入正确的 6 位验证码");
    return;
  }
  if (!forgotPasswordForm.verificationId) {
    message.warning(isPhoneReset ? "请先获取短信验证码" : "请先获取邮箱验证码");
    return;
  }
  if (forgotPasswordForm.newPassword.length < 6) {
    message.warning("新密码至少6位");
    return;
  }
  if (forgotPasswordForm.newPassword !== forgotPasswordForm.confirmPassword) {
    message.warning("两次密码不一致");
    return;
  }
  forgotPasswordLoading.value = true;
  try {
    await apiForgotPassword({
      email: isPhoneReset ? undefined : forgotPasswordForm.email.trim(),
      phone: isPhoneReset ? normalizePhone(forgotPasswordForm.phone) : undefined,
      verificationCode: forgotPasswordForm.verificationCode.trim(),
      verificationId: forgotPasswordForm.verificationId,
      newPassword: forgotPasswordForm.newPassword,
    });
    message.success("密码重置成功，请使用新密码登录");
    loginForm.account = isPhoneReset ? normalizePhone(forgotPasswordForm.phone) : forgotPasswordForm.email.trim();
    loginForm.password = "";
    resetForgotPasswordForm();
    emit("update:tab", "login");
    forgotPasswordDialogOpen.value = false;
    emit("update:open", true);
  } catch (err: any) {
    message.error(err.response?.data?.detail || err.message || "密码重置失败");
  } finally {
    forgotPasswordLoading.value = false;
  }
}

async function handleSendRegisterCode() {
  if (registerChannel.value === "email") {
    if (!registerForm.email) {
      message.warning("请输入邮箱");
      return;
    }
    if (!isValidEmail(registerForm.email)) {
      message.warning("邮箱格式不正确");
      return;
    }
    const blockedReason = getBlockedRegistrationEmailReason(registerForm.email);
    if (blockedReason) {
      message.warning(blockedReason);
      return;
    }
    registerCodeLoading.value = true;
    const email = registerForm.email.trim().toLowerCase();
    try {
      await checkRegistrationEmail(email);
      if (registerForm.email.trim().toLowerCase() !== email) return;
      const { sendRegisterEmailCode } = await loadCloudbaseAuth();
      const verificationId = await sendRegisterEmailCode(email);
      if (registerForm.email.trim().toLowerCase() !== email) return;
      registerForm.verificationId = verificationId;
      startRegisterCountdown();
      message.success("验证码已发送，请检查邮箱");
    } catch (err: any) {
      registerForm.verificationId = "";
      message.error(err.response?.data?.detail || err.message || "验证码发送失败");
    } finally {
      registerCodeLoading.value = false;
    }
    return;
  }

  if (!isValidPhone(registerForm.phone)) {
    message.warning("请输入正确的手机号");
    return;
  }
  registerCodeLoading.value = true;
  const phone = normalizePhone(registerForm.phone);
  try {
    await checkRegistrationPhone(phone);
    if (normalizePhone(registerForm.phone) !== phone) return;
    const { sendRegisterPhoneCode } = await loadCloudbaseAuth();
    const verificationId = await sendRegisterPhoneCode(phone);
    if (normalizePhone(registerForm.phone) !== phone) return;
    registerForm.verificationId = verificationId;
    startRegisterCountdown();
    message.success("验证码已发送，请查收短信");
  } catch (err: any) {
    registerForm.verificationId = "";
    message.error(err.response?.data?.detail || err.message || "验证码发送失败");
  } finally {
    registerCodeLoading.value = false;
  }
}

async function handleRegisterSubmit() {
  const isPhoneRegister = registerChannel.value === "phone";
  const accountReady = isPhoneRegister ? registerForm.phone : registerForm.email;
  if (!accountReady || !registerForm.verificationCode || !registerForm.password) {
    message.warning("请完整填写注册信息");
    return;
  }
  if (!isPhoneRegister && !registerForm.username) {
    message.warning("请完整填写注册信息");
    return;
  }
  if (registerChannel.value === "email") {
    if (!isValidEmail(registerForm.email)) {
      message.warning("邮箱格式不正确");
      return;
    }
    const blockedReason = getBlockedRegistrationEmailReason(registerForm.email);
    if (blockedReason) {
      message.warning(blockedReason);
      return;
    }
  } else if (!isValidPhone(registerForm.phone)) {
    message.warning("请输入正确的手机号");
    return;
  }
  if (registerForm.password.length < 6) {
    message.warning("密码至少6位");
    return;
  }
  if (registerForm.password !== registerForm.confirmPassword) {
    message.warning("两次密码不一致");
    return;
  }
  if (!/^\d{6}$/.test(registerForm.verificationCode.trim())) {
    message.warning("请输入正确的 6 位验证码");
    return;
  }
  if (!registerForm.verificationId) {
    message.warning(registerChannel.value === "email" ? "请先获取邮箱验证码" : "请先获取短信验证码");
    return;
  }
  let inviteOrPromoCode = normalizeInviteCode(registerForm.promoCode);
  let isPersonalInviteRegistration = isPersonalInviteCodeValue(inviteOrPromoCode);
  if (inviteOrPromoCode) {
    try {
      if (isPersonalInviteRegistration) {
        await validateInviteCode(inviteOrPromoCode);
      } else {
        await validatePromoCode(inviteOrPromoCode);
      }
    } catch {
      message.warning("邀请已失效");
      registerForm.promoCode = "";
      inviteOrPromoCode = "";
      isPersonalInviteRegistration = false;
      emit("invite-cleared");
    }
  }
  if (!registerForm.agreedTerms) {
    message.warning("请先阅读并同意用户协议和隐私政策");
    return;
  }
  registerLoading.value = true;
  try {
    const res = await apiRegister(
      inviteOrPromoCode || undefined,
      {
        verificationCode: registerForm.verificationCode.trim(),
        verificationId: registerForm.verificationId,
      },
      registerChannel.value === "email"
        ? {
            email: registerForm.email.trim(),
            username: registerForm.username.trim(),
            password: registerForm.password,
          }
        : {
            phone: normalizePhone(registerForm.phone),
            password: registerForm.password,
          },
    );
    auth.setAuth(res.token, res.user);
    message.success("注册成功");
    const trialCredits = isPhoneRegister ? PHONE_USER_TRIAL_CREDITS : NEW_USER_TRIAL_CREDITS;
    notification.success({
      message: "赠送积分已到账",
      description: inviteOrPromoCode && !isPersonalInviteRegistration
        ? `新用户注册赠送的 ${trialCredits} 个试用积分和推广码额外奖励的 ${PROMO_CODE_REWARD_CREDITS} 个积分已到账。`
        : isPersonalInviteRegistration
          ? `新用户注册赠送的 ${trialCredits} 个试用积分已到账，邀请关系已绑定。`
          : `新用户注册赠送的 ${trialCredits} 个试用积分已到账。`,
      placement: "topRight",
      duration: 6,
    });
    emit("update:open", false);
    resetAuthForms();
    emit("registered", isPersonalInviteRegistration ? "invite" : inviteOrPromoCode ? "promo" : "plain");
    emit("logged-in");
  } catch (err: any) {
    message.error(err.response?.data?.detail || err.message || "注册失败");
  } finally {
    registerLoading.value = false;
  }
}

function sendCodeLabel(loading: boolean, verificationId: string, countdown: number) {
  if (loading) return "发送中...";
  if (countdown > 0) return `${countdown}s`;
  return verificationId ? "重新发送" : "发送验证码";
}
</script>

<template>
  <a-modal
    v-model:open="modalOpen"
    :title="null"
    :footer="null"
    :width="420"
    centered
    @after-close="resetAuthForms"
  >
    <a-tabs v-model:activeKey="authTab" centered class="auth-tabs">
      <a-tab-pane key="login" tab="登录">
        <a-form
          class="auth-form"
          layout="vertical"
          :model="loginForm"
          @finish="handleLoginSubmit"
        >
          <a-form-item label="邮箱 / 用户名 / 手机号">
            <a-input
              v-model:value="loginForm.account"
              size="large"
              placeholder="请输入邮箱、用户名或手机号"
              :prefix="h(UserOutlined, { style: authInputPrefixStyle })"
            />
          </a-form-item>
          <a-form-item label="密码">
            <a-input-password
              v-model:value="loginForm.password"
              size="large"
              placeholder="请输入密码"
              :prefix="h(LockOutlined, { style: authInputPrefixStyle })"
              @press-enter="handleLoginSubmit"
            />
          </a-form-item>
          <div class="auth-row-action">
            <a @click="openForgotPasswordDialog">忘记密码？</a>
          </div>
          <a-form-item style="margin-bottom: 8px">
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              :loading="loginLoading"
              block
              class="warm-primary-btn"
            >
              <template #icon><ThunderboltOutlined /></template>
              {{ loginLoading ? "登录中..." : "登录" }}
            </a-button>
          </a-form-item>
          <div class="auth-switch-hint">用户名重复时，请改用邮箱或手机号登录</div>
          <div class="auth-switch-hint" style="margin-top: 6px">
            还没有账号？<a @click="authTab = 'register'">立即注册</a>
          </div>
        </a-form>
      </a-tab-pane>

      <a-tab-pane key="register" tab="注册">
        <div class="auth-channel-switch">
          <button type="button" class="auth-channel-btn" :class="{ active: registerChannel === 'email' }" @click="registerChannel = 'email'">
            邮箱注册
          </button>
          <button type="button" class="auth-channel-btn" :class="{ active: registerChannel === 'phone' }" @click="registerChannel = 'phone'">
            手机号注册
          </button>
        </div>
        <a-form class="auth-form" layout="vertical" :model="registerForm" @finish="handleRegisterSubmit">
          <a-form-item v-if="registerChannel === 'email'" label="邮箱">
            <a-input
              v-model:value="registerForm.email"
              size="large"
              placeholder="请输入常用邮箱"
              :prefix="h(MailOutlined, { style: authInputPrefixStyle })"
              :maxlength="255"
            />
          </a-form-item>
          <a-form-item v-else label="手机号">
            <a-input
              v-model:value="registerForm.phone"
              size="large"
              placeholder="请输入 11 位手机号"
              :prefix="h(MobileOutlined, { style: authInputPrefixStyle })"
              :maxlength="11"
            />
          </a-form-item>
          <a-form-item label="验证码">
            <div class="auth-code-row">
              <a-input
                v-model:value="registerForm.verificationCode"
                size="large"
                placeholder="请输入 6 位验证码"
                :maxlength="6"
                @press-enter="handleRegisterSubmit"
              />
              <a-button
                size="large"
                class="auth-code-btn"
                :loading="registerCodeLoading"
                :disabled="registerCountdown > 0"
                @click="handleSendRegisterCode"
              >
                {{ sendCodeLabel(registerCodeLoading, registerForm.verificationId, registerCountdown) }}
              </a-button>
            </div>
          </a-form-item>
          <a-form-item v-if="registerChannel === 'email'" label="用户名">
            <a-input
              v-model:value="registerForm.username"
              size="large"
              placeholder="2-20 个字符"
              :prefix="h(UserOutlined, { style: authInputPrefixStyle })"
              :maxlength="20"
            />
          </a-form-item>
          <a-form-item label="密码">
            <a-input-password
              v-model:value="registerForm.password"
              size="large"
              placeholder="至少 6 位"
              :prefix="h(LockOutlined, { style: authInputPrefixStyle })"
            />
          </a-form-item>
          <a-form-item label="确认密码">
            <a-input-password
              v-model:value="registerForm.confirmPassword"
              size="large"
              placeholder="请再次输入密码"
              :prefix="h(LockOutlined, { style: authInputPrefixStyle })"
              @press-enter="handleRegisterSubmit"
            />
          </a-form-item>
          <a-form-item class="auth-agreement-item">
            <a-checkbox v-model:checked="registerForm.agreedTerms">
              我同意
              <RouterLink to="/user-agreement" target="_blank">用户协议</RouterLink>
              和
              <RouterLink to="/privacy-policy" target="_blank">隐私政策</RouterLink>
            </a-checkbox>
          </a-form-item>
          <a-form-item style="margin-bottom: 8px">
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              :loading="registerLoading"
              :disabled="!registerForm.agreedTerms"
              block
              class="warm-primary-btn"
            >
              <template #icon><UserAddOutlined /></template>
              {{ registerLoading ? "注册中..." : "注册" }}
            </a-button>
          </a-form-item>
          <div v-if="registerChannel === 'phone'" class="auth-switch-hint">
            注册后可用手机号 + 密码登录，用户名会按手机尾号自动生成
          </div>
          <div class="auth-switch-hint" :style="registerChannel === 'phone' ? 'margin-top: 6px' : undefined">
            已有账号？<a @click="authTab = 'login'">去登录</a>
          </div>
        </a-form>
      </a-tab-pane>
    </a-tabs>
  </a-modal>

  <a-modal
    v-model:open="forgotPasswordDialogOpen"
    title="找回密码"
    :footer="null"
    :width="420"
    centered
    @after-close="resetForgotPasswordForm"
  >
    <a-form class="auth-form forgot-password-form" layout="vertical" :model="forgotPasswordForm" @finish="handleForgotPasswordSubmit">
      <div class="auth-channel-switch">
        <button type="button" class="auth-channel-btn" :class="{ active: forgotPasswordChannel === 'email' }" @click="forgotPasswordChannel = 'email'">
          邮箱
        </button>
        <button type="button" class="auth-channel-btn" :class="{ active: forgotPasswordChannel === 'phone' }" @click="forgotPasswordChannel = 'phone'">
          手机号
        </button>
      </div>
      <a-form-item v-if="forgotPasswordChannel === 'email'" label="邮箱">
        <a-input
          v-model:value="forgotPasswordForm.email"
          size="large"
          placeholder="请输入已绑定邮箱"
          :prefix="h(MailOutlined, { style: authInputPrefixStyle })"
          :maxlength="255"
        />
      </a-form-item>
      <a-form-item v-else label="手机号">
        <a-input
          v-model:value="forgotPasswordForm.phone"
          size="large"
          placeholder="请输入已绑定手机号"
          :prefix="h(MobileOutlined, { style: authInputPrefixStyle })"
          :maxlength="11"
        />
      </a-form-item>
      <a-form-item label="验证码">
        <div class="auth-code-row">
          <a-input
            v-model:value="forgotPasswordForm.verificationCode"
            size="large"
            placeholder="请输入 6 位验证码"
            :maxlength="6"
          />
          <a-button
            size="large"
            class="auth-code-btn"
            :loading="forgotPasswordCodeLoading"
            :disabled="forgotPasswordCountdown > 0"
            @click="handleSendForgotPasswordCode"
          >
            {{ sendCodeLabel(forgotPasswordCodeLoading, forgotPasswordForm.verificationId, forgotPasswordCountdown) }}
          </a-button>
        </div>
      </a-form-item>
      <a-form-item label="新密码">
        <a-input-password
          v-model:value="forgotPasswordForm.newPassword"
          size="large"
          placeholder="至少 6 位"
          :prefix="h(LockOutlined, { style: authInputPrefixStyle })"
        />
      </a-form-item>
      <a-form-item label="确认新密码">
        <a-input-password
          v-model:value="forgotPasswordForm.confirmPassword"
          size="large"
          placeholder="请再次输入新密码"
          :prefix="h(LockOutlined, { style: authInputPrefixStyle })"
          @press-enter="handleForgotPasswordSubmit"
        />
      </a-form-item>
      <a-form-item style="margin-bottom: 8px">
        <a-button
          type="primary"
          html-type="submit"
          size="large"
          :loading="forgotPasswordLoading"
          block
          class="warm-primary-btn"
        >
          <template #icon><LockOutlined /></template>
          {{ forgotPasswordLoading ? "重置中..." : "重置密码" }}
        </a-button>
      </a-form-item>
      <div class="auth-switch-hint">
        想起密码了？<a @click="forgotPasswordDialogOpen = false; authTab = 'login'; emit('update:open', true)">返回登录</a>
      </div>
    </a-form>
  </a-modal>
</template>

<style scoped lang="scss">
.auth-channel-switch {
  display: flex;
  gap: 8px;
  margin: 8px 0 4px;
}

.auth-channel-btn {
  flex: 1;
  height: 36px;
  border: 1px solid var(--theme-border);
  border-radius: 10px;
  background: transparent;
  color: var(--theme-text-muted);
  font-weight: 600;
  cursor: pointer;

  &.active {
    border-color: var(--theme-accent);
    color: var(--theme-accent-text);
    background: var(--theme-panel-bg-soft);
  }
}

.auth-tabs {
  :deep(.ant-tabs-nav) {
    margin-bottom: 0;
  }

  :deep(.ant-tabs-tab) {
    font-weight: 700;
    font-size: 15px;
    color: var(--theme-text-muted);
  }

  :deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
    color: var(--theme-accent-text) !important;
  }

  :deep(.ant-tabs-ink-bar) {
    background: var(--theme-accent);
    height: 3px;
    border-radius: 2px;
  }
}

.auth-form {
  margin-top: 4px;

  :deep(.ant-form-item) {
    margin-bottom: 14px;
  }

  :deep(.ant-form-item-label) {
    padding-bottom: 4px;
  }

  :deep(.ant-form-item-label > label) {
    height: 20px;
    font-size: 13px;
  }

  .auth-agreement-item {
    margin-bottom: 10px;
  }
}

.auth-switch-hint {
  text-align: center;
  font-size: 13px;
  color: var(--theme-text-muted);

  a {
    color: var(--theme-link);
    font-weight: 600;
    cursor: pointer;

    &:hover {
      color: var(--theme-link-hover);
    }
  }
}

.auth-row-action {
  margin: -4px 0 12px;
  text-align: right;
  font-size: 13px;

  a {
    color: var(--theme-link);
    font-weight: 600;
    cursor: pointer;

    &:hover {
      color: var(--theme-link-hover);
    }
  }
}

.auth-code-row {
  display: flex;
  gap: 10px;

  > :first-child {
    flex: 1;
  }
}

.auth-code-btn {
  flex: 0 0 auto;
}
</style>
