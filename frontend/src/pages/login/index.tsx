import { useEffect } from "react";
import { Button } from "@douyinfe/semi-ui";
import { redirectToLogin } from "@/utils/feishu";
import { useAuthStore } from "@/stores";
import { useNavigate } from "react-router-dom";

export default function LoginPage() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/", { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleLogin = async () => {
    await redirectToLogin();
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        gap: 24,
      }}
    >
      <h1 style={{ fontSize: 24, fontWeight: 600 }}>企业行政智能系统</h1>
      <p style={{ color: "#666" }}>AI 行政数字员工</p>
      <Button theme="solid" size="large" onClick={handleLogin}>
        飞书授权登录
      </Button>
    </div>
  );
}
