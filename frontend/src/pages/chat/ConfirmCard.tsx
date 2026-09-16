import { Button, Card } from "@douyinfe/semi-ui";

interface ConfirmCardProps {
  cardData: Record<string, unknown>;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmCard({ cardData, onConfirm, onCancel }: ConfirmCardProps) {
  const businessType = cardData.business_type as string;
  const slots = (cardData.slots as Record<string, string>) || {};
  const warning = (cardData.warning as string) || "请确认以下操作";

  const typeLabels: Record<string, string> = {
    leave: "请假申请",
    expense: "报销申请",
    travel: "差旅申请",
    meeting_room: "会议室预定",
    material: "物资领用",
    seal: "用印申请",
    certificate: "证明开具",
  };

  return (
    <Card
      style={{
        background: "#fffbe6",
        border: "1px solid #ffe58f",
        borderRadius: 8,
        maxWidth: 320,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 8 }}>
        {typeLabels[businessType] || businessType}
      </div>
      <div style={{ fontSize: 13, color: "#666", marginBottom: 12 }}>{warning}</div>
      <div style={{ fontSize: 13, marginBottom: 12 }}>
        {Object.entries(slots).map(([key, value]) => (
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
