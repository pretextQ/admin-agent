import { useLocation, useNavigate } from "react-router-dom";
import { IconComment, IconTickCircle } from "@douyinfe/semi-icons";

const tabs = [
  { key: "/", label: "对话", icon: <IconComment /> },
  { key: "/tasks", label: "任务", icon: <IconTickCircle /> },
];

export default function TabBar() {
  const location = useLocation();
  const navigate = useNavigate();

  const activeKey = location.pathname.startsWith("/tasks") ? "/tasks" : "/";

  return (
    <div
      style={{
        display: "flex",
        borderTop: "1px solid #f0f0f0",
        background: "#fff",
        paddingBottom: "env(safe-area-inset-bottom)",
      }}
    >
      {tabs.map((tab) => {
        const isActive = activeKey === tab.key;
        return (
          <div
            key={tab.key}
            onClick={() => navigate(tab.key)}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "8px 0",
              cursor: "pointer",
              color: isActive ? "#3370ff" : "#999",
              fontSize: 12,
              gap: 2,
            }}
          >
            <span style={{ fontSize: 20 }}>{tab.icon}</span>
            <span>{tab.label}</span>
          </div>
        );
      })}
    </div>
  );
}
