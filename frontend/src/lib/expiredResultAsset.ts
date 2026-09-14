import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { APP_THEME_ATTRIBUTE } from "@/config/theme";
import { getCurrentTheme } from "@/lib/theme";

function readThemeColor(name: string, fallback: string) {
  if (typeof document === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function buildExpiredResultAsset() {
  const midnight = getCurrentTheme() === "midnight";
  const bgStart = midnight ? "#2c2c2c" : readThemeColor("--theme-page-base", "#fffaf4");
  const bgEnd = midnight ? "#252526" : readThemeColor("--theme-panel-bg-strong", "#ffe6c8");
  const border = midnight ? "#a8a8a8" : readThemeColor("--theme-panel-border-strong", "#efc784");
  const accent = midnight ? "#ffffff" : readThemeColor("--theme-accent", "#d08a24");
  const accentSoft = midnight ? "#e6e6e6" : readThemeColor("--theme-accent-strong", "#ffd585");
  const title = midnight ? "#ffffff" : readThemeColor("--theme-title", "#8c5a16");
  const subtitle = midnight ? "#d0d0d0" : readThemeColor("--theme-text-secondary", "#a9742e");

  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(`
<svg xmlns="http://www.w3.org/2000/svg" width="960" height="960" viewBox="0 0 960 960">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${bgStart}"/>
      <stop offset="100%" stop-color="${bgEnd}"/>
    </linearGradient>
  </defs>
  <rect width="960" height="960" rx="56" fill="url(#bg)"/>
  <rect x="74" y="74" width="812" height="812" rx="42" fill="none" stroke="${border}" stroke-dasharray="18 16" stroke-width="10"/>
  <g fill="none" stroke="${accent}" stroke-linecap="round" stroke-linejoin="round">
    <rect x="282" y="248" width="396" height="286" rx="28" stroke-width="18"/>
    <path d="M326 490l110-108 92 88 72-66 76 86" stroke-width="18"/>
    <circle cx="400" cy="330" r="34" fill="${accentSoft}" stroke-width="12"/>
  </g>
  <text x="480" y="654" text-anchor="middle" font-size="54" font-weight="700" fill="${title}">原图已过期</text>
  <text x="480" y="726" text-anchor="middle" font-size="34" fill="${subtitle}">服务器保留原图15天</text>
  <text x="480" y="776" text-anchor="middle" font-size="34" fill="${subtitle}">请在有效期内查看或下载</text>
</svg>
`)}`;
}

export function useExpiredResultAsset() {
  const themeName = ref(getCurrentTheme());
  let observer: MutationObserver | null = null;

  const expiredResultAsset = computed(() => {
    void themeName.value;
    return buildExpiredResultAsset();
  });

  onMounted(() => {
    themeName.value = getCurrentTheme();
    observer = new MutationObserver(() => {
      themeName.value = getCurrentTheme();
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: [APP_THEME_ATTRIBUTE],
    });
  });

  onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
  });

  return expiredResultAsset;
}
