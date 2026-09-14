<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  type ComponentPublicInstance,
} from "vue";
import {
  AppstoreOutlined,
  PictureOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons-vue";
import { useRouter } from "vue-router";
import { getGenerationModels } from "@/api/config";
import { resolveImageUrl } from "@/api/images";
import { getTemplateDetail, listTemplates } from "@/api/templates";
import { importAfterExtendedAntd } from "@/lib/antd";
import type { CreativeTemplate, GenerationModelOption } from "@/types";

const router = useRouter();
const openCreditsContact = inject<(() => void) | undefined>("openCreditsContact", undefined);
const TemplateDetailDialog = defineAsyncComponent(() => importAfterExtendedAntd(() => import("@/components/templates/TemplateDetailDialog.vue")));
const showcaseItems = ref<CreativeTemplate[]>([]);
const loadingShowcase = ref(true);
const generationModels = ref<GenerationModelOption[]>([]);
const detailOpen = ref(false);
const detailLoading = ref(false);
const detail = ref<CreativeTemplate | null>(null);
const canvasModelSourceImage = "/homepage/canvas-model-source.webp";
const canvasJeansImage = "/homepage/canvas-jeans.webp";
const canvasJacketImage = "/homepage/canvas-jacket.webp";
const canvasResultImage = "/homepage/canvas-result.webp";
const canvasResultVideo = "/homepage/canvas-result-video.mp4";
const canvasFlowViewBox = { width: 1000, height: 760 };

type CanvasNodeKey = "note" | "source" | "result" | "video" | "jeans" | "jacket";
type CanvasPoint = { x: number; y: number };
type CanvasRect = { left: number; top: number; width: number; height: number };

const canvasShellRef = ref<HTMLElement | null>(null);
const canvasSvgRef = ref<SVGSVGElement | null>(null);
const canvasVideoCardRef = ref<HTMLElement | null>(null);
const shouldLoadCanvasVideo = ref(false);
const canvasNodeRefs = {
  note: ref<HTMLElement | null>(null),
  source: ref<HTMLElement | null>(null),
  result: ref<HTMLElement | null>(null),
  video: ref<HTMLElement | null>(null),
  jeans: ref<HTMLElement | null>(null),
  jacket: ref<HTMLElement | null>(null),
} satisfies Record<CanvasNodeKey, ReturnType<typeof ref<HTMLElement | null>>>;
const canvasFlowPaths = ref({
  note: "",
  source: "",
  video: "",
  jeans: "",
  jacket: "",
});
let canvasResizeObserver: ResizeObserver | null = null;
let heroMediaObserver: IntersectionObserver | null = null;
let canvasFlowFrame = 0;
let nonCriticalLoadTimer: number | null = null;
let nonCriticalIdleCallbackId: number | null = null;

const capabilityCards = [
  {
    title: "AI 生图",
    eyebrow: "Image Generation",
    desc: "快速生成海报、商品图、人物视觉和概念图，让创意方向更快落地成可用画面。",
    route: "/generate",
    action: "开始生图",
    icon: PictureOutlined,
    points: ["模版快速起步", "支持自定义提示词", "适合商业视觉产出"],
  },
  {
    title: "AI 生视频",
    eyebrow: "Video Generation",
    desc: "把静态内容延展成动态片段，适合镜头预演、短视频内容和素材表达升级。",
    route: "/video-generate",
    action: "开始生视频",
    icon: VideoCameraOutlined,
    points: ["图像延展视频", "更适合内容传播", "减少后期试错成本"],
  },
  {
    title: "无限画布",
    eyebrow: "Infinite Canvas",
    desc: "把指令、素材、生成结果和修改方向放在同一块画布中，方便长期整理、比较和迭代。",
    route: "/canvas",
    action: "进入无限画布",
    icon: AppstoreOutlined,
    points: ["集中管理灵感与结果", "支持多轮编辑上下文", "适合长期项目推进"],
  },
] as const;

const imageUseCases = [
  {
    title: "商品图",
    desc: "换背景、换衣服、生成主图",
  },
  {
    title: "电商模特",
    desc: "真人换装、姿势保持、搭配展示",
  },
  {
    title: "海报设计",
    desc: "节日海报、活动视觉、宣传图",
  },
  {
    title: "头像写真",
    desc: "证件照、职业照、风格写真",
  },
  {
    title: "室内家装",
    desc: "软装搭配、空间换风格",
  },
  {
    title: "文案配图",
    desc: "文章封面、小红书配图",
  },
  {
    title: "修图增强",
    desc: "去瑕疵、补画面、高清放大",
  },
  {
    title: "创意合成",
    desc: "多图合成、产品场景化",
  },
] as const;

const footerNavLinks = [
  { label: "创意模版", route: "/templates" },
  { label: "AI 生图", route: "/generate" },
  { label: "AI 视频", route: "/video-generate" },
  { label: "无限画布", route: "/canvas" },
] as const;

const footerLegalLinks = [
  { label: "关于", route: "/" },
  { label: "用户协议", route: "/user-agreement" },
  { label: "隐私政策", route: "/privacy-policy" },
] as const;

const marqueeItems = computed(() => [...showcaseItems.value, ...showcaseItems.value]);
const idleWindow = window as Window & typeof globalThis & {
  requestIdleCallback?: (callback: IdleRequestCallback, options?: IdleRequestOptions) => number;
  cancelIdleCallback?: (handle: number) => void;
};

async function loadShowcase() {
  loadingShowcase.value = true;
  try {
    const res = await listTemplates(1, 12);
    showcaseItems.value = res.items.filter((item) => !!item.result_image).slice(0, 10);
  } catch {
    showcaseItems.value = [];
  } finally {
    loadingShowcase.value = false;
  }
}

async function loadModels() {
  try {
    generationModels.value = await getGenerationModels();
  } catch {
    generationModels.value = [];
  }
}

function scheduleNonCriticalHomeLoads() {
  requestAnimationFrame(() => {
    if (typeof idleWindow.requestIdleCallback === "function") {
      nonCriticalIdleCallbackId = idleWindow.requestIdleCallback(() => {
        nonCriticalIdleCallbackId = null;
        void loadModels();
        void loadShowcase();
      }, { timeout: 1500 });
      return;
    }

    nonCriticalLoadTimer = window.setTimeout(() => {
      nonCriticalLoadTimer = null;
      void loadModels();
      void loadShowcase();
    }, 180);
  });
}

function setCanvasVideoNodeRef(element: Element | ComponentPublicInstance | null) {
  const node = element instanceof HTMLElement ? element : null;
  canvasNodeRefs.video.value = node;
  canvasVideoCardRef.value = node;
}

function setupHeroMediaObserver() {
  const videoCard = canvasVideoCardRef.value;
  if (!videoCard) {
    shouldLoadCanvasVideo.value = true;
    return;
  }

  if (typeof IntersectionObserver !== "function") {
    shouldLoadCanvasVideo.value = true;
    return;
  }

  heroMediaObserver = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return;
    shouldLoadCanvasVideo.value = true;
    heroMediaObserver?.disconnect();
    heroMediaObserver = null;
  }, {
    rootMargin: "160px 0px",
    threshold: 0.01,
  });
  heroMediaObserver.observe(videoCard);
}

