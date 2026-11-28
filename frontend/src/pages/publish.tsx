import type { Role } from "@/lib/sample-data";
import { ApiRegisterForm } from "@/pages/api-register";

// 카탈로그 등록 > API 등록. 타겟 시스템이 직접 개발한 MCP 서버는 'MCP 등록', API를 MCP로 여는 것은 'MCP 변환'.
export function PublishPage({ role }: { role: Role }) {
  return <ApiRegisterForm role={role} />;
}
