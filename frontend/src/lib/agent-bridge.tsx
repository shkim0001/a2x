// Agent 패널 ↔ 화면 연결: 화면 문맥(선택한 자산 · 트랜잭션), 자동 채움 제안 전달, 화면에서 Agent에게 질문 보내기.
// 상태는 Portal(App.tsx)이 갖고 Context로 내려준다. 제안 값은 화면이 채우기만 하고 제출은 사용자가 한다.
import { createContext, useContext, useEffect, useRef } from "react";
import type { FormKind, FormSuggestion } from "@/lib/api";

export type AgentFocus = { asset_id?: number; transaction_id?: string };
// 카탈로그 '수정' → 등록 양식 화면으로 이동해 저장된 값을 불러온다
export type EditRequest = { type: "API" | "MCP"; id: number };

export type AgentBridge = {
  focus: AgentFocus;
  setFocus: (f: AgentFocus) => void;
  ask: (message: string) => void; // 패널을 열고 이 메시지를 보낸다
  suggestion: FormSuggestion | null;
  apply: (s: FormSuggestion) => void; // 해당 양식 화면으로 이동해 값을 채운다
  clear: () => void;
  editing: EditRequest | null;
  edit: (r: EditRequest) => void;
  clearEdit: () => void;
  // 카탈로그 사용 신청 화면을 이 자산(들)을 담은 채로 연다(내 권한 '더 신청', Agent의 Tool 신청 안내)
  requesting: number[] | null;
  request: (assetIds: number[]) => void;
  clearRequest: () => void;
};

export const AgentBridgeContext = createContext<AgentBridge | null>(null);

export function useAgentBridge(): AgentBridge {
  const ctx = useContext(AgentBridgeContext);
  if (!ctx) throw new Error("AgentBridgeContext가 없습니다.");
  return ctx;
}

// 이 양식(API · MCP)에 해당하는 수정 요청이 오면 한 번 처리하고 비운다
export function useEditRequest(type: EditRequest["type"], load: (id: number) => void) {
  const { editing, clearEdit } = useAgentBridge();
  const ref = useRef(load);
  ref.current = load;
  useEffect(() => {
    if (editing?.type === type) {
      ref.current(editing.id);
      clearEdit();
    }
  }, [editing, type, clearEdit]);
}

// 사용 신청 요청이 오면 한 번 처리하고 비운다(카탈로그 화면)
export function useRequestOpen(open: (assetIds: number[]) => void) {
  const { requesting, clearRequest } = useAgentBridge();
  const ref = useRef(open);
  ref.current = open;
  useEffect(() => {
    if (requesting) {
      ref.current(requesting);
      clearRequest();
    }
  }, [requesting, clearRequest]);
}

// 이 양식에 해당하는 제안이 오면 한 번 적용하고 비운다(화면이 새로 열릴 때도 적용).
export function useSuggestion(form: FormKind, apply: (s: FormSuggestion) => void) {
  const { suggestion, clear } = useAgentBridge();
  const ref = useRef(apply);
  ref.current = apply;
  useEffect(() => {
    if (suggestion?.form === form) {
      ref.current(suggestion);
      clear();
    }
  }, [suggestion, form, clear]);
}
