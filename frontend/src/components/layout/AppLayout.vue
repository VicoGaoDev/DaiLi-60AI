<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, h, provide, nextTick, watch, defineAsyncComponent, type Component } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { message, notification } from "ant-design-vue";
import {
  getMe,
  getContactConfig,
  getAnnouncementConfig,
  redeemCreditKey,
} from "@/api/auth";
import { createPaymentOrder, listPaymentPlans } from "@/api/payments";
import { createFeedback, getMyUnreadFeedbackCount } from "@/api/feedback";
import { getAdminUnreadFeedbackCount } from "@/api/admin";
import { getAvatarImageSrc } from "@/api/images";
import { withBaseUrl } from "@/lib/assets";
import {
  getStoredAdminUnresolvedFeedbackCount,
  setStoredAdminUnresolvedFeedbackCount,
  subscribeAdminUnresolvedFeedbackCount,
} from "@/lib/adminFeedbackNotice";
import {
  getStoredUserCompletedUnreadFeedbackCount,
  setStoredUserCompletedUnreadFeedbackCount,
  subscribeUserCompletedUnreadFeedbackCount,
} from "@/lib/userFeedbackNotice";
import { getMyUnreadSystemMessageCount, listMySystemMessages } from "@/api/systemMessages";
import {
  getStoredUnreadSystemMessageCount,
  setStoredUnreadSystemMessageCount,
  subscribeUnreadSystemMessageCount,
} from "@/lib/systemMessageNotice";
import { contentLooksLikeHtml } from "@/lib/htmlContent";
import { subscribeAuthSessionExpired } from "@/lib/authSessionNotice";
import {
  isAiAssistantDockTabEnabled,
  subscribeAiAssistantDockTabEnabled,
} from "@/lib/aiAssistantDock";
import {
  isTutorialDockTabEnabled,
  subscribeTutorialDockTabEnabled,
} from "@/lib/generateTutorialDock";
import { APP_THEME_ATTRIBUTE, appThemes, getAppThemeGroups, isAppThemeName, type AppThemeName } from "@/config/theme";
import { importAfterExtendedAntd } from "@/lib/antd";
import { getCurrentTheme, setAppTheme } from "@/lib/theme";
import NavGenerateImageIcon from "@/components/icons/NavGenerateImageIcon.vue";
import ThemeStyleMenuEntry from "@/components/theme/ThemeStyleMenuEntry.vue";
import AuthModal from "@/components/auth/AuthModal.vue";
import type { AnnouncementConfig, PaymentPlan } from "@/types";
import {
  PictureOutlined,
  SettingOutlined,
  TeamOutlined,
  NumberOutlined,
  CommentOutlined,
  BarChartOutlined,
  BugOutlined,
  KeyOutlined,
  CloudUploadOutlined,
  VideoCameraOutlined,
  LogoutOutlined,
  DownOutlined,
  UserOutlined,
  UserAddOutlined,
  ThunderboltOutlined,
  PayCircleFilled,
  MenuOutlined,
  MailOutlined,
  MessageOutlined,
  CustomerServiceOutlined,
  GiftOutlined,
  UsergroupAddOutlined,
  AccountBookOutlined,
  MoneyCollectOutlined,
  BellOutlined,
  BulbOutlined,
  CheckOutlined,
  ClockCircleOutlined,
  AppstoreOutlined,
  TagsOutlined,
  FontSizeOutlined,
  SearchOutlined,
  HighlightOutlined,
  ScissorOutlined,
  ShareAltOutlined,
  CloseOutlined,
  ReadOutlined,
  BgColorsOutlined,
} from "@ant-design/icons-vue";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const UserSuggestionDialog = defineAsyncComponent(() => importAfterExtendedAntd(() => import("@/components/feedback/UserSuggestionDialog.vue")));
const NotificationCenterDialog = defineAsyncComponent(() => importAfterExtendedAntd(() => import("@/components/update-log/NotificationCenterDialog.vue")));
const isAdmin = computed(() => auth.isAdmin);
const isSuperAdmin = computed(() => auth.isSuperAdmin);
const hideTopMenu = computed(() => route.meta.hideTopMenu === true);
const isWorkbenchLayout = computed(() => route.meta.workbenchLayout === true);
const isCanvasRoute = computed(() => route.path.startsWith("/canvas") || route.path.startsWith("/admin/user-canvases/"));
const isAdminRoute = computed(() => route.path.startsWith("/admin"));
const shouldSyncUserNoticeCounts = computed(() => !isCanvasRoute.value && !isAdminRoute.value);
const showDesktopSideNav = computed(() => !hideTopMenu.value || (isWorkbenchLayout.value && isCanvasRoute.value));
const showSuggestionFab = computed(() =>
  !hideTopMenu.value
  && !isWorkbenchLayout.value
  && !isAdminRoute.value,
);
const AiAssistantDock = defineAsyncComponent(() => importAfterExtendedAntd(() => import("@/components/chat/AiAssistantDock.vue")));
const GenerateTutorialDock = defineAsyncComponent(() => importAfterExtendedAntd(() => import("@/components/tutorial/GenerateTutorialDock.vue")));
const aiAssistantDockTabEnabled = ref(isAiAssistantDockTabEnabled());
const tutorialDockTabEnabled = ref(isTutorialDockTabEnabled());
let unsubscribeAiAssistantDockTabEnabled: (() => void) | null = null;
let unsubscribeTutorialDockTabEnabled: (() => void) | null = null;
const showAiAssistantDock = computed(() => {
  if (!aiAssistantDockTabEnabled.value) return false;
  if (isAdminRoute.value) return false;
  const path = route.path;
  return (
    path.startsWith("/generate")
    || path.startsWith("/video-generate")
    || path.startsWith("/canvas")
    || path.startsWith("/history")
    || path.startsWith("/templates")
  );
});
const showGenerateTutorialDock = computed(() => {
  if (!tutorialDockTabEnabled.value) return false;
  if (isAdminRoute.value) return false;
  const path = route.path;
  return (
    path.startsWith("/tutorial")
    || path.startsWith("/generate")
    || path.startsWith("/video-generate")
    || path.startsWith("/canvas")
    || path.startsWith("/history")
    || path.startsWith("/templates")
    || path.startsWith("/batch-generate")
  );
});
const SUGGESTION_FAB_POSITION_KEY = "userSuggestionFabPosition";
const INVITE_CODE_SESSION_KEY = "bananaInviteCode";
const PROMO_CODE_SESSION_KEY = "bananaPromoCode";
const SUGGESTION_FAB_EDGE_GAP = 0;
const SUGGESTION_FAB_SNAP_THRESHOLD = 40;
const SUGGESTION_FAB_LEGACY_EDGE_GAP = 24;
const SUGGESTION_FAB_DESKTOP_SIZE = 40;
const SUGGESTION_FAB_MOBILE_SIZE = 36;
const USER_NOTICE_CARD_STYLE = {
  cursor: "pointer",
  borderRadius: "20px",
  background: "linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft))",
  border: "1px solid var(--theme-border-accent)",
  boxShadow: "0 16px 28px var(--theme-shadow-soft)",
  color: "var(--theme-title)",
} as const;
const mobileDrawerOpen = ref(false);
const routeTransitionName = ref("route-page-forward");
const canManagePromoCodes = computed(() => auth.user?.is_whitelisted === true);
const canAccessCanvasMenu = computed(() => auth.isLoggedIn);
const suggestionFabWrapRef = ref<HTMLElement | null>(null);
const desktopSideNavRef = ref<HTMLElement | null>(null);
const suggestionFabPosition = ref<{ x: number; y: number } | null>(null);
let suggestionFabDragState: {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
  moved: boolean;
} | null = null;

function renderUserNoticeIcon(icon: Component) {
  return h(
    "span",
    {
      style: {
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "34px",
        height: "34px",
        borderRadius: "50%",
        border: "1px solid var(--theme-border-accent)",
        background: "var(--theme-control-active)",
        boxShadow: "0 10px 20px var(--theme-shadow-soft)",
      },
    },
    [
      h(icon, {
        style: {
          fontSize: "20px",
          color: "var(--theme-accent-contrast)",
        },
      }),
    ],
  );
}

function openUserNoticeNotification(options: {
  key: string;
  title: string;
  description: string;
  icon: Component;
  duration?: number;
  onClick: () => void;
}) {
  notification.info({
    key: options.key,
    class: "app-user-notice-card",
    message: options.title,
    description: options.description,
    icon: renderUserNoticeIcon(options.icon),
    closeIcon: h(CloseOutlined, {
      style: {
        color: "var(--theme-accent-text)",
        fontSize: "18px",
      },
    }),
    placement: "topRight",
    duration: options.duration ?? 5,
    style: USER_NOTICE_CARD_STYLE,
    onClick: options.onClick,
  });
}

const suggestionFabWrapStyle = computed(() => {
  if (!suggestionFabPosition.value) return {};
  return {
    left: `${suggestionFabPosition.value.x}px`,
    top: `${suggestionFabPosition.value.y}px`,
    right: "auto",
    bottom: "auto",
  };
});

const suggestionFabTooltipPlacement = computed(() => {
  const position = suggestionFabPosition.value;
  if (!position || typeof window === "undefined") return "left";
  const minX = getSuggestionFabMinX();
  const mid = minX + (window.innerWidth - minX) / 2;
  return position.x < mid ? "right" : "left";
});

const routeOrder = new Map<string, number>([
  ["/", 0],
  ["/chat", 1],
  ["/generate", 2],
  ["/video-generate", 3],
  ["/canvas", 4],
  ["/templates", 5],
  ["/history", 6],
  ["/tutorial", 6.5],
  ["/tutorial/general", 6.5],
  ["/tutorial/generate", 6.5],
  ["/tutorial/chat", 6.5],
  ["/tutorial/video", 6.5],
  ["/tutorial/canvas", 6.5],
  ["/profile", 7],
  ["/api-keys", 8],
  ["/system-messages", 9],
  ["/system-messages/:messageId", 10],
  ["/settings", 11],
  ["/credit-logs", 12],
  ["/invite-rewards", 13],
  ["/promo-codes", 14],
  ["/feedbacks", 15],
  ["/feedbacks/:feedbackId", 16],
  ["/admin/templates", 17],
  ["/admin/prompt-optimize", 17.5],
  ["/admin/example-canvases", 18],
  ["/admin/users", 19],
  ["/admin/user-tasks", 20],
  ["/admin/user-videos", 21],
  ["/admin/user-canvases", 22],
  ["/admin/user-conversations", 22.5],
  ["/admin/dashboard", 23],
  ["/admin/image-dashboard", 24],
  ["/admin/video-dashboard", 25],
  ["/admin/error-analytics", 26],
  ["/admin/general-settings", 27],
  ["/admin/redeem-keys", 28],
  ["/admin/ledger", 29],
  ["/admin/revenue", 30],
  ["/admin/invite-rewards", 31],
  ["/admin/promo-stats", 32],
  ["/admin/payment-orders", 33],
  ["/admin/feedbacks", 34],
  ["/admin/feedbacks/:feedbackId", 35],
  ["/admin/system-messages", 36],
  ["/admin/update-logs", 36],
  ["/admin/cos-config", 37],
  ["/admin/external-api-configs", 38],
  ["/admin/generation-scene-categories", 38.5],
  ["/admin/video-api-configs", 39],
  ["/admin/chat-api-configs", 40],
]);

const currentTheme = ref<AppThemeName>(getCurrentTheme());
const themeMenuGroups = getAppThemeGroups();
let themeObserver: MutationObserver | null = null;
const adminUnresolvedFeedbackCount = ref(getStoredAdminUnresolvedFeedbackCount());
let unsubscribeAdminFeedbackCount: (() => void) | null = null;
const userCompletedUnreadFeedbackCount = ref(getStoredUserCompletedUnreadFeedbackCount());
let unsubscribeUserFeedbackCount: (() => void) | null = null;
const userUnreadSystemMessageCount = ref(getStoredUnreadSystemMessageCount());
let unsubscribeSystemMessageCount: (() => void) | null = null;
let systemMessagePollTimer: number | null = null;
let unsubscribeAuthSessionExpired: (() => void) | null = null;
const UNRESOLVED_FEEDBACK_NOTIFICATION_KEY = "global-admin-unresolved-feedback";
const USER_UNREAD_FEEDBACK_NOTIFICATION_KEY = "global-user-unread-feedback";
const USER_UNREAD_SYSTEM_MESSAGE_NOTIFICATION_KEY = "global-user-unread-system-message";
const notifiedUnreadSystemMessageIdsByUser = new Map<string, Set<string>>();

type PrimaryMenuItem = {
  key: string;
  label: string;
  iconSrc: string;
  darkIconSrc?: string;
  icon?: Component;
  badgeText?: string;
};

type GenerateEntryMode = "textGenerate" | "imageEdit" | "inpaint" | "smartCutout" | "promptReverse";
const GENERATE_MENU_ENTRY_EVENT = "banana:generate-menu-entry";
const SHOW_PRIMARY_MENU_BADGES = true;
const INVITE_REWARDS_BADGE_TEXT = "";
const ADMIN_BADGE_OFFSET: [number, number] = [-8, 2];

const generateEntryPrimaryMenuItems: Array<{ key: GenerateEntryMode; label: string; icon: Component }> = [
  { key: "textGenerate", label: "文生图", icon: FontSizeOutlined },
  { key: "imageEdit", label: "图编辑", icon: PictureOutlined },
];
const generateEntryToolMenuItems: Array<{ key: GenerateEntryMode; label: string; icon: Component }> = [
  { key: "inpaint", label: "局部重绘", icon: HighlightOutlined },
  { key: "smartCutout", label: "智能抠图", icon: ScissorOutlined },
  { key: "promptReverse", label: "提示词反推", icon: SearchOutlined },
];

type VideoEntryMode = "textGenerate" | "imageToVideo" | "firstLastFrame";
type VideoEntryMenuKey = "video-textGenerate" | "video-imageToVideo" | "video-firstLastFrame";
const videoEntryMenuItems: Array<{ key: VideoEntryMenuKey; mode: VideoEntryMode; label: string; icon: Component }> = [
  { key: "video-textGenerate", mode: "textGenerate", label: "文生视频", icon: FontSizeOutlined },
  { key: "video-imageToVideo", mode: "imageToVideo", label: "图生视频", icon: PictureOutlined },
  { key: "video-firstLastFrame", mode: "firstLastFrame", label: "首尾帧视频", icon: VideoCameraOutlined },
];

type MoreFeatureMenuKey = "templates" | "history" | "tutorial";
const moreFeatureMenuItems: Array<{ key: MoreFeatureMenuKey; label: string; icon: Component; iconSrc: string }> = [
  { key: "templates", label: "创意模版", icon: BulbOutlined, iconSrc: withBaseUrl("nav-templates.svg") },
  { key: "history", label: "历史图片", icon: ClockCircleOutlined, iconSrc: withBaseUrl("nav-history.svg") },
  { key: "tutorial", label: "使用教程", icon: ReadOutlined, iconSrc: withBaseUrl("nav-templates.svg") },
];

const primaryMenuItems = computed<PrimaryMenuItem[]>(() => [
  {
    key: "chat",
    label: "AI 对话",
    iconSrc: withBaseUrl("nav-generate.svg"),
    icon: MessageOutlined,
    badgeText: SHOW_PRIMARY_MENU_BADGES ? "新" : undefined,
  },
  { key: "generate", label: "AI 生图", iconSrc: withBaseUrl("nav-generate.svg"), icon: NavGenerateImageIcon },
  {
    key: "video-generate",
    label: "AI 视频",
    iconSrc: withBaseUrl("nav-generate.svg"),
    icon: VideoCameraOutlined,
  },
  ...(canAccessCanvasMenu.value
    ? [{
        key: "canvas",
        label: "无限画布",
        iconSrc: withBaseUrl("nav-canvas.svg"),
        icon: NumberOutlined,
      }]
    : []),
  {
    key: "more",
    label: "更多",
    iconSrc: withBaseUrl("nav-templates.svg"),
    icon: MenuOutlined,
  },
]);

function getPrimaryMenuIconSrc(item: PrimaryMenuItem) {
  if (currentTheme.value !== "warm" && item.darkIconSrc) {
    return item.darkIconSrc;
  }
  return item.iconSrc;
}

const ADMIN_TEMPLATE_MENU_KEY = "admin-template";
const ADMIN_USER_DATA_MENU_KEY = "admin-user-data";
const ADMIN_ANALYTICS_MENU_KEY = "admin-analytics";
const ADMIN_FUNDS_MENU_KEY = "admin-funds";
const ADMIN_THIRD_PARTY_MENU_KEY = "admin-third-party";
const ADMIN_NOTICE_MENU_KEY = "admin-notice";

const adminMenuItems = computed(() =>
  [
    { key: "/admin/templates", label: "图片模版", icon: PictureOutlined, superAdminOnly: false },
    { key: "/admin/prompt-optimize", label: "提示词优化", icon: ThunderboltOutlined, superAdminOnly: false },
    { key: "/admin/example-canvases", label: "画布模版", icon: AppstoreOutlined, superAdminOnly: false },
    { key: "/admin/users", label: "用户管理", icon: TeamOutlined, superAdminOnly: false },
    { key: "/admin/user-tasks", label: "用户图片", icon: PictureOutlined, superAdminOnly: false },
    { key: "/admin/user-videos", label: "用户视频", icon: VideoCameraOutlined, superAdminOnly: false },
    { key: "/admin/user-canvases", label: "用户画布", icon: NumberOutlined, superAdminOnly: false },
    { key: "/admin/user-conversations", label: "用户对话", icon: CommentOutlined, superAdminOnly: false },
    { key: "/admin/dashboard", label: "数据总览", icon: BarChartOutlined, superAdminOnly: false },
    { key: "/admin/image-dashboard", label: "图片数据", icon: PictureOutlined, superAdminOnly: false },
    { key: "/admin/video-dashboard", label: "视频数据", icon: VideoCameraOutlined, superAdminOnly: false },
    { key: "/admin/error-analytics", label: "错误统计", icon: BugOutlined, superAdminOnly: false },
    { key: "/admin/general-settings", label: "通用设置", icon: SettingOutlined, superAdminOnly: false },
    { key: "/admin/revenue", label: "营业额", icon: AccountBookOutlined, superAdminOnly: false },
    { key: "/admin/ledger", label: "账本", icon: MoneyCollectOutlined, superAdminOnly: false },
    { key: "/admin/redeem-keys", label: "兑换码", icon: GiftOutlined, superAdminOnly: false },
    { key: "/admin/invite-rewards", label: "邀请奖励", icon: ShareAltOutlined, superAdminOnly: false },
    { key: "/admin/promo-stats", label: "推广返利", icon: UsergroupAddOutlined, superAdminOnly: false },
    { key: "/admin/feedbacks", label: "用户反馈", icon: MessageOutlined, superAdminOnly: false },
    { key: "/admin/system-messages", label: "系统邮件", icon: MailOutlined, superAdminOnly: false },
    { key: "/admin/update-logs", label: "更新日志", icon: BellOutlined, superAdminOnly: false },
    { key: "/admin/cos-config", label: "COS 配置", icon: CloudUploadOutlined, superAdminOnly: true },
    { key: "/admin/external-api-configs", label: "生图接口", icon: KeyOutlined, superAdminOnly: true },
    { key: "/admin/generation-scene-categories", label: "生图分类", icon: TagsOutlined, superAdminOnly: true },
    { key: "/admin/video-api-configs", label: "视频接口", icon: VideoCameraOutlined, superAdminOnly: true },
    { key: "/admin/chat-api-configs", label: "对话接口", icon: MessageOutlined, superAdminOnly: true },
  ].filter((item) => !item.superAdminOnly || isSuperAdmin.value)
);
const adminMenuTemplateItems = computed(() =>
  adminMenuItems.value.filter((item) => ["/admin/templates", "/admin/prompt-optimize", "/admin/example-canvases"].includes(item.key))
);
const adminMenuUserDataItems = computed(() =>
  adminMenuItems.value.filter((item) => [
    "/admin/users",
    "/admin/user-tasks",
    "/admin/user-videos",
    "/admin/user-canvases",
    "/admin/user-conversations",
  ].includes(item.key))
);
const adminMenuAnalyticsItems = computed(() =>
  adminMenuItems.value.filter((item) => [
    "/admin/dashboard",
    "/admin/image-dashboard",
    "/admin/video-dashboard",
    "/admin/error-analytics",
  ].includes(item.key))
);
const adminMenuPromoDataItems = computed(() =>
  adminMenuItems.value.filter((item) => ["/admin/invite-rewards", "/admin/promo-stats"].includes(item.key))
);
const adminMenuFundItems = computed(() =>
  adminMenuItems.value.filter((item) => ["/admin/ledger", "/admin/revenue"].includes(item.key))
);
const adminMenuBaseItems = computed(() =>
  adminMenuItems.value.filter((item) => [
    "/admin/general-settings",
  ].includes(item.key))
);
const isAdminTemplateRoute = computed(() =>
  route.path.startsWith("/admin/templates")
  || route.path.startsWith("/admin/prompt-optimize")
  || route.path.startsWith("/admin/example-canvases")
);
const isAdminUserDataRoute = computed(() =>
  route.path.startsWith("/admin/users")
  || route.path.startsWith("/admin/user-tasks")
  || route.path.startsWith("/admin/user-videos")
  || route.path.startsWith("/admin/user-canvases")
  || route.path.startsWith("/admin/user-conversations")
);
const isAdminAnalyticsRoute = computed(() =>
  route.path.startsWith("/admin/dashboard")
  || route.path.startsWith("/admin/image-dashboard")
  || route.path.startsWith("/admin/video-dashboard")
  || route.path.startsWith("/admin/error-analytics")
  || route.path.startsWith("/admin/invite-rewards")
  || route.path.startsWith("/admin/promo-stats")
);
const isAdminFundsRoute = computed(() =>
  route.path.startsWith("/admin/ledger")
  || route.path.startsWith("/admin/revenue")
);
const isAdminThirdPartyRoute = computed(() =>
  route.path.startsWith("/admin/cos-config")
  || route.path.startsWith("/admin/external-api-configs")
  || route.path.startsWith("/admin/generation-scene-categories")
  || route.path.startsWith("/admin/video-api-configs")
  || route.path.startsWith("/admin/chat-api-configs")
);
const isAdminNoticeRoute = computed(() =>
  route.path.startsWith("/admin/feedbacks")
  || route.path.startsWith("/admin/system-messages")
  || route.path.startsWith("/admin/update-logs")
);
const adminMenuOpenKeys = ref<string[]>([
  ...(isAdminTemplateRoute.value ? [ADMIN_TEMPLATE_MENU_KEY] : []),
  ...(isAdminUserDataRoute.value ? [ADMIN_USER_DATA_MENU_KEY] : []),
  ...(isAdminAnalyticsRoute.value ? [ADMIN_ANALYTICS_MENU_KEY] : []),
  ...(isAdminFundsRoute.value ? [ADMIN_FUNDS_MENU_KEY] : []),
  ...(isAdminThirdPartyRoute.value ? [ADMIN_THIRD_PARTY_MENU_KEY] : []),
  ...(isAdminNoticeRoute.value ? [ADMIN_NOTICE_MENU_KEY] : []),
]);