async function openDetail(id: number) {
  detailOpen.value = true;
  detailLoading.value = true;
  try {
    detail.value = await getTemplateDetail(id);
  } catch {
    detailOpen.value = false;
  } finally {
    detailLoading.value = false;
  }
}

function toCanvasRect(element: HTMLElement, svgRect: DOMRect): CanvasRect {
  const rect = element.getBoundingClientRect();
  const scaleX = canvasFlowViewBox.width / svgRect.width;
  const scaleY = canvasFlowViewBox.height / svgRect.height;

  return {
    left: (rect.left - svgRect.left) * scaleX,
    top: (rect.top - svgRect.top) * scaleY,
    width: rect.width * scaleX,
    height: rect.height * scaleY,
  };
}

function getEdgePoint(from: CanvasRect, to: CanvasRect): CanvasPoint {
  const fromCenter = {
    x: from.left + from.width / 2,
    y: from.top + from.height / 2,
  };
  const toCenter = {
    x: to.left + to.width / 2,
    y: to.top + to.height / 2,
  };
  const dx = toCenter.x - fromCenter.x;
  const dy = toCenter.y - fromCenter.y;
  const halfWidth = from.width / 2;
  const halfHeight = from.height / 2;

  if (Math.abs(dx) / halfWidth > Math.abs(dy) / halfHeight) {
    return {
      x: fromCenter.x + (dx > 0 ? halfWidth : -halfWidth),
      y: fromCenter.y + (dy / Math.max(Math.abs(dx), 1)) * halfWidth,
    };
  }

  return {
    x: fromCenter.x + (dx / Math.max(Math.abs(dy), 1)) * halfHeight,
    y: fromCenter.y + (dy > 0 ? halfHeight : -halfHeight),
  };
}

function buildLinePath(from: CanvasRect, to: CanvasRect) {
  const start = getEdgePoint(from, to);
  const end = getEdgePoint(to, from);
  return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} L ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
}

function buildCurvePath(from: CanvasRect, to: CanvasRect) {
  const start = getEdgePoint(from, to);
  const end = getEdgePoint(to, from);
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const controlOffset = Math.abs(dx) > Math.abs(dy) ? dx * 0.46 : dy * 0.46;
  const controlA = Math.abs(dx) > Math.abs(dy)
    ? { x: start.x + controlOffset, y: start.y }
    : { x: start.x, y: start.y + controlOffset };
  const controlB = Math.abs(dx) > Math.abs(dy)
    ? { x: end.x - controlOffset, y: end.y }
    : { x: end.x, y: end.y - controlOffset };

  return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${controlA.x.toFixed(1)} ${controlA.y.toFixed(1)}, ${controlB.x.toFixed(1)} ${controlB.y.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
}

function buildVerticalThenDiagonalPath(from: CanvasRect, to: CanvasRect) {
  const start = getEdgePoint(from, to);
  const end = getEdgePoint(to, from);
  const bendY = start.y + (end.y - start.y) * 0.72;

  return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} L ${start.x.toFixed(1)} ${bendY.toFixed(1)} L ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
}

function updateCanvasFlowPaths() {
  const svg = canvasSvgRef.value;
  const entries = Object.entries(canvasNodeRefs) as Array<[CanvasNodeKey, ReturnType<typeof ref<HTMLElement | null>>]>;

  if (!svg || entries.some(([, nodeRef]) => !nodeRef.value)) return;

  const svgRect = svg.getBoundingClientRect();
  if (!svgRect.width || !svgRect.height) return;

  const rects = Object.fromEntries(
    entries.map(([key, nodeRef]) => [key, toCanvasRect(nodeRef.value as HTMLElement, svgRect)])
  ) as Record<CanvasNodeKey, CanvasRect>;

  canvasFlowPaths.value = {
    note: buildLinePath(rects.note, rects.result),
    source: buildCurvePath(rects.source, rects.result),
    video: buildLinePath(rects.result, rects.video),
    jeans: buildVerticalThenDiagonalPath(rects.jeans, rects.result),
    jacket: buildCurvePath(rects.jacket, rects.result),
  };
}

