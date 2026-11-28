import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import type { Role } from "@/lib/sample-data";
import { post, type AssetDetail, type ToolSuggestion } from "@/lib/api";
import { ASSET_STATUS, TOOL_KIND } from "@/lib/labels";
import { useAction, useAsset, useAssets, useConvertPreview, useMe } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/status-badge";
import { Empty, ErrorNote, Loading } from "@/components/feedback";

type Row = ToolSuggestion & { checked: boolean };

export function ConvertPage({ role }: { role: Role }) {
  const me = useMe().data!;
  const managed = new Set(me.managed_system_ids);
  const all = useAssets().data ?? [];
  // 변환은 운영 중인 API를 가진 시스템의 담당자(또는 admin)가 한다
  const apis = all.filter((a) => a.type === "API" && a.status === "LIVE" && (role === "admin" || managed.has(a.system.id)));
  const converted = all.filter((a) => a.source === "MCP_CONVERTED");

  const [picked, setPicked] = useState<number | null>(null);
  const apiId = picked ?? apis[0]?.id ?? null;
  const api = apis.find((a) => a.id === apiId);
  const preview = useConvertPreview(apiId);

  const [rows, setRows] = useState<Row[]>([]);
  const [serverName, setServerName] = useState("");
  const [enhanced, setEnhanced] = useState(false);
  const create = useAction((submit: boolean) =>
    post<AssetDetail>(`/assets/${apiId}/convert`, {
      name: serverName,
      tools: rows.filter((r) => r.checked).map((r) => ({ operation_id: r.operation_id, name: r.tool_name, description: r.description })),
      submit,
    }),
  );

  // API를 바꾸면 규칙 제안으로 다시 채운다(변경 오퍼레이션은 기본 해제)
  useEffect(() => {
    if (!preview.data) return;
    setRows(preview.data.map((s) => ({ ...s, checked: s.method === "GET" })));
    setServerName(api ? api.name.replace(/\s*API$/, "") + " MCP" : "");
    setEnhanced(false);
    create.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview.data, apiId]);

  const upd = (i: number, patch: Partial<Row>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  // 설명 보강: LLM 계층(T0-3) 전까지는 규칙 기반 문장
  const enhance = () => {
    setRows((r) => r.map((x) => ({ ...x, description: x.description.includes("읽기 전용") || x.description.includes("사용자 확인") ? x.description : `${x.description}. ${x.kind === "WRITE" ? "데이터를 변경하므로 사용자 확인 후 호출한다." : "읽기 전용."}` })));
    setEnhanced(true);
  };

  const selected = rows.filter((r) => r.checked);
  const previewJson = useMemo(
    () => JSON.stringify({ tools: selected.map((r) => ({ name: r.tool_name, description: r.description, inputSchema: r.input_schema })) }, null, 2),
    [selected],
  );
  const dup = new Set(selected.map((r) => r.tool_name)).size !== selected.length;

  if (!all.length) return <Loading />;
  if (apis.length === 0) {
    return <Empty>변환할 수 있는 API가 없습니다. 내가 담당하는 시스템에 운영 중인 API가 있어야 합니다.</Empty>;
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle>API → MCP Tool 변환</CardTitle>
            <CardDescription>등록된 API의 오퍼레이션을 골라 MCP Tool로 변환하고, MCP 서버로 열어 구독 · Tool 신청을 받습니다.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm">
                <span className="font-medium">원본 API</span>
                <NativeSelect value={apiId ?? ""} onChange={(e) => setPicked(Number(e.target.value))}>
                  {apis.map((a) => <option key={a.id} value={a.id}>{a.system.name} · {a.name}</option>)}
                </NativeSelect>
              </label>
              <label className="space-y-1.5 text-sm">
                <span className="font-medium">생성할 MCP 서버 이름</span>
                <Input value={serverName} onChange={(e) => setServerName(e.target.value)} />
              </label>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">오퍼레이션 → Tool</p>
                <Button variant="outline" size="sm" onClick={enhance} disabled={enhanced || !rows.length}>
                  <Sparkles /> {enhanced ? "설명 보강됨" : "Tool 설명 보강"}
                </Button>
              </div>
              {preview.isLoading && <Loading />}
              <ErrorNote error={preview.error} />
              {rows.map((r, i) => (
                <div key={r.operation_id} className={`rounded-2xl bg-[#f5f6f8] p-3.5 ${r.checked ? "" : "opacity-60"}`}>
                  <div className="flex items-center gap-3 text-sm">
                    <input type="checkbox" checked={r.checked} onChange={() => upd(i, { checked: !r.checked })} />
                    <span className="font-mono text-xs">
                      <b>{r.method}</b> {r.path}
                    </span>
                    <ArrowRight className="size-3.5 text-muted-foreground" />
                    <Input className="h-8 w-56 font-mono text-xs" value={r.tool_name} onChange={(e) => upd(i, { tool_name: e.target.value })} disabled={!r.checked} />
                    <Badge variant={r.kind === "WRITE" ? "warning" : "secondary"}>{TOOL_KIND[r.kind]}</Badge>
                  </div>
                  <Input
                    className="mt-2 h-8 text-xs"
                    value={r.description}
                    onChange={(e) => upd(i, { description: e.target.value })}
                    disabled={!r.checked}
                    placeholder="Tool 설명 (Agent가 Tool을 고를 때 읽는 문장)"
                  />
                </div>
              ))}
              <p className="text-xs text-muted-foreground">
                Tool 이름 · 입력 스키마는 서버의 규칙 코드가 제안합니다(메서드 + 경로). 변경(POST · PUT · DELETE) 오퍼레이션은 기본으로 빠져 있습니다. LLM 설명 보강은 LLM 계층 연결 후 추가됩니다.
              </p>
            </div>

            <ErrorNote error={create.error} />
            {create.data && (
              <p className="rounded-xl bg-[#e6f6ea] px-3 py-2 text-[13px] text-[#1e6b34]">
                '{create.data.name}' 만들었습니다 · 상태 {ASSET_STATUS[create.data.status]} · 엔드포인트 <span className="font-mono">{create.data.endpoint}</span>
              </p>
            )}
            <div className="flex items-center justify-end gap-3 border-t pt-4">
              {dup && <span className="text-sm text-red-600">Tool 이름이 겹칩니다.</span>}
              <Button variant="outline" onClick={() => create.mutate(false)} disabled={selected.length === 0 || !serverName || dup || create.isPending}>저장</Button>
              <Button onClick={() => create.mutate(true)} disabled={selected.length === 0 || !serverName || dup || create.isPending}>
                MCP 서버로 오픈 신청
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">미리보기 · MCP tools/list</CardTitle>
              <CardDescription>Agent가 받게 될 Tool 정의</CardDescription>
            </CardHeader>
            <CardContent>
              <pre className="max-h-96 overflow-auto rounded-2xl bg-[#1d1d1f] p-3 text-xs leading-relaxed text-zinc-100">{previewJson}</pre>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">오픈 절차</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-2.5 text-sm">
                {["오퍼레이션 선택 · Tool 정의", "정적 검사 (2차 M4)", "admin 승인", "컨버터 런타임이 MCP 서버로 제공", "카탈로그 공개 → 시스템 구독 · Tool 신청"].map((s, i) => (
                  <li key={s} className="flex gap-3">
                    <span className="grid size-5 shrink-0 place-items-center rounded-[9px] bg-[#e5eefc] text-[13px] text-primary">{i + 1}</span>
                    {s}
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>변환된 MCP 서버</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {converted.map((a) => (
            <ConvertedRow key={a.id} id={a.id} />
          ))}
          {converted.length === 0 && <Empty>아직 변환된 MCP 서버가 없습니다.</Empty>}
        </CardContent>
      </Card>
    </div>
  );
}

function ConvertedRow({ id }: { id: number }) {
  const a = useAsset(id).data;
  const src = useAsset(a?.converted_from_id).data;
  if (!a) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-[#f5f6f8] p-3.5 text-sm">
      <span className="font-medium">{a.name}</span>
      <StatusBadge status={ASSET_STATUS[a.status]} />
      <span className="text-muted-foreground">← {src?.name ?? "원본 API"} ({a.system.name})</span>
      <span className="font-mono text-[11.5px] text-muted-foreground">{a.endpoint}</span>
      <div className="ml-auto flex flex-wrap gap-1.5">
        {a.tools.map((t) => (
          <span key={t.id} className="rounded border bg-white px-1.5 py-0.5 font-mono text-xs">{t.name}</span>
        ))}
      </div>
    </div>
  );
}