watch(isAdminTemplateRoute, (active) => {
  if (active && !adminMenuOpenKeys.value.includes(ADMIN_TEMPLATE_MENU_KEY)) {
    adminMenuOpenKeys.value = [...adminMenuOpenKeys.value, ADMIN_TEMPLATE_MENU_KEY];
  }
});
watch(isAdminUserDataRoute, (active) => {
  if (active && !adminMenuOpenKeys.value.includes(ADMIN_USER_DATA_MENU_KEY)) {
    adminMenuOpenKeys.value = [...adminMenuOpenKeys.value, ADMIN_USER_DATA_MENU_KEY];
  }
});
watch(isAdminAnalyticsRoute, (active) => {
  if (active && !adminMenuOpenKeys.value.includes(ADMIN_ANALYTICS_MENU_KEY)) {
    adminMenuOpenKeys.value = [...adminMenuOpenKeys.value, ADMIN_ANALYTICS_MENU_KEY];
  }
});
watch(isAdminFundsRoute, (active) => {
  if (active && !adminMenuOpenKeys.value.includes(ADMIN_FUNDS_MENU_KEY)) {
    adminMenuOpenKeys.value = [...adminMenuOpenKeys.value, ADMIN_FUNDS_MENU_KEY];
  }
});
watch(isAdminThirdPartyRoute, (active) => {
  if (active && !adminMenuOpenKeys.value.includes(ADMIN_THIRD_PARTY_MENU_KEY)) {
    adminMenuOpenKeys.value = [...adminMenuOpenKeys.value, ADMIN_THIRD_PARTY_MENU_KEY];
  }
});
watch(isAdminNoticeRoute, (active) => {
  if (active && !adminMenuOpenKeys.value.includes(ADMIN_NOTICE_MENU_KEY)) {
    adminMenuOpenKeys.value = [...adminMenuOpenKeys.value, ADMIN_NOTICE_MENU_KEY];
  }
});
const adminMenuBusinessItems = computed(() =>
  adminMenuItems.value.filter((item) => ["/admin/redeem-keys"].includes(item.key))
);
const adminMenuNoticeItems = computed(() =>
  adminMenuItems.value.filter((item) => ["/admin/feedbacks", "/admin/system-messages", "/admin/update-logs"].includes(item.key))
);
const adminMenuConfigItems = computed(() =>
  adminMenuItems.value.filter((item) => [
    "/admin/cos-config",
    "/admin/external-api-configs",
    "/admin/generation-scene-categories",
    "/admin/video-api-configs",
    "/admin/chat-api-configs",
  ].includes(item.key))
);

const hasAdminUnresolvedFeedback = computed(() => adminUnresolvedFeedbackCount.value > 0);
const hasUserUnreadFeedback = computed(() => userCompletedUnreadFeedbackCount.value > 0);
const hasUserUnreadSystemMessage = computed(() => userUnreadSystemMessageCount.value > 0);
const hasUserUnreadNotice = computed(() => hasUserUnreadFeedback.value || hasUserUnreadSystemMessage.value);

const userMenuItems = computed(() => [
  { key: "profile", label: "个人主页", icon: UserOutlined, danger: false },
  { key: "credits", label: "积分明细", icon: ThunderboltOutlined, danger: false },
  ...(canManagePromoCodes.value ? [{ key: "promo-codes", label: "我的推广码", icon: UsergroupAddOutlined, danger: false }] : []),
  { key: "api-keys", label: "API 调用", icon: KeyOutlined, danger: false },
  { key: "my-feedback", label: "我的反馈", icon: MessageOutlined, danger: false },
  { key: "system-messages", label: "系统消息", icon: MailOutlined, danger: false },
  { key: "update-logs", label: "更新日志", icon: BellOutlined, danger: false },
  { key: "contact", label: "联系我们", icon: CustomerServiceOutlined, danger: false },
  { key: "settings", label: "设置", icon: SettingOutlined, danger: false },
  { key: "logout", label: "退出登录", icon: LogoutOutlined, danger: true },
]);
const userMenuAccountItems = computed(() =>
  userMenuItems.value.filter((item) => ["profile", "credits", "promo-codes", "api-keys"].includes(item.key))
);
const userMenuSettingsItems = computed(() =>
  userMenuItems.value.filter((item) => ["contact"].includes(item.key))
);
const userMenuNoticeItems = computed(() =>
  userMenuItems.value.filter((item) => ["my-feedback", "system-messages", "update-logs"].includes(item.key))
);
const userMenuDangerItems = computed(() => userMenuItems.value.filter((item) => item.danger));

const creditPurchasePlans = ref<PaymentPlan[]>([]);

function getRouteRank(path: string) {
  if (path.startsWith("/feedbacks/")) return routeOrder.get("/feedbacks/:feedbackId") ?? 0;
  if (path.startsWith("/system-messages/")) return routeOrder.get("/system-messages/:messageId") ?? 0;
  if (path.startsWith("/admin/feedbacks/")) return routeOrder.get("/admin/feedbacks/:feedbackId") ?? 0;
  if (path.startsWith("/chat")) return routeOrder.get("/chat") ?? 0;
  if (path.startsWith("/tutorial")) return routeOrder.get("/tutorial") ?? 6.5;
  if (path.startsWith("/canvas")) return routeOrder.get("/canvas") ?? 0;
  if (path.startsWith("/history")) return routeOrder.get("/history") ?? 0;
  return routeOrder.get(path) ?? 0;
}

/** 同页内参数切换（如对话 session）使用稳定 key，避免整页淡出重挂载 */
function getRoutePageKey(currentRoute: { path: string; name?: string | symbol | null }) {
  if (currentRoute.path.startsWith("/chat")) return "chat";
  if (currentRoute.path.startsWith("/tutorial")) return "tutorial";
  if (currentRoute.path.startsWith("/admin/user-conversations")) return "admin-user-conversations";
  return currentRoute.path;
}

const selectedKeys = computed(() => {
  const p = route.path;
  if (p.startsWith("/admin")) return ["admin"];
  if (p === "/") return [];
  if (p === "/templates") return ["more", "templates"];
  if (p.startsWith("/tutorial")) return ["more", "tutorial"];
  if (p === "/video-generate") return ["video-generate"];
  if (p.startsWith("/chat")) return ["chat"];
  if (p.startsWith("/canvas")) return ["canvas"];
  if (p === "/batch-generate") return ["batch-generate"];
  if (p.startsWith("/history")) return ["more", "history"];
  if (
    p === "/profile" ||
    p === "/settings" ||
    p === "/credit-logs" ||
    p === "/invite-rewards" ||
    p === "/promo-codes" ||
    p === "/api-keys" ||
    p.startsWith("/feedbacks") ||
    p.startsWith("/system-messages")
  ) return [];
  return ["generate", activeGenerateEntryMode.value];
});

const activeMoreFeatureKey = computed<MoreFeatureMenuKey | "">(() => {
  if (route.path.startsWith("/tutorial")) return "tutorial";
  if (route.path === "/templates") return "templates";
  if (route.path.startsWith("/history")) return "history";
  return "";
});

const activeGenerateEntryMode = computed<GenerateEntryMode>(() => {
  if (route.path !== "/generate") return "imageEdit";
  const mode = Array.isArray(route.query.mode) ? route.query.mode[0] : route.query.mode;
  if (mode === "textGenerate" || mode === "imageEdit" || mode === "inpaint" || mode === "smartCutout" || mode === "promptReverse") {
    return mode;
  }
  return "imageEdit";
});

const activeVideoEntryMenuKey = computed<VideoEntryMenuKey | "">(() => {
  if (route.path !== "/video-generate") return "";
  const mode = Array.isArray(route.query.mode) ? route.query.mode[0] : route.query.mode;
  if (mode === "textGenerate") return "video-textGenerate";
  if (mode === "imageToVideo") return "video-imageToVideo";
  if (mode === "firstLastFrame") return "video-firstLastFrame";
  return "video-imageToVideo";
});

const adminSelectedKeys = computed(() => {
  if (!route.path.startsWith("/admin")) return [];
  if (route.path.startsWith("/admin/feedbacks")) return ["/admin/feedbacks"];
  if (route.path.startsWith("/admin/user-canvases")) return ["/admin/user-canvases"];
  if (route.path.startsWith("/admin/user-conversations")) return ["/admin/user-conversations"];
  return [route.path];
});

watch(
  () => route.path,
  (to, from) => {
    const toRank = getRouteRank(to);
    const fromRank = getRouteRank(from ?? "");
    routeTransitionName.value = toRank < fromRank ? "route-page-back" : "route-page-forward";
  },
  { immediate: true }
);

watch(
  () => route.path,
  (path) => {
    if (path === "/") {
      void syncAdminUnresolvedFeedbackCount({ showToast: true });
    }
  }
);

function handleMenuClick({ key }: { key: string }) {
  mobileDrawerOpen.value = false;
  if (key === "more") return;
  if (key === "templates") router.push("/templates");
  else if (key === "generate") {
    window.dispatchEvent(new CustomEvent(GENERATE_MENU_ENTRY_EVENT));
    router.push("/generate");
  }
  else if (
    key === "textGenerate"
    || key === "imageEdit"
    || key === "inpaint"
    || key === "smartCutout"
    || key === "promptReverse"
  ) {
    openGenerateEntry(key);
    return;
  }
  else if (key === "video-generate") router.push("/video-generate");
  else if (
    key === "video-textGenerate"
    || key === "video-imageToVideo"
    || key === "video-firstLastFrame"
  ) {
    openVideoEntryByMenuKey(key);
  }
  else if (key === "chat") {
    if (!auth.isLoggedIn) {
      openAuthModal("login");
      return;
    }
    router.push("/chat");
  }
  else if (key === "canvas") {
    if (!auth.isLoggedIn) {
      openAuthModal("login");
      return;
    }
    router.push("/canvas");
  }
  else if (key === "history") {
    if (!auth.isLoggedIn) {
      openAuthModal("login");
      return;
    }
    router.push("/history");
  }
  else if (key === "tutorial") {
    router.push("/tutorial");
  }
}

function handleMoreFeatureMenu({ key }: { key: string }) {
  if (key === "templates" || key === "history" || key === "tutorial") {
    handleMenuClick({ key });
  }
}

function openGenerateEntry(mode: GenerateEntryMode) {
  mobileDrawerOpen.value = false;
  window.dispatchEvent(new CustomEvent(GENERATE_MENU_ENTRY_EVENT, { detail: { mode } }));
  router.push({
    path: "/generate",
    query: { mode },
  });
}

function handleGenerateEntryMenu({ key }: { key: string }) {
  if (key === "textGenerate" || key === "imageEdit" || key === "inpaint" || key === "smartCutout" || key === "promptReverse") {
    openGenerateEntry(key);
  }
}

function openVideoEntry(mode: VideoEntryMode) {
  mobileDrawerOpen.value = false;
  router.push({
    path: "/video-generate",
    query: { mode },
  });
}

function openVideoEntryByMenuKey(key: VideoEntryMenuKey) {
  const item = videoEntryMenuItems.find((entry) => entry.key === key);
  if (item) openVideoEntry(item.mode);
}

function handleVideoEntryMenu({ key }: { key: string }) {
  if (
    key === "video-textGenerate"
    || key === "video-imageToVideo"
    || key === "video-firstLastFrame"
  ) {
    openVideoEntryByMenuKey(key);
  }
}

function handleAdminMenu({ key }: { key: string }) {
  if (!key.startsWith("/")) return;
  mobileDrawerOpen.value = false;
  router.push(key);
}

function handleAdminMenuOpenChange(keys: string[]) {
  adminMenuOpenKeys.value = keys;
}

function applyUserTheme(theme: AppThemeName) {
  if (theme === currentTheme.value) return;
  setAppTheme(theme);
  currentTheme.value = theme;
  message.success(`已切换为${appThemes[theme].label}`);
}

function handleUserMenu({ key }: { key: string }) {
  if (key === "theme-style-entry") return;
  if (key.startsWith("theme:")) {
    const theme = key.slice("theme:".length);
    if (isAppThemeName(theme)) applyUserTheme(theme);
    return;
  }
  mobileDrawerOpen.value = false;
  if (key === "profile") router.push("/profile");
  else if (key === "system-messages") router.push("/system-messages");
  else if (key === "my-feedback") router.push("/feedbacks");
  else if (key === "update-logs") {
    notificationCenterDefaultTab.value = "update-logs";
    notificationCenterDialogOpen.value = true;
  }
  else if (key === "contact") openCreditsContact();
  else if (key === "settings") router.push("/settings");
  else if (key === "credits") router.push("/credit-logs");
  else if (key === "promo-codes") router.push("/promo-codes");
  else if (key === "api-keys") router.push("/api-keys");
  else if (key === "logout") {
    resetUserUnreadSystemMessageNotificationState();
    auth.logout();
    setStoredUnreadSystemMessageCount(0);
    stopSystemMessagePolling();
    router.push("/");
  }
}

async function syncAdminUnresolvedFeedbackCount(options?: { showToast?: boolean }) {
  if (!auth.isLoggedIn || !auth.isAdmin) return;
  try {
    const { count } = await getAdminUnreadFeedbackCount();
    adminUnresolvedFeedbackCount.value = setStoredAdminUnresolvedFeedbackCount(count);
    if (options?.showToast && count > 0) {
      notification.warning({
        key: UNRESOLVED_FEEDBACK_NOTIFICATION_KEY,
        message: "有用户反馈新消息",
        description: `当前有 ${count} 条反馈包含用户新回复，点击前往处理。`,
        placement: "topRight",
        duration: 5,
        style: { cursor: "pointer" },
        onClick: () => {
          notification.close(UNRESOLVED_FEEDBACK_NOTIFICATION_KEY);
          router.push("/admin/feedbacks");
        },
      });
      return;
    }
    notification.close(UNRESOLVED_FEEDBACK_NOTIFICATION_KEY);
  } catch {
    // ignore unresolved feedback count failures
  }
}

async function syncUserCompletedUnreadFeedbackCount(options?: { showToast?: boolean; forceToast?: boolean }) {
  if (!auth.isLoggedIn) return;
  if (!shouldSyncUserNoticeCounts.value) return;
  try {
    const previous = userCompletedUnreadFeedbackCount.value;
    const { count } = await getMyUnreadFeedbackCount();
    userCompletedUnreadFeedbackCount.value = setStoredUserCompletedUnreadFeedbackCount(count);
    if (options?.showToast && count > 0 && (options.forceToast || count > previous)) {
      openUserNoticeNotification({
        key: USER_UNREAD_FEEDBACK_NOTIFICATION_KEY,
        title: "您的反馈有新回复",
        description: `当前有 ${count} 条反馈待查看，点击前往查看详情。`,
        icon: MessageOutlined,
        onClick: () => {
          notification.close(USER_UNREAD_FEEDBACK_NOTIFICATION_KEY);
          router.push("/feedbacks");
        },
      });
      return;
    }
    if (count <= 0) {
      notification.close(USER_UNREAD_FEEDBACK_NOTIFICATION_KEY);
    }
  } catch {
    // ignore user unread feedback count failures
  }
}

async function syncUserUnreadSystemMessageCount(options?: { showToast?: boolean; forceToast?: boolean }) {
  if (!auth.isLoggedIn) return;
  if (!shouldSyncUserNoticeCounts.value) return;
  try {
    const previous = userUnreadSystemMessageCount.value;
    const { count } = await getMyUnreadSystemMessageCount();
    userUnreadSystemMessageCount.value = setStoredUnreadSystemMessageCount(count);
    if (options?.showToast && count > 0 && (options.forceToast || count > previous)) {
      await notifyLatestUnreadSystemMessage(count);
    }
  } catch {
    // ignore system message count failures
  }
}

async function notifyLatestUnreadSystemMessage(unreadCount: number) {
  if (unreadCount <= 0) {
    notification.close(USER_UNREAD_SYSTEM_MESSAGE_NOTIFICATION_KEY);
    return;
  }

  const { items } = await listMySystemMessages(1, Math.max(5, unreadCount));
  const latestUnread = items.find((item) => !item.is_read);
  const userKey = auth.user?.business_id || auth.user?.id || "anonymous";
  const notifiedIds = notifiedUnreadSystemMessageIdsByUser.get(userKey) || new Set<string>();
  if (!latestUnread || notifiedIds.has(latestUnread.message_id)) return;

  notifiedIds.add(latestUnread.message_id);
  notifiedUnreadSystemMessageIdsByUser.set(userKey, notifiedIds);
  openUserNoticeNotification({
    key: USER_UNREAD_SYSTEM_MESSAGE_NOTIFICATION_KEY,
    title: latestUnread.subject || "新的系统消息",
    description: unreadCount > 1 ? `你有 ${unreadCount} 条未读系统消息，点击查看详情。` : "你有新的系统消息，点击查看详情。",
    icon: MailOutlined,
    duration: 6,
    onClick: () => {
      notification.close(USER_UNREAD_SYSTEM_MESSAGE_NOTIFICATION_KEY);
      router.push(`/system-messages/${latestUnread.message_id}`);
    },
  });
}

