export async function copyText(text: string): Promise<void> {
  const normalized = String(text ?? "");

  if (
    typeof navigator !== "undefined"
    && typeof window !== "undefined"
    && window.isSecureContext
    && typeof navigator.clipboard?.writeText === "function"
    && document.hasFocus()
  ) {
    try {
      await navigator.clipboard.writeText(normalized);
      return;
    } catch {
      // Fall through to legacy copy path for Edge and other browsers
      // that may reject Clipboard API calls despite user interaction.
    }
  }

  if (typeof document === "undefined") {
    throw new Error("Clipboard unavailable");
  }

  const textarea = document.createElement("textarea");
  const activeElement = document.activeElement as HTMLElement | null;
  textarea.value = normalized;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";

  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  try {
    const copied = document.execCommand("copy");
    if (!copied) {
      throw new Error("execCommand copy failed");
    }
  } finally {
    document.body.removeChild(textarea);
    activeElement?.focus?.();
  }
}
