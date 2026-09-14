<script setup lang="ts">
import DeferredWorkbenchPage from "@/components/generate/DeferredWorkbenchPage.vue";

const tabs = ["文生图", "图编辑"];
const loadGenerateView = () => import("@/views/GenerateView.vue");
</script>

<template>
  <DeferredWorkbenchPage
    cache-key="generate"
    :load="loadGenerateView"
    :tabs="tabs"
    action-label="开始生成"
  />
</template>
