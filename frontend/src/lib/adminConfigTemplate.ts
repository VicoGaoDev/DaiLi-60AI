export type AdminConfigTemplateKind =
  | "image-api-config"
  | "image-scene-binding"
  | "video-api-config"
  | "video-scene-binding"
  | "chat-api-config"
  | "chat-scene-binding";

export interface AdminConfigTemplateEnvelope<T = object> {
  banana_admin_template: true;
  version: 1;
  kind: AdminConfigTemplateKind;
  data: T;
}

export function buildAdminConfigTemplate<T extends object>(
  kind: AdminConfigTemplateKind,
  data: T,
): AdminConfigTemplateEnvelope<T> {
  return {
    banana_admin_template: true,
    version: 1,
    kind,
    data,
  };
}

export function stringifyAdminConfigTemplate<T extends object>(
  kind: AdminConfigTemplateKind,
  data: T,
): string {
  return JSON.stringify(buildAdminConfigTemplate(kind, data), null, 2);
}

export function parseAdminConfigTemplate(raw: string): {
  kind: AdminConfigTemplateKind;
  data: Record<string, unknown>;
} {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("JSON 解析失败，请检查格式");
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON 顶层必须是对象");
  }

  const envelope = parsed as Partial<AdminConfigTemplateEnvelope<Record<string, unknown>>>;
  if (envelope.banana_admin_template === true) {
    if (!envelope.kind || !isAdminConfigTemplateKind(envelope.kind)) {
      throw new Error("未识别的模板类型");
    }
    if (!envelope.data || typeof envelope.data !== "object" || Array.isArray(envelope.data)) {
      throw new Error("模板 data 必须是对象");
    }
    return {
      kind: envelope.kind,
      data: envelope.data,
    };
  }

  return inferTemplateKindFromPlainObject(parsed as Record<string, unknown>);
}

function isAdminConfigTemplateKind(value: string): value is AdminConfigTemplateKind {
  return [
    "image-api-config",
    "image-scene-binding",
    "video-api-config",
    "video-scene-binding",
    "chat-api-config",
    "chat-scene-binding",
  ].includes(value);
}

function inferTemplateKindFromPlainObject(data: Record<string, unknown>) {
  if (typeof data.request_url === "string") {
    if (
      hasOwn(data, "result_video_url_field")
      || hasOwn(data, "poll_result_video_url_field")
      || hasOwn(data, "poll_result_cover_url_field")
    ) {
      return { kind: "video-api-config" as const, data };
    }
    if (hasOwn(data, "result_text_field")) {
      return { kind: "chat-api-config" as const, data };
    }
    return { kind: "image-api-config" as const, data };
  }

  if (typeof data.scene_key === "string") {
    if (
      hasOwn(data, "duration_options_json")
      || hasOwn(data, "availability_modes")
      || hasOwn(data, "credit_billing_mode")
      || hasOwn(data, "hide_duration")
    ) {
      return { kind: "video-scene-binding" as const, data };
    }
    if (
      hasOwn(data, "system_prompt")
      || hasOwn(data, "context_message_limit")
      || hasOwn(data, "opening_greeting")
      || hasOwn(data, "starter_prompts")
    ) {
      return { kind: "chat-scene-binding" as const, data };
    }
    return { kind: "image-scene-binding" as const, data };
  }

  throw new Error("未识别的模板内容");
}

function hasOwn(data: Record<string, unknown>, key: string) {
  return Object.prototype.hasOwnProperty.call(data, key);
}
