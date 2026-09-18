import "vue-router";

declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean;
    requiresAdmin?: boolean;
    requiresSuperAdmin?: boolean;
    requiresAgent?: boolean;
    hideTopMenu?: boolean;
    workbenchLayout?: boolean;
    deferHeavyPage?: boolean;
  }
}
