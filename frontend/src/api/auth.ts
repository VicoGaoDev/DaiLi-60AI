import client from "./client";
import type {
  LoginResponse,
  UserInfo,
  CreditLog,
  AnnouncementConfig,
  PromptHistoryItem,
  RedeemCreditResult,
  PromoCodeListResponse,
  PromoReferralListResponse,
  PromoReferralActivityListResponse,
} from "@/types";

export function login(account: string, password: string): Promise<LoginResponse> {
  return client.post("/auth/login", {
    account,
    username: account,
    password,
  });
}

export function checkRegistrationEmail(email: string): Promise<{ available: boolean }> {
  return client.post("/auth/register/email-check", { email });
}

export function checkRegistrationPhone(phone: string): Promise<{ available: boolean }> {
  return client.post("/auth/register/phone-check", { phone });
}

export function checkLoginPhone(phone: string): Promise<{ registered: boolean }> {
  return client.post("/auth/login/phone-check", { phone });
}

export function checkLoginEmail(email: string): Promise<{ registered: boolean }> {
  return client.post("/auth/login/email-check", { email });
}

export function register(
  promoCode?: string,
  verification?: { verificationCode: string; verificationId: string },
  account?: { email?: string; phone?: string; username?: string; password?: string },
): Promise<LoginResponse> {
  return client.post("/auth/register", {
    username: account?.username,
    email: account?.email,
    phone: account?.phone,
    password: account?.password,
    promo_code: promoCode?.trim() || undefined,
    verification_code: verification?.verificationCode,
    verification_id: verification?.verificationId,
  });
}

export function bindEmail(payload: {
  email: string;
  verificationCode: string;
  verificationId: string;
}): Promise<UserInfo> {
  return client.post("/auth/bind/email", {
    email: payload.email,
    verification_code: payload.verificationCode,
    verification_id: payload.verificationId,
  });
}

export function bindPhone(payload: {
  phone: string;
  verificationCode: string;
  verificationId: string;
}): Promise<UserInfo> {
  return client.post("/auth/bind/phone", {
    phone: payload.phone,
    verification_code: payload.verificationCode,
    verification_id: payload.verificationId,
  });
}

export function changePassword(oldPassword: string | undefined, newPassword: string): Promise<any> {
  return client.post("/auth/change-password", {
    old_password: oldPassword,
    new_password: newPassword,
  });
}

export function forgotPassword(payload: {
  email?: string;
  phone?: string;
  verificationCode: string;
  verificationId: string;
  newPassword: string;
}): Promise<{ message: string }> {
  return client.post("/auth/forgot-password", {
    email: payload.email,
    phone: payload.phone,
    verification_code: payload.verificationCode,
    verification_id: payload.verificationId,
    new_password: payload.newPassword,
  });
}

export function getMe(): Promise<UserInfo> {
  return client.get("/auth/me");
}

export function redeemCreditKey(key: string): Promise<RedeemCreditResult> {
  return client.post("/auth/redeem-key", { key });
}

export function updateProfile(payload: { username: string }): Promise<UserInfo> {
  return client.put("/auth/profile", payload);
}

export function uploadAvatar(file: File): Promise<UserInfo> {
  const formData = new FormData();
  formData.append("file", file);
  return client.post("/auth/avatar", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function getPromptHistory(): Promise<PromptHistoryItem[]> {
  return client.get("/auth/prompt-history");
}

export function deletePromptHistory(id: number): Promise<void> {
  return client.delete(`/auth/prompt-history/${id}`);
}

export function deletePromptOptimizeTask(id: number): Promise<void> {
  return client.delete(`/auth/prompt-optimize-tasks/${id}`);
}

export function getCreditLogs(params: {
  page?: number;
  page_size?: number;
  user_id?: string;
  start_date?: string;
  end_date?: string;
  direction?: "increase" | "decrease";
  mode?: "text_generate" | "image_edit" | "inpaint" | "smart_cutout" | "promptReverse" | "promptOptimize" | "manual" | "redeem" | "purchase";
}): Promise<{ total: number; items: CreditLog[] }> {
  return client.get("/auth/credit-logs", { params });
}

export function getContactConfig(): Promise<{ contact_qr_image: string }> {
  return client.get("/config/contact");
}

export function getAnnouncementConfig(): Promise<AnnouncementConfig> {
  return client.get("/config/announcement");
}

export function getMyPromoCodes(params?: { month?: string }): Promise<PromoCodeListResponse> {
  return client.get("/auth/promo-codes/me", { params });
}

export function createPromoCode(platformName: string): Promise<PromoCodeListResponse> {
  return client.post("/auth/promo-codes", { platform_name: platformName });
}

export function updatePromoCodePlatform(promoCodeId: number, platformName: string): Promise<PromoCodeListResponse> {
  return client.patch(`/auth/promo-codes/${promoCodeId}`, { platform_name: platformName });
}

export function getMyPromoReferrals(): Promise<PromoReferralListResponse> {
  return client.get("/auth/promo-referrals");
}

export function getMyPromoReferralsWithFilters(params: {
  keyword?: string;
  platform_name?: string;
  start_date?: string;
  end_date?: string;
}): Promise<PromoReferralListResponse> {
  return client.get("/auth/promo-referrals", { params });
}

export function getMyPromoReferralActivities(params: {
  keyword?: string;
  platform_name?: string;
  start_date?: string;
  end_date?: string;
}): Promise<PromoReferralActivityListResponse> {
  return client.get("/auth/promo-referral-activities", { params });
}

export function validatePromoCode(code: string): Promise<{ valid: boolean; code: string; platform_name: string }> {
  return client.get("/auth/promo-codes/validate", {
    params: { code },
  });
}
