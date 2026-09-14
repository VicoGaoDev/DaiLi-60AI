<script setup lang="ts">
import DeferredWorkbenchPage from "@/components/generate/DeferredWorkbenchPage.vue";

const tabs = ["文生视频", "图生视频", "首尾帧"];
const loadVideoGenerateView = () => import("@/views/VideoGenerateView.vue");
</script>

<template>
  <DeferredWorkbenchPage
    cache-key="video-generate"
    :load="loadVideoGenerateView"
    :tabs="tabs"
    action-label="开始生成"
  />
</template>
