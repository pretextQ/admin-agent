import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Tabs, Tag, Empty, Spin, List } from "@douyinfe/semi-ui";
import { taskApi } from "@/api";
import type { TaskItem, TaskStatus } from "@/types";

const STATUS_COLORS: Record<string, string> = {
  pending: "blue",
  approving: "orange",
  completed: "green",
  failed: "red",
  cancelled: "grey",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  approving: "审批中",
  completed: "已完成",
  failed: "已失败（含驳回）",
  cancelled: "已取消",
};

export default function TaskList() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<"mine" | "approval">("mine");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === "mine") {
        const resp = await taskApi.getMyTasks({
          status: statusFilter || undefined,
          page: 1,
          page_size: 50,
        });
        setTasks(resp.items);
        setTotal(resp.total);
      } else {
        const resp = await taskApi.getPendingApproval({ page: 1, page_size: 50 });
        setTasks(resp.items);
        setTotal(resp.total);
      }
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab, statusFilter]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  return (
    <div style={{ padding: "0 12px" }}>
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as "mine" | "approval")}
      >
        <Tabs.TabPane tab="我发起的" itemKey="mine" />
        <Tabs.TabPane tab="待我审批" itemKey="approval" />
      </Tabs>

      {activeTab === "mine" && (
        <div style={{ display: "flex", gap: 8, margin: "12px 0" }}>
          {["", "pending", "approving", "completed", "failed"].map((s) => (
            <Tag
              key={s}
              size="small"
              color={s === statusFilter ? "blue" : "grey"}
              style={{ cursor: "pointer" }}
              onClick={() => setStatusFilter(s)}
            >
              {s ? STATUS_LABELS[s] : "全部"}
            </Tag>
          ))}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin />
        </div>
      ) : tasks.length === 0 ? (
        <Empty description="暂无任务" />
      ) : (
        <List
          dataSource={tasks}
          renderItem={(item) => (
            <List.Item
              style={{ cursor: "pointer", padding: "12px 0" }}
              onClick={() => navigate(`/tasks/${item.id}`)}
            >
              <div style={{ width: "100%" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontWeight: 500 }}>{item.title || "未命名任务"}</span>
                  <Tag size="small" color={STATUS_COLORS[item.status || ""]}>
                    {STATUS_LABELS[item.status || ""] || item.status}
                  </Tag>
                </div>
                <div style={{ fontSize: 12, color: "#999" }}>
                  {item.type && <span style={{ marginRight: 12 }}>类型：{item.type}</span>}
                  {item.created_at && <span>{new Date(item.created_at).toLocaleString()}</span>}
                </div>
              </div>
            </List.Item>
          )}
        />
      )}

      {total > 0 && (
        <div style={{ textAlign: "center", padding: 12, color: "#999", fontSize: 12 }}>
          共 {total} 条
        </div>
      )}
    </div>
  );
}
