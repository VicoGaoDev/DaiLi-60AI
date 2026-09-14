<script setup lang="ts">
import { computed, defineAsyncComponent, inject, onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";
import { CloseOutlined, PlusOutlined } from "@ant-design/icons-vue";
import { Modal } from "ant-design-vue";
import { useRouter } from "vue-router";
import { withBaseUrl } from "@/lib/assets";
import { setAiAssistantDockTabEnabled } from "@/lib/aiAssistantDock";
import { CLOSE_AI_ASSISTANT_DOCK_EVENT } from "@/lib/chatGenerateDraft";
import { requestCloseGenerateTutorialDock } from "@/lib/generateTutorialDock";
import { importAfterExtendedAntd } from "@/lib/antd";
import { useAuthStore } from "@/stores/auth";

const ChatWorkspace = defineAsyncComponent(() => importAfterExtendedAntd(() => import("@/components/chat/ChatWorkspace.vue")));
const xiaobaAvatarSrc = withBaseUrl("chat-xiaoba-avatar.png");
const router = useRouter();
const auth = useAuthStore();
const loginModalVisible = inject<Ref<boolean>>("loginModalVisible");

const open = ref(false);
const tabVisible = ref(true);
const workspaceReady = ref(false);
const sessionId = ref<string | null>(null);
const workspaceRef = ref<{ createSession: () => Promise<void> } | null>(null);
let tabRevealTimer = 0;

const chatPageHref = computed(() => (sessionId.value ? `/chat/${sessionId.value}` : "/chat"));

function syncBodyDockClass() {
  document.body.classList.toggle("ai-assistant-dock-open", open.value);
}

function revealTab() {
  window.clearTimeout(tabRevealTimer);
  tabRevealTimer = window.setTimeout(() => {
    if (!open.value) tabVisible.value = true;
  }, 280);
}

function openDock() {
  if (!auth.isLoggedIn) {
    if (loginModalVisible) loginModalVisible.value = true;
    return;
  }
  window.clearTimeout(tabRevealTimer);
  requestCloseGenerateTutorialDock();
  workspaceReady.value = true;
  tabVisible.value = false;
  open.value = true;
}

function closeDock() {
  if (!open.value) return;
  open.value = false;
  revealTab();
}

function confirmHideDockTab() {
  Modal.confirm({
    title: "关闭侧边 AI 助手？",
    content: "关闭后，创作页右侧将不再显示 AI 助手入口。你可以在 AI 对话页面中重新开启侧边模式。",
    okText: "关闭入口",
    cancelText: "取消",
    onOk: () => {
      closeDock();
      setAiAssistantDockTabEnabled(false);
    },
  });
}

function openFullChat() {
  closeDock();
  void router.push(chatPageHref.value);
}

function createNewChat() {
  void workspaceRef.value?.createSession();
}

function handleWindowKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") closeDock();
}

watch(open, syncBodyDockClass);

watch(() => auth.isLoggedIn, (loggedIn) => {
  if (loggedIn) return;
  closeDock();
  workspaceReady.value = false;
  sessionId.value = null;
});

onMounted(() => {
  window.addEventListener("keydown", handleWindowKeydown);
  window.addEventListener(CLOSE_AI_ASSISTANT_DOCK_EVENT, closeDock);
});

onBeforeUnmount(() => {
  window.clearTimeout(tabRevealTimer);
  window.removeEventListener("keydown", handleWindowKeydown);
  window.removeEventListener(CLOSE_AI_ASSISTANT_DOCK_EVENT, closeDock);
  document.body.classList.remove("ai-assistant-dock-open");
});
</script>

