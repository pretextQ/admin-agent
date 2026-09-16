import { useState, type KeyboardEvent } from "react";
import { Button, Input } from "@douyinfe/semi-ui";
import { IconSend } from "@douyinfe/semi-icons";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        padding: "12px 16px",
        borderTop: "1px solid #f0f0f0",
        background: "#fff",
      }}
    >
      <Input
        value={value}
        onChange={setValue}
        onKeyDown={handleKeyDown}
        placeholder="输入消息..."
        disabled={disabled}
        style={{ flex: 1 }}
      />
      <Button
        theme="solid"
        type="primary"
        icon={<IconSend />}
        onClick={handleSend}
        disabled={disabled || !value.trim()}
      />
    </div>
  );
}