function resetUserUnreadSystemMessageNotificationState() {
  notification.close(USER_UNREAD_SYSTEM_MESSAGE_NOTIFICATION_KEY);
  notifiedUnreadSystemMessageIdsByUser.clear();
}

function startSystemMessagePolling() {
  if (!shouldSyncUserNoticeCounts.value) return;
  if (typeof window === "undefined" || systemMessagePollTimer) return;
  systemMessagePollTimer = window.setInterval(() => {
    void syncAdminUnresolvedFeedbackCount({ showToast: true });
    void syncUserCompletedUnreadFeedbackCount({ showToast: true });
    void syncUserUnreadSystemMessageCount({ showToast: true });
  }, 60000);
}

function stopSystemMessagePolling() {
  if (!systemMessagePollTimer) return;
  window.clearInterval(systemMessagePollTimer);
  systemMessagePollTimer = null;
}

const loginModalVisible = ref(false);
const notificationCenterDialogOpen = ref(false);
const notificationCenterDefaultTab = ref<"feedback" | "system-messages" | "update-logs">("update-logs");
provide("loginModalVisible", loginModalVisible);
const authTab = ref<"login" | "register">("login");
const seedRegisterPromoCode = ref("");
const redeemDialogOpen = ref(false);
const redeemLoading = ref(false);
const redeemForm = reactive({ key: "" });
const purchaseDialogOpen = ref(false);
const selectedPurchasePlanKey = ref("");
const selectedPurchasePlan = computed(() =>
  creditPurchasePlans.value.find((item) => item.key === selectedPurchasePlanKey.value && item.purchasable) || null
);
const purchasePlansLoading = ref(false);
const purchaseLoading = ref(false);
const purchaseFeedbackDialogOpen = ref(false);
const purchaseFeedbackSubmitting = ref(false);
const purchaseFeedbackForm = reactive({ content: "" });
const suggestionDialogOpen = ref(false);
const authExpiredPromptVisible = ref(false);
const expiredSessionRedirectPath = ref("");

function normalizeInviteCode(code?: string | null) {
  return (code || "").trim().toUpperCase().replace(/\s+/g, "");
}

function isPersonalInviteCodeValue(code?: string | null) {
  return /^U[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{7}$/.test(normalizeInviteCode(code));
}

function getStoredInviteCode() {
  try {
    const code = normalizeInviteCode(sessionStorage.getItem(INVITE_CODE_SESSION_KEY));
    return isPersonalInviteCodeValue(code) ? code : "";
  } catch {
    return "";
  }
}

function getStoredPromoCode() {
  try {
    const code = normalizeInviteCode(sessionStorage.getItem(PROMO_CODE_SESSION_KEY));
    if (!code || isPersonalInviteCodeValue(code)) return "";
    return code;
  } catch {
    return "";
  }
}

function clearStoredInviteCode() {
  try {
    sessionStorage.removeItem(INVITE_CODE_SESSION_KEY);
  } catch {
    // Ignore storage errors in restricted browser modes.
  }
}

function clearStoredPromoCode() {
  try {
    sessionStorage.removeItem(PROMO_CODE_SESSION_KEY);
  } catch {
    // Ignore storage errors in restricted browser modes.
  }
}

const lockedPromoFromSession = ref("");

function syncLockedPromoFromSession() {
  lockedPromoFromSession.value = getStoredPromoCode();
}

function applyStoredInviteOrPromoCodeToRegisterForm() {
  syncLockedPromoFromSession();
  const storedPromoCode = lockedPromoFromSession.value;
  if (storedPromoCode) {
    seedRegisterPromoCode.value = storedPromoCode;
    return;
  }
  const storedInviteCode = getStoredInviteCode();
  seedRegisterPromoCode.value = storedInviteCode || seedRegisterPromoCode.value;
}

function captureInviteCodeFromRoute() {
  if (auth.isLoggedIn) return;
  const rawInvite = Array.isArray(route.query.invite) ? route.query.invite[0] : route.query.invite;
  const inviteCode = normalizeInviteCode(typeof rawInvite === "string" ? rawInvite : "");
  if (!isPersonalInviteCodeValue(inviteCode)) return;
  try {
    sessionStorage.setItem(INVITE_CODE_SESSION_KEY, inviteCode);
    sessionStorage.removeItem(PROMO_CODE_SESSION_KEY);
  } catch {
    // Ignore storage errors in restricted browser modes.
  }
  seedRegisterPromoCode.value = inviteCode;
}

function capturePromoCodeFromRoute() {
  if (auth.isLoggedIn) return;
  const rawPromo = Array.isArray(route.query.promo) ? route.query.promo[0] : route.query.promo;
  const promoCode = normalizeInviteCode(typeof rawPromo === "string" ? rawPromo : "");
  if (!promoCode || isPersonalInviteCodeValue(promoCode)) return;
  try {
    sessionStorage.setItem(PROMO_CODE_SESSION_KEY, promoCode);
    sessionStorage.removeItem(INVITE_CODE_SESSION_KEY);
  } catch {
    // Ignore storage errors in restricted browser modes.
  }
  lockedPromoFromSession.value = promoCode;
  seedRegisterPromoCode.value = promoCode;
}

watch(
  () => [route.query.invite, route.query.promo] as const,
  () => {
    // promo 与 invite 不是同一套码；同时出现时优先使用 promo 查询参数。
    if (route.query.promo) {
      capturePromoCodeFromRoute();
      return;
    }
    captureInviteCodeFromRoute();
  },
  { immediate: true },
);

function openAuthModal(tab: "login" | "register") {
  mobileDrawerOpen.value = false;
  authTab.value = tab;
  if (tab === "register") {
    applyStoredInviteOrPromoCodeToRegisterForm();
  }
  loginModalVisible.value = true;
}

function handleAuthSessionExpired(detail: { redirectPath: string }) {
  resetUserUnreadSystemMessageNotificationState();
  auth.logout();
  expiredSessionRedirectPath.value = detail.redirectPath || route.fullPath || "/templates";
  if (loginModalVisible.value) return;
  authTab.value = "login";
  loginModalVisible.value = true;
  if (authExpiredPromptVisible.value) return;
  authExpiredPromptVisible.value = true;
  message.warning("登录已过期，请重新登录");
}

watch(loginModalVisible, (open) => {
  if (!open) {
    authExpiredPromptVisible.value = false;
  }
});

function clearInviteAndPromoSeeds() {
  clearStoredInviteCode();
  clearStoredPromoCode();
  lockedPromoFromSession.value = "";
  seedRegisterPromoCode.value = "";
}

function handleRegistered(kind: "invite" | "promo" | "plain") {
  if (kind === "invite" || kind === "promo") {
    clearInviteAndPromoSeeds();
  }
}

async function handleAuthLoggedIn() {
  const redirectPath = expiredSessionRedirectPath.value;
  expiredSessionRedirectPath.value = "";
  await nextTick();
  await checkAnnouncement();
  await syncUserCompletedUnreadFeedbackCount({ showToast: true, forceToast: true });
  await syncUserUnreadSystemMessageCount({ showToast: true, forceToast: true });
  startSystemMessagePolling();
  if (redirectPath && redirectPath !== route.fullPath) {
    await router.replace(redirectPath);
  }
}

async function handleRedeemCredits() {
  const normalizedKey = redeemForm.key.trim().toUpperCase();
  if (!normalizedKey) {
    message.warning("请输入兑换码");
    return;
  }
  redeemLoading.value = true;
  try {
    const res = await redeemCreditKey(normalizedKey);
    try {
      auth.updateUser(await getMe());
    } catch {
      if (auth.user) {
        auth.updateUser({ ...auth.user, credits: res.credits });
      }
    }
    message.success(`兑换成功，已到账 ${res.credit_amount} 积分`);
    redeemDialogOpen.value = false;
    redeemForm.key = "";
  } catch (err: any) {
    message.error(err.response?.data?.detail || "兑换失败");
  } finally {
    redeemLoading.value = false;
  }
}

const creditsContactVisible = ref(false);
const contactQrImage = ref("");
const announcementVisible = ref(false);
const announcementDismissToday = ref(false);
const announcementConfig = ref<AnnouncementConfig>({
  announcement_enabled: false,
  announcement_content: "",
  announcement_updated_at: null,
});
const ANNOUNCEMENT_DISMISS_KEY = "systemAnnouncementDismissState";

const avatarUrl = computed(() => getAvatarImageSrc(auth.user?.avatar_url || ""));
const avatarFallback = computed(() => auth.user?.username?.charAt(0)?.toUpperCase() || "U");
const announcementLooksLikeHtml = computed(() => contentLooksLikeHtml(announcementConfig.value.announcement_content));

function getTodayString() {
  return new Date().toLocaleDateString("en-CA");
}

function getAnnouncementVersion(config: AnnouncementConfig) {
  return config.announcement_updated_at || "";
}

function shouldSuppressAnnouncement(config: AnnouncementConfig) {
  try {
    const raw = localStorage.getItem(ANNOUNCEMENT_DISMISS_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw);
    return parsed?.date === getTodayString() && parsed?.version === getAnnouncementVersion(config);
  } catch {
    return false;
  }
}

function handleAnnouncementClose() {
  if (announcementDismissToday.value) {
    localStorage.setItem(ANNOUNCEMENT_DISMISS_KEY, JSON.stringify({
      date: getTodayString(),
      version: getAnnouncementVersion(announcementConfig.value),
    }));
  }
  announcementVisible.value = false;
}

async function checkAnnouncement() {
  try {
    const res = await getAnnouncementConfig();
    announcementConfig.value = res;
    if (!res.announcement_enabled || !res.announcement_content.trim() || shouldSuppressAnnouncement(res)) {
      return;
    }
    announcementDismissToday.value = false;
    announcementVisible.value = true;
  } catch {
    // ignore announcement config failures
  }
}

async function loadPaymentPlans() {
  if (!auth.isLoggedIn) return;
  purchasePlansLoading.value = true;
  try {
    const res = await listPaymentPlans();
    creditPurchasePlans.value = res.items;
    if (!res.items.some((item) => item.key === selectedPurchasePlanKey.value && item.purchasable)) {
      selectedPurchasePlanKey.value = "";
    }
    const firstPurchasablePlan = res.items.find((item) => item.purchasable);
    if (!selectedPurchasePlanKey.value && firstPurchasablePlan) {
      selectedPurchasePlanKey.value = firstPurchasablePlan.key;
    }
  } catch {
    creditPurchasePlans.value = [];
    selectedPurchasePlanKey.value = "";
  } finally {
    purchasePlansLoading.value = false;
  }
}

function handleSelectPurchasePlan(plan: PaymentPlan) {
  if (!plan.purchasable) return;
  selectedPurchasePlanKey.value = plan.key;
}

function resetPurchaseState() {
  purchaseLoading.value = false;
}

function getSuggestionFabSize() {
  if (typeof window === "undefined") return SUGGESTION_FAB_DESKTOP_SIZE;
  return window.innerWidth <= 920 ? SUGGESTION_FAB_MOBILE_SIZE : SUGGESTION_FAB_DESKTOP_SIZE;
}

function getSuggestionFabMinX() {
  const sideNav = desktopSideNavRef.value;
  if (!sideNav) return SUGGESTION_FAB_EDGE_GAP;
  const rect = sideNav.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return SUGGESTION_FAB_EDGE_GAP;
  return Math.max(SUGGESTION_FAB_EDGE_GAP, Math.round(rect.right));
}

function getSuggestionFabBounds() {
  const width = suggestionFabWrapRef.value?.offsetWidth || getSuggestionFabSize();
  const height = suggestionFabWrapRef.value?.offsetHeight || getSuggestionFabSize();
  const minX = getSuggestionFabMinX();
  return {
    width,
    height,
    minX,
    maxX: Math.max(minX, window.innerWidth - width - SUGGESTION_FAB_EDGE_GAP),
    maxY: Math.max(SUGGESTION_FAB_EDGE_GAP, window.innerHeight - height - SUGGESTION_FAB_EDGE_GAP),
  };
}

function clampSuggestionFabPosition(position: { x: number; y: number }) {
  if (typeof window === "undefined") return position;
  const { minX, maxX, maxY } = getSuggestionFabBounds();
  return {
    x: Math.min(Math.max(position.x, minX), maxX),
    y: Math.min(Math.max(position.y, SUGGESTION_FAB_EDGE_GAP), maxY),
  };
}

function snapSuggestionFabToNearbyEdge(position: { x: number; y: number }) {
  if (typeof window === "undefined") return position;
  const { minX, maxX, maxY } = getSuggestionFabBounds();
  let { x, y } = position;
  if (x <= minX + SUGGESTION_FAB_SNAP_THRESHOLD) x = minX;
  else if (x >= maxX - SUGGESTION_FAB_SNAP_THRESHOLD) x = maxX;
  if (y <= SUGGESTION_FAB_SNAP_THRESHOLD) y = SUGGESTION_FAB_EDGE_GAP;
  else if (y >= maxY - SUGGESTION_FAB_SNAP_THRESHOLD) y = maxY;
  return { x, y };
}

function migrateLegacySuggestionFabPosition(position: { x: number; y: number }) {
  if (typeof window === "undefined") return position;
  const { minX, maxX, maxY } = getSuggestionFabBounds();
  let { x, y } = position;
  if (x >= maxX - SUGGESTION_FAB_LEGACY_EDGE_GAP) x = maxX;
  if (x <= minX + SUGGESTION_FAB_LEGACY_EDGE_GAP) x = minX;
  if (y >= maxY - SUGGESTION_FAB_LEGACY_EDGE_GAP) y = maxY;
  if (y <= SUGGESTION_FAB_LEGACY_EDGE_GAP) y = SUGGESTION_FAB_EDGE_GAP;
  return { x, y };
}

function getDefaultSuggestionFabPosition() {
  if (typeof window === "undefined") {
    return { x: 0, y: 0 };
  }
  const { maxX, maxY } = getSuggestionFabBounds();
  return {
    x: maxX,
    y: maxY,
  };
}

function saveSuggestionFabPosition(position: { x: number; y: number }) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(SUGGESTION_FAB_POSITION_KEY, JSON.stringify(position));
  } catch {
    // ignore localStorage failures
  }
}

function restoreSuggestionFabPosition() {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SUGGESTION_FAB_POSITION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.x !== "number" || typeof parsed?.y !== "number") return null;
    return { x: parsed.x, y: parsed.y };
  } catch {
    return null;
  }
}

function syncSuggestionFabPosition() {
  if (suggestionFabPosition.value) {
    suggestionFabPosition.value = clampSuggestionFabPosition(suggestionFabPosition.value);
    return;
  }
  const storedPosition = restoreSuggestionFabPosition();
  const basePosition = storedPosition
    ? migrateLegacySuggestionFabPosition(storedPosition)
    : getDefaultSuggestionFabPosition();
  suggestionFabPosition.value = clampSuggestionFabPosition(basePosition);
}

function handleSuggestionFabPointerDown(event: PointerEvent) {
  if (event.button !== 0) return;
  syncSuggestionFabPosition();
  const currentPosition = suggestionFabPosition.value || getDefaultSuggestionFabPosition();
  suggestionFabDragState = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: currentPosition.x,
    originY: currentPosition.y,
    moved: false,
  };
  const currentTarget = event.currentTarget as HTMLElement | null;
  currentTarget?.setPointerCapture?.(event.pointerId);
  event.preventDefault();
}

function handleSuggestionFabPointerMove(event: PointerEvent) {
  if (!suggestionFabDragState || suggestionFabDragState.pointerId !== event.pointerId) return;
  const deltaX = event.clientX - suggestionFabDragState.startX;
  const deltaY = event.clientY - suggestionFabDragState.startY;
  if (Math.hypot(deltaX, deltaY) > 3) {
    suggestionFabDragState.moved = true;
  }
  suggestionFabPosition.value = clampSuggestionFabPosition({
    x: suggestionFabDragState.originX + deltaX,
    y: suggestionFabDragState.originY + deltaY,
  });
}

function handleSuggestionFabPointerUp(event: PointerEvent) {
  if (!suggestionFabDragState || suggestionFabDragState.pointerId !== event.pointerId) return;
  const moved = suggestionFabDragState.moved;
  if (suggestionFabPosition.value) {
    suggestionFabPosition.value = clampSuggestionFabPosition(
      snapSuggestionFabToNearbyEdge(suggestionFabPosition.value),
    );
    saveSuggestionFabPosition(suggestionFabPosition.value);
  }
  suggestionFabDragState = null;
  if (!moved) {
    openSuggestionEntry();
  }
}

function handleWindowResize() {
  syncSuggestionFabPosition();
}

watch(showDesktopSideNav, async () => {
  await nextTick();
  if (suggestionFabPosition.value) {
    suggestionFabPosition.value = clampSuggestionFabPosition(suggestionFabPosition.value);
  }
});

onMounted(async () => {
  unsubscribeAdminFeedbackCount = subscribeAdminUnresolvedFeedbackCount((count) => {
    adminUnresolvedFeedbackCount.value = count;
  });
  unsubscribeUserFeedbackCount = subscribeUserCompletedUnreadFeedbackCount((count) => {
    userCompletedUnreadFeedbackCount.value = count;
  });
  unsubscribeSystemMessageCount = subscribeUnreadSystemMessageCount((count) => {
    userUnreadSystemMessageCount.value = count;
  });
  unsubscribeAuthSessionExpired = subscribeAuthSessionExpired(handleAuthSessionExpired);
  unsubscribeAiAssistantDockTabEnabled = subscribeAiAssistantDockTabEnabled((enabled) => {
    aiAssistantDockTabEnabled.value = enabled;
  });
  unsubscribeTutorialDockTabEnabled = subscribeTutorialDockTabEnabled((enabled) => {
    tutorialDockTabEnabled.value = enabled;
  });

  if (typeof document !== "undefined") {
    themeObserver = new MutationObserver(() => {
      currentTheme.value = getCurrentTheme();
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: [APP_THEME_ATTRIBUTE],
    });
  }
  if (typeof window !== "undefined") {
    window.addEventListener("pointermove", handleSuggestionFabPointerMove);
    window.addEventListener("pointerup", handleSuggestionFabPointerUp);
    window.addEventListener("pointercancel", handleSuggestionFabPointerUp);
    window.addEventListener("resize", handleWindowResize);
  }
  await nextTick();
  syncSuggestionFabPosition();

  await Promise.allSettled([
    (async () => {
      const res = await getContactConfig();
      contactQrImage.value = res.contact_qr_image || "";
    })(),
    checkAnnouncement(),
    loadPaymentPlans(),
  ]);

  if (!auth.isLoggedIn) return;
  try {
    auth.updateUser(await getMe());
  } catch {
    // ignore sync failures for stale sessions
  }
  await syncAdminUnresolvedFeedbackCount();
  await syncUserCompletedUnreadFeedbackCount({ showToast: true, forceToast: true });
  await syncUserUnreadSystemMessageCount({ showToast: true, forceToast: true });
  startSystemMessagePolling();
});

onBeforeUnmount(() => {
  unsubscribeAdminFeedbackCount?.();
  unsubscribeAdminFeedbackCount = null;
  unsubscribeUserFeedbackCount?.();
  unsubscribeUserFeedbackCount = null;
  unsubscribeSystemMessageCount?.();
  unsubscribeSystemMessageCount = null;
  unsubscribeAuthSessionExpired?.();
  unsubscribeAuthSessionExpired = null;
  unsubscribeAiAssistantDockTabEnabled?.();
  unsubscribeAiAssistantDockTabEnabled = null;
  unsubscribeTutorialDockTabEnabled?.();
  unsubscribeTutorialDockTabEnabled = null;
  stopSystemMessagePolling();
  themeObserver?.disconnect();
  themeObserver = null;
  if (typeof window !== "undefined") {
    window.removeEventListener("pointermove", handleSuggestionFabPointerMove);
    window.removeEventListener("pointerup", handleSuggestionFabPointerUp);
    window.removeEventListener("pointercancel", handleSuggestionFabPointerUp);
    window.removeEventListener("resize", handleWindowResize);
  }
});

