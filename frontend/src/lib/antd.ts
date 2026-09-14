import type { App } from "vue";

let appRef: App | null = null;
let extendedAntdRegistration: Promise<void> | null = null;

function requireAntdApp() {
  if (!appRef) {
    throw new Error("Ant Design app is not bound");
  }
  return appRef;
}

export function bindAntdApp(app: App) {
  appRef = app;
}

export function registerExtendedAntdComponents() {
  if (extendedAntdRegistration) return extendedAntdRegistration;

  extendedAntdRegistration = import("./antd-extended").then(({ registerExtendedAntd }) => {
    registerExtendedAntd(requireAntdApp());
  }).catch((error) => {
    extendedAntdRegistration = null;
    throw error;
  });

  return extendedAntdRegistration;
}

export async function importAfterExtendedAntd<T>(loader: () => Promise<T>): Promise<T> {
  await registerExtendedAntdComponents();
  return loader();
}

export function scheduleExtendedAntdPreload() {
  window.setTimeout(() => {
    void registerExtendedAntdComponents().catch((error) => {
      console.warn("Failed to preload extended Ant Design components", error);
    });
  }, 0);
}
