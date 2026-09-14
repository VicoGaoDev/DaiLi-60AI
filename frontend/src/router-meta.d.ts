import "vue-router";

declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean;
    requiresAdmin?: boolean;
    requiresSuperAdmin?: boolean;
    hideTopMenu?: boolean;
    workbenchLayout?: boolean;
    deferHeavyPage?: boolean;
  }
}
