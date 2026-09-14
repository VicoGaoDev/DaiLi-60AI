<script setup lang="ts">
import { computed } from "vue";
import { CloseOutlined } from "@ant-design/icons-vue";
import { getGenerateCameraById, matchGenerateCameraPreset } from "@/lib/generateCameras";
import { getGenerateStyleById } from "@/lib/generateStyles";

const props = defineProps<{
  colorStyleId: string;
  lightingStyleId: string;
  cameraBodyId?: string;
  cameraLensId?: string;
  cameraFocalId?: string;
  cameraApertureId?: string;
}>();

const emit = defineEmits<{
  "update:colorStyleId": [value: string];
  "update:lightingStyleId": [value: string];
  "update:cameraBodyId": [value: string];
  "update:cameraLensId": [value: string];
  "update:cameraFocalId": [value: string];
  "update:cameraApertureId": [value: string];
}>();

const colorStyle = computed(() => getGenerateStyleById(props.colorStyleId));
const lightingStyle = computed(() => getGenerateStyleById(props.lightingStyleId));
const cameraBody = computed(() => getGenerateCameraById(props.cameraBodyId));
const cameraLens = computed(() => getGenerateCameraById(props.cameraLensId));
const cameraFocal = computed(() => getGenerateCameraById(props.cameraFocalId));
const cameraAperture = computed(() => getGenerateCameraById(props.cameraApertureId));
const cameraItems = computed(() => (
  [
    cameraBody.value && { label: "机身", name: cameraBody.value.name },
    cameraLens.value && { label: "镜头", name: cameraLens.value.name },
    cameraFocal.value && { label: "焦距", name: cameraFocal.value.name },
    cameraAperture.value && { label: "光圈", name: cameraAperture.value.name },
  ].filter(Boolean) as Array<{ label: string; name: string }>
));
const hasCameraTag = computed(() => cameraItems.value.length > 0);
const matchedCameraPreset = computed(() => matchGenerateCameraPreset({
  bodyId: props.cameraBodyId || "",
  lensId: props.cameraLensId || "",
  focalId: props.cameraFocalId || "",
  apertureId: props.cameraApertureId || "",
}));
const cameraTagLabel = computed(() => (
  matchedCameraPreset.value ? `摄像机 · ${matchedCameraPreset.value.name}` : "摄像机参数"
));
const hasTags = computed(() => Boolean(colorStyle.value || lightingStyle.value || hasCameraTag.value));

function clearCamera() {
  emit("update:cameraBodyId", "");
  emit("update:cameraLensId", "");
  emit("update:cameraFocalId", "");
  emit("update:cameraApertureId", "");
}
</script>

