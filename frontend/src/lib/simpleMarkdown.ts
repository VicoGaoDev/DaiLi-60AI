import MarkdownIt from "markdown-it";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatInline(text: string): string {
  let html = escapeHtml(text);
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  return html;
}

function stripInlineMarkdown(text: string): string {
  return text
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1$2")
    .trim();
}

export function stripMarkdownDecorations(text: string): string {
  return text
    .replace(/```[\w-]*\n?([\s\S]*?)```/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^>\s?/gm, "")
    .replace(/^[-*]\s+/gm, "")
    .replace(/^\d+\.\s+/gm, "")
    .replace(/^---+$/gm, "")
    .split("\n")
    .map((line) => stripInlineMarkdown(line))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const markdownRenderer = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
});

const defaultLinkOpen =
  markdownRenderer.renderer.rules.link_open
  || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));

markdownRenderer.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  token.attrSet("target", "_blank");
  token.attrSet("rel", "noopener noreferrer nofollow");
  return defaultLinkOpen(tokens, idx, options, env, self);
};

markdownRenderer.renderer.rules.table_open = () => '<div class="md-table-wrap"><table class="md-table">';
markdownRenderer.renderer.rules.table_close = () => "</table></div>";

const COPY_ICON = '<svg viewBox="64 64 896 896" width="14" height="14" aria-hidden="true" fill="currentColor"><path d="M832 64H296c-4.4 0-8 3.6-8 8v56c0 4.4 3.6 8 8 8h496v688c0 4.4 3.6 8 8 8h56c4.4 0 8-3.6 8-8V96c0-17.7-14.3-32-32-32zM704 192H192c-17.7 0-32 14.3-32 32v530.7c0 8.5 3.4 16.6 9.4 22.6l173.3 173.3c2.2 2.2 4.7 4 7.4 5.5v1.9h4.2c3.5 1.3 7.2 2 11 2H704c17.7 0 32-14.3 32-32V224c0-17.7-14.3-32-32-32zM350 856.2L263.9 770H350v86.2zM664 888H414V746c0-22.1-17.9-40-40-40H232V264h432v624z"/></svg>';
const CHECK_ICON = '<svg viewBox="64 64 896 896" width="14" height="14" aria-hidden="true" fill="currentColor"><path d="M912 190h-69.9c-9.8 0-19.1 4.5-25.1 12.2L404.7 724.5 207 474a32 32 0 00-25.1-12.2H112c-6.7 0-10.4 7.7-6.3 12.9l273.9 347c12.8 16.2 37.4 16.2 50.3 0l488.4-618.9c4.1-5.1.4-12.8-6.3-12.8z"/></svg>';
const GENERATE_ICON = '<svg viewBox="64 64 896 896" width="14" height="14" aria-hidden="true" fill="currentColor"><path d="M928 160H96c-17.7 0-32 14.3-32 32v640c0 17.7 14.3 32 32 32h832c17.7 0 32-14.3 32-32V192c0-17.7-14.3-32-32-32zm-40 632H136v-39.9l138.5-164.3 150.1 178L658.1 489 888 761.6V792zm0-129.8L664.2 396.8c-3.2-3.8-9-3.8-12.2 0L424.6 666.4l-144-170.7c-3.2-3.8-9-3.8-12.2 0L136 652.7V232h752v430.2zM304 456a88 88 0 100-176 88 88 0 000 176zm0-116c15.5 0 28 12.5 28 28s-12.5 28-28 28-28-12.5-28-28 12.5-28 28-28z"/></svg>';

function fenceInfoName(info: string): string {
  return (info || "").trim().split(/\s+/)[0] || "";
}

function isPromptFence(info: string): boolean {
  const raw = fenceInfoName(info);
  return raw === "提示词" || raw.toLowerCase() === "prompt";
}

function normalizeLang(info: string): string {
  if (isPromptFence(info)) return "plaintext";
  const lang = fenceInfoName(info).toLowerCase().replace(/[^a-z0-9_+#-]/g, "");
  return lang || "plaintext";
}

function fenceToolbarLabel(info: string): string {
  if (isPromptFence(info)) return "提示词";
  return normalizeLang(info);
}

function highlightJson(code: string): string {
  const parts: string[] = [];
  const re = /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(code))) {
    parts.push(escapeHtml(code.slice(last, match.index)));
    if (match[1]) {
      const cls = match[2] ? "md-tok-key" : "md-tok-str";
      parts.push(`<span class="${cls}">${escapeHtml(match[1])}</span>${escapeHtml(match[2] || "")}`);
    } else if (match[3]) {
      parts.push(`<span class="md-tok-num">${escapeHtml(match[3])}</span>`);
    } else {
      parts.push(`<span class="md-tok-kw">${escapeHtml(match[4])}</span>`);
    }
    last = match.index + match[0].length;
  }
  parts.push(escapeHtml(code.slice(last)));
  return parts.join("");
}

