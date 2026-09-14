import { createRouter, createWebHistory } from "vue-router";
import AppLayout from "@/components/layout/AppLayout.vue";
import GenerateEntry from "@/views/GenerateEntry.vue";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/",
      component: AppLayout,
      children: [
        {
          path: "",
          name: "Home",
          component: () => import("@/views/HomeView.vue"),
        },
        {
          path: "templates",
          name: "Templates",
          component: () => import("@/views/TemplatesView.vue"),
        },
        {
          path: "generate",
          name: "Generate",
          meta: { deferHeavyPage: true },
          component: GenerateEntry,
        },
        {
          path: "video-generate",
          name: "VideoGenerate",
          meta: { deferHeavyPage: true },
          component: () => import("@/views/VideoGenerateEntry.vue"),
        },
        {
          path: "chat/:sessionId?",
          name: "Chat",
          meta: { requiresAuth: true },
          component: () => import("@/views/ChatView.vue"),
        },
        {
          path: "canvas",
          name: "Canvas",
          meta: { requiresAuth: true },
          component: () => import("@/views/CanvasListView.vue"),
        },
        {
          path: "canvas/:projectId",
          name: "CanvasDetail",
          meta: { requiresAuth: true, hideTopMenu: true, workbenchLayout: true },
          component: () => import("@/views/CanvasView.vue"),
          props: (route) => ({ projectId: String(route.params.projectId || "") }),
        },
        {
          path: "batch-generate",
          name: "BatchGenerate",
          component: () => import("@/views/BatchGenerateView.vue"),
        },
        {
          path: "tutorial",
          redirect: "/tutorial/general",
        },
        {
          path: "tutorial/:module",
          name: "Tutorial",
          component: () => import("@/views/TutorialView.vue"),
        },
        {
          path: "history",
          name: "HistoryBoards",
          component: () => import("@/views/HistoryBoardsView.vue"),
        },
        {
          path: "history/board/default",
          name: "HistoryDefaultBoard",
          component: () => import("@/views/HistoryView.vue"),
          props: { boardKey: "default" },
        },
        {
          path: "history/board/:boardId",
          name: "HistoryBoardDetail",
          component: () => import("@/views/HistoryView.vue"),
          props: (route) => ({ boardKey: `board:${route.params.boardId}` }),
        },
        {
          path: "profile",
          name: "Profile",
          meta: { requiresAuth: true },
          component: () => import("@/views/ProfileView.vue"),
        },
        {
          path: "credit-logs",
          name: "CreditLogs",
          meta: { requiresAuth: true },
          component: () => import("@/views/CreditLogsView.vue"),
        },
        {
          path: "promo-codes",
          name: "PromoCodes",
          meta: { requiresAuth: true },
          component: () => import("@/views/PromoCodesView.vue"),
        },
        {
          path: "invite-rewards",
          name: "InviteRewards",
          meta: { requiresAuth: true },
          component: () => import("@/views/InviteRewardsView.vue"),
        },
        {
          path: "payment-result",
          name: "PaymentResult",
          component: () => import("@/views/PaymentResultView.vue"),
        },
        {
          path: "api-keys",
          name: "ApiKeys",
          meta: { requiresAuth: true },
          component: () => import("@/views/ApiKeysView.vue"),
        },
        {
          path: "feedbacks",
          name: "FeedbackList",
          meta: { requiresAuth: true },
          component: () => import("@/views/FeedbackListView.vue"),
        },
        {
          path: "feedbacks/:feedbackId",
          name: "FeedbackDetail",
          meta: { requiresAuth: true },
          component: () => import("@/views/FeedbackDetailView.vue"),
        },
        {
          path: "system-messages",
          name: "SystemMessageList",
          meta: { requiresAuth: true },
          component: () => import("@/views/SystemMessageListView.vue"),
        },
        {
          path: "system-messages/:messageId",
          name: "SystemMessageDetail",
          meta: { requiresAuth: true },
          component: () => import("@/views/SystemMessageDetailView.vue"),
        },
        {
          path: "user-agreement",
          name: "UserAgreement",
          meta: { hideTopMenu: true },
          component: () => import("@/views/LegalDocumentView.vue"),
        },
        {
          path: "privacy-policy",
          name: "PrivacyPolicy",
          meta: { hideTopMenu: true },
          component: () => import("@/views/LegalDocumentView.vue"),
        },
        {
          path: "settings",
          name: "Settings",
          meta: { requiresAuth: true },
          component: () => import("@/views/admin/ApiKeyView.vue"),
        },
        {
          path: "admin/templates",
          name: "TemplateManage",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/TemplateManageView.vue"),
        },
        {
          path: "admin/prompt-optimize",
          name: "AdminPromptOptimizeManage",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/PromptOptimizeManageView.vue"),
        },
        {
          path: "admin/users",
          name: "UserManage",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/UserManageView.vue"),
        },
        {
          path: "admin/redeem-keys",
          name: "RedeemKeyManage",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/RedeemKeyManageView.vue"),
        },
        {
          path: "admin/ledger",
          name: "AdminLedger",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/LedgerView.vue"),
        },
        {
          path: "admin/revenue",
          name: "AdminRevenue",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/RevenueView.vue"),
        },
        {
          path: "admin/invite-rewards",
          name: "AdminInviteRewards",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/InviteRewardStatsView.vue"),
        },
        {
          path: "admin/promo-stats",
          name: "AdminPromoStats",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/PromoStatsView.vue"),
        },
        {
          path: "admin/payment-orders",
          name: "AdminPaymentOrders",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/PaymentOrderManageView.vue"),
        },
        {
          path: "admin/user-tasks",
          name: "AdminUserTasks",
          meta: { requiresAdmin: true },
          component: () => import("@/views/HistoryView.vue"),
          props: { adminUserTasks: true },
        },
        {
          path: "admin/user-videos",
          name: "AdminUserVideos",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/UserVideosPlaceholderView.vue"),
        },
        {
          path: "admin/user-canvases",
          name: "AdminUserCanvases",
          meta: { requiresAdmin: true },
          component: () => import("@/views/CanvasListView.vue"),
          props: { adminCanvases: true },
        },
        {
          path: "admin/user-conversations/:sessionId?",
          name: "AdminUserConversations",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/AdminUserConversationsView.vue"),
        },
        {
          path: "admin/example-canvases",
          name: "AdminExampleCanvases",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/ExampleCanvasManageView.vue"),
        },
        {
          path: "admin/user-canvases/:projectId",
          name: "AdminUserCanvasDetail",
          meta: { requiresAdmin: true, hideTopMenu: true, workbenchLayout: true },
          component: () => import("@/views/CanvasView.vue"),
          props: (route) => ({ projectId: String(route.params.projectId || "") }),
        },
        {
          path: "admin/dashboard",
          name: "AdminDashboard",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/AdminOverviewDashboardView.vue"),
        },
        {
          path: "admin/image-dashboard",
          name: "AdminImageDashboard",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/DashboardView.vue"),
        },
        {
          path: "admin/video-dashboard",
          name: "AdminVideoDashboard",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/VideoDashboardPlaceholderView.vue"),
        },
        {
          path: "admin/error-analytics",
          name: "AdminErrorAnalytics",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/ErrorAnalyticsView.vue"),
        },
        {
          path: "admin/general-settings",
          name: "AdminGeneralSettings",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/GeneralSettingsView.vue"),
        },
        {
          path: "admin/feedbacks",
          name: "AdminFeedbackManage",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/FeedbackManageView.vue"),
        },
        {
          path: "admin/feedbacks/:feedbackId",
          name: "AdminFeedbackDetail",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/FeedbackDetailView.vue"),
        },
        {
          path: "admin/system-messages",
          name: "AdminSystemMessageManage",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/SystemMessageManageView.vue"),
        },
        {
          path: "admin/update-logs",
          name: "AdminUpdateLogManage",
          meta: { requiresAdmin: true },
          component: () => import("@/views/admin/UpdateLogManageView.vue"),
        },
        {
          path: "admin/api-key",
          redirect: "/admin/general-settings",
        },
        {
          path: "admin/cos-config",
          name: "CosConfigManage",
          meta: { requiresSuperAdmin: true },
          component: () => import("@/views/admin/CosConfigView.vue"),
        },
        {
          path: "admin/external-api-configs",
          name: "ExternalApiConfigManage",
          meta: { requiresSuperAdmin: true },
          component: () => import("@/views/admin/ExternalApiConfigView.vue"),
        },
        {
          path: "admin/generation-scene-categories",
          name: "GenerationSceneCategoryManage",
          meta: { requiresSuperAdmin: true },
          component: () => import("@/views/admin/GenerationSceneCategoryView.vue"),
        },
        {
          path: "admin/video-api-configs",
          name: "VideoApiConfigManage",
          meta: { requiresSuperAdmin: true },
          component: () => import("@/views/admin/VideoApiConfigView.vue"),
        },
        {
          path: "admin/chat-api-configs",
          name: "ChatApiConfigManage",
          meta: { requiresSuperAdmin: true },
          component: () => import("@/views/admin/ChatApiConfigView.vue"),
        },
      ],
    },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { name: "Home" };
  }
  if (to.meta.requiresSuperAdmin && !auth.isSuperAdmin) {
    return { name: "Templates" };
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: "Templates" };
  }
});

export default router;