<template>
  <div v-show="tabVisible" class="ai-assistant-tab-wrap">
    <button
      type="button"
      class="ai-assistant-tab"
      aria-label="AI助手"
      @click="openDock"
    >
      <img :src="xiaobaAvatarSrc" alt="" class="ai-assistant-tab-avatar" />
      <span class="ai-assistant-tab-label">AI助手</span>
    </button>
    <button
      type="button"
      class="ai-assistant-tab-close"
      aria-label="关闭侧边AI助手"
      title="关闭侧边入口"
      @click.stop="confirmHideDockTab"
    >
      <CloseOutlined />
    </button>
  </div>

  <aside
    class="ai-assistant-panel"
    :class="{ 'is-open': open }"
    :aria-hidden="!open"
  >
    <header class="ai-assistant-panel-head">
      <div class="ai-assistant-panel-title">
        <img :src="xiaobaAvatarSrc" alt="" class="ai-assistant-panel-icon" />
        <strong>AI助手</strong>
        <button
          type="button"
          class="ai-assistant-new-chat"
          @click="createNewChat"
        >
          <PlusOutlined />
          <span>新建对话</span>
        </button>
      </div>
      <div class="ai-assistant-panel-actions">
        <button type="button" class="ai-assistant-open-full" @click="openFullChat">
          在对话页打开
        </button>
        <button type="button" class="ai-assistant-close" aria-label="关闭" @click="closeDock">
          <CloseOutlined />
        </button>
      </div>
    </header>
    <div class="ai-assistant-panel-body">
      <ChatWorkspace
        v-if="workspaceReady"
        ref="workspaceRef"
        embedded
        :sync-route="false"
        @update:session-id="sessionId = $event"
      />
    </div>
  </aside>
</template>

<style scoped>
.ai-assistant-tab-wrap {
  position: fixed;
  top: 50%;
  right: 0;
  z-index: 1060;
  transform: translateY(-50%);
}

.ai-assistant-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 44px;
  padding: 12px 6px 14px;
  border: 1px solid var(--theme-accent);
  border-right: 0;
  border-radius: 16px 0 0 16px;
  background: var(--theme-accent);
  box-shadow: -6px 8px 20px var(--theme-fab-shadow);
  color: var(--theme-accent-contrast);
  cursor: pointer;
  transition:
    background 0.2s ease,
    box-shadow 0.2s ease,
    width 0.2s ease;
}

.ai-assistant-tab-wrap:hover .ai-assistant-tab {
  width: 50px;
  background: var(--primary-dark);
  box-shadow: -8px 10px 24px var(--theme-fab-shadow);
}

.ai-assistant-tab-close {
  position: absolute;
  top: 2px;
  left: 2px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: color-mix(in srgb, #000 28%, transparent);
  color: #fff;
  font-size: 10px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease, background 0.16s ease;
}

.ai-assistant-tab-wrap:hover .ai-assistant-tab-close {
  opacity: 1;
  pointer-events: auto;
}

.ai-assistant-tab-close:hover {
  background: color-mix(in srgb, #000 46%, transparent);
}

.ai-assistant-tab-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  object-fit: cover;
}

.ai-assistant-tab-label {
  writing-mode: vertical-rl;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.12em;
  line-height: 1.1;
}

.ai-assistant-panel {
  position: fixed;
  top: 0;
  right: 0;
  z-index: 1061;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  width: min(598px, 100vw);
  max-width: 598px;
  height: 100dvh;
  overflow: hidden;
  background: var(--theme-page-base);
  box-shadow: -12px 0 28px var(--theme-shadow-medium);
  transform: translateX(100%);
  visibility: hidden;
  pointer-events: none;
  transition: transform 0.28s ease, visibility 0s linear 0.28s;
}

.ai-assistant-panel.is-open {
  transform: translateX(0);
  visibility: visible;
  pointer-events: auto;
  transition: transform 0.28s ease;
}

.ai-assistant-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  height: 56px;
  padding: 0 16px;
  border-bottom: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.06));
}

.ai-assistant-panel-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ai-assistant-panel-icon {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}

.ai-assistant-panel-head strong {
  color: var(--theme-title, #3d2f22);
  font-size: 16px;
}

.ai-assistant-new-chat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--theme-panel-border, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
  background: var(--theme-panel-bg-muted, #fff);
  color: var(--theme-title, #3d2f22);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.ai-assistant-new-chat:hover {
  background: var(--theme-control-hover-bg, rgba(0, 0, 0, 0.04));
  border-color: var(--theme-border-strong, rgba(0, 0, 0, 0.16));
}

.ai-assistant-panel-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ai-assistant-open-full {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--theme-link, #d38a12);
  font-size: 13px;
  cursor: pointer;
}

.ai-assistant-close {
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

.ai-assistant-close:hover {
  background: color-mix(in srgb, var(--theme-title, #3d2f22) 8%, transparent);
  color: var(--theme-title, #3d2f22);
}

.ai-assistant-panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 768px) {
  .ai-assistant-tab-wrap {
    display: none;
  }
}
</style>

<style>
body.ai-assistant-dock-open .suggestion-fab-wrap {
  visibility: hidden;
  pointer-events: none;
}
</style>