const HASH_COMMENT_LANGS = new Set([
  "bash", "ini", "perl", "py", "python", "r", "rb", "ruby", "sh", "shell", "toml", "yaml", "yml", "zsh",
]);

function highlightGeneric(code: string, lang: string): string {
  const hashComment = HASH_COMMENT_LANGS.has(lang) ? "|#[^\\n]*" : "";
  const re = new RegExp(
    `//[^\\n]*|/\\*[\\s\\S]*?\\*/${hashComment}|"(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\`(?:\\\\.|[^\`\\\\])*\`|\\b-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b|\\b(?:true|false|null|undefined|None|True|False)\\b`,
    "g",
  );
  const parts: string[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(code))) {
    parts.push(escapeHtml(code.slice(last, match.index)));
    const token = match[0];
    let cls = "md-tok-str";
    if (token.startsWith("//") || token.startsWith("/*") || token.startsWith("#")) {
      cls = "md-tok-comment";
    } else if (/^-?\d/.test(token)) {
      cls = "md-tok-num";
    } else if (/^(true|false|null|undefined|None|True|False)$/.test(token)) {
      cls = "md-tok-kw";
    }
    parts.push(`<span class="${cls}">${escapeHtml(token)}</span>`);
    last = match.index + match[0].length;
  }
  parts.push(escapeHtml(code.slice(last)));
  return parts.join("");
}

function highlightCode(code: string, lang: string): string {
  if (lang === "json") return highlightJson(code);
  if (lang === "plaintext" || lang === "text" || lang === "txt") return escapeHtml(code);
  return highlightGeneric(code, lang);
}

function renderCopyActions(): string {
  return [
    `<div class="md-code-actions">`,
    `<button type="button" class="md-code-copy" data-tooltip="复制" aria-label="复制">`,
    `<span class="md-code-copy-icon">${COPY_ICON}</span>`,
    `<span class="md-code-copy-done">${CHECK_ICON}</span>`,
    `</button>`,
    `<button type="button" class="md-code-generate" data-tooltip="复制并去生图" aria-label="复制并去生图">`,
    `<span class="md-code-generate-icon">${GENERATE_ICON}</span>`,
    `</button>`,
    `</div>`,
  ].join("");
}

function isCodeLangLabel(label: string): boolean {
  return /^[a-z0-9_+#-]+$/i.test(label) && !/^(plaintext|text|txt)$/i.test(label);
}

function renderCopyToolbar(label: string): string {
  const langClass = isCodeLangLabel(label) ? "md-code-lang" : "md-code-lang is-plain";
  return [
    `<div class="md-code-block md-copyable">`,
    `<div class="md-code-toolbar">`,
    `<span class="${langClass}">${escapeHtml(label)}</span>`,
    renderCopyActions(),
    `</div>`,
  ].join("");
}

function renderCodeBlock(code: string, lang: string): string {
  const language = normalizeLang(lang);
  const body = highlightCode(code.replace(/\n$/, ""), language);
  return [
    renderCopyToolbar(fenceToolbarLabel(lang)),
    `<pre data-md-copy-source><code class="language-${escapeHtml(language)}">${body}</code></pre>`,
    `</div>`,
  ].join("");
}

markdownRenderer.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx];
  return renderCodeBlock(token.content, token.info || "");
};

markdownRenderer.renderer.rules.code_block = (tokens, idx) => (
  renderCodeBlock(tokens[idx].content, "plaintext")
);

const STRONG_HEADING_MAX = 24;

function shouldRenderStrongAsTitle(text: string): boolean {
  const value = (text || "").trim();
  if (!value || value.includes("\n")) return false;
  return (
    value.length <= STRONG_HEADING_MAX
    || /^\d+[\.、．]/.test(value)
    || /^[一二三四五六七八九十]+[、.．]/.test(value)
    || /[：:]$/.test(value)
  );
}

type MdInlineToken = {
  type: string;
  content: string;
  children: MdInlineToken[] | null;
};

function isIgnorableInline(token: MdInlineToken): boolean {
  if (token.type === "softbreak" || token.type === "hardbreak") return true;
  return token.type === "text" && !token.content.trim();
}