function openCreditsContact() {
  mobileDrawerOpen.value = false;
  creditsContactVisible.value = true;
}

provide("openCreditsContact", openCreditsContact);
provide("openPurchaseEntry", openPurchaseEntry);

function openRedeemEntry() {
  mobileDrawerOpen.value = false;
  if (!auth.isLoggedIn) {
    openAuthModal("login");
    return;
  }
  redeemDialogOpen.value = true;
}

function openInviteRewardsEntry() {
  mobileDrawerOpen.value = false;
  if (!auth.isLoggedIn) {
    openAuthModal("login");
    return;
  }
  router.push("/invite-rewards");
}

function openPurchaseEntry() {
  mobileDrawerOpen.value = false;
  if (!auth.isLoggedIn) {
    openAuthModal("login");
    return;
  }
  if (!creditPurchasePlans.value.length) {
    void loadPaymentPlans();
  }
  resetPurchaseState();
  purchaseDialogOpen.value = true;
}

function getDropdownPopupContainer() {
  return document.body;
}

async function handlePurchaseCredits() {
  const selectedPlan = creditPurchasePlans.value.find((item) => item.key === selectedPurchasePlanKey.value);
  if (!selectedPlan) return;
  purchaseLoading.value = true;
  const payWindow = window.open("", "_blank");
  try {
    const res = await createPaymentOrder(selectedPlan.key);
    if (payWindow) {
      payWindow.location.href = res.pay_url;
      purchaseDialogOpen.value = false;
      await router.push(
        `/payment-result?order_no=${encodeURIComponent(res.order_no)}&payment_token=${encodeURIComponent(res.result_token)}`
      );
      return;
    }
    window.location.href = res.pay_url;
  } catch (err: any) {
    payWindow?.close();
    message.error(err.response?.data?.detail || "创建支付订单失败");
  } finally {
    purchaseLoading.value = false;
  }
}

function openSuggestionEntry() {
  mobileDrawerOpen.value = false;
  if (!auth.isLoggedIn) {
    openAuthModal("login");
    return;
  }
  suggestionDialogOpen.value = true;
}

function openPurchaseFeedbackDialog() {
  purchaseFeedbackForm.content = "";
  purchaseFeedbackDialogOpen.value = true;
}

function closePurchaseFeedbackDialog() {
  purchaseFeedbackDialogOpen.value = false;
}

async function handleSubmitPurchaseFeedback() {
  const normalized = purchaseFeedbackForm.content.trim();
  if (!normalized) {
    message.warning("请输入反馈内容");
    return;
  }

  const selectedPlan = creditPurchasePlans.value.find((item) => item.key === selectedPurchasePlanKey.value);
  const planText = selectedPlan ? `当前套餐：¥${selectedPlan.display_amount} / ${selectedPlan.credits}积分` : "当前套餐：未选择";
  purchaseFeedbackSubmitting.value = true;
  try {
    await createFeedback(null, `【积分购买反馈】\n${planText}\n\n${normalized}`, {
      feedback_type: "purchase",
    });
    message.success("反馈已提交");
    closePurchaseFeedbackDialog();
  } catch (err: any) {
    message.error(err.response?.data?.detail || "提交反馈失败");
  } finally {
    purchaseFeedbackSubmitting.value = false;
  }
}

function openContactFromPurchaseFeedback() {
  purchaseFeedbackDialogOpen.value = false;
  openCreditsContact();
}

function goCreditLogs() {
  mobileDrawerOpen.value = false;
  router.push("/credit-logs");
}

function toggleMobileDrawer() {
  mobileDrawerOpen.value = !mobileDrawerOpen.value;
}

watch(
  () => route.fullPath,
  () => {
    mobileDrawerOpen.value = false;
  }
);

watch(
  shouldSyncUserNoticeCounts,
  (shouldSync) => {
    if (!shouldSync) {
      stopSystemMessagePolling();
      notification.close(USER_UNREAD_SYSTEM_MESSAGE_NOTIFICATION_KEY);
      return;
    }
    if (!auth.isLoggedIn) return;
    void syncUserUnreadSystemMessageCount({ showToast: true });
    startSystemMessagePolling();
  },
  { immediate: true }
);

watch(
  () => auth.isLoggedIn,
  (loggedIn) => {
    if (!loggedIn) {
      creditPurchasePlans.value = [];
      selectedPurchasePlanKey.value = "";
      return;
    }
    void loadPaymentPlans();
  }
);

watch(purchaseDialogOpen, (open) => {
  if (!open) {
    resetPurchaseState();
  }
});

watch(
  showSuggestionFab,
  async (visible) => {
    if (!visible) return;
    await nextTick();
    syncSuggestionFabPosition();
  }
);

</script>

