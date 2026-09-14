export const APP_THEME_STORAGE_KEY = "banana-web-theme";
export const APP_THEME_ATTRIBUTE = "data-theme";
export const APP_PAGE_THEME_ATTRIBUTE = "data-page-theme";

export type AppThemeGroup = "dark" | "eye";

export const appThemeGroupMeta = [
  { key: "dark", label: "黑暗主题" },
  { key: "eye", label: "护眼主题" },
] as const;

export type AppThemeSwatch = {
  label: string;
  color: string;
};

export const appThemes = {
  warm: {
    key: "warm",
    label: "琥珀橙",
    group: "eye",
    order: 0,
    palette: [
      { label: "背景", color: "#fffaf4" },
      { label: "卡片", color: "#fffdf8" },
      { label: "强调", color: "#ffab25" },
      { label: "文字", color: "#4c341a" },
    ],
  },
  jade: {
    key: "jade",
    label: "玉子绿",
    group: "eye",
    order: 1,
    palette: [
      { label: "背景", color: "#fffeee" },
      { label: "卡片", color: "#eef3e4" },
      { label: "强调", color: "#00797c" },
      { label: "文字", color: "#0c4a4c" },
    ],
  },
  iris: {
    key: "iris",
    label: "鸢尾蓝",
    group: "eye",
    order: 2,
    palette: [
      { label: "背景", color: "#fffbea" },
      { label: "卡片", color: "#efe8d4" },
      { label: "强调", color: "#0f64b5" },
      { label: "文字", color: "#16181d" },
    ],
  },
  cyan: {
    key: "cyan",
    label: "天青",
    group: "eye",
    order: 3,
    palette: [
      { label: "背景", color: "#ffffff" },
      { label: "卡片", color: "#ceeff0" },
      { label: "主青", color: "#05afb5" },
      { label: "行动", color: "#233d4f" },
    ],
  },
  mauve: {
    key: "mauve",
    label: "蕈紫",
    group: "eye",
    order: 6,
    palette: [
      { label: "背景", color: "#fafbe6" },
      { label: "卡片", color: "#fafbe6" },
      { label: "强调", color: "#a48ce6" },
      { label: "文字", color: "#3b2c5c" },
    ],
  },
  alum: {
    key: "alum",
    label: "青矾绿",
    group: "eye",
    order: 4,
    palette: [
      { label: "背景", color: "#f5f4f7" },
      { label: "卡片", color: "#ffffff" },
      { label: "强调", color: "#2c9678" },
      { label: "文字", color: "#1a4d3e" },
    ],
  },
  mist: {
    key: "mist",
    label: "紫幽兰",
    group: "eye",
    order: 5,
    palette: [
      { label: "背景", color: "#e3e3e5" },
      { label: "卡片", color: "#f4f4f6" },
      { label: "强调", color: "#707899" },
      { label: "文字", color: "#2f3344" },
    ],
  },
  dark: {
    key: "dark",
    label: "石墨灰",
    group: "dark",
    order: 1,
    palette: [
      { label: "背景", color: "#f6f7f9" },
      { label: "卡片", color: "#fbfbfc" },
      { label: "强调", color: "#34363d" },
      { label: "文字", color: "#1f2229" },
    ],
  },
  midnight: {
    key: "midnight",
    label: "墨夜",
    group: "dark",
    order: 0,
    palette: [
      { label: "背景", color: "#181818" },
      { label: "卡片", color: "#1f1f1f" },
      { label: "强调", color: "#e8a43a" },
      { label: "文字", color: "#e6e6e6" },
    ],
  },
} as const;

export type AppThemeName = keyof typeof appThemes;
export type AppThemeMeta = (typeof appThemes)[AppThemeName];

export const DEFAULT_APP_THEME: AppThemeName = "warm";

export const appThemeList = Object.values(appThemes) as AppThemeMeta[];

export function isAppThemeName(value: string | null | undefined): value is AppThemeName {
  return !!value && value in appThemes;
}

export function isDarkAppTheme(theme: AppThemeName) {
  return appThemes[theme].group === "dark";
}

export function getAppThemesByGroup(group: AppThemeGroup) {
  return appThemeList
    .filter((theme) => theme.group === group)
    .sort((left, right) => left.order - right.order);
}

export function getAppThemeGroups() {
  return appThemeGroupMeta.map((group) => ({
    ...group,
    themes: getAppThemesByGroup(group.key),
  }));
}