function collectInlineText(tokens: MdInlineToken[]): string {
  return tokens.map((token) => {
    if (token.type === "text" || token.type === "code_inline") return token.content;
    if (token.type === "softbreak" || token.type === "hardbreak") return "\n";
    return "";
  }).join("");
}

function findStrongSpan(tokens: MdInlineToken[], openIdx: number): { closeIdx: number; inner: MdInlineToken[] } | null {
  let depth = 1;
  for (let i = openIdx + 1; i < tokens.length; i += 1) {
    if (tokens[i].type === "strong_open") depth += 1;
    if (tokens[i].type !== "strong_close") continue;
    depth -= 1;
    if (depth === 0) return { closeIdx: i, inner: tokens.slice(openIdx + 1, i) };
  }
  return null;
}

function renderSectionTitle(text: string): string {
  return `<p class="md-section-title">${escapeHtml(text)}</p>\n`;
}

function isInsideContainer(
  tokens: Array<{ type: string }>,
  idx: number,
  openType: string,
  closeType: string,
): boolean {
  let depth = 0;
  for (let i = idx - 1; i >= 0; i -= 1) {
    const type = tokens[i].type;
    if (type === closeType) depth += 1;
    if (type !== openType) continue;
    if (depth === 0) return true;
    depth -= 1;
  }
  return false;
}

markdownRenderer.core.ruler.after("inline", "strong_section_title", (state) => {
  const tokens = state.tokens;
  for (let i = 0; i < tokens.length; i += 1) {
    if (tokens[i].type !== "paragraph_open") continue;
    if (
      isInsideContainer(tokens, i, "list_item_open", "list_item_close")
      || isInsideContainer(tokens, i, "blockquote_open", "blockquote_close")
    ) {
      continue;
    }
    const inline = tokens[i + 1];
    const close = tokens[i + 2];
    if (!inline || inline.type !== "inline" || !close || close.type !== "paragraph_close") continue;

    const children = (inline.children || []) as MdInlineToken[];
    let start = 0;
    let end = children.length;
    while (start < end && isIgnorableInline(children[start])) start += 1;
    while (end > start && isIgnorableInline(children[end - 1])) end -= 1;

    if (children[start]?.type !== "strong_open") continue;
    const span = findStrongSpan(children, start);
    if (!span || span.closeIdx !== end - 1) continue;
    const text = collectInlineText(span.inner).trim();
    if (!shouldRenderStrongAsTitle(text)) continue;

    const htmlToken = new state.Token("html_block", "", 0);
    htmlToken.content = renderSectionTitle(text);
    tokens.splice(i, 3, htmlToken);
  }
});

/** Prefer the pasteable prompt section from assistant replies; fallback to full text. */
export function stripGenerateImageFence(text: string): string {
  return (text || "")
    .replace(/```(?:generate-image|generate_image)\s*\n[\s\S]*?(```|$)/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function extractGeneratePrompt(content: string): string {
  const text = stripGenerateImageFence(content || "");
  if (!text) return "";

  const fenced = text.match(/```(?:[\w-]*)\n([\s\S]*?)```/);
  if (fenced?.[1]?.trim()) {
    return fenced[1].trim();
  }

  const section = text.match(
    /##[^\n]*(?:可直接粘贴|最终提示词|提示词)[^\n]*\n([\s\S]*?)(?=\n##\s|\n---\s*\n|$)/i,
  );
  if (section?.[1]) {
    let body = section[1].trim();
    body = body.replace(/^\*\*[^*\n]+\*\*\s*\n?/, "").trim();
    const chunk = body.split(/\n---\n|\n{2,}(?=\*\*|##)/)[0]?.trim() || body;
    const cleaned = stripMarkdownDecorations(chunk);
    if (cleaned) return cleaned;
  }

  return stripMarkdownDecorations(text);
}

function normalizeFenceLayout(markdown: string): string {
  return (markdown || "")
    .replace(/([^\n])```([^\n`]*)\n/g, "$1\n```$2\n")
    .replace(/\n```([^\n`]*)\n/g, "\n\n```$1\n")
    .replace(/\n```\s*([.,;:!?，。；：！？、)\]}])/g, "\n```\n$1")
    .replace(/\n{3,}```/g, "\n\n```");
}

export function renderSimpleMarkdown(markdown: string): string {
  const source = normalizeFenceLayout((markdown || "").replace(/\r\n/g, "\n"));
  if (!source.trim()) return "";
  return markdownRenderer.render(source);
}