<template>
  <a-layout class="app-layout" :class="{ 'app-layout-desktop-side-nav': showDesktopSideNav }">
    <a-layout-header v-if="!hideTopMenu" class="app-header">
      <div class="header-inner">
        <div class="header-brand-wrap">
          <div class="header-brand" @click="router.push('/')">
            <div class="brand-mark">
              <img src="/香蕉.svg" alt="80AI" class="brand-mark-image" />
            </div>
            <div class="brand-copy">
              <span class="brand-name">80AI</span>
              <span class="brand-sub">AI Creative Studio</span>
            </div>
          </div>
          <a-button
            v-if="!auth.isLoggedIn"
            type="text"
            class="top-link-btn"
            @click="openCreditsContact"
          >
            联系我们
          </a-button>
          <div v-if="auth.isLoggedIn && isAdmin" class="desktop-admin-entry">
            <a-dropdown :trigger="['hover']" overlay-class-name="warm-dropdown">
              <a-badge :count="adminUnresolvedFeedbackCount" :offset="ADMIN_BADGE_OFFSET" :show-zero="false">
                <a-button class="admin-btn" type="text">
                  <SettingOutlined />
                  管理后台
                  <DownOutlined style="font-size: 10px; margin-left: 4px" />
                </a-button>
              </a-badge>
              <template #overlay>
                <a-menu :selected-keys="adminSelectedKeys" @click="handleAdminMenu">
                  <a-sub-menu :key="ADMIN_TEMPLATE_MENU_KEY" popup-class-name="warm-dropdown">
                    <template #icon><PictureOutlined /></template>
                    <template #title>模版管理</template>
                    <a-menu-item
                      v-for="item in adminMenuTemplateItems"
                      :key="item.key"
                    >
                      <template #icon><component :is="item.icon" /></template>
                      {{ item.label }}
                    </a-menu-item>
                  </a-sub-menu>
                  <a-sub-menu :key="ADMIN_USER_DATA_MENU_KEY" popup-class-name="warm-dropdown">
                    <template #icon><TeamOutlined /></template>
                    <template #title>用户数据</template>
                    <a-menu-item
                      v-for="item in adminMenuUserDataItems"
                      :key="item.key"
                    >
                      <template #icon><component :is="item.icon" /></template>
                      {{ item.label }}
                    </a-menu-item>
                  </a-sub-menu>
                  <a-sub-menu :key="ADMIN_ANALYTICS_MENU_KEY" popup-class-name="warm-dropdown">
                    <template #icon><BarChartOutlined /></template>
                    <template #title>数据统计</template>
                    <a-menu-item
                      v-for="item in adminMenuAnalyticsItems"
                      :key="item.key"
                    >
                      <template #icon><component :is="item.icon" /></template>
                      {{ item.label }}
                    </a-menu-item>
                    <a-menu-divider />
                    <a-menu-item
                      v-for="item in adminMenuPromoDataItems"
                      :key="item.key"
                    >
                      <template #icon><component :is="item.icon" /></template>
                      {{ item.label }}
                    </a-menu-item>
                  </a-sub-menu>
                  <template v-if="adminMenuConfigItems.length">
                    <a-sub-menu :key="ADMIN_THIRD_PARTY_MENU_KEY" popup-class-name="warm-dropdown">
                      <template #icon><KeyOutlined /></template>
                      <template #title>第三方管理</template>
                      <a-menu-item
                        v-for="item in adminMenuConfigItems"
                        :key="item.key"
                      >
                        <template #icon><component :is="item.icon" /></template>
                        {{ item.label }}
                      </a-menu-item>
                    </a-sub-menu>
                  </template>
                  <a-menu-divider />
                  <a-menu-item
                    v-for="item in adminMenuBusinessItems"
                    :key="item.key"
                  >
                    <template #icon><component :is="item.icon" /></template>
                    {{ item.label }}
                  </a-menu-item>
                  <template v-if="adminMenuFundItems.length">
                    <a-sub-menu :key="ADMIN_FUNDS_MENU_KEY" popup-class-name="warm-dropdown">
                      <template #icon><AccountBookOutlined /></template>
                      <template #title>资金</template>
                      <a-menu-item
                        v-for="item in adminMenuFundItems"
                        :key="item.key"
                      >
                        <template #icon><component :is="item.icon" /></template>
                        {{ item.label }}
                      </a-menu-item>
                    </a-sub-menu>
                  </template>
                  <a-menu-divider />
                  <a-sub-menu :key="ADMIN_NOTICE_MENU_KEY" popup-class-name="warm-dropdown">
                    <template #icon><BellOutlined /></template>
                    <template #title>通知中心</template>
                    <a-menu-item
                      v-for="item in adminMenuNoticeItems"
                      :key="item.key"
                      :class="{ 'admin-feedback-dropdown-item': item.key === '/admin/feedbacks' }"
                    >
                      <template #icon><component :is="item.icon" /></template>
                      <span v-if="item.key === '/admin/feedbacks'" class="admin-menu-feedback-label">
                        <span>{{ item.label }}</span>
                        <a-badge
                          v-if="hasAdminUnresolvedFeedback"
                          :count="adminUnresolvedFeedbackCount"
                          :number-style="{ backgroundColor: '#ff4d4f', color: '#fff' }"
                        />
                      </span>
                      <template v-else>{{ item.label }}</template>
                    </a-menu-item>
                  </a-sub-menu>
                  <template v-if="adminMenuBaseItems.length">
                    <a-menu-divider />
                    <a-menu-item
                      v-for="item in adminMenuBaseItems"
                      :key="item.key"
                    >
                      <template #icon><component :is="item.icon" /></template>
                      {{ item.label }}
                    </a-menu-item>
                  </template>
                </a-menu>
              </template>
            </a-dropdown>
          </div>
        </div>

        <div class="mobile-nav-entry">
          <div v-if="auth.isLoggedIn" class="mobile-nav-credits" @click="goCreditLogs">
            <ThunderboltOutlined />
            <span>{{ auth.user?.credits ?? 0 }}</span>
          </div>
          <a-button class="mobile-nav-fab" type="primary" shape="circle" @click="toggleMobileDrawer">
            <template #icon><MenuOutlined /></template>
          </a-button>
        </div>

        <a-menu
          :key="primaryMenuItems.map((item) => item.key).join('-')"
          mode="horizontal"
          :disabled-overflow="true"
          :selected-keys="selectedKeys"
          class="header-menu"
          @click="handleMenuClick"
        >
          <template v-for="item in primaryMenuItems" :key="item.key">
            <a-sub-menu v-if="item.key === 'more'" key="more" popup-class-name="warm-dropdown">
              <template #icon>
                <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
                <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
              </template>
              <template #title>{{ item.label }}</template>
              <a-menu-item v-for="subItem in moreFeatureMenuItems" :key="subItem.key">
                <template #icon><component :is="subItem.icon" /></template>
                {{ subItem.label }}
              </a-menu-item>
            </a-sub-menu>
            <a-sub-menu v-else-if="item.key === 'video-generate'" key="video-generate" popup-class-name="warm-dropdown">
              <template #icon>
                <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
                <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
              </template>
              <template #title>{{ item.label }}</template>
              <a-menu-item v-for="subItem in videoEntryMenuItems" :key="subItem.key">
                <template #icon><component :is="subItem.icon" /></template>
                {{ subItem.label }}
              </a-menu-item>
            </a-sub-menu>
            <a-menu-item v-else :key="item.key">
              <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
              <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
              <span>{{ item.label }}</span>
            </a-menu-item>
          </template>
        </a-menu>

        <div class="header-actions">
          <a-button type="text" class="top-link-btn" @click="openPurchaseEntry">
            <span class="purchase-credit-content">
              <PayCircleFilled class="purchase-credit-icon" />
              <span>购买积分</span>
            </span>
          </a-button>
          <a-button type="text" class="top-link-btn" @click="openRedeemEntry">
            兑换积分
          </a-button>
          <a-button type="text" class="top-link-btn" @click="openInviteRewardsEntry">
            <template #icon><ShareAltOutlined /></template>
            <span>邀请奖励</span>
            <span v-if="INVITE_REWARDS_BADGE_TEXT" class="nav-menu-new-badge">{{ INVITE_REWARDS_BADGE_TEXT }}</span>
          </a-button>
          <template v-if="auth.isLoggedIn">
            <div class="credits-badge" @click="goCreditLogs">
              <ThunderboltOutlined />
              <span>{{ auth.user?.credits ?? 0 }}</span>
            </div>

            <a-dropdown :trigger="['hover']" overlay-class-name="warm-dropdown">
              <a-badge
                dot
                :offset="[-2, 6]"
                :show-zero="false"
                :count="hasUserUnreadNotice ? 1 : 0"
                :dot-style="{ width: '12px', height: '12px', minWidth: '12px', boxShadow: '0 0 0 2px #fffdf8' }"
              >
                <div class="user-trigger">
                  <a-avatar :size="34" class="user-avatar" :src="avatarUrl || undefined">
                    {{ avatarFallback }}
                  </a-avatar>
                  <span class="user-name">{{ auth.user?.username }}</span>
                </div>
              </a-badge>
              <template #overlay>
                <a-menu @click="handleUserMenu">
                  <a-menu-item
                    v-for="item in userMenuAccountItems"
                    :key="item.key"
                  >
                    <component :is="item.icon" />
                    <span style="margin-left: 8px">{{ item.label }}</span>
                  </a-menu-item>
                  <a-menu-divider />
                  <a-sub-menu key="user-notice-submenu" popup-class-name="warm-dropdown">
                    <template #icon><BellOutlined /></template>
                    <template #title>通知中心</template>
                    <a-menu-item
                      v-for="item in userMenuNoticeItems"
                      :key="item.key"
                      class="user-feedback-dropdown-item"
                    >
                      <template #icon><component :is="item.icon" /></template>
                      <span v-if="item.key === 'my-feedback'" class="user-menu-feedback-label">
                        <span>{{ item.label }}</span>
                        <a-badge
                          v-if="hasUserUnreadFeedback"
                          dot
                          :dot-style="{ width: '10px', height: '10px', minWidth: '10px' }"
                        />
                      </span>
                      <span v-else-if="item.key === 'system-messages'" class="user-menu-feedback-label">
                        <span>{{ item.label }}</span>
                        <a-badge
                          v-if="hasUserUnreadSystemMessage"
                          dot
                          :dot-style="{ width: '10px', height: '10px', minWidth: '10px' }"
                        />
                      </span>
                      <span v-else-if="item.key === 'update-logs'">{{ item.label }}</span>
                      <span v-else>{{ item.label }}</span>
                    </a-menu-item>
                  </a-sub-menu>
                  <a-menu-item key="theme-style-entry" class="theme-style-menu-item">
                    <template #icon><BgColorsOutlined /></template>
                    <ThemeStyleMenuEntry :current-theme="currentTheme" />
                  </a-menu-item>
                  <a-menu-item
                    v-for="item in userMenuSettingsItems"
                    :key="item.key"
                  >
                    <component :is="item.icon" />
                    <span style="margin-left: 8px">{{ item.label }}</span>
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item
                    v-for="item in userMenuDangerItems"
                    :key="item.key"
                    danger
                  >
                    <component :is="item.icon" />
                    <span style="margin-left: 8px">{{ item.label }}</span>
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>

          <template v-else>
            <a-button type="primary" class="login-header-btn" @click="openAuthModal('login')">
              <template #icon><UserOutlined /></template>
              登录
            </a-button>
            <a-button class="register-header-btn" @click="openAuthModal('register')">
              <template #icon><UserAddOutlined /></template>
              注册
            </a-button>
          </template>
        </div>
      </div>
    </a-layout-header>

    <aside v-if="showDesktopSideNav" ref="desktopSideNavRef" class="canvas-side-nav" aria-label="全局导航">
      <div class="canvas-side-brand-wrap">
        <button type="button" class="canvas-side-brand" title="返回首页" @click="router.push('/')">
          <img src="/香蕉.svg" alt="80AI" class="brand-mark-image" />
        </button>
        <span class="canvas-side-brand-name">80AI</span>
      </div>
      <nav class="canvas-side-nav-menu">
        <template v-for="item in primaryMenuItems" :key="item.key">
          <a-dropdown
            v-if="item.key === 'generate'"
            :trigger="['hover']"
            placement="rightTop"
            :auto-adjust-overflow="false"
            :align="{ offset: [16, 0], overflow: { adjustX: false, adjustY: false } }"
            :get-popup-container="getDropdownPopupContainer"
            overlay-class-name="warm-dropdown"
          >
            <button
              type="button"
              class="canvas-side-nav-item"
              :class="{ active: selectedKeys.includes(item.key) }"
              @click="handleMenuClick({ key: item.key })"
            >
              <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
              <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
              <span>{{ item.label }}</span>
              <span v-if="item.badgeText" class="nav-menu-new-badge">{{ item.badgeText }}</span>
            </button>
            <template #overlay>
              <a-menu :selected-keys="[activeGenerateEntryMode]" @click="handleGenerateEntryMenu">
                <a-menu-item v-for="subItem in generateEntryPrimaryMenuItems" :key="subItem.key">
                  <template #icon><component :is="subItem.icon" /></template>
                  {{ subItem.label }}
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item v-for="subItem in generateEntryToolMenuItems" :key="subItem.key">
                  <template #icon><component :is="subItem.icon" /></template>
                  {{ subItem.label }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
          <a-dropdown
            v-else-if="item.key === 'video-generate'"
            :trigger="['hover']"
            placement="rightTop"
            :auto-adjust-overflow="false"
            :align="{ offset: [16, 0], overflow: { adjustX: false, adjustY: false } }"
            :get-popup-container="getDropdownPopupContainer"
            overlay-class-name="warm-dropdown"
          >
            <button
              type="button"
              class="canvas-side-nav-item"
              :class="{ active: selectedKeys.includes(item.key) }"
              @click="handleMenuClick({ key: item.key })"
            >
              <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
              <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
              <span>{{ item.label }}</span>
              <span v-if="item.badgeText" class="nav-menu-new-badge">{{ item.badgeText }}</span>
            </button>
            <template #overlay>
              <a-menu
                :selected-keys="activeVideoEntryMenuKey ? [activeVideoEntryMenuKey] : []"
                @click="handleVideoEntryMenu"
              >
                <a-menu-item v-for="subItem in videoEntryMenuItems" :key="subItem.key">
                  <template #icon><component :is="subItem.icon" /></template>
                  {{ subItem.label }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
          <a-dropdown
            v-else-if="item.key === 'more'"
            :trigger="['hover']"
            placement="rightTop"
            :auto-adjust-overflow="false"
            :align="{ offset: [16, 0], overflow: { adjustX: false, adjustY: false } }"
            :get-popup-container="getDropdownPopupContainer"
            overlay-class-name="warm-dropdown"
          >
            <button
              type="button"
              class="canvas-side-nav-item"
              :class="{ active: selectedKeys.includes(item.key) }"
            >
              <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
              <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
              <span>{{ item.label }}</span>
            </button>
            <template #overlay>
              <a-menu :selected-keys="activeMoreFeatureKey ? [activeMoreFeatureKey] : []" @click="handleMoreFeatureMenu">
                <a-menu-item v-for="subItem in moreFeatureMenuItems" :key="subItem.key">
                  <template #icon><component :is="subItem.icon" /></template>
                  {{ subItem.label }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
          <button
            v-else
            type="button"
            class="canvas-side-nav-item"
            :class="{ active: selectedKeys.includes(item.key) }"
            @click="handleMenuClick({ key: item.key })"
          >
            <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
            <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
            <span>{{ item.label }}</span>
            <span v-if="item.badgeText" class="nav-menu-new-badge">{{ item.badgeText }}</span>
          </button>
        </template>
      </nav>

      <div class="canvas-side-nav-actions">
        <button type="button" class="canvas-side-nav-item canvas-side-nav-action" @click="openPurchaseEntry">
          <PayCircleFilled />
          <span>购买积分</span>
        </button>
        <button type="button" class="canvas-side-nav-item canvas-side-nav-action" @click="openRedeemEntry">
          <GiftOutlined />
          <span>兑换积分</span>
        </button>
        <button type="button" class="canvas-side-nav-item canvas-side-nav-action" @click="openInviteRewardsEntry">
          <ShareAltOutlined />
          <span>邀请奖励</span>
          <span v-if="INVITE_REWARDS_BADGE_TEXT" class="nav-menu-new-badge">{{ INVITE_REWARDS_BADGE_TEXT }}</span>
        </button>
        <template v-if="!auth.isLoggedIn">
          <span class="canvas-side-nav-divider"></span>
          <button type="button" class="canvas-side-nav-item canvas-side-nav-action" @click="openCreditsContact">
            <CustomerServiceOutlined />
            <span>联系我们</span>
          </button>
        </template>

        <a-dropdown
          v-if="auth.isLoggedIn && isAdmin"
          :trigger="['hover']"
          placement="rightBottom"
          :auto-adjust-overflow="false"
          :align="{ offset: [12, 0], overflow: { adjustX: false, adjustY: false } }"
          :get-popup-container="getDropdownPopupContainer"
          overlay-class-name="warm-dropdown"
        >
          <a-badge :count="adminUnresolvedFeedbackCount" :offset="ADMIN_BADGE_OFFSET" :show-zero="false">
            <button type="button" class="canvas-side-nav-item canvas-side-nav-action">
              <SettingOutlined />
              <span>后台管理</span>
            </button>
          </a-badge>
          <template #overlay>
            <a-menu :selected-keys="adminSelectedKeys" @click="handleAdminMenu">
              <a-sub-menu :key="ADMIN_TEMPLATE_MENU_KEY" popup-class-name="warm-dropdown">
                <template #icon><PictureOutlined /></template>
                <template #title>模版管理</template>
                <a-menu-item v-for="item in adminMenuTemplateItems" :key="item.key">
                  <template #icon><component :is="item.icon" /></template>
                  {{ item.label }}
                </a-menu-item>
              </a-sub-menu>
              <a-sub-menu :key="ADMIN_USER_DATA_MENU_KEY" popup-class-name="warm-dropdown">
                <template #icon><TeamOutlined /></template>
                <template #title>用户数据</template>
                <a-menu-item v-for="item in adminMenuUserDataItems" :key="item.key">
                  <template #icon><component :is="item.icon" /></template>
                  {{ item.label }}
                </a-menu-item>
              </a-sub-menu>
              <a-sub-menu :key="ADMIN_ANALYTICS_MENU_KEY" popup-class-name="warm-dropdown">
                <template #icon><BarChartOutlined /></template>
                <template #title>数据统计</template>
                <a-menu-item v-for="item in adminMenuAnalyticsItems" :key="item.key">
                  <template #icon><component :is="item.icon" /></template>
                  {{ item.label }}
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item v-for="item in adminMenuPromoDataItems" :key="item.key">
                  <template #icon><component :is="item.icon" /></template>
                  {{ item.label }}
                </a-menu-item>
              </a-sub-menu>
              <template v-if="adminMenuConfigItems.length">
                <a-sub-menu :key="ADMIN_THIRD_PARTY_MENU_KEY" popup-class-name="warm-dropdown">
                  <template #icon><KeyOutlined /></template>
                  <template #title>第三方管理</template>
                  <a-menu-item v-for="item in adminMenuConfigItems" :key="item.key">
                    <template #icon><component :is="item.icon" /></template>
                    {{ item.label }}
                  </a-menu-item>
                </a-sub-menu>
              </template>
              <a-menu-divider />
              <a-menu-item v-for="item in adminMenuBusinessItems" :key="item.key">
                <template #icon><component :is="item.icon" /></template>
                {{ item.label }}
              </a-menu-item>
              <template v-if="adminMenuFundItems.length">
                <a-sub-menu :key="ADMIN_FUNDS_MENU_KEY" popup-class-name="warm-dropdown">
                  <template #icon><AccountBookOutlined /></template>
                  <template #title>资金</template>
                  <a-menu-item v-for="item in adminMenuFundItems" :key="item.key">
                    <template #icon><component :is="item.icon" /></template>
                    {{ item.label }}
                  </a-menu-item>
                </a-sub-menu>
              </template>
              <a-menu-divider />
              <a-sub-menu :key="ADMIN_NOTICE_MENU_KEY" popup-class-name="warm-dropdown">
                <template #icon><BellOutlined /></template>
                <template #title>通知中心</template>
                <a-menu-item
                  v-for="item in adminMenuNoticeItems"
                  :key="item.key"
                  :class="{ 'admin-feedback-dropdown-item': item.key === '/admin/feedbacks' }"
                >
                  <template #icon><component :is="item.icon" /></template>
                  <span v-if="item.key === '/admin/feedbacks'" class="admin-menu-feedback-label">
                    <span>{{ item.label }}</span>
                    <a-badge
                      v-if="hasAdminUnresolvedFeedback"
                      :count="adminUnresolvedFeedbackCount"
                      :number-style="{ backgroundColor: '#ff4d4f', color: '#fff' }"
                    />
                  </span>
                  <template v-else>{{ item.label }}</template>
                </a-menu-item>
              </a-sub-menu>
              <template v-if="adminMenuBaseItems.length">
                <a-menu-divider />
                <a-menu-item v-for="item in adminMenuBaseItems" :key="item.key">
                  <template #icon><component :is="item.icon" /></template>
                  {{ item.label }}
                </a-menu-item>
              </template>
            </a-menu>
          </template>
        </a-dropdown>
      </div>

      <div class="canvas-side-nav-footer">
        <button v-if="auth.isLoggedIn" type="button" class="canvas-side-credit-pill" title="购买积分" @click="openPurchaseEntry">
          <ThunderboltOutlined />
          <span>{{ auth.user?.credits ?? 0 }}</span>
        </button>

        <a-dropdown
          v-if="auth.isLoggedIn"
          :trigger="['hover']"
          placement="rightBottom"
          :auto-adjust-overflow="false"
          :align="{ offset: [12, 0], overflow: { adjustX: false, adjustY: false } }"
          :get-popup-container="getDropdownPopupContainer"
          overlay-class-name="warm-dropdown"
        >
          <a-badge
            dot
            :offset="[-2, 6]"
            :show-zero="false"
            :count="hasUserUnreadNotice ? 1 : 0"
            :dot-style="{ width: '12px', height: '12px', minWidth: '12px', boxShadow: '0 0 0 2px #fffdf8' }"
          >
            <button type="button" class="canvas-side-user-trigger" title="账户菜单">
              <a-avatar :size="44" class="user-avatar" :src="avatarUrl || undefined">
                {{ avatarFallback }}
              </a-avatar>
            </button>
          </a-badge>
          <template #overlay>
            <a-menu @click="handleUserMenu">
              <div class="canvas-side-user-menu-header">
                <span class="canvas-side-user-menu-name">{{ auth.user?.username }}</span>
                <span class="canvas-side-user-menu-role">
                  {{ isSuperAdmin ? "超级管理员" : isAdmin ? "管理员" : "积分用户" }}
                </span>
              </div>
              <a-menu-divider />
              <a-menu-item v-for="item in userMenuAccountItems" :key="item.key">
                <component :is="item.icon" />
                <span style="margin-left: 8px">{{ item.label }}</span>
              </a-menu-item>
              <a-menu-divider />
              <a-sub-menu key="canvas-user-notice-submenu" popup-class-name="warm-dropdown">
                <template #icon><BellOutlined /></template>
                <template #title>通知中心</template>
                <a-menu-item v-for="item in userMenuNoticeItems" :key="item.key" class="user-feedback-dropdown-item">
                  <template #icon><component :is="item.icon" /></template>
                  <span v-if="item.key === 'my-feedback'" class="user-menu-feedback-label">
                    <span>{{ item.label }}</span>
                    <a-badge v-if="hasUserUnreadFeedback" dot :dot-style="{ width: '10px', height: '10px', minWidth: '10px' }" />
                  </span>
                  <span v-else-if="item.key === 'system-messages'" class="user-menu-feedback-label">
                    <span>{{ item.label }}</span>
                    <a-badge v-if="hasUserUnreadSystemMessage" dot :dot-style="{ width: '10px', height: '10px', minWidth: '10px' }" />
                  </span>
                  <span v-else-if="item.key === 'update-logs'">{{ item.label }}</span>
                  <span v-else>{{ item.label }}</span>
                </a-menu-item>
              </a-sub-menu>
              <a-menu-item key="theme-style-entry" class="theme-style-menu-item">
                <template #icon><BgColorsOutlined /></template>
                <ThemeStyleMenuEntry :current-theme="currentTheme" />
              </a-menu-item>
              <a-menu-item v-for="item in userMenuSettingsItems" :key="item.key">
                <component :is="item.icon" />
                <span style="margin-left: 8px">{{ item.label }}</span>
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item v-for="item in userMenuDangerItems" :key="item.key" danger>
                <component :is="item.icon" />
                <span style="margin-left: 8px">{{ item.label }}</span>
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>

        <button v-else type="button" class="canvas-side-nav-item canvas-side-nav-action" @click="openAuthModal('login')">
          <UserOutlined />
          <span>登录</span>
        </button>
      </div>
    </aside>

    <a-layout-content
      class="app-content"
      :class="{
        'app-content-workbench': isWorkbenchLayout,
        'app-content-desktop-side-nav': showDesktopSideNav,
      }"
    >
      <div class="content-inner">
        <router-view v-slot="{ Component, route: currentRoute }">
          <transition :name="routeTransitionName" mode="out-in">
            <div :key="getRoutePageKey(currentRoute)" class="route-page-shell">
              <component :is="Component" />
            </div>
          </transition>
        </router-view>
      </div>
    </a-layout-content>

    <a-drawer
      v-if="!hideTopMenu"
      v-model:open="mobileDrawerOpen"
      placement="right"
      :width="320"
      root-class-name="mobile-nav-drawer"
      class="mobile-nav-drawer"
      title="导航菜单"
    >
      <div class="mobile-drawer-content">
        <div class="mobile-drawer-brand">
          <div class="mobile-drawer-brand-main">
            <div class="brand-mark">
              <img src="/香蕉.svg" alt="80AI" class="brand-mark-image" />
            </div>
            <div class="brand-copy">
              <span class="brand-name">80AI</span>
              <span class="brand-sub">AI Creative Studio</span>
            </div>
          </div>
        </div>

        <div v-if="auth.isLoggedIn" class="mobile-user-card">
          <a-avatar :size="48" class="user-avatar" :src="avatarUrl || undefined">
            {{ avatarFallback }}
          </a-avatar>
          <div class="mobile-user-meta">
            <span class="mobile-user-name">{{ auth.user?.username }}</span>
            <span class="mobile-user-role">
              {{ isSuperAdmin ? "超级管理员" : isAdmin ? "管理员" : "普通用户" }}
            </span>
          </div>
          <div class="mobile-user-actions">
            <div class="mobile-user-credits" @click="goCreditLogs">
              <ThunderboltOutlined />
              <span>{{ auth.user?.credits ?? 0 }}</span>
            </div>
          </div>
        </div>

        <div class="mobile-drawer-section">
          <div class="mobile-drawer-section-title">功能导航</div>
          <a-menu
            mode="inline"
            :selected-keys="selectedKeys"
            class="mobile-drawer-menu"
            @click="handleMenuClick"
          >
            <template v-for="item in primaryMenuItems" :key="item.key">
              <a-sub-menu v-if="item.key === 'more'" key="more">
                <template #icon>
                  <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
                  <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
                </template>
                <template #title>{{ item.label }}</template>
                <a-menu-item v-for="subItem in moreFeatureMenuItems" :key="subItem.key">
                  <template #icon><component :is="subItem.icon" /></template>
                  {{ subItem.label }}
                </a-menu-item>
              </a-sub-menu>
              <a-sub-menu v-else-if="item.key === 'generate'" key="generate">
                <template #icon>
                  <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
                  <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
                </template>
                <template #title>{{ item.label }}</template>
                <a-menu-item v-for="subItem in generateEntryPrimaryMenuItems" :key="subItem.key">
                  <template #icon><component :is="subItem.icon" /></template>
                  {{ subItem.label }}
                </a-menu-item>
                <a-menu-item v-for="subItem in generateEntryToolMenuItems" :key="subItem.key">
                  <template #icon><component :is="subItem.icon" /></template>
                  {{ subItem.label }}
                </a-menu-item>
              </a-sub-menu>
              <a-sub-menu v-else-if="item.key === 'video-generate'" key="video-generate">
                <template #icon>
                  <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
                  <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
                </template>
                <template #title>{{ item.label }}</template>
                <a-menu-item v-for="subItem in videoEntryMenuItems" :key="subItem.key">
                  <template #icon><component :is="subItem.icon" /></template>
                  {{ subItem.label }}
                </a-menu-item>
              </a-sub-menu>
              <a-menu-item v-else :key="item.key">
                <template #icon>
                  <component v-if="item.icon" :is="item.icon" class="nav-menu-system-icon" />
                  <img v-else :src="getPrimaryMenuIconSrc(item)" :alt="item.label" class="nav-menu-icon" />
                </template>
                <span>{{ item.label }}</span>
                <span v-if="item.badgeText" class="nav-menu-new-badge nav-menu-new-badge-mobile">{{ item.badgeText }}</span>
              </a-menu-item>
            </template>
          </a-menu>
        </div>

        <div class="mobile-drawer-section">
          <div class="mobile-drawer-section-title">积分服务</div>
          <div class="mobile-drawer-credit-actions">
            <a-button block class="mobile-drawer-action-btn" @click="openPurchaseEntry">
              <span class="purchase-credit-content">
                <PayCircleFilled class="purchase-credit-icon" />
                <span>购买积分</span>
              </span>
            </a-button>
            <a-button block class="mobile-drawer-action-btn" @click="openRedeemEntry">
              <template #icon><GiftOutlined /></template>
              兑换积分
            </a-button>
            <a-button block class="mobile-drawer-action-btn" @click="openInviteRewardsEntry">
              <template #icon><ShareAltOutlined /></template>
              <span>邀请奖励</span>
              <span v-if="INVITE_REWARDS_BADGE_TEXT" class="nav-menu-new-badge nav-menu-new-badge-mobile">{{ INVITE_REWARDS_BADGE_TEXT }}</span>
            </a-button>
          </div>
        </div>

        <div v-if="auth.isLoggedIn && isAdmin" class="mobile-drawer-section">
          <div class="mobile-drawer-section-title">
            <span>管理后台</span>
            <a-badge
              v-if="hasAdminUnresolvedFeedback"
              :count="adminUnresolvedFeedbackCount"
              :number-style="{ backgroundColor: '#ff4d4f', color: '#fff' }"
            />
          </div>
          <a-menu
            mode="inline"
            :selected-keys="adminSelectedKeys"
            :open-keys="adminMenuOpenKeys"
            class="mobile-drawer-menu"
            @openChange="handleAdminMenuOpenChange"
            @click="handleAdminMenu"
          >
            <a-sub-menu :key="ADMIN_TEMPLATE_MENU_KEY">
              <template #icon><PictureOutlined /></template>
              <template #title>模版管理</template>
              <a-menu-item v-for="item in adminMenuTemplateItems" :key="item.key">
                <template #icon><component :is="item.icon" /></template>
                {{ item.label }}
              </a-menu-item>
            </a-sub-menu>
            <a-sub-menu :key="ADMIN_USER_DATA_MENU_KEY">
              <template #icon><TeamOutlined /></template>
              <template #title>用户数据</template>
              <a-menu-item v-for="item in adminMenuUserDataItems" :key="item.key">
                <template #icon><component :is="item.icon" /></template>
                {{ item.label }}
              </a-menu-item>
            </a-sub-menu>
            <a-sub-menu :key="ADMIN_ANALYTICS_MENU_KEY">
              <template #icon><BarChartOutlined /></template>
              <template #title>数据统计</template>
              <a-menu-item v-for="item in adminMenuAnalyticsItems" :key="item.key">
                <template #icon><component :is="item.icon" /></template>
                {{ item.label }}
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item v-for="item in adminMenuPromoDataItems" :key="item.key">
                <template #icon><component :is="item.icon" /></template>
                {{ item.label }}
              </a-menu-item>
            </a-sub-menu>
            <template v-if="adminMenuConfigItems.length">
              <a-sub-menu :key="ADMIN_THIRD_PARTY_MENU_KEY">
                <template #icon><KeyOutlined /></template>
                <template #title>第三方管理</template>
                <a-menu-item v-for="item in adminMenuConfigItems" :key="item.key">
                  <template #icon><component :is="item.icon" /></template>
                  {{ item.label }}
                </a-menu-item>
              </a-sub-menu>
            </template>
            <a-menu-divider />
            <a-menu-item v-for="item in adminMenuBusinessItems" :key="item.key">
              <template #icon><component :is="item.icon" /></template>
              {{ item.label }}
            </a-menu-item>
            <template v-if="adminMenuFundItems.length">
              <a-sub-menu :key="ADMIN_FUNDS_MENU_KEY">
                <template #icon><AccountBookOutlined /></template>
                <template #title>资金</template>
                <a-menu-item v-for="item in adminMenuFundItems" :key="item.key">
                  <template #icon><component :is="item.icon" /></template>
                  {{ item.label }}
                </a-menu-item>
              </a-sub-menu>
            </template>
            <a-menu-divider />
            <a-sub-menu :key="ADMIN_NOTICE_MENU_KEY">
              <template #icon><BellOutlined /></template>
              <template #title>通知中心</template>
              <a-menu-item v-for="item in adminMenuNoticeItems" :key="item.key">
                <template #icon><component :is="item.icon" /></template>
                <span v-if="item.key === '/admin/feedbacks'" class="admin-menu-feedback-label">
                  <span>{{ item.label }}</span>
                  <a-badge
                    v-if="hasAdminUnresolvedFeedback"
                    :count="adminUnresolvedFeedbackCount"
                    :number-style="{ backgroundColor: '#ff4d4f', color: '#fff' }"
                  />
                </span>
                <template v-else>{{ item.label }}</template>
              </a-menu-item>
            </a-sub-menu>
            <template v-if="adminMenuBaseItems.length">
              <a-menu-divider />
              <a-menu-item v-for="item in adminMenuBaseItems" :key="item.key">
                <template #icon><component :is="item.icon" /></template>
                {{ item.label }}
              </a-menu-item>
            </template>
          </a-menu>
        </div>

        <div class="mobile-drawer-section">
          <div class="mobile-drawer-section-title">
            {{ auth.isLoggedIn ? "账户操作" : "账户入口" }}
          </div>

          <div v-if="auth.isLoggedIn">
            <a-menu mode="inline" class="mobile-drawer-menu" @click="handleUserMenu">
              <a-menu-item
                v-for="item in userMenuAccountItems"
                :key="item.key"
              >
                <component :is="item.icon" />
                <span>{{ item.label }}</span>
              </a-menu-item>
              <a-menu-divider />
              <a-sub-menu key="mobile-user-notice-submenu">
                <template #icon><BellOutlined /></template>
                <template #title>通知中心</template>
                <a-menu-item
                  v-for="item in userMenuNoticeItems"
                  :key="item.key"
                >
                  <template #icon><component :is="item.icon" /></template>
                  <span v-if="item.key === 'my-feedback'" class="user-menu-feedback-label">
                    <span>{{ item.label }}</span>
                    <a-badge
                      v-if="hasUserUnreadFeedback"
                      dot
                      :dot-style="{ width: '10px', height: '10px', minWidth: '10px' }"
                    />
                  </span>
                  <span v-else-if="item.key === 'system-messages'" class="user-menu-feedback-label">
                    <span>{{ item.label }}</span>
                    <a-badge
                      v-if="hasUserUnreadSystemMessage"
                      dot
                      :dot-style="{ width: '10px', height: '10px', minWidth: '10px' }"
                    />
                  </span>
                  <span v-else-if="item.key === 'update-logs'">{{ item.label }}</span>
                  <span v-else>{{ item.label }}</span>
                </a-menu-item>
              </a-sub-menu>
              <a-sub-menu key="mobile-user-theme-submenu">
                <template #icon><BgColorsOutlined /></template>
                <template #title>主题风格</template>
                <a-menu-item-group
                  v-for="group in themeMenuGroups"
                  :key="`mobile-theme-group-${group.key}`"
                  :title="group.label"
                >
                  <a-menu-item
                    v-for="option in group.themes"
                    :key="`theme:${option.key}`"
                    class="mobile-theme-menu-item"
                  >
                    <span class="theme-menu-item-title">
                      <span>{{ option.label }}</span>
                      <CheckOutlined v-if="currentTheme === option.key" class="theme-menu-check" />
                    </span>
                    <div class="theme-menu-swatches-inline">
                      <span
                        v-for="swatch in option.palette"
                        :key="swatch.label"
                        class="theme-menu-swatch-chip-inline"
                        :style="{ background: swatch.color }"
                        :title="swatch.label"
                      />
                    </div>
                  </a-menu-item>
                </a-menu-item-group>
              </a-sub-menu>
              <a-menu-item
                v-for="item in userMenuSettingsItems"
                :key="item.key"
              >
                <component :is="item.icon" />
                <span>{{ item.label }}</span>
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item
                v-for="item in userMenuDangerItems"
                :key="item.key"
                danger
              >
                <component :is="item.icon" />
                <span>{{ item.label }}</span>
              </a-menu-item>
            </a-menu>
          </div>
          <div v-else class="mobile-auth-actions">
            <a-button block class="mobile-drawer-guest-contact" @click="openCreditsContact">
              <template #icon><CustomerServiceOutlined /></template>
              联系我们
            </a-button>
            <a-button type="primary" class="login-header-btn" block @click="openAuthModal('login')">
              <template #icon><UserOutlined /></template>
              登录
            </a-button>
            <a-button class="register-header-btn" block @click="openAuthModal('register')">
              <template #icon><UserAddOutlined /></template>
              注册
            </a-button>
          </div>
        </div>
      </div>
    </a-drawer>

    <div
      v-if="showSuggestionFab"
      ref="suggestionFabWrapRef"
      class="suggestion-fab-wrap"
      :style="suggestionFabWrapStyle"
      @pointerdown="handleSuggestionFabPointerDown"
    >
      <a-tooltip title="提交建议" :placement="suggestionFabTooltipPlacement">
        <button type="button" class="suggestion-fab" aria-label="提交建议">
          <MessageOutlined />
        </button>
      </a-tooltip>
    </div>

    <AiAssistantDock v-if="showAiAssistantDock" />
    <GenerateTutorialDock v-if="showGenerateTutorialDock" />

    <UserSuggestionDialog v-if="suggestionDialogOpen" v-model:open="suggestionDialogOpen" />
    <NotificationCenterDialog
      v-if="notificationCenterDialogOpen"
      v-model:open="notificationCenterDialogOpen"
      :default-tab="notificationCenterDefaultTab"
    />

    <a-modal
      v-model:open="creditsContactVisible"
      title="联系我们"
      :footer="null"
      :width="420"
      centered
    >
      <div class="credits-contact-modal">
        <div v-if="contactQrImage" class="credits-contact-qr">
          <img :src="contactQrImage" alt="contact qr code" />
        </div>
        <div v-else class="credits-contact-empty">
          暂未配置联系二维码，请联系管理员
        </div>
        <ul class="credits-contact-list">
          <li>积分获取</li>
          <li>API调用</li>
          <li>技术支持</li>
          <li>需求定制</li>
        </ul>
      </div>
    </a-modal>

    <a-modal
      v-model:open="purchaseDialogOpen"
      :footer="null"
      :width="520"
      centered
      wrap-class-name="credits-purchase-modal-wrap"
    >
      <template #title>
        <div class="credits-purchase-title">
          <span>积分套餐</span>
          <button type="button" class="credits-purchase-title-feedback" @click="openPurchaseFeedbackDialog">
            遇到问题？
          </button>
        </div>
      </template>
      <div class="credits-purchase-modal">
        <div class="credits-purchase-list">
          <button
            v-for="plan in creditPurchasePlans"
            :key="plan.key"
            type="button"
            class="credits-purchase-card"
            :class="[
              `credits-purchase-card-${plan.key}`,
              {
                'credits-purchase-card-active': plan.purchasable && selectedPurchasePlanKey === plan.key,
                'credits-purchase-card-disabled': !plan.purchasable,
              },
            ]"
            :disabled="!plan.purchasable"
            @click="handleSelectPurchasePlan(plan)"
          >
            <span v-if="plan.tag" class="credits-purchase-tag" :class="`credits-purchase-tag-${plan.key}`">{{ plan.tag }}</span>
            <div class="credits-purchase-price">
              <span class="credits-purchase-price-unit">¥</span>
              <span class="credits-purchase-price-value">{{ plan.display_amount }}</span>
            </div>
            <div class="credits-purchase-points">
              {{ plan.credits }} 积分
            </div>
            <div class="credits-purchase-name">
              <span>{{ plan.title }}</span>
              <span v-if="!plan.purchasable && plan.disabled_reason" class="credits-purchase-disabled-text">
                {{ plan.disabled_reason }}
              </span>
            </div>
            <div class="credits-purchase-check" :class="{ 'credits-purchase-check-active': plan.purchasable && selectedPurchasePlanKey === plan.key }">
              <CheckOutlined v-if="plan.purchasable && selectedPurchasePlanKey === plan.key" />
            </div>
          </button>
        </div>
        <div v-if="purchasePlansLoading" class="credits-purchase-safe-tip">正在加载积分套餐...</div>
        <div v-else-if="selectedPurchasePlan" class="credits-purchase-safe-tip">
          将跳转到支付宝收银台，实付 ¥{{ selectedPurchasePlan.display_amount }}，到账 {{ selectedPurchasePlan.credits }} 积分
        </div>
        <div v-else class="credits-purchase-safe-tip">暂未获取到可售积分套餐，请稍后再试</div>
        <a-button
          type="primary"
          block
          class="warm-primary-btn credits-purchase-submit"
          :loading="purchaseLoading"
          :disabled="purchasePlansLoading || !selectedPurchasePlan"
          @click="handlePurchaseCredits"
        >
          前往支付宝支付
        </a-button>
        <div class="credits-purchase-contact-tip">
          定制积分充值请
          <button type="button" class="credits-purchase-contact-link" @click="openCreditsContact">
            联系客服
          </button>
        </div>
      </div>
    </a-modal>

    <a-modal
      v-model:open="purchaseFeedbackDialogOpen"
      title="提交反馈"
      :footer="null"
      :width="420"
      centered
      @cancel="closePurchaseFeedbackDialog"
    >
      <div class="purchase-feedback-modal">
        <a-form layout="vertical">
          <a-form-item label="问题描述" style="margin-bottom: 0">
            <a-textarea
              v-model:value="purchaseFeedbackForm.content"
              :rows="5"
              :maxlength="500"
              show-count
              placeholder="请描述你在积分购买时遇到的问题，我们会尽快处理"
            />
          </a-form-item>
        </a-form>
        <div class="purchase-feedback-hint">
          当前购买反馈入口已打开，你也可以通过
          <button type="button" class="purchase-feedback-contact-link" @click="openContactFromPurchaseFeedback">
            联系我们
          </button>
          获取更快支持。
        </div>
        <div class="purchase-feedback-actions">
          <a-button class="warm-secondary-btn" @click="closePurchaseFeedbackDialog">
            关闭
          </a-button>
          <a-button type="primary" class="warm-primary-btn" :loading="purchaseFeedbackSubmitting" @click="handleSubmitPurchaseFeedback">
            提交反馈
          </a-button>
        </div>
      </div>
    </a-modal>

    <a-modal
      v-model:open="announcementVisible"
      title="系统公告"
      :footer="null"
      :width="640"
      centered
      @cancel="handleAnnouncementClose"
    >
      <div class="announcement-modal">
        <div
          class="announcement-content"
          :class="{ 'is-html': announcementLooksLikeHtml }"
          v-html="announcementConfig.announcement_content"
        />
        <a-checkbox v-model:checked="announcementDismissToday">
          今日不再弹出
        </a-checkbox>
        <div class="announcement-actions">
          <a-button type="primary" class="warm-primary-btn" @click="handleAnnouncementClose">
            知道了
          </a-button>
        </div>
      </div>
    </a-modal>

    <a-modal
      v-model:open="redeemDialogOpen"
      title="兑换积分"
      :confirm-loading="redeemLoading"
      :ok-button-props="{ class: 'warm-primary-btn' }"
      :cancel-button-props="{ class: 'warm-secondary-btn' }"
      ok-text="立即兑换"
      cancel-text="取消"
      centered
      :width="420"
      @ok="handleRedeemCredits"
    >
      <a-form layout="vertical" style="margin-top: 16px">
        <a-form-item label="兑换码" style="margin-bottom: 0">
          <a-input
            v-model:value="redeemForm.key"
            class="warm-input"
            :maxlength="16"
            placeholder="请输入 16 位兑换码"
            @press-enter="handleRedeemCredits"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <AuthModal
      v-model:open="loginModalVisible"
      v-model:tab="authTab"
      :locked-promo-code="lockedPromoFromSession"
      :seed-promo-code="seedRegisterPromoCode"
      @logged-in="handleAuthLoggedIn"
      @registered="handleRegistered"
      @invite-cleared="clearInviteAndPromoSeeds"
    />
  </a-layout>
</template>

<style scoped lang="scss">
.app-layout {
  min-height: 100vh;
  background: var(--theme-page-base);
}

.app-header {
  background: var(--theme-header-bg) !important;
  box-shadow: 0 16px 32px var(--theme-header-shadow);
  padding: 0 50px !important;
  height: 74px;
  line-height: normal;
  position: sticky;
  top: 0;
  z-index: 1000;
  border-bottom: 1px solid var(--theme-header-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.header-inner {
  width: 100%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0;
  height: 100%;
  background: transparent;
}

.header-brand-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  margin-right: 34px;
  flex-shrink: 0;
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--theme-accent);
  box-shadow: 0 12px 22px var(--theme-brand-shadow);
  overflow: hidden;
}

.brand-mark-image {
  width: 60%;
  height: 60%;
  object-fit: contain;
  display: block;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--theme-title);
  letter-spacing: -0.2px;
}

