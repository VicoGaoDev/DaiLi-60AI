import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { UserInfo } from "@/types";
import { clearStoredAuth, getStoredToken, getStoredUser, persistAuth, persistUser } from "@/lib/auth";

export const useAuthStore = defineStore("auth", () => {
  const token = ref(getStoredToken());
  const user = ref<UserInfo | null>(getStoredUser());

  const isLoggedIn = computed(() => !!token.value);
  const isSuperAdmin = computed(() => user.value?.role === "superadmin");
  const isAdmin = computed(() => user.value?.role === "admin" || user.value?.role === "superadmin");

  function setAuth(t: string, u: UserInfo) {
    token.value = t;
    user.value = u;
    persistAuth(t, u);
  }

  function updateUser(next: UserInfo) {
    user.value = next;
    persistUser(next);
  }

  function logout() {
    token.value = "";
    user.value = null;
    clearStoredAuth();
  }

  return { token, user, isLoggedIn, isAdmin, isSuperAdmin, setAuth, updateUser, logout };
});
