<script setup lang="ts">
import OptionGridPicker from "@/components/generate/OptionGridPicker.vue";
import type { SceneOptionItem } from "@/types";

defineProps<{
  modelValue: string;
  options: SceneOptionItem[];
}>();

defineEmits<{
  "update:modelValue": [value: string];
}>();
</script>

<template>
  <OptionGridPicker
    :model-value="modelValue"
    :options="options"
    panel-title="选择宽高比"
    placeholder="选择宽高比"
    show-preview
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>
