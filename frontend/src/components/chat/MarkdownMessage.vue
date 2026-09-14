<script setup lang="ts">
import { computed, onBeforeUnmount } from "vue";
import { message } from "ant-design-vue";
import { copyText } from "@/lib/clipboard";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";

const props = defineProps<{
  content: string;
  streaming?: boolean;
}>();

const emit = defineEmits<{
  generate: [value: string];
}>();

const renderedHtml = computed(() => renderSimpleMarkdown(props.content));

let copiedTimer: number | null = null;

onBeforeUnmount(() => {
  if (copiedTimer !== null) window.clearTimeout(copiedTimer);
});

function readCopyableText(button: HTMLElement): string {
  const block = button.closest(".md-copyable");
  const source = block?.querySelector("[data-md-copy-source]");
  return (source?.textContent || "").replace(/\n$/, "");
}

function markCopied(button: HTMLButtonElement) {
  button.classList.add("is-copied");
  button.setAttribute("aria-label", "已复制");
  button.setAttribute("data-tooltip", "已复制");
  if (copiedTimer !== null) window.clearTimeout(copiedTimer);
  copiedTimer = window.setTimeout(() => {
    button.classList.remove("is-copied");
    button.setAttribute("aria-label", "复制");
    button.setAttribute("data-tooltip", "复制");
    copiedTimer = null;
  }, 1600);
}

async function handleClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  const generateButton = target?.closest<HTMLButtonElement>(".md-code-generate");
  const copyButton = target?.closest<HTMLButtonElement>(".md-code-copy");
  const button = generateButton || copyButton;
  if (!button) return;

  const code = readCopyableText(button);
  if (!code) {
    message.warning("没有可复制的内容");
    return;
  }

  try {
    await copyText(code);
    if (copyButton) markCopied(copyButton);
    if (generateButton) emit("generate", code);
  } catch {
    message.error("复制失败，请检查剪贴板权限");
  }
}
</script>

<template>
  <div
    class="message-content md-body"
    :class="{ 'is-streaming': streaming }"
    v-html="renderedHtml"
    @click="handleClick"
  ></div>
</template>
