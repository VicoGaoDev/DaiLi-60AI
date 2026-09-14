<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import privacyPolicy from "../../../docs/privacy_policy.md?raw";
import userAgreement from "../../../docs/user_agreement.md?raw";

type LegalBlock =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "quote"; text: string }
  | { type: "list"; items: string[] }
  | { type: "divider" };

const route = useRoute();

const documents = {
  UserAgreement: {
    title: "用户协议",
    content: userAgreement,
  },
  PrivacyPolicy: {
    title: "隐私政策",
    content: privacyPolicy,
  },
} as const;

const currentDocument = computed(() => {
  return route.name === "PrivacyPolicy" ? documents.PrivacyPolicy : documents.UserAgreement;
});

const legalBlocks = computed(() => {
  return parseLegalMarkdown(currentDocument.value.content);
});

function parseLegalMarkdown(markdown: string): LegalBlock[] {
  const blocks: LegalBlock[] = [];
  let listItems: string[] = [];

  function flushList() {
    if (!listItems.length) return;
    blocks.push({ type: "list", items: listItems });
    listItems = [];
  }

  markdown.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }

    const listItem = /^[-*]\s+(.+)$/.exec(line);
    if (listItem) {
      listItems.push(listItem[1]);
      return;
    }

    flushList();

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      blocks.push({
        type: "heading",
        level: Math.min(heading[1].length, 3) as 1 | 2 | 3,
        text: heading[2],
      });
      return;
    }

    if (/^---+$/.test(line)) {
      blocks.push({ type: "divider" });
      return;
    }

    if (line.startsWith(">")) {
      blocks.push({ type: "quote", text: line.replace(/^>\s?/, "") });
      return;
    }

    blocks.push({ type: "paragraph", text: line });
  });

  flushList();
  return blocks;
}
</script>

<template>
  <div class="legal-page">
    <a-card class="legal-card" :bordered="false">
      <div class="legal-header">
        <div class="legal-eyebrow">80 AI</div>
        <h1>{{ currentDocument.title }}</h1>
      </div>

      <div class="legal-content">
        <template v-for="(block, index) in legalBlocks" :key="index">
          <h1 v-if="block.type === 'heading' && block.level === 1">{{ block.text }}</h1>
          <h2 v-else-if="block.type === 'heading' && block.level === 2">{{ block.text }}</h2>
          <h3 v-else-if="block.type === 'heading'">{{ block.text }}</h3>
          <blockquote v-else-if="block.type === 'quote'">{{ block.text }}</blockquote>
          <ul v-else-if="block.type === 'list'">
            <li v-for="(item, itemIndex) in block.items" :key="itemIndex">{{ item }}</li>
          </ul>
          <hr v-else-if="block.type === 'divider'" />
          <p v-else>{{ block.text }}</p>
        </template>
      </div>
    </a-card>
  </div>
</template>

<style scoped lang="scss">
.legal-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 42px 20px 72px;
}

.legal-card {
  border-radius: 28px;
  box-shadow: 0 24px 60px rgba(105, 69, 42, 0.12);
}

.legal-header {
  margin-bottom: 28px;
  padding-bottom: 22px;
  border-bottom: 1px solid rgba(105, 69, 42, 0.12);

  h1 {
    margin: 8px 0 0;
    color: var(--theme-title);
    font-size: 30px;
    font-weight: 800;
  }
}

.legal-eyebrow {
  color: var(--theme-subtitle);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.legal-content {
  color: var(--theme-text);
  font-size: 15px;
  line-height: 1.9;

  h1,
  h2,
  h3 {
    color: var(--theme-title);
    font-weight: 800;
    line-height: 1.35;
  }

  h1 {
    margin: 0 0 18px;
    font-size: 26px;
  }

  h2 {
    margin: 30px 0 12px;
    font-size: 20px;
  }

  h3 {
    margin: 22px 0 10px;
    font-size: 17px;
  }

  p {
    margin: 0 0 12px;
  }

  blockquote {
    margin: 0 0 18px;
    padding: 12px 16px;
    color: var(--theme-text-secondary);
    background: rgba(255, 178, 77, 0.1);
    border-left: 4px solid var(--theme-primary);
    border-radius: 12px;
  }

  ul {
    margin: 0 0 16px;
    padding-left: 22px;
  }

  li {
    margin-bottom: 8px;
  }

  hr {
    margin: 26px 0;
    border: none;
    border-top: 1px solid rgba(105, 69, 42, 0.12);
  }
}
</style>
