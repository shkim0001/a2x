import { useMemo, useState } from "react";
import { ArrowRight, Plus } from "lucide-react";
import { post } from "@/lib/api";
import { REQ_STATUS, fmtDate } from "@/lib/labels";
import { useAction, useMe, useToolRequests } from "@/lib/queries";
import { useAgentBridge } from "@/lib/agent-bridge";
import type { PageKey } from "@/App";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { StatusBadge } from "@/components/status-badge";
import { SearchInput } from "@/components/search-input";
import { Empty, ErrorNote, Loading } from "@/components/feedback";

// 구독 · 권한 › 내 권한: 내가 신청한 Tool의 승인 상태를 보고 취소 · 해지한다.
// 새 Tool 신청은 카탈로그 사용 신청 화면 한 곳에서 한다(같은 MCP 서버의 Tool은 '더 신청'으로 그 서버를 담아 연다).
export function MyAccessPage({ onNavigate }: { onNavigate: (p: PageKey) => void }) {
  const me = useMe().data!;
  const [q, setQ] = useState("");
  const mine = useToolRequests({ scope: "mine", q });
  const cancel = useAction((id: number) => post(`/tool-requests/${id}/cancel`));
  const bridge = useAgentBridge();
  const rows = mine.data ?? [];
  // '더 신청'은 MCP 서버마다 첫 줄에만 보인다
  const firstOfAsset = useMemo(() => {
    const seen = new Set<number>();
    return new Set(rows.filter((t) => !seen.has(t.asset.id) && seen.add(t.asset.id)).map((t) => t.id));
  }, [rows]);

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle>내 Tool 권한 · 신청 현황</CardTitle>
          <CardDescription>{me.user.name} 님이 신청한 MCP Tool · {rows.length}건. 새 Tool은 카탈로그에서 신청합니다.</CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SearchInput value={q} onChange={setQ} placeholder="Tool, Agent, 대상 시스템" />
          <Button size="sm" onClick={() => onNavigate("catalog")}>
            카탈로그에서 Tool 신청 <ArrowRight />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {mine.isLoading && <Loading />}
        <ErrorNote error={mine.error ?? cancel.error} />
        <Table>
          <THead>
            <TR>
              <TH>Agent 시스템</TH>
              <TH>대상 시스템 · MCP 서버</TH>
              <TH>Tool</TH>
              <TH>신청일</TH>
              <TH>상태</TH>
              <TH className="text-right" />
            </TR>
          </THead>
          <TBody>
            {rows.map((t) => (
              <TR key={t.id}>
                <TD className="font-medium">{t.client_system.name}</TD>
                <TD>{t.provider_system.name} · {t.asset.name}</TD>
                <TD className="font-mono">{t.tool.name}</TD>
                <TD className="text-muted-foreground">{fmtDate(t.created_at)}</TD>
                <TD title={t.decision_note}><StatusBadge status={REQ_STATUS[t.status]} /></TD>
                <TD className="text-right">
                  <div className="flex justify-end gap-1">
                    {firstOfAsset.has(t.id) && (
                      <Button size="sm" variant="outline" onClick={() => bridge.request([t.asset.id])} title={`${t.asset.name}의 다른 Tool을 신청합니다`}>
                        <Plus /> 더 신청
                      </Button>
                    )}
                    {t.can_cancel && (
                      <Button size="sm" variant="ghost" onClick={() => cancel.mutate(t.id)}>{t.status === "PENDING" ? "신청 취소" : "해지"}</Button>
                    )}
                  </div>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
        {!mine.isLoading && !rows.length && <Empty>신청한 Tool이 없습니다. 카탈로그에서 MCP 서버를 찾아 Tool을 신청하세요.</Empty>}
      </CardContent>
    </Card>
  );
}
