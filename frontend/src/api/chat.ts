import client from "./client";
import type { ChatResponse } from "@/types";

export const chatApi = {
  sendMessage: (data: { message: string; conversation_id?: string }) =>
    client.post("/chat/send", data) as Promise<ChatResponse>,

  getHistory: (conversationId: string) =>
    client.get(`/chat/history/${conversationId}`),

  confirmAction: (taskId: string, confirmed: boolean) =>
    client.post(`/chat/confirm/${taskId}`, { confirmed }) as Promise<ChatResponse>,

  transferToHuman: (conversationId: string) =>
    client.post(`/chat/transfer/${conversationId}`) as Promise<ChatResponse>,
};
