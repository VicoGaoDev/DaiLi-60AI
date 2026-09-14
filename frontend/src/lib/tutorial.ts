export const TUTORIAL_MODULES = ["general", "generate", "chat", "video", "canvas"] as const;

export type TutorialModule = (typeof TUTORIAL_MODULES)[number];

export const DEFAULT_TUTORIAL_MODULE: TutorialModule = "general";

export const tutorialModuleMeta: Record<
  TutorialModule,
  { label: string; path: string; doc: string; placeholder?: boolean }
> = {
  general: {
    label: "通用教程",
    path: "/tutorial/general",
    doc: "docs/general-tutorial.html",
  },
  generate: {
    label: "AI 生图",
    path: "/tutorial/generate",
    doc: "docs/generate-tutorial.html",
  },
  chat: {
    label: "AI 对话",
    path: "/tutorial/chat",
    doc: "docs/chat-tutorial.html",
  },
  video: {
    label: "AI 视频",
    path: "/tutorial/video",
    doc: "docs/video-tutorial.html",
  },
  canvas: {
    label: "无限画布",
    path: "/tutorial/canvas",
    doc: "docs/canvas-tutorial.html",
  },
};

export const tutorialNavOrder: TutorialModule[] = ["general", "chat", "generate", "video", "canvas"];

export const generalTutorialSections = [
  { id: "redeem", label: "1. 兑换积分" },
] as const;

export const generateTutorialSections = [
  { id: "overview", label: "1. 进入页面与布局" },
  { id: "modes", label: "2. 选择创作模式" },
  { id: "text-generate", label: "3. 文生图" },
  { id: "image-edit", label: "4. 图编辑" },
  { id: "inpaint", label: "5. 局部重绘" },
  { id: "smart-cutout", label: "6. 智能抠图" },
  { id: "prompt-reverse", label: "7. 提示词反推" },
  { id: "prompt-tools", label: "8. 提示词工具" },
  { id: "style-camera", label: "9. 风格与摄像机参数" },
  { id: "model-params", label: "10. 模型与参数" },
  { id: "submit", label: "11. 开始生成" },
  { id: "results", label: "12. 查看与处理结果" },
  { id: "assets-boards", label: "13. 素材、看板与历史" },
  { id: "batch", label: "14. 批量生图" },
  { id: "assistant", label: "15. AI 助手联动" },
  { id: "tips", label: "16. 使用建议" },
] as const;

export const chatTutorialSections = [
  { id: "overview", label: "1. 进入页面与布局" },
  { id: "sessions", label: "2. 新建与管理对话" },
  { id: "scenes", label: "3. 选择对话场景" },
  { id: "send", label: "4. 发送文字消息" },
  { id: "images", label: "5. 发送图片" },
  { id: "starters", label: "6. 快捷提问" },
  { id: "replies", label: "7. 处理回复" },
  { id: "generate", label: "8. 从对话去生图" },
  { id: "assistant", label: "9. 生图页的 AI 助手" },
  { id: "tips", label: "10. 使用建议" },
] as const;

export const videoTutorialSections = [
  { id: "overview", label: "1. 进入页面与布局" },
  { id: "modes", label: "2. 选择创作模式" },
  { id: "text-generate", label: "3. 文生视频" },
  { id: "image-to-video", label: "4. 图生视频" },
  { id: "first-last-frame", label: "5. 首尾帧" },
  { id: "model-params", label: "6. 模型与参数" },
  { id: "prompt-assets", label: "7. 提示词与素材" },
  { id: "submit", label: "8. 开始生成" },
  { id: "results", label: "9. 查看与处理结果" },
  { id: "from-image", label: "10. 从生图结果生成视频" },
  { id: "tips", label: "11. 使用建议" },
] as const;

export const canvasTutorialSections = [
  { id: "overview", label: "1. 进入页面与布局" },
  { id: "projects", label: "2. 新建与管理画布" },
  { id: "navigate", label: "3. 浏览与缩放" },
  { id: "image-generate", label: "4. 在画布里生图" },
  { id: "video-generate", label: "5. 在画布里生视频" },
  { id: "free-nodes", label: "6. 添加自由节点" },
  { id: "node-actions", label: "7. 处理节点结果" },
  { id: "references", label: "8. 选择参考图" },
  { id: "groups", label: "9. 分组与关联线" },
  { id: "search-arrange", label: "10. 搜索与一键整理" },
  { id: "assets-feedback", label: "11. 素材与反馈" },
  { id: "tips", label: "12. 使用建议" },
] as const;

export function getTutorialSections(module: TutorialModule) {
  if (module === "general") return generalTutorialSections;
  if (module === "generate") return generateTutorialSections;
  if (module === "chat") return chatTutorialSections;
  if (module === "video") return videoTutorialSections;
  if (module === "canvas") return canvasTutorialSections;
  return [];
}

export function isTutorialModule(value: string | undefined): value is TutorialModule {
  return TUTORIAL_MODULES.includes(value as TutorialModule);
}

export function resolveTutorialModule(value: string | undefined): TutorialModule {
  return isTutorialModule(value) ? value : DEFAULT_TUTORIAL_MODULE;
}

export function resolveTutorialModuleFromPath(path: string): TutorialModule {
  if (path.startsWith("/tutorial/")) {
    return resolveTutorialModule(path.split("/")[2]);
  }
  if (path.startsWith("/chat")) return "chat";
  if (path.startsWith("/canvas")) return "canvas";
  if (path.startsWith("/video")) return "video";
  return "generate";
}
