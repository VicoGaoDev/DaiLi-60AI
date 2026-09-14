import cloudbase from "@cloudbase/js-sdk";

let app: ReturnType<typeof cloudbase.init> | null = null;

type CloudbaseErrorLike = {
  code?: string | number;
  message?: string;
  msg?: string;
  error?: string;
  error_description?: string;
  description?: string;
  details?: string;
  response?: {
    data?: {
      error_description?: string;
      message?: string;
      error?: string;
    };
  };
};

type VerificationInfo = {
  verification_id?: string;
};

function getEnvId() {
  const envId = (import.meta.env.VITE_CLOUDBASE_ENV_ID || "").trim();
  if (!envId) {
    throw new Error("CloudBase 环境 ID 未配置");
  }
  return envId;
}

function getAuth() {
  if (!app) {
    app = cloudbase.init({ env: getEnvId() });
  }
  return app.auth({ persistence: "session" });
}

function getErrorText(err: unknown) {
  const maybeError = (err || {}) as CloudbaseErrorLike;
  return [
    maybeError.code,
    maybeError.message,
    maybeError.msg,
    maybeError.error,
    maybeError.error_description,
    maybeError.description,
    maybeError.details,
    maybeError.response?.data?.error_description,
    maybeError.response?.data?.message,
    maybeError.response?.data?.error,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function mapCloudbaseAuthError(
  err: unknown,
  action: "sendCode" | "register" | "resetPassword",
  contact: "邮箱" | "手机号" = "邮箱",
) {
  const text = getErrorText(err);

  if (text.includes("environment id") || text.includes("env id")) {
    return "CloudBase 环境 ID 未配置";
  }
  if (text.includes("invalid email") || text.includes("email format")) {
    return "邮箱格式不正确";
  }
  if (
    text.includes("invalid phone")
    || text.includes("incorrect phone")
    || text.includes("incorrect number")
    || text.includes("phone number") && text.includes("format")
  ) {
    return "手机号格式不正确";
  }
  if (
    text.includes("already exists")
    || text.includes("already registered")
    || text.includes("email already")
    || text.includes("phone already")
    || text.includes("duplicate")
    || text.includes("is_user")
    || text.includes("已存在")
  ) {
    return `该${contact}已注册`;
  }
  if (
    text.includes("too many requests")
    || text.includes("too frequent")
    || text.includes("rate limit")
    || text.includes("exceed")
  ) {
    return action === "sendCode" ? "验证码发送过于频繁，请稍后再试" : "操作过于频繁，请稍后再试";
  }
  if (
    text.includes("verification code")
    || text.includes("verification_code")
    || text.includes("verify code")
    || text.includes("otp")
  ) {
    if (text.includes("expire") || text.includes("expired") || text.includes("timeout")) {
      return "验证码已过期，请重新获取";
    }
    if (
      text.includes("invalid")
      || text.includes("incorrect")
      || text.includes("wrong")
      || text.includes("mismatch")
      || text.includes("error")
      || text.includes("failed")
    ) {
      return "验证码错误";
    }
  }
  if (
    text.includes("weak password")
    || text.includes("password should")
    || text.includes("password is too short")
    || text.includes("password invalid")
    || text.includes("password format")
  ) {
    return "密码不符合要求，请使用至少 6 位密码";
  }

  if (action === "sendCode") {
    return "验证码发送失败，请稍后重试";
  }
  if (action === "resetPassword") {
    return "密码重置失败，请检查邮箱、验证码和新密码";
  }
  return "注册验证失败，请检查邮箱、验证码和密码";
}

async function sendEmailCode(email: string, usage: "SIGNUP" | "PASSWORD_RESET") {
  const auth = getAuth();
  try {
    const verification = await auth.getVerification({
      email: email.trim().toLowerCase(),
      usage,
    }) as VerificationInfo;
    if (!verification?.verification_id) {
      throw new Error("验证码发送失败，请稍后重试");
    }
    return verification.verification_id;
  } catch (err) {
    if (err instanceof Error && err.message === "验证码发送失败，请稍后重试") {
      throw err;
    }
    throw new Error(mapCloudbaseAuthError(err, "sendCode", "邮箱"));
  }
}

export function toCloudbasePhone(phone: string) {
  const digits = phone.replace(/\D/g, "");
  const normalized = digits.startsWith("86") && digits.length === 13 ? digits.slice(2) : digits;
  if (!/^1\d{10}$/.test(normalized)) {
    throw new Error("手机号格式不正确");
  }
  return `+86 ${normalized}`;
}

async function sendPhoneCode(phone: string, usage?: "SIGNUP") {
  const auth = getAuth();
  try {
    const payload = usage
      ? { phone_number: toCloudbasePhone(phone), usage }
      : { phone_number: toCloudbasePhone(phone) };
    const verification = await auth.getVerification(payload) as VerificationInfo;
    if (!verification?.verification_id) {
      throw new Error("验证码发送失败，请稍后重试");
    }
    return verification.verification_id;
  } catch (err) {
    if (err instanceof Error && (err.message === "验证码发送失败，请稍后重试" || err.message === "手机号格式不正确")) {
      throw err;
    }
    throw new Error(mapCloudbaseAuthError(err, "sendCode", "手机号"));
  }
}

export async function sendRegisterEmailCode(email: string) {
  return sendEmailCode(email, "SIGNUP");
}

export async function sendBindEmailCode(email: string) {
  return sendEmailCode(email, "SIGNUP");
}

export async function sendRegisterPhoneCode(phone: string) {
  return sendPhoneCode(phone, "SIGNUP");
}

export async function sendBindPhoneCode(phone: string) {
  return sendPhoneCode(phone, "SIGNUP");
}

export async function sendPasswordResetPhoneCode(phone: string) {
  return sendPhoneCode(phone);
}

export async function sendPasswordResetEmailCode(email: string) {
  const auth = getAuth();
  try {
    const verification = await auth.getVerification({
      email: email.trim().toLowerCase(),
    }) as VerificationInfo;
    if (!verification?.verification_id) {
      throw new Error("验证码发送失败，请稍后重试");
    }
    return verification.verification_id;
  } catch (err) {
    if (err instanceof Error && err.message === "验证码发送失败，请稍后重试") {
      throw err;
    }
    throw new Error(mapCloudbaseAuthError(err, "sendCode"));
  }
}

export async function registerCloudbaseAccount(email: string, code: string, password: string) {
  const auth = getAuth();
  try {
    await auth.signUp({
      email: email.trim().toLowerCase(),
      password,
      verification_code: code.trim(),
    });
  } catch (err) {
    throw new Error(mapCloudbaseAuthError(err, "register"));
  } finally {
    try {
      await auth.signOut();
    } catch {
      // ignore CloudBase sign-out failures after signup
    }
  }
}
