export const CUSTOM_SIZE_PIXEL_MULTIPLE = 16;
export const CUSTOM_SIZE_MAX_ASPECT_RATIO = 3;
export const CUSTOM_SIZE_MAX_SIDE = 3840;
export const CUSTOM_SIZE_MIN_PIXELS = 655360;
export const CUSTOM_SIZE_DEFAULT_SIDE = 1024;

export type CustomSizeBounds = {
  min: number;
  max: number;
  limit: number;
};

export function getCustomSizeBounds(min?: number | null, max?: number | null): CustomSizeBounds {
  const nextMin = Math.max(1, Number(min || 256));
  const nextMax = Math.max(nextMin, Number(max || 4096));
  return {
    min: nextMin,
    max: nextMax,
    limit: Math.min(nextMax, CUSTOM_SIZE_MAX_SIDE),
  };
}

export function snapToCustomSizeMultiple(value: number) {
  return Math.round(value / CUSTOM_SIZE_PIXEL_MULTIPLE) * CUSTOM_SIZE_PIXEL_MULTIPLE;
}

export function normalizeCustomDimension(value: number, bounds: CustomSizeBounds) {
  const snapped = snapToCustomSizeMultiple(Number(value) || bounds.min);
  return Math.min(bounds.limit, Math.max(bounds.min, snapped));
}

export function parseCustomSizeValue(value?: string | null) {
  const normalized = String(value || "").trim();
  if (!normalized) return null;
  const match = normalized.match(/^(\d+)\s*[xX×*]\s*(\d+)$/);
  if (!match) return null;
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }
  return { width, height };
}

export function formatCustomSizeValue(width: number, height: number) {
  return `${Number(width)}x${Number(height)}`;
}

export function parseCustomSizeInput(value: string) {
  return String(value ?? "").replace(/\D/g, "");
}

export function formatCustomSizeInput(value: string | number) {
  return String(value ?? "").replace(/\D/g, "");
}

export function stepCustomDimension(current: number, direction: 1 | -1, bounds: CustomSizeBounds) {
  const multiple = CUSTOM_SIZE_PIXEL_MULTIPLE;
  const next = direction > 0
    ? Math.ceil((current + multiple) / multiple) * multiple
    : Math.floor((current - 1) / multiple) * multiple;
  return Math.min(bounds.limit, Math.max(bounds.min, next));
}

export function applyCustomDimensionChange(current: number, incoming: number | string | null, bounds: CustomSizeBounds) {
  const next = Number(incoming);
  if (!Number.isFinite(next)) return current;
  if (Number.isFinite(current) && next === current + CUSTOM_SIZE_PIXEL_MULTIPLE) {
    return stepCustomDimension(current, 1, bounds);
  }
  if (Number.isFinite(current) && next === current - CUSTOM_SIZE_PIXEL_MULTIPLE) {
    return stepCustomDimension(current, -1, bounds);
  }
  return next;
}

export function getCustomDimensionError(value: number, otherValue: number, bounds: CustomSizeBounds) {
  if (!Number.isInteger(value)) {
    return "必须是16倍数";
  }
  if (value % CUSTOM_SIZE_PIXEL_MULTIPLE !== 0) {
    return "必须是16倍数";
  }
  if (value > CUSTOM_SIZE_MAX_SIDE) {
    return `最大边长不超过 ${CUSTOM_SIZE_MAX_SIDE}px`;
  }
  if (value < bounds.min || value > bounds.max) {
    return `须为 ${bounds.min}-${bounds.max} 的整数`;
  }
  if (
    Number.isInteger(otherValue)
    && otherValue > 0
    && value > otherValue * CUSTOM_SIZE_MAX_ASPECT_RATIO
  ) {
    return `长短边比例不能超过 ${CUSTOM_SIZE_MAX_ASPECT_RATIO}:1`;
  }
  if (Number.isInteger(otherValue) && otherValue > 0 && value * otherValue < CUSTOM_SIZE_MIN_PIXELS) {
    return `总像素数不得低于 ${CUSTOM_SIZE_MIN_PIXELS}px`;
  }
  return "";
}

function bindDigitsOnlyInput(input: HTMLInputElement) {
  const sanitize = () => {
    const digits = input.value.replace(/\D/g, "");
    if (input.value !== digits) {
      input.value = digits;
    }
  };

  const abortIme = (event: Event) => {
    event.preventDefault();
    event.stopPropagation();
    input.setAttribute("readonly", "readonly");
    sanitize();
    requestAnimationFrame(() => {
      input.removeAttribute("readonly");
      sanitize();
    });
  };

  const onKeydown = (event: KeyboardEvent) => {
    if (event.isComposing || event.key === "Process" || event.key === "Unidentified") {
      event.preventDefault();
      abortIme(event);
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (["Backspace", "Delete", "Tab", "Enter", "Escape", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      return;
    }
    if (/^\d$/.test(event.key)) return;
    event.preventDefault();
  };

  const onBeforeInput = (event: InputEvent) => {
    if (event.isComposing || event.inputType === "insertCompositionText") {
      event.preventDefault();
      abortIme(event);
      return;
    }
    if (event.data && !/^\d+$/.test(event.data)) {
      event.preventDefault();
    }
  };

  const onPaste = (event: ClipboardEvent) => {
    event.preventDefault();
    const digits = (event.clipboardData?.getData("text") ?? "").replace(/\D/g, "");
    if (!digits) return;
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    input.value = `${input.value.slice(0, start)}${digits}${input.value.slice(end)}`.replace(/\D/g, "");
    const caret = Math.min(input.value.length, start + digits.length);
    input.setSelectionRange(caret, caret);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  };

  input.setAttribute("inputmode", "numeric");
  input.setAttribute("pattern", "[0-9]*");
  input.setAttribute("lang", "en");
  input.setAttribute("autocomplete", "off");
  input.addEventListener("keydown", onKeydown, true);
  input.addEventListener("beforeinput", onBeforeInput as EventListener, true);
  input.addEventListener("compositionstart", abortIme, true);
  input.addEventListener("compositionupdate", abortIme, true);
  input.addEventListener("compositionend", abortIme, true);
  input.addEventListener("input", sanitize, true);
  input.addEventListener("paste", onPaste, true);

  return () => {
    input.removeEventListener("keydown", onKeydown, true);
    input.removeEventListener("beforeinput", onBeforeInput as EventListener, true);
    input.removeEventListener("compositionstart", abortIme, true);
    input.removeEventListener("compositionupdate", abortIme, true);
    input.removeEventListener("compositionend", abortIme, true);
    input.removeEventListener("input", sanitize, true);
    input.removeEventListener("paste", onPaste, true);
  };
}

export function createDigitsOnlyDirective() {
  const cleanups = new WeakMap<HTMLElement, () => void>();
  const boundInputs = new WeakMap<HTMLElement, HTMLInputElement>();

  return {
    mounted(el: HTMLElement) {
      const input = el.tagName === "INPUT" ? el as HTMLInputElement : el.querySelector("input");
      if (!input) return;
      cleanups.set(el, bindDigitsOnlyInput(input));
      boundInputs.set(el, input);
    },
    updated(el: HTMLElement) {
      const input = el.tagName === "INPUT" ? el as HTMLInputElement : el.querySelector("input");
      if (!input || boundInputs.get(el) === input) return;
      cleanups.get(el)?.();
      cleanups.set(el, bindDigitsOnlyInput(input));
      boundInputs.set(el, input);
    },
    unmounted(el: HTMLElement) {
      cleanups.get(el)?.();
      cleanups.delete(el);
      boundInputs.delete(el);
    },
  };
}
