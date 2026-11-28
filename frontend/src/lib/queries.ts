// TanStack Query 훅. 변경(mutation) 후에는 데이터 목록을 모두 새로고친다(me 제외).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  get,
  qs,
  type AssetDetail,
  type AssetSummary,
  type CallDetail,
  type CallPage,
  type ConsultDocOut,
  type MonitoringSummary,
  type StatRow,
  type ConnectionOut,
  type Me,
  type ServerRow,
  type SubscriptionOut,
  type SystemOut,
  type ToolRequestOut,
  type ToolSuggestion,
  type UserBrief,
  type Instances,
} from "./api";

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await get<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

export const useSystems = (p: { q?: string; kind?: string; process?: string; mine?: boolean } = {}) =>
  useQuery({ queryKey: ["systems", p], queryFn: () => get<SystemOut[]>(`/systems${qs(p)}`) });

export const useServers = (p: { q?: string; env?: string; process?: string; mine?: boolean } = {}) =>
  useQuery({ queryKey: ["servers", p], queryFn: () => get<ServerRow[]>(`/servers${qs(p)}`) });

export const useAssets = (p: { q?: string; type?: string; status?: string } = {}) =>
  useQuery({ queryKey: ["assets", p], queryFn: () => get<AssetSummary[]>(`/assets${qs(p)}`) });

export const useAsset = (id: number | null | undefined) =>
  useQuery({ queryKey: ["asset", id], queryFn: () => get<AssetDetail>(`/assets/${id}`), enabled: !!id });

export const useSubscriptions = (p: { scope: string; status?: string; q?: string }) =>
  useQuery({ queryKey: ["subs", p], queryFn: () => get<SubscriptionOut[]>(`/subscriptions${qs(p)}`) });

export const useToolRequests = (p: { scope: string; status?: string; q?: string }) =>
  useQuery({ queryKey: ["toolreqs", p], queryFn: () => get<ToolRequestOut[]>(`/tool-requests${qs(p)}`) });

export const useConnections = () => useQuery({ queryKey: ["connections"], queryFn: () => get<ConnectionOut[]>("/connections") });

export const useConvertPreview = (apiId: number | null) =>
  useQuery({ queryKey: ["convert-preview", apiId], queryFn: () => get<ToolSuggestion[]>(`/assets/${apiId}/convert/preview`), enabled: !!apiId });

// 모니터링: 호출 로그는 계속 쌓이므로 1분마다 새로고친다
// 기간: days(최근 N일, 끝은 지금) 또는 start · end("YYYY-MM-DDTHH:mm", KST)
export const useCalls = (p: { kind?: "API" | "MCP"; status?: "success" | "failed"; q?: string; days?: number; start?: string; end?: string; page?: number; size?: number }) =>
  useQuery({
    queryKey: ["calls", p],
    queryFn: () => get<CallPage>(`/monitoring/calls${qs(p)}`),
    refetchInterval: 60_000,
    placeholderData: (prev) => prev, // 페이지를 넘길 때 이전 페이지를 잠깐 보여 깜빡임을 줄인다
  });

export const useCallDetail = (txId: string | null) =>
  useQuery({ queryKey: ["call", txId], queryFn: () => get<CallDetail>(`/monitoring/calls/${encodeURIComponent(txId!)}`), enabled: !!txId });

// start · end: "YYYY-MM-DD"(월별은 그 날짜가 속한 달). 없으면 일별 최근 30일 · 월별 최근 12개월
export const useCallStats = (unit: "daily" | "monthly", start?: string, end?: string) =>
  useQuery({
    queryKey: ["call-stats", unit, start, end],
    queryFn: () => get<StatRow[]>(`/monitoring/stats${qs({ unit, start, end })}`),
    placeholderData: (prev) => prev,
  });

// 인스턴스 모니터링: 15초마다 자동 점검(auto=false면 멈춤). enabled=false면 부르지 않는다(일반 사용자)
export const useInstances = (auto = true, enabled = true) =>
  useQuery({ queryKey: ["instances"], queryFn: () => get<Instances>("/monitoring/instances"), refetchInterval: auto ? 15_000 : false, enabled });

export const useMonitoringSummary = () =>
  useQuery({ queryKey: ["monitoring-summary"], queryFn: () => get<MonitoringSummary>("/monitoring/summary"), refetchInterval: 60_000 });

export const useConsultDocs = () => useQuery({ queryKey: ["consult-docs"], queryFn: () => get<ConsultDocOut[]>("/consult-docs") });

// 담당자 지정용 사용자 검색(로그인한 사용자 누구나, 이름 · 이메일만)
export const useUsers = (q: string, enabled = true) =>
  useQuery({ queryKey: ["users", q], queryFn: () => get<UserBrief[]>(`/users${qs({ q, limit: 20 })}`), enabled, staleTime: 30_000 });

/** 변경 작업: 성공하면 목록 데이터를 새로고친다. */
export function useAction<TArgs, TRes>(fn: (args: TArgs) => Promise<TRes>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" }),
  });
}

export const errText = (e: unknown) => (e instanceof Error ? e.message : e ? String(e) : "");
