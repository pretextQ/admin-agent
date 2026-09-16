import { Empty as SemiEmpty } from "@douyinfe/semi-ui";

interface EmptyProps {
  description?: string;
}

export default function Empty({ description = "暂无数据" }: EmptyProps) {
  return (
    <div style={{ padding: "80px 0", textAlign: "center" }}>
      <SemiEmpty description={description} />
    </div>
  );
}
