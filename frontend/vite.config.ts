import { defineConfig, type PluginOption } from "vite";
import vue from "@vitejs/plugin-vue";
import { visualizer } from "rollup-plugin-visualizer";
import { resolve } from "path";

const shouldAnalyzeBundle = process.env.ANALYZE === "true";
const plugins: PluginOption[] = [
  vue(),
];

if (shouldAnalyzeBundle) {
  plugins.push(visualizer({
    filename: "stats.html",
    gzipSize: true,
    brotliSize: true,
    template: "treemap",
  }) as PluginOption);
}

export default defineConfig({
  base: "/",
  plugins,
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          // Keep ant-design-vue and CloudBase out of named vendor buckets so
          // Vite's preload helper and unused UI code stay off the first paint.
          if (id.includes("@cloudbase") || id.includes("ant-design-vue")) return;
          if (
            id.includes("/vue/")
            || id.includes("/@vue/")
            || id.includes("/vue-router/")
            || id.includes("/pinia/")
          ) {
            return "vue";
          }
          if (id.includes("echarts") || id.includes("vue-echarts")) return "charts";
          if (id.includes("@wangeditor")) return "editor";
          if (id.includes("markdown-it")) return "markdown";
          if (id.includes("cos-js-sdk-v5")) return "uploads";
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      "^/api(/|$)": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        timeout: 630_000,
        proxyTimeout: 630_000,
        configure(proxy) {
          proxy.on("proxyRes", (proxyRes, _req, res) => {
            const contentType = String(proxyRes.headers["content-type"] || "");
            if (!contentType.includes("text/event-stream")) return;
            proxyRes.headers["cache-control"] = "no-cache";
            proxyRes.headers["connection"] = "keep-alive";
            proxyRes.headers["x-accel-buffering"] = "no";
            res.setHeader("Cache-Control", "no-cache");
            res.setHeader("Connection", "keep-alive");
            res.setHeader("X-Accel-Buffering", "no");
            proxyRes.on("data", () => {
              if (typeof (res as { flush?: () => void }).flush === "function") {
                (res as { flush: () => void }).flush();
              }
            });
          });
        },
      },
      "/uploads": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
