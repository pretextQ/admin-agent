import { Avatar } from "@douyinfe/semi-ui";
import { IconUser, IconRobot } from "@douyinfe/semi-icons";
import type { Message } from "@/types";
import ConfirmCard from "./ConfirmCard";

interface MessageBubbleProps {
  message: Message;
  onConfirm?: (confirmed: boolean) => void;
}

export default function MessageBubble({ message, onConfirm }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 16,
        gap: 8,
      }}
    >
      {!isUser && (
        <Avatar size="small" style={{ background: "#3370ff", flexShrink: 0 }}>
          <IconRobot />
        </Avatar>
      )}
      <div style={{ maxWidth: "75%" }}>
        {message.card_data && onConfirm ? (
          <ConfirmCard
            cardData={message.card_data}
            onConfirm={() => onConfirm(true)}
            onCancel={() => onConfirm(false)}
          />
        ) : (
          <div
            style={{
              padding: "8px 12px",
              borderRadius: 12,
              background: isUser ? "#3370ff" : "#f5f5f5",
              color: isUser ? "#fff" : "#333",
              fontSize: 14,
              lineHeight: 1.6,
              wordBreak: "break-word",
            }}
          >
            {message.content}
          </div>
        )}
      </div>
      {isUser && (
        <Avatar size="small" style={{ background: "#34c724", flexShrink: 0 }}>
          <IconUser />
        </Avatar>
      )}
    </div>
  );
}
