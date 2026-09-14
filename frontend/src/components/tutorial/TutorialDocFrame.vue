<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from "vue";
import { DoubleLeftOutlined, DoubleRightOutlined } from "@ant-design/icons-vue";
import { withBaseUrl } from "@/lib/assets";
import { APP_THEME_ATTRIBUTE } from "@/config/theme";
import { getCurrentTheme } from "@/lib/theme";
import {
  getTutorialSections,
  tutorialModuleMeta,
  tutorialNavOrder,
  type TutorialModule,
} from "@/lib/tutorial";

const props = defineProps<{
  module: TutorialModule;
  sectionId?: string;
  showDockSwitch?: boolean;
  dockTabEnabled?: boolean;
}>();

const emit = defineEmits<{
  "update:module": [value: TutorialModule];
  "update:section": [value: string];
  "update:dockTabEnabled": [value: boolean];
}>();

const iframeRef = ref<HTMLIFrameElement | null>(null);
let themeObserver: MutationObserver | null = null;
const navCollapsed = ref(false);
function firstSectionId(module: TutorialModule) {
  return getTutorialSections(module)[0]?.id || "";
}

const activeSectionId = ref(props.sectionId || firstSectionId(props.module));
const pendingSectionId = ref("");
const preview = ref<{ src: string; alt: string; caption: string } | null>(null);
const showBackTop = ref(false);
const openGroups = reactive<Record<TutorialModule, boolean>>({
  general: false,
  chat: false,
  generate: false,
  video: false,
  canvas: false,
});

function setExclusiveOpen(module: TutorialModule) {
  for (const item of tutorialNavOrder) {
    openGroups[item] = item === module;
  }
}

setExclusiveOpen(props.module);

const currentMeta = computed(() => tutorialModuleMeta[props.module]);

function resolveFrameSrc(module: TutorialModule, sectionId?: string) {
  const base = withBaseUrl(tutorialModuleMeta[module].doc);
  const id = (sectionId || "").trim();
  return id ? `${base}#${encodeURIComponent(id)}` : base;
}

const frameSrc = ref(resolveFrameSrc(props.module, props.sectionId));

function closePreview() {
  preview.value = null;
}

function setNavCollapsed(collapsed: boolean) {
  navCollapsed.value = collapsed;
  try {
    const mobile = window.matchMedia("(max-width: 768px)").matches;
    const key = mobile ? "tutorial-nav-collapsed-mobile" : "tutorial-nav-collapsed";
    localStorage.setItem(key, collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}

function toggleNavCollapsed() {
  setNavCollapsed(!navCollapsed.value);
}

function toggleGroup(module: TutorialModule) {
  openGroups[module] = !openGroups[module];
}

function selectModule(module: TutorialModule) {
  if (props.module === module) {
    toggleGroup(module);
    return;
  }
  setExclusiveOpen(module);
  emit("update:module", module);
}

function scrollToSection(id: string) {
  if (!id) return;
  activeSectionId.value = id;
  const frameWindow = iframeRef.value?.contentWindow;
  if (!frameWindow) return;
  try {
    frameWindow.postMessage({ type: "banana-tutorial-scroll", id }, window.location.origin);
  } catch {
    frameWindow.location.hash = id;
  }
}

function openModuleSection(module: TutorialModule, id: string) {
  if (props.module !== module) {
    pendingSectionId.value = id;
    setExclusiveOpen(module);
    emit("update:module", module);
    emit("update:section", id);
    return;
  }
  scrollToSection(id);
  emit("update:section", id);
  if (window.matchMedia("(max-width: 768px)").matches) {
    setNavCollapsed(true);
  }
}

function postThemeToFrame() {
  const frameWindow = iframeRef.value?.contentWindow;
  if (!frameWindow) return;
  try {
    frameWindow.postMessage(
      { type: "banana-tutorial-theme", theme: getCurrentTheme() },
      window.location.origin,
    );
  } catch {
    /* ignore */
  }
}

function handleFrameLoad() {
  postThemeToFrame();
  const id = pendingSectionId.value || props.sectionId;
  pendingSectionId.value = "";
  showBackTop.value = false;
  if (getTutorialSections(props.module).length && id) {
    window.setTimeout(() => scrollToSection(id), 80);
  }
}

function scrollToDocTop() {
  const frameWindow = iframeRef.value?.contentWindow;
  if (!frameWindow) return;
  try {
    frameWindow.postMessage({ type: "banana-tutorial-scroll-top" }, window.location.origin);
  } catch {
    /* ignore */
  }
}

function handleFrameMessage(event: MessageEvent) {
  if (event.origin !== window.location.origin) return;
  if (event.source !== iframeRef.value?.contentWindow) return;
  const data = event.data;
  if (!data || typeof data !== "object") return;
  if (data.type === "banana-tutorial-scroll-state") {
    showBackTop.value = Boolean(data.visible);
    return;
  }
  if (data.type === "banana-tutorial-preview" && typeof data.src === "string" && data.src) {
    preview.value = {
      src: data.src,
      alt: typeof data.alt === "string" ? data.alt : "",
      caption: typeof data.caption === "string" ? data.caption : "",
    };
    return;
  }
  if (typeof data.id !== "string") return;
  if (data.type === "banana-tutorial-section") {
    activeSectionId.value = data.id;
    return;
  }
  if (data.type === "banana-tutorial-hash") {
    activeSectionId.value = data.id;
    emit("update:section", data.id);
  }
}

function handlePreviewKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape" || !preview.value) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  closePreview();
}

watch(preview, (value) => {
  document.body.classList.toggle("tutorial-shot-lightbox-open", Boolean(value));
});

watch(
  () => props.module,
  (module) => {
    setExclusiveOpen(module);
    activeSectionId.value = props.sectionId || firstSectionId(module);
    frameSrc.value = resolveFrameSrc(module, props.sectionId || firstSectionId(module));
    closePreview();
  },
);

watch(
  () => props.sectionId,
  (id) => {
    if (id) scrollToSection(id);
  },
);

onMounted(() => {
  navCollapsed.value = false;
  window.addEventListener("message", handleFrameMessage);
  window.addEventListener("keydown", handlePreviewKeydown, true);
  themeObserver = new MutationObserver(postThemeToFrame);
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: [APP_THEME_ATTRIBUTE],
  });
});

