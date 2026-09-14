<script setup lang="ts">
import { computed, ref, watch } from "vue";

const props = withDefaults(defineProps<{
  open: boolean;
  value?: string;
  draftKey?: string;
  maxlength?: number;
  placeholder?: string;
}>(), {
  value: "",
  draftKey: "default",
  maxlength: 5000,
  placeholder: "描述您想要生成的内容...",
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [value: string];
}>();

const drafts = ref<Record<string, string>>({});
const dirtyKeys = ref<Record<string, boolean>>({});
const seededKeys = ref<Record<string, boolean>>({});
const confirming = ref(false);

function currentKey() {
  return props.draftKey || "default";
}

const draft = computed({
  get() {
    return drafts.value[currentKey()] ?? "";
  },
  set(value: string) {
    if (confirming.value) return;
    const key = currentKey();
    drafts.value = { ...drafts.value, [key]: value };
    dirtyKeys.value = { ...dirtyKeys.value, [key]: true };
  },
});

watch(() => props.open, (open) => {
  if (!open) return;
  const key = currentKey();
  if (dirtyKeys.value[key] || seededKeys.value[key]) return;
  drafts.value = { ...drafts.value, [key]: props.value || "" };
  seededKeys.value = { ...seededKeys.value, [key]: true };
});

function closeDialog() {
  emit("update:open", false);
}

function handleConfirm() {
  const key = currentKey();
  const text = draft.value;
  confirming.value = true;
  emit("confirm", text);
  drafts.value = { ...drafts.value, [key]: "" };
  dirtyKeys.value = { ...dirtyKeys.value, [key]: false };
  seededKeys.value = { ...seededKeys.value, [key]: true };
  emit("update:open", false);
  window.setTimeout(() => {
    confirming.value = false;
  }, 0);
}
</script>

<template>
  <a-modal
    :open="open"
    title="编辑提示词"
    centered
    :width="760"
    wrap-class-name="prompt-expand-dialog"
    :body-style="{ padding: '12px 16px 4px' }"
    @update:open="(value: boolean) => emit('update:open', value)"
    @cancel="closeDialog"
  >
    <a-textarea
      v-model:value="draft"
      class="prompt-expand-input"
      :maxlength="maxlength"
      :placeholder="placeholder"
      :auto-size="false"
      show-count
      autofocus
    />
    <template #footer>
      <a-button @click="closeDialog">取消</a-button>
      <a-button type="primary" @click="handleConfirm">确认</a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.prompt-expand-input {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
}

.prompt-expand-input :deep(textarea) {
  min-height: min(56vh, 520px);
  resize: none;
  line-height: 1.7;
  font-size: 15px;
  color: var(--theme-title, #3d2f22);
  border-radius: 14px !important;
  border-color: var(--theme-control-border, #ebd9c1) !important;
  background: var(--theme-control-bg, #fffaf3) !important;
  padding: 14px 16px 36px !important;
}

.prompt-expand-input :deep(textarea:hover),
.prompt-expand-input :deep(textarea:focus) {
  border-color: var(--theme-border-accent, #efc784) !important;
  box-shadow: 0 0 0 3px var(--theme-focus-ring, rgba(247, 168, 49, 0.18));
}

.prompt-expand-input :deep(.ant-input-data-count),
.prompt-expand-input :deep(.ant-input-textarea-show-count)::after {
  color: var(--theme-title, #3d2f22) !important;
  font-size: 12px;
}
</style>
