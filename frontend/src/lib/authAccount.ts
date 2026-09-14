export const PHONE_REGEX = /^1\d{10}$/;
export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const CODE_RESEND_SECONDS = 60;

const bannedEmailDomainSuffixes = [
  "minafter.com",
  "mediaholy.com",
  "mailto.plus",
  "yopmail.com",
  "yopmail.net",
  "yopmail.fr",
  "yopmail.org",
  "cool.fr.nf",
  "jetable.org",
  "tempmail.com",
  "tempmail.org",
  "tempmail.cn",
  "temp-mail.org",
  "temp-mail.io",
  "10minutemail.com",
  "10minutemail.net",
  "10minemail.com",
  "eopyy.com",
  "mailinator.com",
  "mailinator.net",
  "mailinator.org",
  "mailin8r.com",
  "mailinator.us",
  "outlook.com",
  "guerrillamail.com",
  "guerrillamail.info",
  "guerrillamail.biz",
  "guerrillamail.de",
  "guerrillamail.net",
  "sharklasers.com",
  "grr.la",
  "spam4.me",
  "guerrillamailblock.com",
  "dispostable.com",
  "mail.tm",
  "mailsac.com",
  "mailnesia.com",
  "throwawaymail.com",
  "fakeinbox.com",
  "emailondeck.com",
  "maildrop.cc",
  "trashmail.com",
  "getnada.com",
  "spamgourmet.com",
  "zoemail.org",
  "besttempmail.com",
  "mailsbay.com",
  "justdefinition.com",
  "mowan666.com",
  "swagpapa.com",
  "pdf-cutter.com",
  "pdfmerge.xyz",
  "rulersonline.com",
  "ziptools.site",
  "imagecompressor.io",
  "tempmailbox.top",
  "linshiyouxiang.net",
  "randmail.dzz10.cn",
  "aoksend.com",
  "linshi-email.com",
  "moakt.com",
  "zzzmail.top",
  "linsmail.com",
  "suijimail.cn",
  "duanxinmail.com",
  "simplelogin.io",
  "addy.io",
  "anonaddy.com",
  "forwardemail.net",
  "test.com",
  "probe.com",
] as const;

const reservedEmailDomainSuffixes = [
  "80ai.net",
  "80ai.cn",
  "80ai.com",
  "80ai.org",
  "80ai.top",
] as const;

export function normalizePhone(phone: string) {
  const digits = (phone || "").replace(/\D/g, "");
  return digits.startsWith("86") && digits.length === 13 ? digits.slice(2) : digits;
}

export function isValidPhone(phone: string) {
  return PHONE_REGEX.test(normalizePhone(phone));
}

export function isValidEmail(email: string) {
  return EMAIL_REGEX.test((email || "").trim());
}

export function isPhoneAccount(account: string) {
  const normalized = (account || "").trim();
  if (normalized.includes("@")) return false;
  return isValidPhone(normalized);
}

function isEmailDomainInList(email: string, suffixes: readonly string[]) {
  const normalized = email.trim().toLowerCase();
  const atIndex = normalized.lastIndexOf("@");
  if (atIndex < 0) return false;
  const domain = normalized.slice(atIndex + 1);
  return suffixes.some((suffix) => domain === suffix || domain.endsWith(`.${suffix}`));
}

export function getBlockedRegistrationEmailReason(email: string) {
  if (isEmailDomainInList(email, reservedEmailDomainSuffixes)) {
    return "该邮箱域名为官方保留域名，暂不支持注册";
  }
  if (isEmailDomainInList(email, bannedEmailDomainSuffixes)) {
    return "该邮箱域名暂不支持注册，请使用常用邮箱地址";
  }
  return "";
}

export function maskEmail(email?: string | null) {
  const value = (email || "").trim();
  const atIndex = value.indexOf("@");
  if (atIndex <= 0) return value || "";
  const name = value.slice(0, atIndex);
  const domain = value.slice(atIndex);
  if (name.length <= 2) return `${name[0] || "*"}*${domain}`;
  return `${name.slice(0, 2)}***${domain}`;
}

export function maskPhone(phone?: string | null) {
  const value = normalizePhone(phone || "");
  if (!PHONE_REGEX.test(value)) return phone || "";
  return `${value.slice(0, 3)}****${value.slice(7)}`;
}

export function formatAccountContact(user?: { email?: string | null; phone?: string | null } | null) {
  if (user?.email) return user.email;
  if (user?.phone) return maskPhone(user.phone);
  return "未绑定邮箱或手机号";
}
