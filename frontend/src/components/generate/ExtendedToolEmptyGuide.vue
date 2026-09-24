<script setup lang="ts">
import { computed } from "vue";
import { withBaseUrl } from "@/lib/assets";

const props = defineProps<{
  mode: "promptReverse" | "inpaint" | "smartCutout";
}>();

const guides = {
  promptReverse: {
    title: "提示词反推",
    desc: "上传一张图，系统会帮你写出可用的提示词。",
    image: withBaseUrl("docs/tutorial/22-prompt-reverse-tip.jpg"),
    alt: "提示词反推示例：根据图片生成可用提示词",
    captions: null as [string, string] | null,
  },
  inpaint: {
    title: "局部重绘",
    desc: "在原图上涂抹要改的区域，只重绘这一块，其余保持不变。",
    image: withBaseUrl("docs/tutorial/21-inpaint-compare-tip.jpg"),
    alt: "局部重绘前后对比：左边是原图，右边是局部修改后的结果",
    captions: ["编辑前", "编辑后"] as [string, string],
  },
  smartCutout: {
    title: "智能抠图",
    desc: "支持根据提示词自动抠图，也可手动涂抹自定义区域，结果为透明背景 PNG。",
    image: withBaseUrl("docs/tutorial/20-smart-cutout-compare-tip.jpg"),
    alt: "智能抠图前后对比：左边是原图，右边是透明背景结果",
    captions: ["原图", "抠图后"] as [string, string],
  },
};

const guide = computed(() => guides[props.mode]);
</script>

<template>
  <div class="extended-tool-guide">
    <header class="extended-tool-guide-hero">
      <h3>{{ guide.title }}</h3>
      <p>{{ guide.desc }}</p>
    </header>

    <figure class="extended-tool-guide-compare">
      <img
        :src="guide.image"
        :alt="guide.alt"
        class="extended-tool-guide-img"
      />
      <figcaption v-if="guide.captions">
        <span>{{ guide.captions[0] }}</span>
        <span>{{ guide.captions[1] }}</span>
      </figcaption>
    </figure>
  </div>
</template>

<style scoped>
.extended-tool-guide {
  width: min(100%, 560px);
  padding: 2px 0 4px;
  text-align: left;
}

.extended-tool-guide-hero {
  margin-bottom: 14px;
}

.extended-tool-guide h3 {
  margin: 0;
  color: var(--theme-title);
  font-size: 18px;
  font-weight: 800;
  line-height: 1.3;
}

.extended-tool-guide p {
  margin: 6px 0 0;
  color: var(--theme-text-secondary, var(--text-secondary));
  font-size: 13px;
  line-height: 1.6;
}

.extended-tool-guide-compare {
  margin: 0;
}

.extended-tool-guide-img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid var(--theme-panel-border);
  border-radius: 16px;
  background: var(--theme-panel-bg);
}

.extended-tool-guide-compare figcaption {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  padding: 0 8px;
  color: var(--theme-text-secondary, var(--text-secondary));
  font-size: 12px;
  font-weight: 700;
}
</style>