function scheduleCanvasFlowUpdate() {
  if (canvasFlowFrame) cancelAnimationFrame(canvasFlowFrame);
  canvasFlowFrame = requestAnimationFrame(() => {
    canvasFlowFrame = 0;
    updateCanvasFlowPaths();
  });
}

function useTemplate() {
  if (!detail.value) return;
  localStorage.setItem(
    "generateDraftFromTemplate",
    JSON.stringify({
      model: detail.value.model,
      prompt: detail.value.prompt,
      reference_images: detail.value.reference_images,
      num_images: 1,
      size: detail.value.size,
      resolution: detail.value.resolution,
      custom_size: detail.value.custom_size,
    })
  );
  detailOpen.value = false;
  router.push("/generate");
}

function openFooterContact() {
  if (openCreditsContact) {
    openCreditsContact();
    return;
  }
  window.location.href = "mailto:support@80ai.net";
}

onMounted(() => {
  scheduleNonCriticalHomeLoads();
  nextTick(() => {
    updateCanvasFlowPaths();
    setupHeroMediaObserver();
    canvasResizeObserver = new ResizeObserver(scheduleCanvasFlowUpdate);
    const observedNodes = [
      canvasShellRef.value,
      ...Object.values(canvasNodeRefs).map((nodeRef) => nodeRef.value),
    ].filter(Boolean) as HTMLElement[];

    observedNodes.forEach((node) => canvasResizeObserver?.observe(node));
    window.addEventListener("resize", scheduleCanvasFlowUpdate);
  });
});

onBeforeUnmount(() => {
  canvasResizeObserver?.disconnect();
  heroMediaObserver?.disconnect();
  window.removeEventListener("resize", scheduleCanvasFlowUpdate);
  if (canvasFlowFrame) cancelAnimationFrame(canvasFlowFrame);
  if (nonCriticalLoadTimer !== null) window.clearTimeout(nonCriticalLoadTimer);
  if (nonCriticalIdleCallbackId !== null && typeof idleWindow.cancelIdleCallback === "function") {
    idleWindow.cancelIdleCallback(nonCriticalIdleCallbackId);
  }
});
</script>

