<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { DeleteOutlined, UploadOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import {
  isImageUploadTooLarge,
  MAX_IMAGE_UPLOAD_SIZE_TEXT,
  uploadReferenceImage,
} from "@/api/upload";
import { getPreviewImageSrc } from "@/api/images";
import type { TemplatePayload } from "@/api/templates";
import ModelCategorySelect from "@/components/generate/ModelCategorySelect.vue";
import type { GenerationModelOption, TemplateTag } from "@/types";

const props = withDefaults(defineProps<{
  open: boolean;
  title: string;
  initialValue?: TemplatePayload | null;
  generationModels: GenerationModelOption[];
  tags: TemplateTag[];
  confirmLoading?: boolean;
  okText?: string;
}>(), {
  initialValue: null,
  confirmLoading: false,
  okText: "保存",
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: TemplatePayload];
  cancel: [];
}>();

const refInput = ref<HTMLInputElement | null>(null);
const resultInput = ref<HTMLInputElement | null>(null);
const refUploading = ref(false);
const resultUploading = ref(false);

const form = reactive<TemplatePayload>({
  prompt: "",
  model: "banana_pro",
  reference_images: [],
  num_images: 1,
  size: "9:16",
  resolution: "2K",
  custom_size: "",
  result_image: "",
  sort_order: 0,
  tag_names: [],
});

const sizeOptions = [
  { label: "1:1", value: "1:1" },
  { label: "2:3", value: "2:3" },
  { label: "3:2", value: "3:2" },
  { label: "3:4", value: "3:4" },
  { label: "4:3", value: "4:3" },
  { label: "9:16", value: "9:16" },
  { label: "16:9", value: "16:9" },
];

const resolutionOptions = [
  { label: "1K", value: "1K" },
  { label: "2K", value: "2K" },
  { label: "4K", value: "4K" },
];

const selectedModelOption = computed(() => props.generationModels.find((item) => item.model_key === form.model) || null);
const generationModelSelectOptions = computed(() => (
  props.generationModels.map((model) => ({
    value: model.model_key,
    label: model.model_label,
    description: model.model_description,
    sortOrder: model.sort_order,
    categoryId: model.category_id,
    categoryName: model.category_name,
    categorySortOrder: model.category_sort_order,
  }))
));
const customSizeOptions = computed(() => selectedModelOption.value?.custom_size_options || []);
const hideResolution = computed(() => !!selectedModelOption.value?.hide_resolution);
const hideCustomSize = computed(() => !!selectedModelOption.value?.hide_custom_size);
const tagOptions = computed(() => props.tags.map((tag) => ({ label: tag.name, value: tag.name })));

function getDefaultPayload(): TemplatePayload {
  return {
    prompt: "",
    model: props.generationModels[0]?.model_key || "banana_pro",
    reference_images: [],
    num_images: 1,
    size: "9:16",
    resolution: "2K",
    custom_size: "",
    result_image: "",
    sort_order: 0,
    tag_names: [],
  };
}

function syncForm(value?: TemplatePayload | null) {
  const next = value || getDefaultPayload();
  form.prompt = next.prompt || "";
  form.model = next.model || props.generationModels[0]?.model_key || "banana_pro";
  form.reference_images = [...(next.reference_images || [])];
  form.num_images = 1;
  form.size = next.size || "9:16";
  form.resolution = next.resolution || "2K";
  form.custom_size = next.custom_size || "";
  form.result_image = next.result_image || "";
  form.sort_order = Number.isFinite(next.sort_order) ? next.sort_order : 0;
  form.tag_names = [...(next.tag_names || [])];
}

watch(
  () => props.open,
  (open) => {
    if (open) syncForm(props.initialValue);
  },
  { immediate: true },
);

watch(
  () => props.initialValue,
  (value) => {
    if (props.open) syncForm(value);
  },
);

watch(
  () => props.generationModels,
  () => {
    if (!form.model || !props.generationModels.some((item) => item.model_key === form.model)) {
      form.model = props.generationModels[0]?.model_key || "banana_pro";
    }
  },
);

function handleCancel() {
  emit("update:open", false);
  emit("cancel");
}

function handleSave() {
  if (!form.prompt.trim()) {
    message.warning("请输入提示词");
    return;
  }
  if (!form.result_image) {
    message.warning("请上传结果图");
    return;
  }
  emit("save", {
    prompt: form.prompt.trim(),
    model: form.model,
    reference_images: [...form.reference_images],
    num_images: 1,
    size: form.size,
    resolution: hideResolution.value ? "" : form.resolution,
    custom_size: hideCustomSize.value ? "" : form.custom_size,
    result_image: form.result_image,
    sort_order: Number.isFinite(form.sort_order) ? form.sort_order : 0,
    tag_names: [...form.tag_names],
  });
}

function triggerRefUpload() {
  refInput.value?.click();
}

function triggerResultUpload() {
  resultInput.value?.click();
}

async function handleRefUpload(e: Event) {
  const input = e.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  if (!files.length) return;
  refUploading.value = true;
  let uploadedCount = 0;
  try {
    for (const file of files) {
      if (isImageUploadTooLarge(file)) {
        message.warning(`${file.name} 超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}，已跳过`);
        continue;
      }
      const res = await uploadReferenceImage(file, "template");
      form.reference_images.push(res.url);
      uploadedCount += 1;
    }
    if (uploadedCount > 0) {
      message.success(`成功上传 ${uploadedCount} 张参考图`);
    }
  } catch {
    message.error("参考图上传失败");
  } finally {
    refUploading.value = false;
    input.value = "";
  }
}

async function handleResultUpload(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  if (isImageUploadTooLarge(file)) {
    message.warning(`图片大小不能超过 ${MAX_IMAGE_UPLOAD_SIZE_TEXT}`);
    input.value = "";
    return;
  }
  resultUploading.value = true;
  try {
    const res = await uploadReferenceImage(file, "template");
    form.result_image = res.url;
    message.success("结果图上传成功");
  } catch {
    message.error("结果图上传失败");
  } finally {
    resultUploading.value = false;
    input.value = "";
  }
}

function removeRef(index: number) {
  form.reference_images.splice(index, 1);
}
</script>

<template>
  <a-modal
    :open="open"
    :title="title"
    :confirm-loading="confirmLoading"
    :ok-button-props="{ class: 'warm-primary-btn' }"
    :cancel-button-props="{ class: 'warm-secondary-btn' }"
    :ok-text="okText"
    cancel-text="取消"
    centered
    :width="760"
    @update:open="emit('update:open', $event)"
    @ok="handleSave"
    @cancel="handleCancel"
  >
    <a-form layout="vertical" style="margin-top: 16px">
      <a-form-item label="提示词">
        <a-textarea v-model:value="form.prompt" class="warm-textarea" :rows="5" :maxlength="2000" show-count />
      </a-form-item>

      <div class="template-form-grid">
        <a-form-item label="模型">
          <ModelCategorySelect
            v-model="form.model"
            class="warm-select"
            :options="generationModelSelectOptions"
            placeholder="请选择模型"
          />
        </a-form-item>
        <a-form-item label="宽高比">
          <a-select v-model:value="form.size" class="warm-select" :options="sizeOptions" />
        </a-form-item>
        <a-form-item label="排序值">
          <a-input-number v-model:value="form.sort_order" class="warm-input-number" :min="0" :precision="0" />
        </a-form-item>
        <a-form-item v-if="!hideResolution" label="分辨率">
          <a-select v-model:value="form.resolution" class="warm-select" :options="resolutionOptions" />
        </a-form-item>
        <a-form-item v-if="!hideCustomSize" label="自定义分辨率">
          <a-select
            v-model:value="form.custom_size"
            class="warm-select"
            :options="customSizeOptions"
            allow-clear
            placeholder="可选，带入 {{ custom_size }}"
          />
        </a-form-item>
        <a-form-item label="所属标签">
          <a-select
            v-model:value="form.tag_names"
            class="warm-select"
            mode="tags"
            :options="tagOptions"
            placeholder="输入或选择标签"
          />
        </a-form-item>
      </div>

      <a-form-item label="结果图">
        <div class="template-result-upload">
          <div class="template-result-preview">
            <img v-if="form.result_image" :src="getPreviewImageSrc(form.result_image)" alt="结果图" />
            <div v-else class="template-result-placeholder">请上传结果图</div>
          </div>
          <input ref="resultInput" type="file" accept="image/*" hidden @change="handleResultUpload" />
          <a-button class="template-secondary-btn" :loading="resultUploading" @click="triggerResultUpload">
            <template #icon><UploadOutlined /></template>
            上传结果图
          </a-button>
        </div>
      </a-form-item>

      <a-form-item label="参考图片（可选）" style="margin-bottom: 0">
        <input ref="refInput" type="file" accept="image/*" multiple hidden @change="handleRefUpload" />
        <div class="template-ref-grid">
          <div v-for="(url, idx) in form.reference_images" :key="url + idx" class="template-ref-item">
            <img :src="getPreviewImageSrc(url)" alt="参考图" />
            <a-button type="text" danger shape="circle" class="template-ref-remove" @click="removeRef(idx)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>
          <a-button class="template-ref-add template-secondary-btn" :loading="refUploading" @click="triggerRefUpload">
            <template #icon><UploadOutlined /></template>
            上传参考图
          </a-button>
        </div>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped lang="scss">
.template-secondary-btn {
  border-color: var(--theme-control-border-strong) !important;
  background: var(--theme-control-bg) !important;
  color: var(--theme-accent-text) !important;
  border-radius: 12px !important;
  font-weight: 600;
}

.template-secondary-btn:hover,
.template-secondary-btn:focus {
  border-color: var(--theme-border-strong) !important;
  background: var(--theme-control-hover-bg) !important;
  color: var(--theme-accent-text-hover) !important;
}

.template-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.template-result-upload {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.template-result-preview {
  width: 132px;
  height: 132px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  flex-shrink: 0;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.template-result-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.template-ref-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.template-ref-item {
  position: relative;
  width: 84px;
  height: 84px;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.template-ref-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(var(--theme-surface-strong-rgb), 0.92) !important;
  border: 1px solid var(--theme-panel-border) !important;
  color: #d6574b !important;
}

.template-ref-add {
  height: 84px;
  min-width: 120px;
  border-radius: 14px;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .template-ref-remove {
  background: rgba(var(--theme-surface-strong-rgb), 0.92) !important;
  border-color: var(--theme-panel-border) !important;
  color: #de8f84 !important;
}

@media (max-width: 720px) {
  .template-form-grid {
    grid-template-columns: 1fr;
  }

  .template-result-upload {
    flex-direction: column;
  }
}
</style>
