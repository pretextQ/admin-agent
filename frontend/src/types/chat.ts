export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  content: string;
  content_type: string;
  card_data: Record<string, unknown> | null;
  requires_action: boolean;
  tool_calls: unknown[];
  suggestions?: string[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  card_data?: Record<string, unknown>;
  requires_action?: boolean;
  created_at?: string;
}