<template>
  <div class="home-page warm-page motion-page-enter">
    <section class="section-block showcase-shell motion-fade-up" style="--motion-delay: 0.04s">
      <div v-if="loadingShowcase" class="showcase-skeleton-row">
        <div v-for="index in 6" :key="index" class="showcase-skeleton-card">
          <div class="showcase-skeleton-media" />
          <div class="showcase-skeleton-line showcase-skeleton-line-long" />
          <div class="showcase-skeleton-line showcase-skeleton-line-short" />
        </div>
      </div>
      <div v-else-if="showcaseItems.length" class="showcase-marquee">
        <div class="showcase-track showcase-track-single">
          <div
            v-for="(item, index) in marqueeItems"
            :key="`${item.id}-${index}`"
            class="showcase-card"
            @click="openDetail(item.id)"
          >
            <img
              :src="resolveImageUrl(item.result_image_thumb || item.result_image)"
              :alt="item.prompt || '效果图'"
              loading="lazy"
            />
            <div class="showcase-card-mask">
              <div class="showcase-card-prompt">{{ item.prompt || "高质量稳定生图结果" }}</div>
            </div>
            <div class="showcase-overlay">
              <div class="showcase-overlay-text">查看详情</div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="showcase-empty">
        <div class="showcase-empty-title">高质量效果图展示位</div>
        <div class="showcase-empty-desc">模版结果图加载后，这里会自动横向滚动展示真实效果。</div>
      </div>
    </section>

    <section class="canvas-showcase motion-fade-up" style="--motion-delay: 0.08s">
      <div class="canvas-showcase-side">
        <div class="hero-summary">
          <article v-for="item in capabilityCards" :key="item.title" class="summary-card warm-card motion-card-lift">
            <div class="summary-card-top">
              <div class="summary-icon"><component :is="item.icon" /></div>
              <div class="summary-eyebrow">{{ item.eyebrow }}</div>
            </div>
            <div class="summary-title">{{ item.title }}</div>
            <div class="summary-desc">{{ item.desc }}</div>
            <div class="summary-points">
              <span v-for="point in item.points" :key="point" class="summary-point">{{ point }}</span>
            </div>
            <a-button type="primary" class="warm-primary-btn summary-btn" size="large" @click="router.push(item.route)">
              {{ item.action }}
            </a-button>
          </article>
        </div>
      </div>

      <div ref="canvasShellRef" class="canvas-demo-shell">
        <div class="canvas-grid-bg" />
        <svg ref="canvasSvgRef" class="canvas-flow-svg" viewBox="0 0 1000 760" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <marker
              id="canvas-flow-arrow"
              viewBox="0 0 10 10"
              refX="8.5"
              refY="5"
              markerWidth="10"
              markerHeight="10"
              markerUnits="userSpaceOnUse"
              orient="auto"
            >
              <path class="flow-arrow-head" d="M 0 0 L 10 5 L 0 10 z" />
            </marker>
          </defs>
          <path class="flow-path flow-path-note" :d="canvasFlowPaths.note" />
          <path class="flow-path flow-path-source" :d="canvasFlowPaths.source" />
          <path class="flow-path flow-path-video" :d="canvasFlowPaths.video" />
          <path class="flow-path flow-path-jeans" :d="canvasFlowPaths.jeans" />
          <path class="flow-path flow-path-jacket" :d="canvasFlowPaths.jacket" />
        </svg>

        <article :ref="canvasNodeRefs.note" class="canvas-note-card canvas-card canvas-card-note">
          <p>将模特的上衣和裤子改为提供的白色上衣和牛仔裤，模特的姿势保持不变</p>
          <span class="canvas-mini-tag">改图指令</span>
        </article>

        <article :ref="canvasNodeRefs.source" class="canvas-media-card canvas-card canvas-card-source">
          <span class="canvas-card-label">上传</span>
          <div class="fashion-frame fashion-frame-source">
            <img
              class="canvas-photo canvas-photo-model"
              :src="canvasModelSourceImage"
              alt="上传的模特参考图"
              width="574"
              height="1024"
              decoding="async"
            />
          </div>
        </article>

        <article :ref="canvasNodeRefs.result" class="canvas-media-card canvas-card canvas-card-result">
          <div class="canvas-result-badge">改图 1</div>
          <div class="fashion-frame fashion-frame-result">
            <img
              class="canvas-photo canvas-photo-model"
              :src="canvasResultImage"
              alt="改图结果图"
              width="574"
              height="1024"
              decoding="async"
              fetchpriority="high"
            />
          </div>
        </article>

        <article :ref="setCanvasVideoNodeRef" class="canvas-video-card canvas-card">
          <div class="canvas-result-badge canvas-video-badge">生视频</div>
          <span class="canvas-card-label">视频结果</span>
          <div class="fashion-frame fashion-frame-video">
            <video
              class="canvas-video-player"
              :src="shouldLoadCanvasVideo ? canvasResultVideo : undefined"
              autoplay
              muted
              loop
              playsinline
              preload="none"
              aria-label="图片生成视频结果预览"
            />
          </div>
        </article>

        <article :ref="canvasNodeRefs.jeans" class="canvas-garment-card canvas-card canvas-card-jeans">
          <span class="canvas-card-label">上传</span>
          <div class="garment-shape garment-jeans">
            <img
              class="canvas-photo canvas-photo-garment"
              :src="canvasJeansImage"
              alt="上传的裤子参考图"
              width="1024"
              height="1024"
              loading="lazy"
              decoding="async"
            />
          </div>
        </article>

        <article :ref="canvasNodeRefs.jacket" class="canvas-garment-card canvas-card canvas-card-jacket">
          <span class="canvas-card-label">上传</span>
          <div class="garment-shape garment-jacket">
            <img
              class="canvas-photo canvas-photo-garment"
              :src="canvasJacketImage"
              alt="上传的衣服参考图"
              width="1024"
              height="1024"
              loading="lazy"
              decoding="async"
            />
          </div>
        </article>
      </div>
    </section>

    <section class="use-cases-section motion-fade-up" style="--motion-delay: 0.12s">
      <div class="use-cases-shell">
        <div class="use-cases-heading">
          <div class="feature-story-eyebrow">AI 生图常用场景</div>
          <h2>常见生成需求，可以直接在这里快速起步。</h2>
          <p>覆盖商品、电商、海报、写真到修图增强等高频场景，让用户一眼知道 AI 生图能解决哪些实际需求。</p>
        </div>

        <div class="use-cases-grid">
          <article v-for="item in imageUseCases" :key="item.title" class="use-case-card">
            <div class="use-case-title">{{ item.title }}</div>
            <div class="use-case-desc">{{ item.desc }}</div>
          </article>
        </div>
      </div>
    </section>

    <section class="cta-band motion-fade-up" style="--motion-delay: 0.16s">
      <div class="cta-band-copy">
        <div class="feature-story-eyebrow">从展示到创作</div>
        <h2>看完效果图，下一步就进入生成和编辑。</h2>
        <p>首页负责把能力说明白，工作台负责把结果做出来。</p>
      </div>
      <div class="cta-band-actions">
        <a-button size="large" class="hero-secondary-btn" @click="router.push('/history')">查看历史记录</a-button>
        <a-button type="primary" size="large" class="warm-primary-btn" @click="router.push('/generate')">立即去创作</a-button>
      </div>
    </section>

    <footer class="home-footer motion-fade-up" style="--motion-delay: 0.2s">
      <div class="home-footer-watermark" aria-hidden="true">80AI</div>
      <div class="home-footer-main">
        <div class="home-footer-brand">
          <button type="button" class="home-footer-logo" @click="router.push('/')">
            <img src="/香蕉.svg" alt="80AI" />
            <span>80AI.net</span>
          </button>
          <p>聚合全球领先 AI 生图模型，一个入口接入数百种创作能力。</p>
        </div>

        <div class="home-footer-links">
          <div class="home-footer-column">
            <div class="home-footer-column-title">导航</div>
            <button
              v-for="item in footerNavLinks"
              :key="item.route"
              type="button"
              class="home-footer-link"
              @click="router.push(item.route)"
            >
              {{ item.label }}
            </button>
          </div>
          <div class="home-footer-column">
            <div class="home-footer-column-title">联系</div>
            <button type="button" class="home-footer-link" @click="openFooterContact">联系我们</button>
            <a class="home-footer-link" href="mailto:support@80ai.net">邮箱</a>
          </div>
        </div>
      </div>

      <div class="home-footer-bottom">
        <span>@ 2026 80AI. 版权所有</span>
        <div class="home-footer-legal">
          <button
            v-for="item in footerLegalLinks"
            :key="item.label"
            type="button"
            class="home-footer-link home-footer-legal-link"
            @click="router.push(item.route)"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
    </footer>

    <TemplateDetailDialog
      v-if="detailOpen"
      v-model:open="detailOpen"
      :loading="detailLoading"
      :detail="detail"
      :generation-models="generationModels"
      @use-template="useTemplate"
    />
  </div>
</template>

<style scoped lang="scss">
.home-page {
  display: flex;
  flex-direction: column;
  gap: 22px;
  min-height: calc(100vh - 130px);
}

