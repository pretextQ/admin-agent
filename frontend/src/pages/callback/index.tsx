import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Spin } from "@douyinfe/semi-ui";
import { useAuthStore } from "@/stores";
import { authApi } from "@/api";

export default function CallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const login = useAuthStore((s) => s.login);

  // 必须先落 token 再取用户信息：axios 拦截器从 localStorage 读取 token，
  // 否则 getMe 不带 Authorization 头会 401。
  const completeLogin = useCallback(
    async (token: string) => {
      login(token, { user_id: "", employee_id: "", role: "employee" });
      try {
        const userInfo = await authApi.getMe();
        login(token, userInfo);
      } catch {
        // 已持有可用 token，用户信息获取失败不阻断登录
      }
      navigate("/", { replace: true });
    },
    [login, navigate]
  );

  useEffect(() => {
    const jwt = searchParams.get("jwt");
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    async function handleCallback() {
      if (jwt) {
        await completeLogin(jwt);
        return;
      }

      if (code && state) {
        try {
          const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
          const resp = await fetch(
            `${base}/auth/feishu/callback?code=${code}&state=${state}`,
            { redirect: "follow" }
          );
          const data = await resp.json();
          if (data.code === 0 && data.data?.access_token) {
            await completeLogin(data.data.access_token);
          } else {
            setError(data.message || "登录失败");
          }
        } catch {
          setError("网络错误，请重试");
        }
        return;
      }

      setError("无效的回调参数");
    }

    handleCallback();
  }, [searchParams, completeLogin]);

  if (error) {
    return (
      <div style={{ textAlign: "center", paddingTop: 120 }}>
        <p style={{ color: "#f53f3f" }}>{error}</p>
        <a onClick={() => navigate("/login")}>重新登录</a>
      </div>
    );
  }

  return (
    <div style={{ textAlign: "center", paddingTop: 120 }}>
      <Spin size="large" />
      <p style={{ marginTop: 16, color: "#666" }}>正在登录...</p>
    </div>
  );
}
