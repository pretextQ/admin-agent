import { useEffect, useRef } from "react";
import { Spin } from "@douyinfe/semi-ui";
import type { Message } from "@/types";
import MessageBubble from "./MessageBubble";

interface MessageListProps {
  messages: Message[];
  isTyping: boolean;
  onConfirm?: (confirmed: boolean) => void;
}

export default function MessageList({ messages, isTyping, onConfirm }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "16px 12px",
      }}
    >
      {messages.length === 0 && (
        <div style={{ textAlign: "center", color: "#999", paddingTop: 80 }}>
          <p style={{ fontSize: 16, marginBottom: 8 }}>你好，我是行政助手</p>
          <p style={{ fontSize: 13 }}>请问有什么可以帮您？</p>
        </div>
      )}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onConfirm={onConfirm} />
      ))}
      {isTyping && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#999", fontSize: 13 }}>
          <Spin size="small" />
          <span>助手正在输入...</span>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