.home-footer {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  margin-top: 18px;
  padding: 34px 42px 24px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 28px 28px 0 0;
  background:
    radial-gradient(circle at 14% 18%, color-mix(in srgb, var(--theme-accent) 10%, transparent), transparent 30%),
    radial-gradient(circle at 86% 16%, rgba(var(--theme-surface-strong-rgb), 0.42), transparent 26%),
    var(--theme-page-gradient);
  color: var(--theme-text);
  box-shadow: 0 -18px 55px var(--theme-shadow-soft);
}

.home-footer::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -2;
  opacity: 0.42;
  background-image: radial-gradient(rgba(130, 108, 83, 0.16) 1px, transparent 1px);
  background-size: 14px 14px;
  mask-image: linear-gradient(180deg, #000 0%, rgba(0, 0, 0, 0.75) 48%, transparent 100%);
}

.home-footer::after {
  content: "";
  position: absolute;
  left: 42px;
  right: 42px;
  bottom: 74px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--theme-panel-border), transparent);
}

.home-footer-watermark {
  position: absolute;
  left: 50%;
  bottom: -16px;
  z-index: -1;
  transform: translateX(-50%);
  color: color-mix(in srgb, var(--theme-accent) 18%, transparent);
  font-size: clamp(86px, 18vw, 230px);
  font-weight: 900;
  letter-spacing: -0.08em;
  line-height: 0.78;
  white-space: nowrap;
  pointer-events: none;
}

.home-footer-main {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(320px, 0.72fr);
  gap: 48px;
  align-items: start;
  min-height: 132px;
}

.home-footer-brand {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 520px;
}

.home-footer-logo {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--theme-title);
  font-size: 18px;
  font-weight: 800;
  cursor: pointer;
}

.home-footer-logo img {
  width: 44px;
  height: 44px;
  box-sizing: border-box;
  padding: 9px;
  border-radius: 16px;
  background: var(--theme-accent);
  object-fit: contain;
  box-shadow: 0 12px 22px var(--theme-brand-shadow);
}

.home-footer-brand p {
  margin: 0;
  color: var(--theme-text-secondary);
  font-size: 14px;
  line-height: 1.8;
}

.home-footer-links {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: 54px;
}

.home-footer-column {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.home-footer-column-title {
  margin-bottom: 2px;
  color: var(--theme-title);
  font-size: 13px;
  font-weight: 800;
}

.home-footer-link {
  display: inline-flex;
  align-items: center;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--theme-text-secondary);
  font-size: 13px;
  line-height: 1.5;
  text-decoration: none;
  cursor: pointer;
  transition:
    color var(--motion-duration-hover) var(--motion-ease-soft),
    transform var(--motion-duration-hover) var(--motion-ease-enter);
}

.home-footer-link:hover {
  color: var(--theme-accent-text-hover);
  transform: translateX(2px);
}

.home-footer-bottom {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 34px;
  padding-top: 24px;
  color: var(--theme-muted-text);
  font-size: 12px;
}

.home-footer-legal {
  display: inline-flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.home-footer-legal-link {
  color: var(--theme-muted-text);
}

.section-block {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.showcase-shell {
  padding: 8px 0 12px;
  overflow: hidden;
}

.showcase-skeleton-row {
  display: flex;
  gap: 16px;
  overflow: hidden;
}

.showcase-skeleton-card {
  width: 184px;
  flex: 0 0 auto;
  padding: 10px;
  border-radius: 18px;
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-panel-border);
}

.showcase-skeleton-media,
.showcase-skeleton-line {
  position: relative;
  overflow: hidden;
  background: var(--theme-panel-bg-strong);

  &::after {
    content: "";
    position: absolute;
    inset: 0;
    transform: translateX(-100%);
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.65), transparent);
    animation: showcase-skeleton-shimmer 1.4s ease-in-out infinite;
  }
}

.showcase-skeleton-media {
  height: 180px;
  border-radius: 14px;
  margin-bottom: 12px;
}

.showcase-skeleton-line {
  height: 10px;
  border-radius: 999px;
}

.showcase-skeleton-line-long {
  width: 88%;
  margin-bottom: 8px;
}

.showcase-skeleton-line-short {
  width: 56%;
}

.showcase-marquee {
  position: relative;
  overflow: hidden;
  padding-top: 4px;

  &::before,
  &::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    width: 72px;
    z-index: 2;
    pointer-events: none;
  }

  &::before {
    left: 0;
    background: linear-gradient(90deg, var(--theme-page-base) 0%, rgba(var(--theme-page-base-rgb), 0) 100%);
  }

  &::after {
    right: 0;
    background: linear-gradient(270deg, var(--theme-page-base) 0%, rgba(var(--theme-page-base-rgb), 0) 100%);
  }
}

.showcase-track {
  display: flex;
  gap: 16px;
  width: max-content;
}

.showcase-track-single {
  animation: showcase-scroll-left 38s linear infinite;
}

.showcase-marquee:hover .showcase-track {
  animation-play-state: paused;
}

.showcase-card {
  position: relative;
  width: 184px;
  height: 236px;
  flex: 0 0 auto;
  border-radius: 18px;
  overflow: hidden;
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 16px 28px var(--theme-shadow-soft);
  cursor: pointer;
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    box-shadow var(--motion-duration-hover) var(--motion-ease-soft),
    border-color var(--motion-duration-hover) var(--motion-ease-soft);

  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: cover;
    transition: transform var(--motion-duration-emphasis) var(--motion-ease-enter);
  }

  &:hover {
    transform: translateY(-6px);
    border-color: var(--theme-border-accent);
    box-shadow: 0 22px 40px var(--theme-shadow-medium);
  }

  &:hover img {
    transform: scale(1.045);
  }
}

