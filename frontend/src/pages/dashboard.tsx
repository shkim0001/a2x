import { AlertTriangle, ArrowRight, Boxes, Clock, KeyRound } from "lucide-react";
import type { PageKey } from "@/App";
import type { Role } from "@/lib/sample-data";
import { REQ_STATUS } from "@/lib/labels";
import { useAssets, useMonitoringSummary, useSubscriptions, useToolRequests } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/status-badge";
import { Empty } from "@/components/feedback";

export function DashboardPage({ role, onNavigate }: { role: Role; onNavigate: (p: PageKey) => void }) {
  const assets = useAssets().data ?? [];
  const pendingSubs = useSubscriptions({ scope: "approve", status: "PENDING" }).data ?? [];
  const pendingTools = useToolRequests({ scope: "approve", status: "PENDING" }).data ?? [];
  const myTools = (useToolRequests({ scope: "mine" }).data ?? []).filter((t) => t.status === "APPROVED");
  const summary = useMonitoringSummary().data;
  const canApprove = role !== "일반 사용자";

  const stats = [
    { label: "운영 중 API · MCP", value: assets.filter((a) => a.status === "LIVE").length, icon: Boxes },
    { label: "내 Tool 권한", value: myTools.length, icon: KeyRound },
    ...(canApprove ? [{ label: "내 승인 대기", value: pendingSubs.length + pendingTools.length, icon: Clock }] : []),
    { label: "오늘 오류율", value: `${(summary?.today_error_rate ?? 0).toFixed(2)}%`, icon: AlertTriangle },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map(({ label, value, icon: Icon }) => (
          <Card key={label}>
            <CardContent className="flex items-center justify-between p-5">
              <div>
                <p className="text-sm text-muted-foreground">{label}</p>
                <p className="mt-2 font-display text-[40px] leading-none font-bold tracking-[-0.025em]">{value}</p>
              </div>
              <span className="grid size-11 place-items-center rounded-[13px] bg-[#e5eefc] text-primary"><Icon className="size-5" /></span>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {canApprove ? (
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>내가 승인할 요청</CardTitle>
                <CardDescription>내가 담당하는 시스템을 대상으로 들어온 신청</CardDescription>
              </div>
              <Button variant="ghost" size="sm" onClick={() => onNavigate("subscriptions")}>
                구독 · 승인 <ArrowRight />
              </Button>
            </CardHeader>
            <CardContent className="space-y-2">
              {pendingSubs.map((s) => (
                <div key={`s${s.id}`} className="flex items-center justify-between rounded-2xl bg-[#f5f6f8] p-3.5 text-sm">
                  <div>
                    <Badge variant="outline" className="mb-1">시스템 구독</Badge>
                    <p className="font-medium">{s.client_system.name} → {s.asset.name}</p>
                    <p className="text-muted-foreground">{s.purpose}</p>
                  </div>
                  <StatusBadge status={REQ_STATUS[s.status]} />
                </div>
              ))}
              {pendingTools.map((t) => (
                <div key={`t${t.id}`} className="flex items-center justify-between rounded-2xl bg-[#f5f6f8] p-3.5 text-sm">
                  <div>
                    <Badge variant="outline" className="mb-1">Tool 사용</Badge>
                    <p className="font-medium">{t.user.name} · {t.tool.name}</p>
                    <p className="text-muted-foreground">{t.client_system.name} → {t.asset.name}</p>
                  </div>
                  <StatusBadge status={REQ_STATUS[t.status]} />
                </div>
              ))}
              {pendingSubs.length + pendingTools.length === 0 && <Empty>대기 중인 요청이 없습니다.</Empty>}
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>내 Tool 권한</CardTitle>
                <CardDescription>승인된 Agent – 대상 시스템 연계의 Tool</CardDescription>
              </div>
              <Button variant="ghost" size="sm" onClick={() => onNavigate("my-access")}>
                전체 <ArrowRight />
              </Button>
            </CardHeader>
            <CardContent className="space-y-2">
              {myTools.map((t) => (
                <div key={t.id} className="flex items-center justify-between rounded-2xl bg-[#f5f6f8] p-3.5 text-sm">
                  <div>
                    <p className="font-mono font-medium">{t.tool.name}</p>
                    <p className="text-muted-foreground">{t.client_system.name} → {t.asset.name}</p>
                  </div>
                  <StatusBadge status={REQ_STATUS[t.status]} />
                </div>
              ))}
              {myTools.length === 0 && <Empty>승인된 Tool이 없습니다.</Empty>}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>최근 오류</CardTitle>
              <CardDescription className="mt-1">최근 24시간 · 내 조회 범위 · 같은 대상 · 코드로 묶음</CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={() => onNavigate(role === "일반 사용자" ? "usage-mcp" : "usage-api")}>
              모니터링 <ArrowRight />
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {(summary?.recent_errors ?? []).map((e) => (
              <div key={e.name + e.code} className="flex items-center justify-between rounded-2xl bg-[#f5f6f8] p-3.5 text-sm">
                <div>
                  <p className="font-medium">{e.name}</p>
                  <p className="text-muted-foreground">{e.code} · {e.category}</p>
                </div>
                <span className="text-muted-foreground">{e.count}건</span>
              </div>
            ))}
            {summary && summary.recent_errors.length === 0 && <Empty>최근 24시간 오류가 없습니다.</Empty>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
