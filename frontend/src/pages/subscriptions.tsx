import { useState } from "react";
import type { Role } from "@/lib/sample-data";
import { post, type AssetStatus } from "@/lib/api";
import { ASSET_STATUS, REQ_STATUS, TOOL_KIND, fmtDate } from "@/lib/labels";
import { useAction, useAssets, useSubscriptions, useToolRequests } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/tabs";
import { StatusBadge } from "@/components/status-badge";
import { SearchInput, matches } from "@/components/search-input";
import { Empty, ErrorNote, Loading } from "@/components/feedback";

type Tab = "system" | "tool" | "asset";
type Scope = "approve" | "requested" | "all";

export function SubscriptionsPage({ role }: { role: Role }) {
  const [tab, setTab] = useState<Tab>("system");
  const [scope, setScope] = useState<Scope>("approve");
  const [q, setQ] = useState("");

  const subs = useSubscriptions({ scope, q });
  const tools = useToolRequests({ scope, q });
  const pendingSub = useSubscriptions({ scope: "approve", status: "PENDING" }).data?.length ?? 0;
  const pendingTool = useToolRequests({ scope: "approve", status: "PENDING" }).data?.length ?? 0;
  const assets = useAssets();
  const pendingAssets = (assets.data ?? []).filter((a) => a.status === "PENDING").length;

  // 버튼 표시는 서버가 계산한 can_decide · can_cancel을 따른다
  const act = useAction(({ path, note }: { path: string; note?: string }) => post(path, note ? { note } : {}));
  const decide = (path: string, ask?: string) => {
    const note = ask ? prompt(ask) ?? undefined : undefined;
    if (ask && note === undefined) return;
    act.mutate({ path, note });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs<Tab>
          value={tab}
          onChange={setTab}
          items={[
            { value: "system", label: "① 시스템 구독", count: pendingSub },
            { value: "tool", label: "② Tool 사용 신청", count: pendingTool },
            ...(role === "admin" ? [{ value: "asset" as Tab, label: "API · MCP 등록 승인 (admin)", count: pendingAssets }] : []),
          ]}
        />
        <div className="flex flex-wrap items-center gap-2">
          {tab !== "asset" && (
            <Tabs<Scope>
              value={scope}
              onChange={setScope}
              items={[
                { value: "approve", label: "내가 승인할 것" },
                { value: "requested", label: "내 시스템이 신청한 것" },
                ...(role === "admin" ? [{ value: "all" as Scope, label: "전체" }] : []),
              ]}
            />
          )}
          <SearchInput value={q} onChange={setQ} placeholder={tab === "tool" ? "사용자, Tool, Agent, 대상" : tab === "asset" ? "이름, 시스템" : "시스템, API · MCP, 신청자"} />
        </div>
      </div>

      <ErrorNote error={act.error} />

      {tab === "asset" && role === "admin" ? (
        <AssetApprovals q={q} onAct={decide} />
      ) : tab === "system" ? (
        <Card>
          <CardHeader>
            <CardTitle>시스템 구독</CardTitle>
            <CardDescription>구독 시스템(Agent 포함)이 대상 시스템의 MCP 서버 · API를 신청합니다. 대상 시스템 담당자(또는 admin)가 승인합니다.</CardDescription>
          </CardHeader>
          <CardContent>
            {subs.isLoading && <Loading />}
            <ErrorNote error={subs.error} />
            <Table>
              <THead>
                <TR>
                  <TH>ID</TH>
                  <TH>구독 시스템</TH>
                  <TH>대상 시스템 · 자산</TH>
                  <TH>목적</TH>
                  <TH>신청자 · 일자</TH>
                  <TH>상태</TH>
                  <TH className="text-right">작업</TH>
                </TR>
              </THead>
              <TBody>
                {(subs.data ?? []).map((s) => (
                  <TR key={s.id}>
                    <TD className="text-muted-foreground">{s.id}</TD>
                    <TD className="font-medium">{s.client_system.name}</TD>
                    <TD>
                      {s.provider_system.name} · {s.asset.name} <Badge variant="outline" className="ml-1">{s.asset.type}</Badge>
                    </TD>
                    <TD className="text-muted-foreground">{s.purpose}</TD>
                    <TD className="text-muted-foreground">{s.requested_by?.name ?? "-"} · {fmtDate(s.created_at)}</TD>
                    <TD title={s.decision_note}><StatusBadge status={REQ_STATUS[s.status]} /></TD>
                    <TD className="space-x-1 text-right whitespace-nowrap">
                      {s.can_decide && (
                        <>
                          <Button size="sm" onClick={() => decide(`/subscriptions/${s.id}/approve`)}>승인</Button>
                          <Button size="sm" variant="outline" onClick={() => decide(`/subscriptions/${s.id}/reject`, "반려 사유를 입력하세요")}>반려</Button>
                        </>
                      )}
                      {s.can_cancel && s.status === "APPROVED" && (
                        <Button size="sm" variant="outline" onClick={() => confirm("시스템 구독을 해지하면 그 안의 Tool 권한도 함께 해지됩니다. 해지할까요?") && decide(`/subscriptions/${s.id}/cancel`)}>해지</Button>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            {!subs.isLoading && !subs.data?.length && <Empty>해당하는 신청이 없습니다.</Empty>}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Tool 사용 신청</CardTitle>
            <CardDescription>승인된 MCP 시스템 구독 안에서 개인 사용자가 Tool별로 신청합니다. 대상 시스템 담당자(또는 admin)가 승인합니다. (API 연계는 이 단계 없음)</CardDescription>
          </CardHeader>
          <CardContent>
            {tools.isLoading && <Loading />}
            <ErrorNote error={tools.error} />
            <Table>
              <THead>
                <TR>
                  <TH>ID</TH>
                  <TH>사용자</TH>
                  <TH>연계 (Agent → 대상)</TH>
                  <TH>Tool</TH>
                  <TH>목적</TH>
                  <TH>상태</TH>
                  <TH className="text-right">작업</TH>
                </TR>
              </THead>
              <TBody>
                {(tools.data ?? []).map((t) => (
                  <TR key={t.id}>
                    <TD className="text-muted-foreground">{t.id}</TD>
                    <TD className="font-medium">{t.user.name}</TD>
                    <TD>{t.client_system.name} → {t.asset.name}</TD>
                    <TD>
                      <span className="font-mono">{t.tool.name}</span>
                      {t.tool.kind === "WRITE" && <Badge variant="warning" className="ml-1.5">{TOOL_KIND.WRITE}</Badge>}
                    </TD>
                    <TD className="text-muted-foreground">{t.purpose}</TD>
                    <TD title={t.decision_note}><StatusBadge status={REQ_STATUS[t.status]} /></TD>
                    <TD className="space-x-1 text-right whitespace-nowrap">
                      {t.can_decide && (
                        <>
                          <Button size="sm" onClick={() => decide(`/tool-requests/${t.id}/approve`)}>승인</Button>
                          <Button size="sm" variant="outline" onClick={() => decide(`/tool-requests/${t.id}/reject`, "반려 사유를 입력하세요")}>반려</Button>
                        </>
                      )}
                      {t.can_cancel && t.status === "APPROVED" && (
                        <Button size="sm" variant="outline" onClick={() => decide(`/tool-requests/${t.id}/cancel`)}>해지</Button>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            {!tools.isLoading && !tools.data?.length && <Empty>해당하는 신청이 없습니다.</Empty>}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// admin: API · MCP 등록 승인 (승인 → 스테이지 → 운영 전환)
function AssetApprovals({ q, onAct }: { q: string; onAct: (path: string, ask?: string) => void }) {
  const assets = useAssets();
  const order: AssetStatus[] = ["PENDING", "STAGE", "LIVE", "REJECTED", "SUSPENDED", "DRAFT"];
  const rows = (assets.data ?? [])
    .filter((a) => matches(q, a.name, a.system.name, ASSET_STATUS[a.status]))
    .sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status));
  return (
    <Card>
      <CardHeader>
        <CardTitle>API · MCP 등록 승인</CardTitle>
        <CardDescription>시스템 담당자가 등록한 API · MCP 서버와 변환한 MCP 서버를 admin이 승인합니다. 진행상태: 저장 → 승인 → 스테이지 → 운영. 운영 상태가 되어야 구독할 수 있습니다.</CardDescription>
      </CardHeader>
      <CardContent>
        {assets.isLoading && <Loading />}
        <Table>
          <THead>
            <TR>
              <TH>ID</TH>
              <TH>시스템</TH>
              <TH>이름</TH>
              <TH>구분</TH>
              <TH>구성</TH>
              <TH>상태</TH>
              <TH className="text-right">작업</TH>
            </TR>
          </THead>
          <TBody>
            {rows.map((a) => (
              <TR key={a.id}>
                <TD className="text-muted-foreground">{a.id}</TD>
                <TD>{a.system.name}</TD>
                <TD className="font-medium">{a.name}</TD>
                <TD>
                  <Badge variant="outline">{a.type}</Badge>
                  {a.source === "MCP_CONVERTED" && <Badge variant="secondary" className="ml-1">API 변환</Badge>}
                </TD>
                <TD className="text-muted-foreground">{a.type === "API" ? `오퍼레이션 ${a.operation_count}` : `Tool ${a.tool_count}`}</TD>
                <TD><StatusBadge status={ASSET_STATUS[a.status]} /></TD>
                <TD className="space-x-1 text-right whitespace-nowrap">
                  {a.status === "PENDING" && (
                    <>
                      <Button size="sm" onClick={() => onAct(`/assets/${a.id}/approve`)}>승인 → 스테이지</Button>
                      <Button size="sm" variant="outline" onClick={() => onAct(`/assets/${a.id}/reject`, "반려 사유를 입력하세요")}>반려</Button>
                    </>
                  )}
                  {a.status === "STAGE" && <Button size="sm" variant="outline" onClick={() => onAct(`/assets/${a.id}/go-live`)}>운영 전환</Button>}
                  {a.status === "LIVE" && <Button size="sm" variant="ghost" onClick={() => confirm(`${a.name}을(를) 중지할까요?`) && onAct(`/assets/${a.id}/suspend`)}>중지</Button>}
                  {a.status === "SUSPENDED" && <Button size="sm" variant="outline" onClick={() => onAct(`/assets/${a.id}/resume`)}>재개</Button>}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}
