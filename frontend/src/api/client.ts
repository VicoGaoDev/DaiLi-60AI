import axios from "axios";
import router from "@/router";
import { clearStoredAuth, getStoredToken } from "@/lib/auth";
import { isSessionExpiredError } from "@/lib/authError";
import { emitAuthSessionExpiredNotice } from "@/lib/authSessionNotice";

const BASE = import.meta.env.VITE_API_BASE_URL || "";

const client = axios.create({
  baseURL: `${BASE}/api`,
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (res) => res.data,
  (error) => {
    if (isSessionExpiredError(error)) {
      const url = String(error.config?.url ?? "");
      const isAuthCredentialsRequest =
        url.includes("/auth/login") || url.includes("/auth/register");
      if (!isAuthCredentialsRequest) {
        clearStoredAuth();
        emitAuthSessionExpiredNotice(router.currentRoute.value.fullPath);
      }
    }
    return Promise.reject(error);
  }
);

export default client;
