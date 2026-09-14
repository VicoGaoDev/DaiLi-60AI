<script setup lang="ts">
import { ref } from "vue";
import { SyncOutlined, DownloadOutlined, ZoomInOutlined, LoadingOutlined, CloseCircleOutlined } from "@ant-design/icons-vue";
import type { ImageResult } from "@/types";
import { getDownloadUrl } from "@/api/images";

const props = defineProps<{
  image: ImageResult;
}>();

const emit = defineEmits<{
  regenerate: [imageId: number];
  preview: [url: string];
}>();

const regenerating = ref(false);

function handleRegenerate() {
  regenerating.value = true;
  emit("regenerate", props.image.id);
  setTimeout(() => (regenerating.value = false), 3000);
}

function handlePreview() {
  if (props.image.image_url) emit("preview", props.image.image_url);
}

function handleDownload() {
  const a = document.createElement("a");
  a.href = getDownloadUrl(props.image.id, props.image.image_url);
  a.download = `banana_${props.image.id}.png`;
  a.click();
}
</script>

<template>
  <div class="img-card">
    <div class="img-frame" @click="handlePreview">
      <template v-if="image.status === 'success' && image.image_url">
        <img :src="image.image_url" alt="generated" />
        <div class="img-overlay">
          <a-button shape="circle" size="small" class="overlay-btn" @click.stop="handleDownload">
            <template #icon><DownloadOutlined /></template>
          </a-button>
          <a-button shape="circle" size="small" class="overlay-btn" @click.stop="handlePreview">
            <template #icon><ZoomInOutlined /></template>
          </a-button>
        </div>
      </template>
      <template v-else-if="image.status === 'pending'">
        <div class="img-state">
          <a-spin :indicator="h(LoadingOutlined, { style: { fontSize: '32px', color: '#1890ff' } })" />
          <span style="margin-top: 8px; color: #8c8c8c; font-size: 13px">生成中...</span>
        </div>
      </template>
      <template v-else>
        <div class="img-state error">
          <CloseCircleOutlined style="font-size: 28px; color: #ff4d4f" />
          <span style="margin-top: 6px; color: #ff4d4f; font-size: 13px">生成失败</span>
        </div>
      </template>
    </div>

    <a-button
      type="primary"
      block
      :loading="regenerating"
      class="regen-btn"
      @click="handleRegenerate"
    >
      <template #icon><SyncOutlined /></template>
      重新生成
    </a-button>
  </div>
</template>

<script lang="ts">
import { h } from "vue";
export default {};
</script>

<style scoped lang="scss">
.img-card {
  background: var(--card-bg);
  border-radius: var(--card-radius);
  box-shadow: var(--card-shadow);
  overflow: hidden;
  transition: box-shadow 0.25s, transform 0.25s;

  &:hover {
    box-shadow: 0 20px 27px rgba(0, 0, 0, 0.1);
    transform: translateY(-3px);
  }
}

.img-frame {
  width: 100%;
  aspect-ratio: 3 / 4;
  overflow: hidden;
  cursor: pointer;
  position: relative;
  background: var(--theme-panel-bg-soft);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.3s;
  }

  &:hover img {
    transform: scale(1.04);
  }
}

.img-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  opacity: 0;
  transition: opacity 0.2s;

  .img-frame:hover & {
    opacity: 1;
  }
}

.overlay-btn {
  background: rgba(var(--theme-surface-strong-rgb), 0.9) !important;
  border: 1px solid var(--theme-panel-border) !important;
  color: var(--theme-accent-text) !important;
  box-shadow: 0 2px 8px var(--theme-shadow-soft);

  &:hover {
    background: var(--theme-surface-strong) !important;
    color: var(--theme-accent-text-hover) !important;
  }
}

.img-state {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;

  &.error {
    background: rgba(185, 56, 42, 0.12);
  }
}

.regen-btn {
  margin: 10px 12px 12px;
  width: calc(100% - 24px);
  border-radius: 8px;
  font-weight: 600;
  height: 38px;
}
</style>
