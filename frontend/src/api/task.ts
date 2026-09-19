import client from "./client";
import type { TaskItem, TaskDetail, TimelineEvent, PaginatedData } from "@/types";

export const taskApi = {
  getMyTasks: (params?: { status?: string; type?: string; page?: number; page_size?: number }) =>
    client.get("/tasks/my", { params }) as Promise<PaginatedData<TaskItem> & { pending_count: number; approving_count: number }>,

  getPendingApproval: (params?: { page?: number; page_size?: number }) =>
    client.get("/tasks/pending-approval", { params }) as Promise<PaginatedData<TaskItem>>,

  getTaskDetail: (taskId: string) =>
    client.get(`/tasks/${taskId}`) as Promise<TaskDetail>,

  cancelTask: (taskId: string) =>
    client.post(`/tasks/${taskId}/cancel`) as Promise<{ id: string; status: string }>,

  approveTask: (
    taskId: string,
    payload: { action: "approve" | "reject" | "add_sign"; comment?: string; add_sign_user_id?: string }
  ) =>
    client.post(`/tasks/${taskId}/approve`, payload) as Promise<{
      id: string;
      action: string;
      status: string;
    }>,

  getTimeline: (taskId: string) =>
    client.get(`/tasks/${taskId}/timeline`) as Promise<{ task_id: string; timeline: TimelineEvent[] }>,
};
