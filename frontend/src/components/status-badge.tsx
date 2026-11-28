import { Badge, type BadgeProps } from "@/components/ui/badge";

const MAP: Record<string, BadgeProps["variant"]> = {
  운영: "success",
  승인: "success",
  "색인 완료": "success",
  저장: "outline",
  스테이지: "info",
  "승인 대기": "warning",
  "색인 중": "warning",
  반려: "danger",
  실패: "danger",
  중지: "secondary",
  해지: "secondary",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={MAP[status] ?? "outline"}>{status}</Badge>;
}