onBeforeUnmount(() => {
  window.removeEventListener("message", handleFrameMessage);
  window.removeEventListener("keydown", handlePreviewKeydown, true);
  themeObserver?.disconnect();
  themeObserver = null;
  closePreview();
});
</script>

<template>
  <div class="tutorial-shell" :class="{ 'is-nav-collapsed': navCollapsed }">
    <button
      v-if="!navCollapsed"
      type="button"
      class="tutorial-nav-backdrop"
      aria-label="收起目录"
      @click="setNavCollapsed(true)"
    ></button>
    <nav class="tutorial-nav" aria-label="标题导航">
      <div class="tutorial-nav-head">
        <div class="tutorial-nav-title">目录</div>
        <button
          type="button"
          class="nav-toggle"
          aria-label="收起目录"
          @click="toggleNavCollapsed"
        >
          <DoubleLeftOutlined class="nav-toggle-icon" />
        </button>
      </div>

      <div
        v-for="item in tutorialNavOrder"
        :key="item"
        class="nav-group"
        :class="{ 'is-open': openGroups[item] }"
      >
        <button
          type="button"
          class="nav-group-title"
          :class="{
            'is-current': module === item,
            'is-placeholder': tutorialModuleMeta[item].placeholder,
          }"
          :aria-expanded="openGroups[item]"
          @click="selectModule(item)"
        >
          {{ tutorialModuleMeta[item].label }}
        </button>
        <div class="nav-group-children">
          <div class="nav-group-children-inner">
            <template v-if="getTutorialSections(item).length">
              <button
                v-for="section in getTutorialSections(item)"
                :key="section.id"
                type="button"
                class="nav-link"
                :class="{ 'is-active': module === item && activeSectionId === section.id }"
                @click="openModuleSection(item, section.id)"
              >
                {{ section.label }}
              </button>
            </template>
            <span v-else class="nav-link is-soon">内容即将补充</span>
          </div>
        </div>
      </div>
    </nav>

    <div class="tutorial-main">
      <iframe
        ref="iframeRef"
        class="tutorial-frame"
        :src="frameSrc"
        :title="currentMeta.label + '教程'"
        @load="handleFrameLoad"
      />
    </div>

    <div class="tutorial-float-bar">
      <button
        v-if="navCollapsed"
        type="button"
        class="nav-float-toggle"
        aria-label="展开目录"
        @click="toggleNavCollapsed"
      >
        <DoubleRightOutlined class="nav-toggle-icon" />
      </button>
      <label
        v-if="showDockSwitch"
        class="tutorial-dock-switch"
        title="在创作页显示侧边教程入口"
      >
        <span class="tutorial-dock-switch-label">在创作页显示侧边教程入口</span>
        <span class="tutorial-dock-switch-label-short">侧边入口</span>
        <a-switch
          class="warm-switch"
          :checked="dockTabEnabled"
          size="small"
          @change="emit('update:dockTabEnabled', $event)"
        />
      </label>
      <Teleport to="body" :disabled="!showDockSwitch">
        <a-tooltip v-if="showBackTop" title="回到顶部" placement="left">
          <button
            type="button"
            class="tutorial-back-top"
            :class="{ 'is-viewport': showDockSwitch }"
            aria-label="回到顶部"
            @click="scrollToDocTop"
          ></button>
        </a-tooltip>
      </Teleport>
    </div>

    <Teleport to="body">
      <div
        v-if="preview"
        class="tutorial-shot-lightbox"
        role="dialog"
        aria-modal="true"
        :aria-label="preview.caption || preview.alt || '图片预览'"
        @click.self="closePreview"
      >
        <button type="button" class="tutorial-shot-lightbox-close" aria-label="关闭预览" @click="closePreview"></button>
        <figure class="tutorial-shot-lightbox-figure" @click.stop>
          <img class="tutorial-shot-lightbox-image" :src="preview.src" :alt="preview.alt" />
          <figcaption v-if="preview.caption" class="tutorial-shot-lightbox-caption">{{ preview.caption }}</figcaption>
        </figure>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.tutorial-shell {
  position: relative;
  display: flex;
  align-items: stretch;
  height: 100%;
  min-height: 0;
  background: var(--theme-page-base, #fffaf3);
}

.nav-float-toggle,
.tutorial-nav-backdrop {
  display: none;
}

.tutorial-nav {
  position: relative;
  z-index: 2;
  flex: 0 0 220px;
  width: 220px;
  height: 100%;
  padding: 16px 12px 28px;
  overflow: hidden auto;
  border-right: 1px solid var(--theme-panel-border, rgba(80, 52, 20, 0.08));
  background: var(--theme-panel-bg, #fffdf8);
  transition: flex-basis 0.22s ease, width 0.22s ease, padding 0.22s ease;
}

.tutorial-nav-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 4px 12px;
}

.tutorial-nav-title {
  color: var(--theme-title, #3d2f22);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.nav-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--theme-text-secondary, #8b7457);
  cursor: pointer;
}

.nav-toggle:hover {
  background: var(--theme-nav-hover-bg);
  color: var(--theme-title);
}

.nav-toggle-icon {
  font-size: 14px;
  line-height: 1;
}

.tutorial-shell.is-nav-collapsed .tutorial-nav {
  flex-basis: 44px;
  width: 44px;
  padding: 12px 6px;
}

.tutorial-shell.is-nav-collapsed .tutorial-nav-head {
  margin: 0;
  justify-content: center;
}

.tutorial-shell.is-nav-collapsed .tutorial-nav-title,
.tutorial-shell.is-nav-collapsed .nav-group {
  display: none;
}

.nav-group + .nav-group {
  margin-top: 6px;
}

.nav-group-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--theme-title, #3d2f22);
  font-size: 14px;
  font-weight: 700;
  text-align: left;
  cursor: pointer;
}

.nav-group-title:hover,
.nav-group-title.is-current {
  background: var(--theme-nav-hover-bg);
}

.nav-group-title::after {
  content: "";
  width: 6px;
  height: 6px;
  margin-left: 8px;
  border-right: 1.5px solid var(--theme-text-secondary, #8b7457);
  border-bottom: 1.5px solid var(--theme-text-secondary, #8b7457);
  transform: rotate(-45deg);
  transition: transform 0.18s ease;
}

.nav-group.is-open .nav-group-title::after {
  transform: rotate(45deg);
}

.nav-group-title.is-placeholder {
  color: var(--theme-text-secondary, #8b7457);
  font-weight: 600;
}

.nav-group-children {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.2s ease, padding 0.2s ease;
}

.nav-group-children-inner {
  overflow: hidden;
  min-height: 0;
}

.nav-group.is-open .nav-group-children {
  grid-template-rows: 1fr;
  padding: 2px 0 6px;
}

.nav-link {
  display: block;
  width: 100%;
  padding: 8px 10px 8px 18px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--theme-text-secondary, #8b7457);
  text-align: left;
  text-decoration: none;
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
}

.nav-link:hover {
  background: var(--theme-nav-hover-bg);
  color: var(--theme-title);
}

.nav-link.is-active {
  background: color-mix(in srgb, var(--theme-accent) 16%, transparent);
  color: var(--theme-accent-text);
  font-weight: 700;
}

.nav-link.is-soon {
  color: var(--theme-text-muted);
  cursor: default;
}

.tutorial-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.tutorial-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
  background: var(--theme-page-base, #fffaf3);
}

.tutorial-float-bar {
  pointer-events: none;
}

.tutorial-float-bar > * {
  pointer-events: auto;
}

.tutorial-dock-switch {
  position: absolute;
  top: 12px;
  right: 16px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--theme-panel-border, rgba(80, 52, 20, 0.08));
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-panel-bg) 92%, transparent);
  box-shadow: 0 6px 16px var(--theme-shadow-soft);
  color: var(--theme-text-secondary, #8b7457);
  font-size: 12px;
  line-height: 1.2;
  cursor: pointer;
}

.tutorial-dock-switch-label {
  white-space: nowrap;
}

.tutorial-dock-switch-label-short {
  display: none;
}

.tutorial-back-top.is-viewport {
  position: fixed;
  z-index: 1040;
}

.tutorial-back-top {
  position: absolute;
  right: 88px;
  bottom: 24px;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 1px solid var(--theme-panel-border, rgba(80, 52, 20, 0.08));
  border-radius: 50%;
  background: var(--theme-panel-bg, #fffdf8);
  box-shadow: 0 8px 20px var(--theme-shadow-medium);
  color: var(--theme-title, #3d2f22);
  cursor: pointer;
}

.tutorial-back-top::before {
  content: "";
  width: 8px;
  height: 8px;
  border-top: 2px solid currentColor;
  border-left: 2px solid currentColor;
  transform: translateY(2px) rotate(45deg);
}

@media (max-width: 768px) {
  .tutorial-nav-backdrop {
    display: block;
    position: absolute;
    inset: 0;
    z-index: 5;
    border: 0;
    padding: 0;
    background: var(--theme-overlay-medium);
    cursor: pointer;
  }

  .tutorial-float-bar {
    position: static;
  }

  .nav-float-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    position: absolute;
    top: 0;
    left: 0;
    z-index: 5;
    width: 36px;
    height: 36px;
    padding: 0;
    border: 1px solid var(--theme-panel-border, rgba(80, 52, 20, 0.08));
    border-radius: 10px;
    background: var(--theme-panel-bg, #fffdf8);
    box-shadow: 0 6px 16px var(--theme-shadow-soft);
    color: var(--theme-title, #3d2f22);
    cursor: pointer;
  }

  .tutorial-dock-switch {
    top: 0;
    right: 0;
    z-index: 5;
    padding: 5px 8px;
  }

  .tutorial-dock-switch-label {
    display: none;
  }

  .tutorial-dock-switch-label-short {
    display: inline;
    white-space: nowrap;
  }

  .tutorial-back-top {
    right: 16px;
    bottom: calc(16px + env(safe-area-inset-bottom, 0px));
    width: 36px;
    height: 36px;
  }

  .tutorial-nav {
    position: absolute;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 6;
    flex-basis: min(280px, 82vw);
    width: min(280px, 82vw);
    box-shadow: 8px 0 24px var(--theme-shadow-medium);
  }

  .tutorial-shell.is-nav-collapsed .tutorial-nav {
    flex-basis: 0;
    width: 0;
    padding: 0;
    border: 0;
    overflow: hidden;
    box-shadow: none;
  }
}
</style>

<style>
body.tutorial-shot-lightbox-open {
  overflow: hidden;
}

.tutorial-shot-lightbox {
  position: fixed;
  inset: 0;
  z-index: 4000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px 20px;
  background: var(--theme-overlay-heavy);
  cursor: zoom-out;
}

.tutorial-shot-lightbox-figure {
  margin: 0;
  max-width: min(1200px, 100%);
  max-height: 100%;
  cursor: default;
}

.tutorial-shot-lightbox-image {
  display: block;
  max-width: 100%;
  max-height: calc(100dvh - 96px);
  border: 0;
  border-radius: 12px;
  background: var(--theme-surface-strong);
  box-shadow: 0 18px 48px var(--theme-shadow-strong);
  object-fit: contain;
}

.tutorial-shot-lightbox-caption {
  margin-top: 10px;
  color: #fff;
  font-size: 13px;
  text-align: center;
}

.tutorial-shot-lightbox-close {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  cursor: pointer;
}

.tutorial-shot-lightbox-close::before,
.tutorial-shot-lightbox-close::after {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: 16px;
  height: 1.6px;
  background: currentColor;
}

.tutorial-shot-lightbox-close::before {
  transform: translate(-50%, -50%) rotate(45deg);
}

.tutorial-shot-lightbox-close::after {
  transform: translate(-50%, -50%) rotate(-45deg);
}

.tutorial-shot-lightbox-close:hover {
  background: rgba(255, 255, 255, 0.28);
}
</style>
