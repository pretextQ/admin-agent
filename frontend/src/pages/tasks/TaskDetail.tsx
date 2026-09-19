import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button, Tag, Timeline, Spin, Descriptions } from "@douyinfe/semi-ui";
import { IconArrowLeft } from "@douyinfe/semi-icons";
import { taskApi } from "@/api";
import type { TaskDetail as TaskDetailType, TimelineEvent } from "@/types";

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  approving: "审批中",
  completed: "已完成",
  failed: "已失败（含驳回）",
  cancelled: "已取消",
};

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<TaskDetailType | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);

  const load = useCallback(
    async (taskId: string) => {
      setLoading(true);
      try {
        const [taskData, timelineData] = await Promise.all([
          taskApi.getTaskDetail(taskId),
          taskApi.getTimeline(taskId),
        ]);
        setTask(taskData);
        setTimeline(timelineData.timeline);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (id) load(id);
  }, [id, load]);

  const handleApprove = useCallback(
    async (action: "approve" | "reject") => {
      if (!id) return;
      setActing(true);
      try {
        await taskApi.approveTask(id, { action });
        await load(id);
      } catch {
        // 失败时保留当前状态，用户可重试
      } finally {
        setActing(false);
      }
    },
    [id, load]
  );

  const handleCancel = useCallback(async () => {
    if (!id) return;
    setActing(true);
    try {
      await taskApi.cancelTask(id);
      await load(id);
    } catch {
      // ignore
    } finally {
      setActing(false);
    }
  }, [id, load]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!task) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <p>任务不存在</p>
        <Button onClick={() => navigate(-1)}>返回</Button>
      </div>
    );
  }

  return (
    <div style={{ padding: "0 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <Button
          icon={<IconArrowLeft />}
          theme="borderless"
          onClick={() => navigate(-1)}
        />
        <span style={{ fontWeight: 600, fontSize: 16 }}>任务详情</span>
      </div>

      <Descriptions
        data={[
          { key: "标题", value: task.title || "未命名" },
          { key: "类型", value: task.type || "-" },
          {
            key: "状态",
            value: (
              <Tag color={task.status === "completed" ? "green" : task.status === "failed" ? "red" : "blue"}>
                {STATUS_LABELS[task.status || ""] || task.status}
              </Tag>
            ),
          },
          { key: "风险等级", value: task.risk_level },
          {
            key: "创建时间",
            value: task.created_at ? new Date(task.created_at).toLocaleString() : "-",
          },
          {
            key: "完成时间",
            value: task.completed_at ? new Date(task.completed_at).toLocaleString() : "-",
          },
        ]}
      />

      {task.approvals && task.approvals.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h4 style={{ marginBottom: 12 }}>审批链</h4>
          {task.approvals.map((a) => (
            <div
              key={a.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                padding: "8px 0",
                borderBottom: "1px solid #f0f0f0",
                fontSize: 13,
              }}
            >
              <span>步骤 {a.step} - {a.approver_id}</span>
              <Tag
                size="small"
                color={a.status === "approved" ? "green" : a.status === "pending" ? "blue" : "red"}
              >
                {a.action || a.status}
              </Tag>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 24 }}>
        <h4 style={{ marginBottom: 12 }}>时间线</h4>
        <Timeline>
          {timeline.map((event, idx) => (
            <Timeline.Item
              key={idx}
              time={event.timestamp ? new Date(event.timestamp).toLocaleString() : ""}
            >
              <div>{event.description}</div>
              {event.comment && (
                <div style={{ fontSize: 12, color: "#999", marginTop: 4 }}>{event.comment}</div>
              )}
            </Timeline.Item>
          ))}
        </Timeline>
      </div>

      {(task.can_approve || (task.is_owner && task.status === "approving")) && (
        <div style={{ marginTop: 24, display: "flex", gap: 12 }}>
          {task.can_approve && (
            <>
              <Button theme="solid" type="primary" loading={acting} onClick={() => handleApprove("approve")}>
                同意
              </Button>
              <Button type="danger" loading={acting} onClick={() => handleApprove("reject")}>
                驳回
              </Button>
            </>
          )}
          {task.is_owner && task.status === "approving" && (
            <Button loading={acting} onClick={handleCancel}>
              取消任务
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