.brand-sub {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--theme-subtitle);
}

.top-link-btn {
  position: relative;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  height: 40px !important;
  line-height: 1 !important;
  padding-inline: 12px !important;
  font-weight: 700 !important;
  color: var(--theme-text-secondary) !important;
  border-radius: 999px !important;
}

.top-link-btn:hover,
.top-link-btn:focus {
  color: var(--theme-nav-hover-text) !important;
  background: var(--theme-nav-hover-bg) !important;
  border-color: transparent !important;
  box-shadow: none !important;
}

.purchase-credit-content {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 100%;
  line-height: 1;
  white-space: nowrap;
}

.purchase-credit-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: currentColor;
  font-size: 18px;
  line-height: 1;
}

.header-menu {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: max-content;
  border-bottom: none !important;
  background: transparent;
  line-height: 54px;

  :deep(.ant-menu-item) {
    height: 46px;
    line-height: 46px;
    margin-inline: 4px !important;
    padding-inline: 16px !important;
    border-radius: 16px;
    font-weight: 700;
    color: var(--theme-nav-text);

    &::after {
      display: none;
    }
  }

  :deep(.ant-menu-item-selected) {
    background: var(--theme-accent) !important;
    color: var(--theme-nav-active-text) !important;
    box-shadow: 0 10px 18px var(--theme-nav-active-shadow);
  }

  :deep(.ant-menu-item-selected .nav-menu-icon) {
    filter: var(--theme-nav-icon-active-filter);
  }

  :deep(.ant-menu-item-selected .nav-menu-system-icon) {
    filter: var(--theme-nav-icon-active-filter);
  }

  :deep(.ant-menu-item:not(.ant-menu-item-selected):hover) {
    color: var(--theme-nav-hover-text) !important;
    background: var(--theme-nav-hover-bg) !important;
  }

  :deep(.ant-menu-title-content) {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
}

.nav-menu-icon {
  width: 20px;
  height: 20px;
  display: block;
  flex-shrink: 0;
  filter: var(--theme-nav-icon-filter);
  transition: filter var(--motion-duration-fast) var(--motion-ease-soft);
}

.nav-menu-system-icon {
  width: 20px;
  height: 20px;
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  color: currentColor;
  filter: var(--theme-nav-icon-filter);
  font-size: 19px;
  line-height: 1;
  transition: filter var(--motion-duration-fast) var(--motion-ease-soft);
}

.canvas-side-nav {
  position: fixed;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 1100;
  width: 76px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 7px;
  border-right: 1px solid var(--theme-header-border);
  background: var(--theme-header-bg);
  box-shadow: 12px 0 28px var(--theme-header-shadow);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  overflow-x: hidden;
  overflow-y: auto;
}

.canvas-side-brand-wrap {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}

.canvas-side-brand {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 15px;
  background: var(--theme-accent);
  box-shadow: 0 12px 22px var(--theme-brand-shadow);
  cursor: pointer;
  transition:
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.canvas-side-brand:hover {
  box-shadow: 0 14px 26px var(--theme-brand-shadow);
  transform: translateY(-1px);
}

.canvas-side-brand-name {
  color: var(--theme-title);
  font-size: 14px;
  font-weight: 900;
  line-height: 1;
  letter-spacing: -0.2px;
}

.canvas-side-nav-menu {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 16px;
}

.canvas-side-nav-item {
  position: relative;
  width: 58px;
  height: 58px;
  min-height: 58px;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 3px;
  border: 0;
  border-radius: 16px;
  background: transparent;
  color: var(--theme-nav-text);
  font-size: 11px;
  font-weight: 800;
  line-height: 1.15;
  text-align: center;
  cursor: pointer;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.canvas-side-nav-item .nav-menu-icon {
  width: 20px;
  height: 20px;
}

.canvas-side-nav-item :deep(.anticon),
.canvas-side-nav-item .nav-menu-system-icon {
  width: 20px;
  height: 20px;
  color: currentColor;
  filter: none;
  font-size: 20px;
}

.canvas-side-nav-item:hover {
  color: var(--theme-nav-hover-text);
  background: var(--theme-nav-hover-bg);
  transform: translateY(-1px);
}

.canvas-side-nav-item.active {
  background: var(--theme-accent);
  color: var(--theme-nav-active-text);
  box-shadow: 0 10px 18px var(--theme-nav-active-shadow);
}

.canvas-side-nav-item.active .nav-menu-icon {
  filter: var(--theme-nav-icon-active-filter);
}

.canvas-side-nav-item.active :deep(.anticon),
.canvas-side-nav-item.active .nav-menu-system-icon {
  color: currentColor;
  filter: none;
}

.nav-menu-new-badge {
  position: absolute;
  top: -4px;
  right: -2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  font-size: 9px;
  font-weight: 900;
  line-height: 1;
  letter-spacing: 0.02em;
  box-shadow: 0 8px 16px rgba(255, 95, 109, 0.28);
  pointer-events: none;
}

.canvas-side-nav-actions {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: auto;
  padding-top: 10px;
}

.canvas-side-nav-actions :deep(.ant-badge),
.canvas-side-nav-footer :deep(.ant-badge) {
  width: 100%;
}

.canvas-side-nav-action {
  height: 58px;
  min-height: 58px;
}

.canvas-side-nav-divider {
  width: 52px;
  height: 1px;
  flex: 0 0 auto;
  align-self: center;
  margin: 2px 0;
  background: var(--theme-header-border);
}

.canvas-side-nav-footer {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--theme-header-border);
}

.canvas-side-credit-pill {
  width: 100%;
  min-height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 4px 2px;
  border: 0;
  border-radius: 16px;
  background: transparent;
  color: var(--theme-pill-text);
  font-size: 14px;
  font-weight: 900;
  cursor: pointer;
  box-shadow: none;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.canvas-side-credit-pill :deep(.anticon) {
  font-size: 17px;
}

.canvas-side-credit-pill:hover {
  background: var(--theme-nav-hover-bg);
  color: var(--theme-accent-text-hover);
  transform: translateY(-1px);
}

.canvas-side-user-trigger {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 2px;
  border: 0;
  border-radius: 18px;
  background: transparent;
  color: var(--theme-nav-text);
  cursor: pointer;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.canvas-side-user-trigger:hover {
  background: var(--theme-nav-hover-bg);
  color: var(--theme-accent-text-hover);
  transform: translateY(-1px);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.mobile-nav-fab {
  width: 54px;
  height: 54px;
  display: none;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: none !important;
  background: var(--theme-accent) !important;
  box-shadow: 0 16px 30px var(--theme-fab-shadow);
}

.mobile-nav-entry {
  display: none;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.suggestion-fab-wrap {
  position: fixed;
  right: 0;
  bottom: 0;
  z-index: 1080;
  touch-action: none;
  user-select: none;
}

.suggestion-fab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  font-size: 18px;
  box-shadow: 0 12px 24px var(--theme-fab-shadow);
  cursor: pointer;
  transition:
    transform var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft);

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 16px 28px var(--theme-fab-shadow);
  }
}

.mobile-nav-credits {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 42px;
  padding: 0 14px;
  border-radius: 999px;
  background: var(--theme-pill-bg);
  border: 1px solid var(--theme-pill-border);
  color: var(--theme-pill-text);
  font-weight: 700;
  box-shadow: 0 10px 22px var(--theme-pill-shadow);
  cursor: pointer;
}

.mobile-drawer-credit-actions {
  display: grid;
  gap: 10px;
}

.mobile-drawer-action-btn {
  display: inline-flex !important;
  align-items: center !important;
  height: 44px;
  line-height: 1 !important;
  border-radius: 14px !important;
  border: 1px solid var(--theme-panel-border-strong) !important;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-strong)) !important;
  color: var(--theme-title) !important;
  font-weight: 700;
  text-align: left;
  box-shadow: 0 8px 18px var(--theme-card-shadow);

  &:hover,
  &:focus {
    color: var(--theme-nav-hover-text) !important;
    background: var(--theme-nav-hover-bg) !important;
    border-color: transparent !important;
    box-shadow: none !important;
  }
}

.mobile-drawer-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.mobile-drawer-brand {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.mobile-drawer-brand-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.mobile-user-card {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: 22px;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-strong));
  border: 1px solid var(--theme-panel-border-strong);
  box-shadow: 0 12px 24px var(--theme-card-shadow);
}

.mobile-user-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.mobile-user-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--theme-title);
  word-break: break-all;
}

.mobile-user-role {
  font-size: 12px;
  color: var(--theme-text-secondary);
}

.mobile-user-actions {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  align-self: stretch;
  gap: 8px;
  min-width: 0;
}

.mobile-drawer-contact-link {
  padding: 6px 12px !important;
  height: auto !important;
  border-radius: 16px !important;
  font-weight: 700;
  color: var(--theme-accent-text) !important;

  &:hover {
    color: var(--theme-nav-hover-text) !important;
    background: var(--theme-nav-hover-bg) !important;
  }
}

.mobile-user-credits {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 999px;
  background: var(--theme-pill-bg-strong);
  color: var(--theme-pill-text);
  font-weight: 700;
  cursor: pointer;
}

.mobile-drawer-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mobile-drawer-section-title {
  padding-left: 6px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--theme-subtitle);
  display: flex;
  align-items: center;
  gap: 8px;
}

