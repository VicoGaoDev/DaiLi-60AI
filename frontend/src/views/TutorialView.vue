<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import TutorialDocFrame from "@/components/tutorial/TutorialDocFrame.vue";
import {
  isTutorialDockTabEnabled,
  setTutorialDockTabEnabled,
} from "@/lib/generateTutorialDock";
import {
  DEFAULT_TUTORIAL_MODULE,
  isTutorialModule,
  resolveTutorialModule,
  tutorialModuleMeta,
  type TutorialModule,
} from "@/lib/tutorial";

const route = useRoute();
const router = useRouter();
const dockTabEnabled = ref(isTutorialDockTabEnabled());

const currentModule = computed(() => resolveTutorialModule(String(route.params.module || "")));
const currentSectionId = computed(() => decodeURIComponent(String(route.hash || "").replace(/^#/, "")));

function goModule(module: TutorialModule) {
  if (module === currentModule.value) return;
  void router.push(tutorialModuleMeta[module].path);
}

function goSection(id: string) {
  const nextHash = id ? `#${id}` : "";
  if (route.hash === nextHash) return;
  void router.replace({ hash: nextHash });
}

function handleDockTabEnabledChange(enabled: boolean) {
  dockTabEnabled.value = enabled;
  setTutorialDockTabEnabled(enabled);
}

watch(
  () => route.params.module,
  (module) => {
    if (!isTutorialModule(String(module || ""))) {
      void router.replace(tutorialModuleMeta[DEFAULT_TUTORIAL_MODULE].path);
    }
  },
  { immediate: true },
);
</script>

<template>
  <div class="tutorial-page">
    <TutorialDocFrame
      :module="currentModule"
      :section-id="currentSectionId"
      show-dock-switch
      :dock-tab-enabled="dockTabEnabled"
      @update:module="goModule"
      @update:section="goSection"
      @update:dock-tab-enabled="handleDockTabEnabledChange"
    />
  </div>
</template>

<style scoped>
.tutorial-page {
  position: relative;
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 50px);
  min-height: 560px;
  background: var(--theme-page-base, #fffaf3);
}

@media (max-width: 768px) {
  .tutorial-page {
    min-height: 0;
  }
}
</style>
