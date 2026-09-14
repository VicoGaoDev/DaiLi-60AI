import { createApp, nextTick } from "vue";
import { createPinia } from "pinia";
import { message } from "ant-design-vue";
import "ant-design-vue/dist/reset.css";
import App from "./App.vue";
import { bindAntdApp, registerExtendedAntdComponents, scheduleExtendedAntdPreload } from "./lib/antd";
import { registerCoreAntd } from "./lib/antd-core";
import { initializeAppTheme } from "./lib/theme";
import router from "./router";
import "./styles/global.scss";

initializeAppTheme();

message.config({
  duration: 2.4,
  maxCount: 3,
});

const app = createApp(App);
registerCoreAntd(app);
bindAntdApp(app);

router.beforeEach(async (to) => {
  if (to.name === "Home" || to.path === "/" || to.meta.deferHeavyPage) return;
  await registerExtendedAntdComponents();
});

const APP_BOOT_FALLBACK_MS = 8000;
const APP_BOOT_FADE_MS = 400;

let appMounted = false;
let appBootHidden = false;

function mountApp() {
  if (appMounted) return;
  appMounted = true;
  app.mount("#app");
}

function waitForFirstPaint() {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });
}

function hideAppBootScreen() {
  if (appBootHidden) return;
  appBootHidden = true;

  const boot = document.getElementById("app-boot");
  if (!boot) return;

  const remove = () => boot.remove();
  boot.classList.add("is-leaving");
  boot.addEventListener("transitionend", remove, { once: true });
  window.setTimeout(remove, APP_BOOT_FADE_MS);
}

async function revealApp() {
  try {
    await router.isReady();
    await nextTick();
    await waitForFirstPaint();
  } catch {
    mountApp();
  } finally {
    hideAppBootScreen();
    scheduleExtendedAntdPreload();
  }
}

app.use(createPinia());
app.use(router);
mountApp();
window.setTimeout(() => {
  mountApp();
  hideAppBootScreen();
}, APP_BOOT_FALLBACK_MS);
void revealApp();
