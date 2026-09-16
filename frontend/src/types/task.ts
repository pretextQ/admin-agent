export type TaskStatus = "pending" | "approving" | "completed" | "failed" | "cancelled";
export type TaskType = "leave" | "expense" | "travel" | "meeting_room" | "vehicle" | "material" | "asset" | "seal" | "certificate" | "onboarding";

export interface TaskItem {
  id: string;
  type: TaskType | null;
  status: TaskStatus | null;
  title: string | null;
  risk_level: string;
  created_at: string | null;
}

export interface TaskDetail extends TaskItem {
  data: Record<string, unknown> | null;
  external_id: string | null;
  completed_at: string | null;
  approvals: ApprovalItem[];
}

export interface ApprovalItem {
  id: string;
  step: number;
  approver_id: string;
  action: string | null;
  status: string;
  comment: string | null;
  created_at: string | null;
  decided_at: string | null;
}

export interface TimelineEvent {
  event: string;
  timestamp: string | null;
  description: string;
  comment?: string;
}
