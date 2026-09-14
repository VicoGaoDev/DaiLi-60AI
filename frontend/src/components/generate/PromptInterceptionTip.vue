<script setup lang="ts">
import { WarningFilled } from "@ant-design/icons-vue";
import {
  PROMPT_INTERCEPTION_TIP_FOOTNOTE,
  PROMPT_INTERCEPTION_TIP_SECTIONS,
  PROMPT_INTERCEPTION_TIP_TITLE,
  type PromptInterceptionTipSection,
} from "@/lib/promptInterceptionTip";

withDefaults(defineProps<{
  title?: string;
  sections?: PromptInterceptionTipSection[];
  footnote?: string;
}>(), {
  title: PROMPT_INTERCEPTION_TIP_TITLE,
  sections: () => PROMPT_INTERCEPTION_TIP_SECTIONS,
  footnote: PROMPT_INTERCEPTION_TIP_FOOTNOTE,
});

function getBodyPopupContainer() {
  return document.body;
}
</script>

<template>
  <a-tooltip :title="title" :get-popup-container="getBodyPopupContainer">
    <a-popover
      trigger="click"
      placement="bottomLeft"
      overlay-class-name="prompt-interception-popover"
      class="prompt-interception-popover-trigger"
      :get-popup-container="getBodyPopupContainer"
    >
      <template #content>
        <div class="prompt-interception-tip-panel">
          <div class="prompt-interception-tip-panel-title">{{ title }}</div>
          <div
            v-for="section in sections"
            :key="section.title"
            class="prompt-interception-tip-section"
          >
            <div class="prompt-interception-tip-section-title">{{ section.title }}</div>
            <ul class="prompt-interception-tip-list">
              <li v-for="item in section.items" :key="item">{{ item }}</li>
            </ul>
          </div>
          <div class="prompt-interception-tip-footnote">{{ footnote }}</div>
        </div>
      </template>
      <button type="button" class="prompt-interception-trigger" :aria-label="title">
        <WarningFilled class="prompt-interception-trigger-icon" />
      </button>
    </a-popover>
  </a-tooltip>
</template>

<style scoped lang="scss">
.prompt-interception-popover-trigger {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}

.prompt-interception-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  background: transparent;
  color: #faad14;
  line-height: 1;
  cursor: pointer;
  transition:
    transform var(--motion-duration-press) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    opacity var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    color: #ffc53d;
    transform: translateY(-1px);
  }

  &:active {
    transform: scale(0.96);
  }
}

.prompt-interception-trigger-icon {
  color: inherit;
  font-size: 18px;
}
</style>

<style lang="scss">
.prompt-interception-popover {
  z-index: 1300;
  max-width: calc(100vw - 40px);

  .ant-popover-inner {
    padding: 0;
    border-radius: 16px;
    background: rgba(12, 12, 12, 0.96);
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
  }

  .ant-popover-inner-content {
    padding: 12px 14px;
  }

  .ant-popover-arrow::before {
    background: rgba(12, 12, 12, 0.96);
  }

  .prompt-interception-tip-panel {
    width: min(420px, calc(100vw - 68px));
    color: #f5f5f5;
  }

  .prompt-interception-tip-panel-title {
    margin-bottom: 10px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 800;
    line-height: 1.4;
  }

  .prompt-interception-tip-section + .prompt-interception-tip-section {
    margin-top: 12px;
  }

  .prompt-interception-tip-section-title {
    margin-bottom: 6px;
    color: #ffd666;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.5;
  }

  .prompt-interception-tip-list {
    margin: 0;
    padding-left: 18px;
    color: rgba(245, 245, 245, 0.92);
    font-size: 13px;
    line-height: 1.65;
  }

  .prompt-interception-tip-list li + li {
    margin-top: 6px;
  }

  .prompt-interception-tip-footnote {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    color: rgba(245, 245, 245, 0.78);
    font-size: 12px;
    line-height: 1.6;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .generate-page .prompt-interception-trigger {
  color: #ffc53d;

  &:hover {
    color: #ffd666;
  }
}
</style>