.mobile-drawer-menu {
  border-inline-end: none !important;
  background: transparent !important;

  :deep(.ant-menu-item),
  :deep(.ant-menu-submenu-title) {
    display: flex;
    align-items: center;
    height: 48px;
    line-height: 48px;
    margin: 4px 0 !important;
    padding-inline: 16px !important;
    border-radius: 16px;
    font-weight: 700;
    color: var(--theme-nav-text);
    gap: 8px;
  }

  :deep(.ant-menu-item .ant-menu-item-icon),
  :deep(.ant-menu-submenu-title > .ant-menu-item-icon) {
    display: inline-flex !important;
    align-items: center;
    justify-content: center;
    width: 16px;
    min-width: 16px;
    height: 16px;
    margin: 0 !important;
    font-size: 16px !important;
    line-height: 1;
    flex: none;
  }

  :deep(.ant-menu-item .ant-menu-item-icon .anticon),
  :deep(.ant-menu-item .ant-menu-item-icon .nav-menu-system-icon),
  :deep(.ant-menu-item .ant-menu-item-icon .nav-generate-image-icon),
  :deep(.ant-menu-item .ant-menu-item-icon svg),
  :deep(.ant-menu-submenu-title > .ant-menu-item-icon .anticon),
  :deep(.ant-menu-submenu-title > .ant-menu-item-icon .nav-menu-system-icon),
  :deep(.ant-menu-submenu-title > .ant-menu-item-icon .nav-generate-image-icon),
  :deep(.ant-menu-submenu-title > .ant-menu-item-icon svg) {
    width: 16px !important;
    height: 16px !important;
    min-width: 16px;
    margin: 0 !important;
    font-size: 16px !important;
    line-height: 1;
  }

  :deep(.ant-menu-submenu-title .ant-menu-title-content) {
    display: inline-flex;
    align-items: center;
    min-width: 0;
    flex: 1 1 auto;
    gap: 8px;
  }

  :deep(.ant-menu-sub.ant-menu-inline) {
    background: transparent !important;
  }

  :deep(.ant-menu-submenu .ant-menu-item) {
    padding-left: 40px !important;
  }

  :deep(.ant-menu-title-content) {
    display: inline-flex;
    align-items: center;
    min-width: 0;
    gap: 8px;
  }

  :deep(.ant-menu-item-selected) {
    background: var(--theme-accent) !important;
    color: var(--theme-nav-active-text) !important;
    box-shadow: 0 10px 18px var(--theme-nav-active-shadow);
  }

  :deep(.ant-menu-item-selected .nav-menu-icon) {
    filter: var(--theme-nav-icon-active-filter);
  }

  :deep(.ant-menu-item-selected .nav-menu-system-icon) {
    filter: var(--theme-nav-icon-active-filter);
  }

  :deep(.ant-menu-item-danger) {
    color: #c85a49 !important;
  }

  :deep(.ant-menu-item-danger:hover) {
    background: #fff1ee !important;
    color: #b84b3b !important;
  }

  :deep(.ant-menu-item-group-title) {
    padding: 8px 16px 4px;
    color: var(--theme-text-muted);
    font-size: 12px;
    font-weight: 700;
  }

  :deep(.mobile-theme-menu-item .ant-menu-title-content) {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
  }

  :deep(.mobile-theme-menu-item .theme-menu-item-title) {
    flex: 0 1 auto;
    width: auto;
    min-width: 0;
    justify-content: flex-start;
  }

  :deep(.mobile-theme-menu-item .theme-menu-swatches-inline) {
    flex: none;
    margin-left: auto;
  }
}

.theme-menu-item-title {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
}

.theme-menu-check {
  color: var(--theme-accent);
  font-size: 14px;
}

.theme-menu-swatches-inline {
  display: grid;
  grid-template-columns: repeat(4, 18px);
  gap: 6px;
}

.theme-menu-swatch-chip-inline {
  display: block;
  width: 18px;
  height: 18px;
  border: 1px solid var(--theme-panel-border-strong);
  border-radius: 5px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.24);
}

.nav-menu-new-badge-mobile {
  position: static;
  min-width: 30px;
  height: 18px;
  margin-left: auto;
  font-size: 10px;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .app-layout {
  :deep(.ant-menu-item-danger:hover) {
    background: rgba(185, 56, 42, 0.14) !important;
    color: #de8f84 !important;
  }
}

html:is([data-theme="dark"], [data-theme="midnight"]) .warm-dropdown .ant-dropdown-menu-item-danger:hover {
  background: rgba(185, 56, 42, 0.14) !important;
  color: #de8f84 !important;
}

.mobile-auth-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mobile-drawer-guest-contact {
  height: 48px !important;
  border-radius: 16px !important;
  font-weight: 700 !important;
  border: 1px solid var(--theme-panel-border-strong) !important;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-strong)) !important;
  color: var(--theme-title) !important;
  box-shadow: 0 8px 18px var(--theme-card-shadow);

  &:hover {
    color: var(--theme-nav-hover-text) !important;
    background: var(--theme-nav-hover-bg) !important;
    border-color: transparent !important;
    box-shadow: none !important;
  }
}

.admin-btn {
  height: 40px;
  padding-inline: 14px;
  border-radius: 999px;
  border: 1px solid var(--theme-panel-border-strong) !important;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-strong)) !important;
  color: var(--theme-accent-text) !important;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 10px 22px var(--theme-card-shadow);

  &:hover {
    color: var(--theme-accent-text-hover) !important;
    border-color: var(--theme-border-strong) !important;
    background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg-strong)) !important;
    box-shadow: 0 12px 24px var(--theme-card-shadow-strong);
  }
}

.desktop-admin-entry {
  display: inline-flex;
}

.admin-menu-feedback-label {
  margin-left: 0;
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.admin-menu-feedback-label > span:first-child {
  min-width: 0;
  white-space: nowrap;
}

:deep(.admin-menu-feedback-label .ant-badge) {
  flex: 0 0 auto;
}

:deep(.admin-menu-feedback-label .ant-badge-count) {
  color: #fff !important;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px 6px 6px;
  border-radius: 18px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
  border: 1px solid transparent;

  &:hover {
    background: var(--theme-panel-bg-muted);
    border-color: var(--theme-panel-border);
  }
}

.user-menu-feedback-label {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.user-menu-feedback-label > span:first-child {
  min-width: 0;
  white-space: nowrap;
}

.user-avatar {
  background: var(--theme-accent);
  color: var(--theme-accent-contrast);
  font-weight: 700;
  box-shadow: 0 10px 16px var(--theme-nav-active-shadow);
}

.user-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--theme-title);
}

.credits-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--theme-accent-text);
  cursor: pointer;
  transition: color 0.2s, transform 0.2s;

  &:hover {
    color: var(--theme-accent-text-hover);
    transform: translateY(-1px);
  }
}

.credits-contact-modal {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  padding: 8px 0 4px;
  text-align: center;
}

.credits-contact-list {
  display: grid;
  grid-template-columns: repeat(2, auto);
  justify-content: center;
  justify-items: start;
  column-gap: 28px;
  row-gap: 8px;
  margin: 0 auto;
  width: max-content;
  max-width: 100%;
  padding: 0 0 0 1.15em;
  box-sizing: border-box;
  list-style: disc;
  list-style-position: outside;
  text-align: left;
  color: var(--theme-text-secondary);
  font-size: 14px;
  line-height: 1.6;

  li {
    display: list-item;

    &::marker {
      font-size: 0.75em;
      color: var(--theme-subtitle);
    }
  }
}

.credits-contact-qr {
  width: 240px;
  height: 240px;
  padding: 10px;
  border-radius: 24px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  box-shadow: inset 0 0 0 1px var(--theme-panel-inset);

  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    border-radius: 18px;
    background: var(--theme-empty-bg);
  }
}

.credits-contact-empty {
  width: 100%;
  padding: 26px 18px;
  border-radius: 20px;
  background: var(--theme-panel-bg-soft);
  border: 1px dashed var(--theme-empty-border);
  color: var(--theme-text-secondary);
  line-height: 1.8;
}

.credits-purchase-modal {
  padding: 2px 2px 2px;
}

.credits-purchase-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.credits-purchase-title {
  position: relative;
  display: flex;
  align-items: center;
  padding-right: 56px;
}

.credits-purchase-title-feedback {
  position: absolute;
  right: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--theme-text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.credits-purchase-title-feedback:hover {
  color: var(--theme-accent-text);
}

.credits-purchase-card {
  --credits-purchase-accent: var(--theme-accent);
  --credits-purchase-accent-start: var(--theme-accent-strong);
  --credits-purchase-accent-end: var(--theme-accent);
  --credits-purchase-accent-shadow: var(--theme-shadow-strong);

  position: relative;
  display: grid;
  grid-template-columns: 90px minmax(82px, 0.72fr) minmax(128px, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 70px;
  padding: 14px;
  border-radius: 18px;
  border: 1.5px solid var(--theme-panel-border);
  background: var(--theme-panel-bg);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 10px 30px var(--theme-shadow-soft);
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.credits-purchase-card:hover {
  transform: translateY(-1px);
  border-color: var(--theme-border-strong);
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 14px 36px var(--theme-shadow-medium);
}

.credits-purchase-card-active {
  border: 1px solid var(--theme-accent);
  background: var(--theme-control-hover-bg);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.95),
    0 14px 30px var(--credits-purchase-accent-shadow);
}

.credits-purchase-card-disabled {
  border-color: rgba(183, 176, 168, 0.42);
  background:
    linear-gradient(180deg, rgba(248, 246, 243, 0.98), rgba(240, 237, 233, 0.96)),
    radial-gradient(circle at top, rgba(205, 205, 205, 0.16), transparent 62%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 6px 18px rgba(110, 104, 96, 0.08);
  cursor: not-allowed;
  opacity: 0.72;
}

.credits-purchase-card-disabled:hover {
  transform: none;
  border-color: rgba(183, 176, 168, 0.42);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 6px 18px rgba(110, 104, 96, 0.08);
}

.credits-purchase-tag {
  position: absolute;
  top: -9px;
  left: 14px;
  padding: 5px 11px;
  border-radius: 11px;
  background: linear-gradient(180deg, var(--credits-purchase-accent-start), var(--credits-purchase-accent-end));
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  line-height: 1;
  box-shadow: 0 8px 16px var(--credits-purchase-accent-shadow);
}

.credits-purchase-card-starter,
.credits-purchase-card-intro {
  --credits-purchase-accent: #0ea5e9;
  --credits-purchase-accent-start: #38bdf8;
  --credits-purchase-accent-end: #0ea5e9;
  --credits-purchase-accent-shadow: rgba(14, 165, 233, 0.24);
}

.credits-purchase-card-light,
.credits-purchase-card-plus,
.credits-purchase-card-popular {
  --credits-purchase-accent: var(--theme-accent);
  --credits-purchase-accent-start: var(--theme-accent-strong);
  --credits-purchase-accent-end: var(--theme-accent);
  --credits-purchase-accent-shadow: var(--theme-shadow-strong);
}

.credits-purchase-card-value {
  --credits-purchase-accent: #f43f5e;
  --credits-purchase-accent-start: #fb7185;
  --credits-purchase-accent-end: #f43f5e;
  --credits-purchase-accent-shadow: rgba(244, 63, 94, 0.24);
}

.credits-purchase-card-vip {
  --credits-purchase-accent: #7c3aed;
  --credits-purchase-accent-start: #a78bfa;
  --credits-purchase-accent-end: #7c3aed;
  --credits-purchase-accent-shadow: rgba(124, 58, 237, 0.28);
}

.credits-purchase-card-mega {
  --credits-purchase-accent: #d4a017;
  --credits-purchase-accent-start: #f6d365;
  --credits-purchase-accent-end: #c68a00;
  --credits-purchase-accent-shadow: rgba(212, 160, 23, 0.28);
}

.credits-purchase-price {
  display: inline-flex;
  align-items: flex-end;
  gap: 6px;
  white-space: nowrap;
  color: #22252c;
}

.credits-purchase-price-value {
  font-size: 22px;
  font-weight: 500;
  line-height: 1;
}

.credits-purchase-price-unit {
  padding-bottom: 0;
  font-size: 12px;
  font-weight: 500;
  transform: translateY(1px);
}

.credits-purchase-points {
  display: flex;
  align-items: baseline;
  gap: 4px;
  flex-wrap: nowrap;
  font-size: 14px;
  font-weight: 700;
  color: var(--theme-accent-text);
  white-space: nowrap;
  min-width: 0;
}

.credits-purchase-name {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--theme-text-secondary);
  white-space: nowrap;
}

.credits-purchase-disabled-text {
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  color: #9a9188;
  white-space: normal;
}

.credits-purchase-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  justify-self: end;
  width: 24px;
  height: 24px;
  margin-left: 6px;
  border-radius: 999px;
  border: 1.5px solid var(--theme-control-border);
  color: transparent;
  background: var(--theme-surface-strong);
  font-size: 12px;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.credits-purchase-check-active {
  border-color: var(--credits-purchase-accent);
  background: linear-gradient(180deg, var(--credits-purchase-accent-start), var(--credits-purchase-accent-end));
  color: #fff;
  box-shadow: 0 10px 20px var(--credits-purchase-accent-shadow);
}

.credits-purchase-card-disabled .credits-purchase-price,
.credits-purchase-card-disabled .credits-purchase-points,
.credits-purchase-card-disabled .credits-purchase-name,
.credits-purchase-card-disabled .credits-purchase-check {
  color: #9a9188;
}

.credits-purchase-card-disabled .credits-purchase-check {
  border-color: #d8d0c7;
  background: rgba(255, 255, 255, 0.7);
}

.credits-purchase-card-disabled .credits-purchase-tag {
  background: linear-gradient(180deg, #c9c3bc, #afa79f);
  box-shadow: 0 8px 16px rgba(150, 142, 133, 0.18);
}

.credits-purchase-safe-tip {
  margin: 14px 0 12px;
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--theme-accent-text);
}

.credits-purchase-submit {
  height: 46px !important;
}

.credits-purchase-contact-tip {
  margin-top: 10px;
  text-align: center;
  font-size: 12px;
  line-height: 1.6;
  color: var(--theme-text-secondary);
}

.credits-purchase-contact-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--theme-accent-text);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.credits-purchase-contact-link:hover {
  color: var(--theme-accent-text-hover);
}

.credits-purchase-qr-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 4px;
}

.credits-purchase-qr-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: center;
}

.credits-purchase-qr-subject {
  font-size: 18px;
  font-weight: 700;
  color: var(--theme-title);
}

.credits-purchase-qr-meta {
  font-size: 12px;
  color: var(--theme-text-secondary);
}

.credits-purchase-qr-box {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 244px;
  border-radius: 20px;
  background: var(--theme-surface-strong);
  border: 1px solid var(--theme-panel-border);
}

.credits-purchase-qr-box-empty {
  color: var(--theme-text-secondary);
  font-size: 13px;
}

.credits-purchase-qr-image {
  width: 220px;
  height: 220px;
  object-fit: contain;
}

.credits-purchase-qr-summary {
  display: grid;
  gap: 10px;
}

.credits-purchase-qr-summary div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
}

.credits-purchase-qr-summary span {
  color: var(--theme-text-secondary);
}

.credits-purchase-qr-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.credits-purchase-qr-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 4px;
}

.credits-purchase-qr-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: center;
}

.credits-purchase-qr-subject {
  font-size: 18px;
  font-weight: 700;
  color: var(--theme-title);
}

.credits-purchase-qr-meta {
  font-size: 12px;
  color: var(--theme-text-secondary);
}

.credits-purchase-qr-box {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 244px;
  border-radius: 20px;
  background: var(--theme-surface-strong);
  border: 1px solid var(--theme-panel-border);
}

.credits-purchase-qr-box-empty {
  color: var(--theme-text-secondary);
  font-size: 13px;
}

.credits-purchase-qr-image {
  width: 220px;
  height: 220px;
  object-fit: contain;
}

.credits-purchase-qr-summary {
  display: grid;
  gap: 10px;
}

.credits-purchase-qr-summary div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
}

.credits-purchase-qr-summary span {
  color: var(--theme-text-secondary);
}

.credits-purchase-qr-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.purchase-feedback-modal {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 8px;
}

.purchase-feedback-hint {
  font-size: 12px;
  line-height: 1.7;
  color: var(--theme-text-secondary);
}

.purchase-feedback-contact-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--theme-accent-text);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.purchase-feedback-contact-link:hover {
  color: var(--theme-accent-text-hover);
}

.purchase-feedback-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

:deep(.credits-purchase-modal-wrap .ant-modal-content) {
  border-radius: 22px;
  padding: 16px 18px 18px;
  background:
    radial-gradient(circle at top, var(--theme-page-glow), transparent 38%),
    var(--theme-modal-bg);
  box-shadow:
    0 22px 60px var(--theme-shadow-medium),
    inset 0 1px 0 var(--theme-panel-inset);
}

:deep(.credits-purchase-modal-wrap .ant-modal-close) {
  top: 12px;
  right: 12px;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  background: var(--theme-control-bg);
  color: var(--theme-accent-text);
}

:deep(.credits-purchase-modal-wrap .ant-modal-close:hover) {
  background: var(--theme-control-hover-bg);
  color: var(--theme-accent-text-hover);
}

.announcement-modal {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 6px 0 2px;
}

.announcement-content {
  max-height: min(52vh, 520px);
  overflow-x: hidden;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.85;
  color: var(--theme-text);
  font-size: 14px;
  padding: 16px 18px;
  border-radius: 18px;
  background: var(--theme-panel-bg-soft);
  border: 1px solid var(--theme-panel-border);
  word-break: break-word;
  scrollbar-width: thin;
  scrollbar-color: var(--theme-border-strong) var(--theme-panel-bg-muted);

  &.is-html {
    white-space: normal;
  }

  &.is-html :deep(p) {
    margin: 0 0 12px;
  }

  &.is-html :deep(h1),
  &.is-html :deep(h2),
  &.is-html :deep(h3),
  &.is-html :deep(h4) {
    margin: 16px 0 8px;
    color: var(--theme-heading);
    line-height: 1.35;
  }

  &.is-html :deep(ul),
  &.is-html :deep(ol) {
    margin: 0 0 12px 20px;
    padding-left: 16px;
  }

  &.is-html :deep(li) {
    margin: 4px 0;
  }

  &.is-html :deep(a) {
    color: var(--theme-accent-text);
  }

  &.is-html :deep(img) {
    display: block;
    max-width: 100%;
    height: auto;
    margin: 8px 0 4px;
    border-radius: 12px;
    border: 1px solid var(--theme-panel-border);
    background: var(--theme-empty-bg);
  }

  &.is-html :deep(figcaption) {
    margin: 0 0 14px;
    color: var(--theme-muted-text);
    font-size: 12px;
    line-height: 1.5;
  }

  &.is-html :deep(blockquote) {
    margin: 12px 0;
    padding: 10px 14px;
    border-left: 4px solid var(--theme-panel-border-strong);
    background: var(--theme-panel-bg);
  }

  &.is-html :deep(strong),
  &.is-html :deep(b) {
    color: var(--theme-title);
  }
}

.announcement-content::-webkit-scrollbar {
  width: 8px;
}

.announcement-content::-webkit-scrollbar-track {
  border-radius: 999px;
  background: var(--theme-panel-bg-muted);
}

.announcement-content::-webkit-scrollbar-thumb {
  border-radius: 999px;
  border: 2px solid var(--theme-panel-bg-muted);
  background: var(--theme-border-strong);
}

.announcement-content::-webkit-scrollbar-thumb:hover {
  background: var(--theme-accent);
}

.announcement-actions {
  display: flex;
  justify-content: flex-end;
}

html:is([data-theme="dark"], [data-theme="midnight"]) .announcement-modal :deep(.ant-checkbox + span) {
  color: var(--theme-title);
}

.app-content {
  position: relative;
  padding: 22px 50px 28px;
  background: var(--theme-page-base);

  &::before {
    display: none;
  }
}