.showcase-card-mask {
  position: absolute;
  inset: auto 0 0 0;
  padding: 14px 12px 12px;
  background: linear-gradient(180deg, rgba(53, 37, 18, 0) 0%, rgba(53, 37, 18, 0.78) 100%);
}

.showcase-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, rgba(34, 25, 14, 0.08), rgba(34, 25, 14, 0.56));
  opacity: 0;
  transition: opacity var(--motion-duration-base) var(--motion-ease-soft);

  .showcase-card:hover & {
    opacity: 1;
  }
}

.showcase-overlay-text {
  padding: 10px 18px;
  border-radius: 999px;
  background: var(--theme-surface-strong);
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 700;
  transition: transform var(--motion-duration-swift) var(--motion-ease-soft);

  .showcase-card:hover & {
    transform: translateY(-2px);
  }
}

.showcase-card-prompt {
  color: #fff8ef;
  font-size: 12px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.showcase-empty {
  margin: 8px 26px 0;
  padding: 34px 20px;
  border-radius: 24px;
  border: 1px dashed var(--theme-empty-border);
  background: var(--theme-empty-bg);
  text-align: center;
}

.showcase-empty-title {
  color: var(--theme-title);
  font-size: 18px;
  font-weight: 800;
}

.showcase-empty-desc {
  margin-top: 8px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.cta-band-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-secondary-btn {
  height: 44px;
  padding-inline: 20px;
  border-radius: 14px;
  border-color: var(--theme-control-border-strong);
  color: var(--theme-accent-text);
  background: var(--theme-control-bg);
}

.hero-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.canvas-showcase-side {
  display: flex;
  align-items: stretch;
}

.summary-card,
.cta-band,
.canvas-demo-shell {
  border-radius: 30px;
  border: 1px solid var(--theme-panel-border);
  box-shadow: 0 18px 36px var(--theme-shadow-soft);
}

.summary-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100%;
  padding: 24px;
  background: linear-gradient(180deg, var(--theme-surface-strong), var(--theme-panel-bg-soft));
}

.summary-card-top {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  font-size: 22px;
  box-shadow: 0 12px 20px var(--theme-shadow-medium);
}

.summary-eyebrow,
.feature-story-eyebrow,
.canvas-card-label {
  color: var(--theme-subtitle);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.summary-title,
.cta-band h2 {
  margin: 0;
  color: var(--theme-title);
  font-weight: 800;
}

.summary-title {
  font-size: 20px;
}

.summary-desc,
.cta-band p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.85;
}

.summary-points {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.summary-point {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: var(--theme-pill-bg);
  color: var(--theme-pill-text);
  font-size: 13px;
  font-weight: 700;
}

.summary-btn {
  align-self: flex-start;
  margin-top: auto;
}

.use-cases-section {
  position: relative;
}

.use-cases-shell {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 30px;
  border-radius: 30px;
  border: 1px solid var(--theme-panel-border);
  background:
    radial-gradient(circle at top right, var(--theme-page-glow), transparent 28%),
    linear-gradient(180deg, var(--theme-surface-strong), var(--theme-panel-bg-soft));
  box-shadow: 0 18px 36px var(--theme-shadow-soft);
}

.use-cases-heading {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 820px;

  h2 {
    margin: 0;
    color: var(--theme-title);
    font-size: clamp(22px, 2.8vw, 30px);
    line-height: 1.22;
    font-weight: 800;
  }

  p {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.85;
  }
}

.use-cases-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.use-case-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 126px;
  padding: 20px 18px;
  border-radius: 22px;
  border: 1px solid var(--theme-panel-border);
  background: var(--theme-panel-bg-soft);
  transition:
    transform var(--motion-duration-hover) var(--motion-ease-enter),
    box-shadow var(--motion-duration-hover) var(--motion-ease-soft),
    border-color var(--motion-duration-hover) var(--motion-ease-soft);

  &:hover {
    transform: translateY(-4px);
    border-color: var(--theme-border-accent);
    box-shadow: 0 16px 28px var(--theme-shadow-medium);
  }
}

.use-case-title {
  color: var(--theme-accent-text);
  font-size: 16px;
  font-weight: 800;
}

.use-case-desc {
  color: var(--text-secondary);
  line-height: 1.8;
}

.canvas-showcase {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(560px, 1.22fr);
  gap: 24px;
  align-items: start;
}

.canvas-demo-shell {
  position: relative;
  width: 100%;
  max-width: 880px;
  justify-self: end;
  min-height: 720px;
  overflow: hidden;
  background:
    radial-gradient(circle at center, var(--theme-page-glow), transparent 34%),
    linear-gradient(180deg, var(--theme-surface-strong), var(--theme-panel-bg-soft));
}

.canvas-grid-bg {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(color-mix(in srgb, var(--theme-border-accent) 28%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--theme-border-accent) 28%, transparent) 1px, transparent 1px);
  background-size: 34px 34px;
}

.canvas-flow-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 3;
  pointer-events: none;
}

.flow-path {
  fill: none;
  stroke: color-mix(in srgb, var(--theme-accent) 82%, transparent);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-dasharray: 10 10;
  animation: canvas-flow-dash 10s linear infinite;
  marker-end: url(#canvas-flow-arrow);
}

.flow-arrow-head {
  fill: color-mix(in srgb, var(--theme-accent) 90%, transparent);
}

.canvas-card {
  position: absolute;
  z-index: 2;
  border-radius: 28px;
  border: 1px solid var(--theme-panel-border);
  background: color-mix(in srgb, var(--theme-surface-strong) 82%, transparent);
  box-shadow: 0 20px 38px var(--theme-shadow-medium);
  backdrop-filter: blur(12px);
}

.canvas-card-note {
  top: 26px;
  left: 26px;
  width: 236px;
  padding: 22px;

  p {
    margin: 0 0 18px;
    color: var(--theme-title);
    line-height: 1.85;
    font-weight: 600;
  }
}

.canvas-mini-tag,
.canvas-result-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--theme-pill-bg);
  color: var(--theme-pill-text);
  font-size: 12px;
  font-weight: 700;
}

