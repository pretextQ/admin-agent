import { useCallback } from "react";
import { useAuthStore } from "@/stores";
import { authApi } from "@/api";
import { redirectToLogin } from "@/utils/feishu";

export function useAuth() {
  const { user, isAuthenticated, login, logout } = useAuthStore();

  const handleLogin = useCallback(async () => {
    await redirectToLogin();
  }, []);

  const handleLogout = useCallback(() => {
    logout();
    window.location.href = "/login";
  }, [logout]);

  const fetchUser = useCallback(async () => {
    try {
      const userInfo = await authApi.getMe();
      const token = useAuthStore.getState().getToken();
      if (token) {
        login(token, userInfo);
      }
      return userInfo;
    } catch {
      return null;
    }
  }, [login]);

  return {
    user,
    isAuthenticated,
    login: handleLogin,
    logout: handleLogout,
    fetchUser,
  };
}