.app-content-workbench {
  padding: 0;

  &::before {
    display: none;
  }

  .content-inner,
  .route-page-shell {
    height: 100%;
  }
}

.app-content-desktop-side-nav {
  width: calc(100% - 76px);
  margin-left: 76px;
}

.content-inner {
  width: 100%;
  position: relative;
  z-index: 1;
}

.route-page-shell {
  min-width: 0;
  background: transparent;
  border-radius: 0;
}

.route-page-forward-enter-active,
.route-page-forward-leave-active,
.route-page-back-enter-active,
.route-page-back-leave-active {
  transition:
    opacity var(--motion-duration-reveal-fast) var(--motion-ease-soft),
    transform var(--motion-duration-reveal) var(--motion-ease-enter);
}

.route-page-forward-enter-from {
  opacity: 0;
  transform: translate3d(18px, 0, 0);
}

.route-page-forward-leave-to {
  opacity: 0;
  transform: translate3d(-14px, 0, 0);
}

.route-page-back-enter-from {
  opacity: 0;
  transform: translate3d(-18px, 0, 0);
}

.route-page-back-leave-to {
  opacity: 0;
  transform: translate3d(14px, 0, 0);
}

.route-page-forward-enter-to,
.route-page-forward-leave-from,
.route-page-back-enter-to,
.route-page-back-leave-from {
  opacity: 1;
  transform: translate3d(0, 0, 0);
}

:deep(.mobile-nav-drawer .ant-drawer-content-wrapper),
:deep(.mobile-nav-drawer .ant-drawer-content) {
  border-radius: 0;
}

:deep(.mobile-nav-drawer .ant-drawer-header) {
  padding: 20px 20px 0;
  border-bottom: none;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
}

:deep(.mobile-nav-drawer .ant-drawer-title) {
  color: var(--theme-title);
  font-weight: 700;
}

:deep(.mobile-nav-drawer .ant-drawer-body) {
  padding: 18px 20px 24px;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-muted));
}

:deep(.ant-modal .ant-input-affix-wrapper),
:deep(.ant-modal .ant-input-password),
:deep(.ant-modal .ant-input) {
  border-radius: 14px;
}

:deep(.ant-modal .ant-btn-primary) {
  background: var(--theme-accent) !important;
  border: none !important;
}

.login-header-btn {
  height: 42px;
  padding-inline: 20px;
  border-radius: 999px;
  font-weight: 700;
  background: var(--theme-accent) !important;
  border: none !important;
  box-shadow: 0 10px 22px var(--theme-nav-active-shadow);
}

.register-header-btn {
  height: 42px;
  padding-inline: 20px;
  border-radius: 999px;
  font-weight: 700;
  border: 1px solid var(--theme-panel-border-strong) !important;
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-strong)) !important;
  color: var(--theme-accent-text) !important;
  box-shadow: 0 10px 22px var(--theme-card-shadow);

  &:hover {
    color: var(--theme-accent-text-hover) !important;
    border-color: var(--theme-border-strong) !important;
    background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg-strong)) !important;
  }
}

@media (min-width: 961px) {
  .app-layout-desktop-side-nav .app-header {
    display: none;
  }

  .app-layout-desktop-side-nav .app-content:not(.app-content-workbench) {
    padding: 22px 22px 0;
  }
}

@media (max-width: 960px) {
  .app-layout-desktop-side-nav .canvas-side-nav {
    display: none;
  }

  .app-content-desktop-side-nav {
    width: 100%;
    margin-left: 0;
  }

  .app-header {
    padding-inline: 16px !important;
    height: auto;
  }

  .header-inner {
    gap: 12px;
    height: 74px;
    min-height: 74px;
  }

  .header-brand {
    margin-right: 0;
  }

  .header-brand-wrap {
    gap: 8px;
  }

  .top-link-btn {
    display: none;
  }

  .header-menu {
    display: none;
  }

  .header-actions {
    display: none;
  }

  .desktop-admin-entry {
    display: none;
  }

  .mobile-nav-entry {
    display: inline-flex;
  }

  .mobile-nav-fab {
    display: inline-flex;
  }

  .suggestion-fab-wrap {
    right: 0;
    bottom: 0;
  }

  .suggestion-fab {
    width: 36px;
    height: 36px;
    font-size: 16px;
  }
}

@media (max-width: 768px) {
  .suggestion-fab-wrap {
    display: none;
  }
}

@media (max-width: 640px) {
  .canvas-side-nav {
    width: 64px;
    padding: 9px 5px;
  }

  .canvas-side-brand {
    width: 38px;
    height: 38px;
    border-radius: 14px;
  }

  .canvas-side-brand-name {
    font-size: 12px;
  }

  .canvas-side-nav-menu {
    gap: 5px;
    margin-top: 14px;
  }

  .canvas-side-nav-actions {
    gap: 5px;
    padding-top: 8px;
  }

  .canvas-side-nav-item {
    width: 54px;
    height: 54px;
    min-height: 54px;
    border-radius: 14px;
    font-size: 10px;
  }

  .canvas-side-nav-action {
    height: 54px;
    min-height: 54px;
  }

  .canvas-side-nav-divider {
    width: 48px;
  }

  .canvas-side-nav-item .nav-menu-icon {
    width: 18px;
    height: 18px;
  }

  .canvas-side-nav-item .nav-menu-system-icon {
    width: 18px;
    height: 18px;
    font-size: 17px;
  }

  .canvas-side-nav-item :deep(.anticon) {
    font-size: 18px;
  }

  .canvas-side-nav-footer {
    gap: 7px;
    margin-top: 8px;
    padding-top: 8px;
  }

  .canvas-side-credit-pill {
    min-height: 40px;
    border-radius: 15px;
    font-size: 13px;
  }

  .canvas-side-credit-pill :deep(.anticon) {
    font-size: 16px;
  }

  .canvas-side-user-trigger {
    border-radius: 17px;
  }

  .app-content-desktop-side-nav {
    width: 100%;
    margin-left: 0;
    padding-inline: 0;
  }

  .brand-sub,
  .user-name {
    display: none;
  }

  .admin-btn {
    padding-inline: 12px;
  }

  .app-content {
    padding-inline: 14px;
  }

  :deep(.mobile-nav-drawer .ant-drawer-content-wrapper) {
    width: min(88vw, 320px) !important;
  }

  .credits-purchase-card {
    grid-template-columns: 1fr auto;
    gap: 6px 10px;
    padding: 14px 12px;
  }

  .credits-purchase-price,
  .credits-purchase-points,
  .credits-purchase-name {
    grid-column: 1 / 2;
  }

  .credits-purchase-check {
    grid-column: 2 / 3;
    grid-row: 1 / 4;
    align-self: center;
  }

  .credits-purchase-price-value {
    font-size: 19px;
  }

  .credits-purchase-points {
    font-size: 13px;
    white-space: normal;
  }

  .credits-purchase-name {
    font-size: 11px;
    white-space: normal;
  }

  .credits-purchase-safe-tip {
    margin: 14px 0 12px;
    font-size: 10px;
  }

  .credits-purchase-submit {
    height: 44px !important;
  }

  .credits-purchase-contact-tip {
    font-size: 11px;
  }

  :deep(.credits-purchase-modal-wrap .ant-modal) {
    max-width: calc(100vw - 24px);
    margin: 0 auto;
  }

  :deep(.credits-purchase-modal-wrap .ant-modal-content) {
    padding: 16px 12px 16px;
    border-radius: 18px;
  }
}
</style>

<style lang="scss">
.mobile-nav-drawer.ant-drawer .ant-drawer-content-wrapper,
.mobile-nav-drawer.ant-drawer .ant-drawer-content,
.mobile-nav-drawer .ant-drawer-content-wrapper,
.mobile-nav-drawer .ant-drawer-content {
  border-radius: 0 !important;
}

.warm-dropdown {
  z-index: 1300;
  overflow: visible;
}

.app-layout-desktop-side-nav .generate-page,
.app-layout-desktop-side-nav .content-inner .chat-page {
  min-height: calc(100dvh - 44px) !important;
  height: calc(100dvh - 44px) !important;
}

.warm-dropdown .ant-dropdown-menu {
  min-width: 176px;
  padding: 12px;
  border-radius: 18px;
  border: 1px solid var(--theme-panel-border);
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  box-shadow: 0 16px 28px var(--theme-shadow-soft);
  color: var(--theme-title);
}

.warm-dropdown .canvas-side-user-menu-header {
  display: grid;
  gap: 4px;
  padding: 8px 12px 10px;
}

.warm-dropdown .canvas-side-user-menu-name {
  max-width: 180px;
  overflow: hidden;
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.warm-dropdown .canvas-side-user-menu-role {
  color: var(--theme-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.warm-dropdown .ant-dropdown-menu,
.warm-dropdown .ant-dropdown-menu .ant-dropdown-menu-title-content,
.warm-dropdown .ant-dropdown-menu .ant-dropdown-menu-item,
.warm-dropdown .ant-dropdown-menu .ant-dropdown-menu-item span,
.warm-dropdown .ant-dropdown-menu .ant-dropdown-menu-item a,
.warm-dropdown .ant-dropdown-menu .ant-dropdown-menu-submenu-title,
.warm-dropdown .ant-dropdown-menu .ant-dropdown-menu-submenu-title span {
  color: var(--theme-title) !important;
}

.warm-dropdown .ant-dropdown-menu-item,
.warm-dropdown .ant-dropdown-menu-submenu-title {
  display: flex !important;
  align-items: center !important;
  gap: 8px;
  min-height: 50px;
  margin: 0 !important;
  padding: 10px 16px !important;
  border-radius: 14px;
  color: var(--theme-title);
  font-weight: 700;
  line-height: 1.2;
  transition:
    background var(--motion-duration-fast) var(--motion-ease-soft),
    color var(--motion-duration-fast) var(--motion-ease-soft),
    box-shadow var(--motion-duration-fast) var(--motion-ease-soft),
    transform var(--motion-duration-fast) var(--motion-ease-soft);
}

.warm-dropdown .ant-dropdown-menu-submenu.ant-dropdown-menu-submenu-vertical {
  margin: 0 !important;
  padding: 0 !important;
}

.warm-dropdown .ant-dropdown-menu-submenu-title,
.warm-dropdown .ant-dropdown-menu-item.theme-style-menu-item {
  position: relative;
  width: 100%;
  padding-inline-end: 32px !important;
}

.warm-dropdown .ant-dropdown-menu-item .ant-dropdown-menu-item-icon,
.warm-dropdown .ant-dropdown-menu-submenu-title > .ant-dropdown-menu-item-icon {
  display: inline-flex !important;
  align-items: center;
  justify-content: center;
  width: 16px;
  min-width: 16px !important;
  height: 16px;
  margin: 0 !important;
  font-size: 16px !important;
  line-height: 1;
  flex: none;
}

.warm-dropdown .ant-dropdown-menu-item .ant-dropdown-menu-title-content,
.warm-dropdown .ant-dropdown-menu-submenu-title .ant-dropdown-menu-title-content {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  flex: 1 1 auto;
  margin: 0 !important;
  padding: 0 !important;
  line-height: 1.2;
}

.warm-dropdown .ant-dropdown-menu-submenu-title .ant-dropdown-menu-submenu-expand-icon,
.warm-dropdown .ant-dropdown-menu-submenu-title .ant-dropdown-menu-submenu-arrow,
.warm-dropdown .ant-dropdown-menu-submenu-title .ant-menu-submenu-arrow,
.warm-dropdown .theme-style-entry-arrow {
  position: absolute !important;
  top: 50%;
  inset-inline-end: 16px !important;
  display: inline-flex !important;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  margin: 0 !important;
  color: currentColor;
  font-size: 12px !important;
  line-height: 1;
  transform: translateY(-50%);
}

.warm-dropdown .ant-dropdown-menu-submenu-title .ant-dropdown-menu-submenu-arrow .anticon,
.warm-dropdown .ant-dropdown-menu-submenu-title .ant-dropdown-menu-submenu-expand-icon .anticon,
.warm-dropdown .theme-style-entry-arrow.anticon,
.warm-dropdown .theme-style-entry-arrow .anticon {
  width: 12px !important;
  height: 12px !important;
  font-size: 12px !important;
}

.warm-dropdown .ant-dropdown-menu-submenu-title:hover {
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg-strong));
  color: var(--theme-accent-text-hover) !important;
  box-shadow: 0 10px 22px var(--theme-card-shadow);
  transform: translateY(-1px);
}

.warm-dropdown .ant-dropdown-menu-submenu-selected > .ant-dropdown-menu-submenu-title {
  color: var(--theme-accent-text) !important;
}

.warm-dropdown .ant-dropdown-menu-item:hover {
  background: linear-gradient(180deg, var(--theme-panel-bg-soft), var(--theme-panel-bg-strong));
  color: var(--theme-accent-text-hover) !important;
  box-shadow: 0 10px 22px var(--theme-card-shadow);
  transform: translateY(-1px);
}

.warm-dropdown .ant-dropdown-menu-item:hover span,
.warm-dropdown .ant-dropdown-menu-item:hover a,
.warm-dropdown .ant-dropdown-menu-item:hover .ant-dropdown-menu-title-content {
  color: var(--theme-accent-text-hover) !important;
}

.warm-dropdown .ant-dropdown-menu-item-selected {
  background: var(--theme-accent) !important;
  color: var(--theme-accent-contrast) !important;
  box-shadow:
    inset 0 1px 0 var(--theme-panel-inset),
    0 10px 22px var(--theme-shadow-strong);
}

.warm-dropdown .ant-dropdown-menu-item-selected span,
.warm-dropdown .ant-dropdown-menu-item-selected a,
.warm-dropdown .ant-dropdown-menu-item-selected .ant-dropdown-menu-title-content {
  color: var(--theme-accent-contrast) !important;
}

.warm-dropdown .ant-dropdown-menu-item .anticon,
.warm-dropdown .ant-dropdown-menu-submenu-title .anticon {
  font-size: 16px !important;
  line-height: 1;
  color: currentColor;
}

.warm-dropdown .ant-dropdown-menu-item .theme-style-entry-arrow.anticon,
.warm-dropdown .ant-dropdown-menu-submenu-title .ant-dropdown-menu-submenu-arrow .anticon,
.warm-dropdown .ant-dropdown-menu-submenu-title .ant-dropdown-menu-submenu-expand-icon .anticon {
  font-size: 12px !important;
}

.warm-dropdown .ant-dropdown-menu-item.admin-feedback-dropdown-item,
.warm-dropdown .ant-dropdown-menu-item.admin-feedback-dropdown-item .ant-dropdown-menu-title-content {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.warm-dropdown .ant-dropdown-menu-item.admin-feedback-dropdown-item .ant-dropdown-menu-title-content {
  min-width: 0;
  flex: 1 1 auto;
}

.warm-dropdown .ant-dropdown-menu-item.admin-feedback-dropdown-item .admin-menu-feedback-label {
  margin-left: 0;
}

.warm-dropdown .ant-dropdown-menu-item.user-feedback-dropdown-item,
.warm-dropdown .ant-dropdown-menu-item.user-feedback-dropdown-item .ant-dropdown-menu-title-content {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.warm-dropdown .ant-dropdown-menu-item.user-feedback-dropdown-item .ant-dropdown-menu-title-content {
  min-width: 0;
  flex: 1 1 auto;
}

.warm-dropdown .ant-dropdown-menu-item-danger {
  color: #c85a49 !important;
}

.warm-dropdown .ant-dropdown-menu-item-danger span,
.warm-dropdown .ant-dropdown-menu-item-danger a,
.warm-dropdown .ant-dropdown-menu-item-danger .ant-dropdown-menu-title-content {
  color: inherit !important;
}

.warm-dropdown .ant-dropdown-menu-item-danger:hover {
  background: linear-gradient(180deg, #fff4f1, #ffede8) !important;
  color: #b84b3b !important;
}

.warm-dropdown .ant-dropdown-menu-item-divider {
  margin: 8px 2px;
  background: var(--theme-border);
}

.warm-dropdown .ant-dropdown-menu-item-group-title {
  padding: 10px 16px 6px !important;
  color: var(--theme-text-muted) !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  line-height: 1.2 !important;
}

.warm-dropdown .theme-menu-item-title {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-width: 0;
}

.warm-dropdown .theme-menu-check {
  color: var(--theme-accent) !important;
  font-size: 14px;
}

.warm-dropdown .ant-dropdown-menu-item.theme-style-menu-item,
.warm-dropdown .ant-dropdown-menu-item.theme-style-menu-item .ant-dropdown-menu-title-content,
.warm-dropdown .theme-style-entry,
.warm-dropdown .theme-style-entry > span {
  overflow: visible;
  white-space: nowrap;
  word-break: keep-all;
}

.warm-dropdown .ant-dropdown-menu-item.theme-style-menu-item .ant-dropdown-menu-title-content {
  position: static;
  width: 100%;
  min-width: max-content;
}

.warm-dropdown .ant-dropdown-menu-item.theme-style-menu-item .ant-dropdown-trigger,
.warm-dropdown .ant-dropdown-menu-item.theme-style-menu-item .theme-style-entry {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  width: 100%;
  height: 100%;
  padding-inline-start: 40px;
  box-sizing: border-box;
}

.warm-dropdown .theme-style-overlay {
  top: auto !important;
  right: auto !important;
  bottom: 0 !important;
  left: 100% !important;
  z-index: 1400 !important;
}

.theme-style-overlay .theme-style-panel {
  min-width: 176px;
  max-height: none;
  padding: 12px 10px;
  overflow: visible;
  border-radius: 18px;
  border: 1px solid var(--theme-panel-border);
  background: linear-gradient(180deg, var(--theme-panel-bg), var(--theme-panel-bg-soft));
  box-shadow: 0 16px 28px var(--theme-shadow-soft);
}

.theme-swatch-tooltip {
  z-index: 1400 !important;
}

.theme-swatch-tooltip .ant-tooltip-inner {
  min-width: 228px;
  padding: 12px;
  border: 1px solid var(--theme-panel-border);
  border-radius: 14px;
  background: var(--theme-panel-bg);
  box-shadow: 0 16px 28px var(--theme-shadow-soft);
  color: var(--theme-title);
}

.theme-swatch-tooltip .ant-tooltip-arrow::before,
.theme-swatch-tooltip .ant-tooltip-arrow::after {
  background: var(--theme-panel-bg);
}

.theme-menu-swatches {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  width: 220px;
}

.theme-menu-swatch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.theme-menu-swatch-chip {
  display: block;
  width: 100%;
  height: 28px;
  border: 1px solid var(--theme-panel-border-strong);
  border-radius: 8px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.24);
}

.theme-menu-swatch > span:last-child {
  overflow: hidden;
  max-width: 100%;
  color: var(--theme-text-muted);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-user-notice-card.ant-notification-notice {
  overflow: hidden;
}

.app-user-notice-card.ant-notification-notice .ant-notification-notice-content {
  margin-right: 8px;
}

.app-user-notice-card.ant-notification-notice .ant-notification-notice-with-icon {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  column-gap: 15px;
  align-items: start;
}

.app-user-notice-card.ant-notification-notice .ant-notification-notice-icon {
  position: static;
  margin: 2px 0 0;
  line-height: 1;
  grid-row: 1 / span 2;
}

.app-user-notice-card.ant-notification-notice .ant-notification-notice-message {
  margin-bottom: 10px;
  margin-inline-start: 0;
  padding-right: 36px;
  color: var(--theme-title);
  font-size: 16px;
  font-weight: 800;
  line-height: 1.25;
}

.app-user-notice-card.ant-notification-notice .ant-notification-notice-description {
  margin-inline-start: 0;
  padding-right: 36px;
  color: var(--theme-text-primary);
  font-size: 13px;
  line-height: 1.65;
}

.app-user-notice-card.ant-notification-notice .ant-notification-notice-close {
  top: 20px;
  inset-inline-end: 18px;
  color: var(--theme-accent-text);
}

.app-user-notice-card.ant-notification-notice .ant-notification-notice-close:hover {
  color: var(--theme-accent-text-hover);
}

.app-user-notice-card.ant-notification-notice .ant-notification-notice-close-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