<template>
  <div v-if="hasTags" class="prompt-style-tags">
    <a-tooltip v-if="hasCameraTag" overlay-class-name="prompt-camera-tag-tooltip">
      <template #title>
        <div class="prompt-camera-tag-list">
          <div v-if="matchedCameraPreset" class="prompt-camera-tag-preset">{{ matchedCameraPreset.name }}</div>
          <div v-for="item in cameraItems" :key="item.label" class="prompt-camera-tag-row">
            <span class="prompt-camera-tag-label">{{ item.label }}</span>
            <span class="prompt-camera-tag-value">{{ item.name }}</span>
          </div>
        </div>
      </template>
      <span class="prompt-style-tag">
        <svg class="prompt-style-tag-icon is-camera" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="13" r="4.2" />
          <path d="M4.5 8.2h3.1l1.2-1.8h6.4l1.2 1.8h3.1c.9 0 1.6.7 1.6 1.6v8.1c0 .9-.7 1.6-1.6 1.6H4.5c-.9 0-1.6-.7-1.6-1.6V9.8c0-.9.7-1.6 1.6-1.6Z" />
        </svg>
        <span>{{ cameraTagLabel }}</span>
        <button type="button" class="prompt-style-tag-clear" aria-label="取消摄像机参数" @click.stop="clearCamera">
          <CloseOutlined />
        </button>
      </span>
    </a-tooltip>
    <span v-if="colorStyle" class="prompt-style-tag">
      <svg class="prompt-style-tag-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3.5c-5.1 0-8.5 3.6-8.5 7.4 0 2.6 1.8 4.4 4.2 4.4 1.1 0 1.8-.5 2.1-1.3.2-.5.7-1.7 1.5-1.7.7 0 1 .7 1 1.6 0 2.5-1.5 5.6 1.7 5.6 4.4 0 7.5-3.8 7.5-8.1C21.5 6.7 17.6 3.5 12 3.5Z" />
        <circle cx="8.1" cy="9.1" r="1.15" />
        <circle cx="11.2" cy="7.35" r="1.15" />
        <circle cx="14.7" cy="8.15" r="1.15" />
        <circle cx="16.15" cy="11.35" r="1.15" />
      </svg>
      <span>{{ colorStyle.name }}</span>
      <button type="button" class="prompt-style-tag-clear" aria-label="取消色彩风格" @click="emit('update:colorStyleId', '')">
        <CloseOutlined />
      </button>
    </span>
    <span v-if="lightingStyle" class="prompt-style-tag">
      <svg class="prompt-style-tag-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3.5c-5.1 0-8.5 3.6-8.5 7.4 0 2.6 1.8 4.4 4.2 4.4 1.1 0 1.8-.5 2.1-1.3.2-.5.7-1.7 1.5-1.7.7 0 1 .7 1 1.6 0 2.5-1.5 5.6 1.7 5.6 4.4 0 7.5-3.8 7.5-8.1C21.5 6.7 17.6 3.5 12 3.5Z" />
        <circle cx="8.1" cy="9.1" r="1.15" />
        <circle cx="11.2" cy="7.35" r="1.15" />
        <circle cx="14.7" cy="8.15" r="1.15" />
        <circle cx="16.15" cy="11.35" r="1.15" />
      </svg>
      <span>{{ lightingStyle.name }}</span>
      <button type="button" class="prompt-style-tag-clear" aria-label="取消光影" @click="emit('update:lightingStyleId', '')">
        <CloseOutlined />
      </button>
    </span>
  </div>
</template>

<style scoped lang="scss">
.prompt-style-tags {
  position: absolute;
  top: 10px;
  left: 12px;
  right: 16px;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  pointer-events: none;
}

.prompt-style-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  height: 26px;
  padding: 0 6px 0 8px;
  border-radius: 8px;
  background: rgba(61, 47, 34, 0.08);
  color: var(--theme-title);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  pointer-events: auto;
}

.prompt-style-tag-icon {
  flex: 0 0 auto;
  width: 13px;
  height: 13px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linejoin: round;
}

.prompt-style-tag-icon circle {
  fill: currentColor;
  stroke: none;
}

.prompt-style-tag-icon.is-camera circle {
  fill: none;
  stroke: currentColor;
}

.prompt-style-tag-clear {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  font-size: 9px;
  cursor: pointer;
  opacity: 0.55;

  &:hover {
    opacity: 1;
    background: rgba(0, 0, 0, 0.08);
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-style-tag {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .prompt-style-tag-clear:hover {
  background: rgba(255, 255, 255, 0.14);
}
</style>

<style lang="scss">
.prompt-camera-tag-tooltip .ant-tooltip-inner {
  min-width: 220px;
  padding: 10px 12px;
}

.prompt-camera-tag-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.prompt-camera-tag-preset {
  padding-bottom: 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.16);
  font-weight: 600;
  line-height: 1.3;
}

.prompt-camera-tag-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.prompt-camera-tag-label {
  flex: 0 0 auto;
  opacity: 0.72;
}

.prompt-camera-tag-value {
  flex: 1 1 auto;
  min-width: 0;
  text-align: right;
}
</style>
