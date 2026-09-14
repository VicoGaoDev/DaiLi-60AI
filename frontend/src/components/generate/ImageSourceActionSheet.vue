<script setup lang="ts">
defineEmits<{
  camera: [];
  gallery: [];
  files: [];
  cancel: [];
}>();
</script>

<template>
  <Teleport to="body">
    <div class="image-source-picker-mask" @click="$emit('cancel')">
      <div
        class="image-source-picker"
        role="dialog"
        aria-label="选择要上传的文件"
        @click.stop
      >
        <h2 class="image-source-picker-title">选择要上传的文件</h2>
        <div class="image-source-picker-apps">
          <button type="button" class="image-source-picker-app" @click="$emit('camera')">
            <span class="image-source-picker-icon is-camera" aria-hidden="true">
              <span class="camera-ring" />
              <span class="camera-lens" />
            </span>
            <span>相机</span>
          </button>
          <button type="button" class="image-source-picker-app" @click="$emit('gallery')">
            <span class="image-source-picker-icon is-gallery" aria-hidden="true">
              <svg viewBox="0 0 48 48">
                <rect x="2" y="2" width="44" height="44" rx="10" fill="#8fd4ea" />
                <path d="M2 30.5 16.2 20l9.3 8.4 7.8-6.7L46 32v6.2A7.8 7.8 0 0 1 38.2 46H9.8A7.8 7.8 0 0 1 2 38.2V30.5Z" fill="#fff" />
                <circle cx="15" cy="15" r="4.2" fill="#2f7de1" />
              </svg>
            </span>
            <span>相册</span>
          </button>
          <button type="button" class="image-source-picker-app" @click="$emit('files')">
            <span class="image-source-picker-icon is-files" aria-hidden="true">
              <svg viewBox="0 0 48 48">
                <rect x="2" y="2" width="44" height="44" rx="10" fill="#ffc14d" />
                <path d="M10 18.5h11.2l3.2 3.1H38a3.5 3.5 0 0 1 3.5 3.5V35a4 4 0 0 1-4 4H10.5A4.5 4.5 0 0 1 6 34.5v-12A4 4 0 0 1 10 18.5Z" fill="#fff6d8" />
                <path d="M6 22.2h36V34.5A4 4 0 0 1 38 38.5H10.5A4.5 4.5 0 0 1 6 34.5V22.2Z" fill="#ffe7a3" />
              </svg>
            </span>
            <span>文件</span>
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.image-source-picker-mask {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0 16px calc(12px + env(safe-area-inset-bottom));
  background: transparent;
}

.image-source-picker {
  width: min(100%, 420px);
  padding: 28px 24px 32px;
  border-radius: 28px;
  background: #fff;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12);
}

.image-source-picker-title {
  margin: 0 0 28px;
  color: #1a1a1a;
  font-size: 18px;
  font-weight: 500;
  line-height: 1.3;
  text-align: center;
}

.image-source-picker-apps {
  display: flex;
  justify-content: center;
  gap: 36px;
}

.image-source-picker-app {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: 64px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #333;
  font-size: 13px;
  line-height: 1.3;
}

.image-source-picker-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  overflow: hidden;
}

.image-source-picker-icon svg {
  width: 52px;
  height: 52px;
}

.image-source-picker-icon.is-camera {
  position: relative;
  border-radius: 50%;
  background: #f3f3f3;
}

.camera-ring,
.camera-lens {
  position: absolute;
  border-radius: 50%;
}

.camera-ring {
  width: 24px;
  height: 24px;
  border: 3.2px solid #111;
}

.camera-lens {
  width: 9px;
  height: 9px;
  background: #111;
}

:global(html[data-theme="dark"]) .image-source-picker,
:global(html[data-theme="midnight"]) .image-source-picker {
  background: #2a2a2a;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}

:global(html[data-theme="dark"]) .image-source-picker-title,
:global(html[data-theme="midnight"]) .image-source-picker-title {
  color: #f5f5f5;
}

:global(html[data-theme="dark"]) .image-source-picker-app,
:global(html[data-theme="midnight"]) .image-source-picker-app {
  color: #ddd;
}

:global(html[data-theme="dark"]) .image-source-picker-icon.is-camera,
:global(html[data-theme="midnight"]) .image-source-picker-icon.is-camera {
  background: #3a3a3a;
}
</style>
