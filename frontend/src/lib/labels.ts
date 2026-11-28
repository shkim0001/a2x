// 백엔드 코드값 → 화면 표시(한글). StatusBadge는 이 한글 값으로 색을 고른다.
import type { AssetStatus, DataLevel, EffectiveRole, Impact, ReqStatus, ServerEnv, SystemKind, ToolKind } from "./api";
import type { Role } from "./sample-data";

export const ASSET_STATUS: Record<AssetStatus, string> = {
  DRAFT: "저장",
  PENDING: "승인 대기",
  STAGE: "스테이지",
  LIVE: "운영",
  REJECTED: "반려",
  SUSPENDED: "중지",
};
export const REQ_STATUS: Record<ReqStatus, string> = { PENDING: "승인 대기", APPROVED: "승인", REJECTED: "반려", CANCELLED: "해지" };
export const SYSTEM_KIND: Record<SystemKind, string> = { BUSINESS: "업무 시스템", AGENT: "AI Agent" };
export const SERVER_ENV: Record<ServerEnv, string> = { PROD: "운영", STAGE: "검증", DEV: "개발" };
export const DATA_LEVEL: Record<DataLevel, string> = { PUBLIC: "공개", INTERNAL: "사내 일반", CONFIDENTIAL: "대외비" };
export const IMPACT: Record<Impact, string> = { HIGH: "상", MEDIUM: "중", LOW: "하" };
export const TOOL_KIND: Record<ToolKind, string> = { READ: "조회", WRITE: "변경" };
export const ROLE: Record<EffectiveRole, Role> = { USER: "일반 사용자", MANAGER: "시스템 담당자", ADMIN: "admin" };

export const DOC_STATUS: Record<"INDEXING" | "INDEXED" | "FAILED", string> = { INDEXING: "색인 중", INDEXED: "색인 완료", FAILED: "실패" };

export const LIFECYCLE_STEPS: { status: AssetStatus; label: string }[] = [
  { status: "DRAFT", label: "저장" },
  { status: "PENDING", label: "승인" },
  { status: "STAGE", label: "스테이지" },
  { status: "LIVE", label: "운영" },
];

export const fmtDate = (s: string | null | undefined) => (s ? s.slice(0, 10) : "-");