.canvas-media-card,
.canvas-garment-card {
  padding: 14px;
}

.canvas-card-source {
  left: 34px;
  top: 274px;
  width: 184px;
}

.canvas-card-result {
  left: 50%;
  top: 26px;
  width: 184px;
  transform: translateX(-50%);
  padding: 34px 14px 14px;
}

.canvas-video-card {
  right: 34px;
  top: 26px;
  width: 184px;
  padding: 34px 14px 14px;
}

.canvas-result-badge {
  position: absolute;
  left: -38px;
  top: 40px;
}

.canvas-video-badge {
  left: auto;
  right: -32px;
  top: 26px;
}

.canvas-card-jeans {
  top: 422px;
  left: 396px;
  width: 160px;
}

.canvas-card-jacket {
  right: 34px;
  top: 406px;
  width: 160px;
}

.fashion-frame,
.garment-shape {
  position: relative;
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(250, 250, 250, 0.98), rgba(242, 242, 242, 0.92));
  overflow: hidden;
}

.canvas-media-card,
.canvas-video-card {
  padding: 34px 14px 14px;
}

.canvas-media-card .canvas-card-label,
.canvas-video-card .canvas-card-label {
  position: absolute;
  top: 12px;
  left: 14px;
  z-index: 3;
}

.fashion-frame-result,
.canvas-card-source .fashion-frame,
.fashion-frame-video {
  aspect-ratio: 574 / 1024;
  height: auto;
}

.fashion-frame-video {
  background: #17120b;
}

.fashion-frame-video::before {
  display: none;
}

.garment-shape {
  aspect-ratio: 1 / 1;
  height: auto;
}

.canvas-photo {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: block;
}

.canvas-photo-model {
  object-fit: contain;
  object-position: center;
}

.canvas-photo-garment {
  object-fit: contain;
  object-position: center;
  padding: 0;
}

