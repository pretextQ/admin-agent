import { useCallback } from "react";
import { Message } from "@/types";
import { chatApi } from "@/api";
import { useChatStore } from "@/stores";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

export default function ChatPage() {
  const { messages, isTyping, conversationId, addMessage, setTyping, setConversationId } =
    useChatStore();

  const handleSend = useCallback(
    async (content: string) => {
      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content,
      };
      addMessage(userMsg);
      setTyping(true);

      try {
        const resp = await chatApi.sendMessage({
          message: content,
          conversation_id: conversationId || undefined,
        });

        if (resp.conversation_id && !conversationId) {
          setConversationId(resp.conversation_id);
        }

        const assistantMsg: Message = {
          id: resp.message_id,
          role: "assistant",
          content: resp.content,
          card_data: resp.card_data || undefined,
          requires_action: resp.requires_action,
        };
        addMessage(assistantMsg);
      } catch {
        const errorMsg: Message = {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: "抱歉，发送失败，请稍后重试。",
        };
        addMessage(errorMsg);
      } finally {
        setTyping(false);
      }
    },
    [conversationId, addMessage, setTyping, setConversationId]
  );

  const handleConfirm = useCallback(
    async (confirmed: boolean) => {
      const lastAction = [...messages]
        .reverse()
        .find((m) => m.role === "assistant" && m.requires_action);

      if (!lastAction) return;

      setTyping(true);
      try {
        const resp = await chatApi.confirmAction(
          conversationId || "",
          confirmed
        );

        const assistantMsg: Message = {
          id: resp.message_id,
          role: "assistant",
          content: resp.content,
          card_data: resp.card_data || undefined,
          requires_action: resp.requires_action,
        };
        addMessage(assistantMsg);
      } catch {
        const errorMsg: Message = {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: "操作失败，请稍后重试。",
        };
        addMessage(errorMsg);
      } finally {
        setTyping(false);
      }
    },
    [messages, conversationId, addMessage, setTyping]
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <MessageList messages={messages} isTyping={isTyping} onConfirm={handleConfirm} />
      <ChatInput onSend={handleSend} disabled={isTyping} />
    </div>
  );
}
