/// <reference types="vite/client" />

declare module "*.json" {
  const value: any;
  export default value;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

declare module "@wangeditor/editor-for-vue" {
  import type { DefineComponent } from "vue";

  export const Editor: DefineComponent<Record<string, unknown>, Record<string, unknown>, any>;
  export const Toolbar: DefineComponent<Record<string, unknown>, Record<string, unknown>, any>;
}
