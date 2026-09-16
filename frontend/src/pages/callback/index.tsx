import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Spin } from "@douyinfe/semi-ui";
import { useAuthStore } from "@/stores";
import { authApi } from "@/api";

export default function CallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const login = useAuthStore((s) => s.login);

  useEffect(() => {
    const jwt = searchParams.get("jwt");
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    async function handleCallback() {
      if (jwt) {
        try {
          const userInfo = await authApi.getMe();
          login(jwt, userInfo);
          navigate("/", { replace: true });
          return;
        } catch {
          setError("登录失败，请重试");
          return;
        }
      }

      if (code && state) {
        try {
          const resp = await fetch(
            `${import.meta.env.VITE_API_BASE_URL}/auth/feishu/callback?code=${code}&state=${state}`,
            { redirect: "follow" }
          );
          const data = await resp.json();
          if (data.code === 0 && data.data?.access_token) {
            const userInfo = await authApi.getMe();
            login(data.data.access_token, userInfo);
            navigate("/", { replace: true });
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
  }, [searchParams, navigate, login]);

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
