import { Button, Card } from "@douyinfe/semi-ui";

interface ConfirmCardProps {
  cardData: Record<string, unknown>;
  onConfirm: () => void;
  onCancel: () => void;
}

// 卡片字段与 docs/api/api-spec.md 第 10 节对齐：{ type, title, data, actions, warning }
export default function ConfirmCard({ cardData, onConfirm, onCancel }: ConfirmCardProps) {
  const title = (cardData.title as string) || "请确认以下操作";
  const data = (cardData.data as Record<string, unknown>) || {};
  const warning = (cardData.warning as string) || "";

  return (
    <Card
      style={{
        background: "#fffbe6",
        border: "1px solid #ffe58f",
        borderRadius: 8,
        maxWidth: 320,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{title}</div>
      {warning && (
        <div style={{ fontSize: 13, color: "#b45309", marginBottom: 12 }}>{warning}</div>
      )}
      <div style={{ fontSize: 13, marginBottom: 12 }}>
        {Object.entries(data).map(([key, value]) => (
          <div key={key} style={{ marginBottom: 4 }}>
            <span style={{ color: "#999" }}>{key}：</span>
            <span>{String(value)}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <Button theme="solid" type="primary" size="small" onClick={onConfirm}>
          确认
        </Button>
        <Button size="small" onClick={onCancel}>
          取消
        </Button>
      </div>
    </Card>
  );
}
