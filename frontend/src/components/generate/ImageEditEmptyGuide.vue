<script setup lang="ts">
import { computed } from "vue";
import { withBaseUrl } from "@/lib/assets";

const props = withDefaults(defineProps<{
  mode?: "imageEdit" | "textGenerate";
}>(), {
  mode: "imageEdit",
});

const allSteps = [
  {
    title: "选择模型",
    desc: "先选好模型。不确定时可以点「模型对比」。",
    image: withBaseUrl("docs/tutorial/24-image-edit-step-1-model.png"),
    alt: "配置区中的模型选择",
    id: "model",
  },
  {
    title: "上传参考图",
    desc: "拖拽、点击或从「我的素材」加入至少一张原图。",
    image: withBaseUrl("docs/tutorial/24-image-edit-step-2-ref.png"),
    alt: "上传参考图到图编辑",
    id: "ref",
  },
  {
    title: "输入提示词",
    desc: "写明要保留什么、改成什么，例如换背景或换服装。",
    textGenerateDesc: "描述您想要生成的画面，例如主体、风格、场景和光线。",
    image: withBaseUrl("docs/tutorial/24-image-edit-step-3-prompt.png"),
    alt: "在提示词框描述生成效果",
    id: "prompt",
  },
  {
    title: "选择宽高比、分辨率、生成数量",
    desc: "按需要调整比例、清晰度和一次出几张。",
    image: withBaseUrl("docs/tutorial/24-image-edit-step-4-params.png"),
    alt: "选择宽高比、分辨率和生成数量",
    id: "params",
  },
  {
    title: "点击生成",
    desc: "确认积分后点击「开始生成」，任务会出现在这里。",
    image: withBaseUrl("docs/tutorial/24-image-edit-step-5-submit.png"),
    alt: "点击开始生成提交任务",
    id: "submit",
  },
];

const steps = computed(() => {
  const list = props.mode === "textGenerate"
    ? allSteps.filter((step) => step.id !== "ref")
    : allSteps;

  return list.map((step) => ({
    ...step,
    desc: props.mode === "textGenerate" && step.textGenerateDesc
      ? step.textGenerateDesc
      : step.desc,
  }));
});

const title = computed(() => (
  props.mode === "textGenerate" ? "按 4 步完成文生图" : "按 5 步完成图编辑"
));
</script>

<template>
  <div class="image-edit-guide">
    <header class="image-edit-guide-hero">
      <h3>{{ title }}</h3>
    </header>

    <ol class="image-edit-guide-steps">
      <li v-for="(step, index) in steps" :key="step.title" class="image-edit-guide-step">
        <div class="image-edit-guide-step-copy">
          <div class="image-edit-guide-index">{{ index + 1 }}</div>
          <div>
            <h4>{{ step.title }}</h4>
            <p>{{ step.desc }}</p>
          </div>
        </div>
        <img
          :src="step.image"
          :alt="step.alt"
          class="image-edit-guide-shot"
        />
      </li>
    </ol>
  </div>
</template>

<style scoped>
.image-edit-guide {
  width: min(100%, 680px);
  padding: 2px 0 4px;
  text-align: left;
}

.image-edit-guide-hero {
  margin-bottom: 10px;
}

.image-edit-guide h3 {
  margin: 0;
  color: var(--theme-title);
  font-size: 18px;
  font-weight: 800;
  line-height: 1.3;
}

.image-edit-guide-step p {
  margin: 4px 0 0;
  color: var(--theme-text-secondary, var(--text-secondary));
  font-size: 12px;
  line-height: 1.5;
}

.image-edit-guide-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.image-edit-guide-step {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(188px, 42%);
  gap: 12px;
  align-items: center;
  min-height: 0;
  padding: 8px 10px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 12px;
  background: var(--theme-panel-bg-soft, var(--theme-panel-bg));
}

.image-edit-guide-step-copy {
  display: flex;
  gap: 10px;
  min-width: 0;
}

.image-edit-guide-index {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  font-size: 12px;
  font-weight: 800;
}

.image-edit-guide-step h4 {
  margin: 0;
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 800;
  line-height: 1.3;
}

.image-edit-guide-shot {
  width: 100%;
  height: 84px;
  object-fit: contain;
  object-position: center;
  border: 1px solid var(--theme-panel-border);
  border-radius: 8px;
  background: var(--theme-panel-bg);
}

@media (max-width: 720px) {
  .image-edit-guide-step {
    grid-template-columns: 1fr;
  }

  .image-edit-guide-shot {
    height: 100px;
  }
}
</style>