.canvas-video-player {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.fashion-frame::before,
.garment-shape::before {
  content: "";
  position: absolute;
  inset: auto 0 0 0;
  height: 26%;
  background: linear-gradient(180deg, rgba(210, 201, 190, 0), rgba(213, 205, 196, 0.72));
}

.cta-band {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 28px 30px;
  background:
    radial-gradient(circle at left center, var(--theme-page-glow), transparent 28%),
    linear-gradient(180deg, var(--theme-surface-strong), var(--theme-panel-bg-soft));
}

.cta-band-copy {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 760px;
}

.cta-band h2 {
  font-size: 22px;
  line-height: 1.22;
}

:global(html[data-theme="dark"]),
:global(html[data-theme="midnight"]) {
  .home-page {
    .summary-card,
    .use-cases-shell,
    .use-case-card,
    .canvas-demo-shell,
    .canvas-card,
    .cta-band,
    .hero-secondary-btn,
    .showcase-skeleton-card,
    .showcase-card,
    .showcase-empty {
      background: var(--theme-panel-bg) !important;
      border-color: var(--theme-panel-border) !important;
      box-shadow: none !important;
    }

    .summary-point,
    .canvas-mini-tag,
    .canvas-result-badge {
      background: var(--theme-panel-bg-strong) !important;
      border: 1px solid var(--theme-panel-border);
      color: var(--theme-title) !important;
    }

    .summary-title,
    .use-cases-heading h2,
    .use-case-title,
    .cta-band h2,
    .showcase-empty-title {
      color: var(--theme-title) !important;
    }

    .summary-desc,
    .use-cases-heading p,
    .use-case-desc,
    .cta-band p,
    .summary-eyebrow,
    .feature-story-eyebrow,
    .canvas-card-label,
    .showcase-empty-desc,
    .canvas-card-note p {
      color: var(--text-secondary) !important;
    }

    .summary-icon {
      background: var(--theme-accent) !important;
      color: var(--theme-accent-contrast) !important;
      box-shadow: none !important;
    }

    .canvas-grid-bg {
      opacity: 0.18;
    }

    .fashion-frame,
    .garment-shape {
      background: var(--theme-panel-bg-strong) !important;
    }

    .flow-path {
      stroke: var(--theme-accent) !important;
    }

    .flow-arrow-head {
      fill: var(--theme-accent) !important;
    }

    .showcase-skeleton-media,
    .showcase-skeleton-line {
      background: var(--theme-panel-bg-strong) !important;
    }

    .showcase-marquee::before {
      background: linear-gradient(90deg, var(--theme-panel-bg) 0%, rgba(var(--theme-surface-strong-rgb), 0) 100%) !important;
    }

    .showcase-marquee::after {
      background: linear-gradient(270deg, var(--theme-panel-bg) 0%, rgba(var(--theme-surface-strong-rgb), 0) 100%) !important;
    }

    .showcase-card:hover {
      border-color: var(--theme-border-strong) !important;
      box-shadow: 0 10px 24px var(--theme-shadow-soft) !important;
    }

    .showcase-card-mask {
      background: linear-gradient(180deg, rgba(22, 24, 29, 0) 0%, var(--theme-overlay-heavy) 100%) !important;
    }

    .showcase-card-prompt {
      color: var(--theme-accent-contrast) !important;
    }

    .showcase-overlay {
      background: linear-gradient(180deg, var(--theme-overlay-soft), var(--theme-overlay-strong)) !important;
    }

    .showcase-overlay-text {
      background: rgba(var(--theme-surface-strong-rgb), 0.96) !important;
      color: var(--theme-accent-text-hover) !important;
      border: 1px solid var(--theme-panel-border);
    }
  }
}

:global(html[data-theme="midnight"]) {
  .home-page .showcase-card-prompt {
    color: var(--theme-title) !important;
  }
}

@keyframes showcase-scroll-left {
  from {
    transform: translate3d(0, 0, 0);
  }
  to {
    transform: translate3d(calc(-50% - 8px), 0, 0);
  }
}

@keyframes showcase-skeleton-shimmer {
  to {
    transform: translateX(100%);
  }
}

@keyframes canvas-flow-dash {
  to {
    stroke-dashoffset: -220;
  }
}

@keyframes canvas-result-float {
  0%,
  100% {
    transform: translateX(-50%) translateY(0);
  }
  50% {
    transform: translateX(-50%) translateY(-8px);
  }
}

@media (max-width: 1180px) {
  .canvas-showcase {
    grid-template-columns: 1fr;
  }

  .hero-summary {
    grid-template-columns: 1fr;
  }

  .use-cases-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .home-footer-main {
    grid-template-columns: 1fr;
    gap: 34px;
  }

  .home-footer-links {
    max-width: 520px;
  }
}

@media (max-width: 960px) {
  .canvas-demo-shell {
    min-height: 860px;
  }

  .canvas-card-note {
    width: 220px;
  }

  .canvas-card-source {
    left: 28px;
    top: 486px;
    width: 176px;
  }

  .canvas-card-result {
    top: 140px;
    width: 176px;
  }

  .canvas-video-card {
    right: 28px;
    top: 140px;
    width: 176px;
  }

  .canvas-card-jeans,
  .canvas-card-jacket {
    width: 156px;
  }

  .canvas-card-jeans {
    top: 490px;
    left: 252px;
  }

  .canvas-card-jacket {
    top: 490px;
    left: 424px;
  }

}

@media (max-width: 820px) {
  .cta-band {
    flex-direction: column;
    align-items: flex-start;
  }

  .home-footer {
    padding: 30px 26px 22px;
    border-radius: 24px 24px 0 0;
  }

  .home-footer-links {
    grid-template-columns: 1fr;
    gap: 28px;
  }

  .home-footer-bottom {
    flex-direction: column;
    align-items: flex-start;
  }

  .canvas-demo-shell {
    min-height: 1180px;
  }

  .canvas-flow-svg {
    z-index: 1;
  }

  .flow-path {
    stroke-width: 2;
    stroke-dasharray: 7 9;
    opacity: 0.78;
  }

  .canvas-card-note {
    top: 20px;
    left: 20px;
    right: 20px;
    width: auto;
  }

  .canvas-card-result {
    top: 180px;
    left: 50%;
    width: 180px;
  }

  .canvas-video-card {
    top: 560px;
    bottom: auto;
    width: 180px;
  }

  .canvas-card-source {
    left: 20px;
    top: 810px;
    width: 180px;
  }

  .canvas-card-jeans {
    left: 20px;
    top: 810px;
  }

  .canvas-card-jacket {
    right: 20px;
    top: 810px;
  }

  .canvas-flow-svg {
    opacity: 0.84;
  }
}

@media (max-width: 640px) {
  .summary-card,
  .use-cases-shell,
  .cta-band,
  .home-footer {
    padding: 22px;
    border-radius: 24px;
  }

  .home-footer::after {
    left: 22px;
    right: 22px;
  }

  .home-footer-legal {
    gap: 12px;
  }

  .use-cases-grid {
    grid-template-columns: 1fr;
  }

  .canvas-demo-shell {
    min-height: 1260px;
    border-radius: 24px;
  }

  .canvas-card {
    border-radius: 22px;
  }

  .canvas-card-result {
    width: 168px;
    top: 190px;
  }

  .canvas-video-card {
    top: 536px;
    width: 168px;
  }

  .canvas-card-source {
    width: 168px;
  }

  .canvas-card-jeans,
  .canvas-card-jacket {
    width: calc(50% - 28px);
  }

  .canvas-card-source {
    left: 16px;
    top: 880px;
  }

  .canvas-card-jeans {
    left: 16px;
    top: 880px;
  }

  .canvas-card-jacket {
    right: 16px;
    top: 880px;
  }

  .canvas-card-note {
    left: 16px;
    right: 16px;
    top: 16px;
  }

  .showcase-empty {
    margin-inline: 18px;
  }

  .showcase-card {
    width: 142px;
    height: 190px;
    border-radius: 16px;
  }

  .showcase-skeleton-card {
    width: 142px;
    border-radius: 16px;
  }

  .showcase-skeleton-media {
    height: 136px;
  }
}
</style>

<style lang="scss">
html[data-theme="dark"] .home-page .showcase-marquee,
html[data-theme="dark"] .home-page .showcase-skeleton-row,
html[data-theme="midnight"] .home-page .showcase-marquee,
html[data-theme="midnight"] .home-page .showcase-skeleton-row {
  background: var(--theme-page-base) !important;
}

html[data-theme="dark"] .home-page .showcase-marquee::before,
html[data-theme="midnight"] .home-page .showcase-marquee::before {
  background: linear-gradient(90deg, var(--theme-page-base) 0%, rgba(var(--theme-page-base-rgb), 0) 100%) !important;
}

html[data-theme="dark"] .home-page .showcase-marquee::after,
html[data-theme="midnight"] .home-page .showcase-marquee::after {
  background: linear-gradient(270deg, var(--theme-page-base) 0%, rgba(var(--theme-page-base-rgb), 0) 100%) !important;
}
</style>
