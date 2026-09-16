import { authApi } from "@/api";
import { useAuthStore } from "@/stores";

export function isFeishuEnv(): boolean {
  return /Lark|Feishu/i.test(navigator.userAgent);
}

export async function redirectToLogin(): Promise<void> {
  const isDev = import.meta.env.DEV;

  if (isDev) {
    try {
      const data = await authApi.devLogin("admin001");
      useAuthStore.getState().login(data.access_token, {
        user_id: "dev",
        employee_id: "admin001",
        role: "admin",
      });
      window.location.href = "/";
    } catch (err) {
      console.error("dev-login failed:", err);
    }
    return;
  }

  try {
    const data = await authApi.getLoginUrl();
    window.location.href = data.login_url;
  } catch (err) {
    console.error("get login url failed:", err);
  }
}
