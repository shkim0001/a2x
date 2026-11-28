import { useState } from "react";
import { useAgentBridge, useSuggestion } from "@/lib/agent-bridge";
import { AgentFilledNote, agentRing } from "@/components/agent-filled";
import type { FormSuggestion } from "@/lib/api";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { PROCESSES, type Role } from "@/lib/sample-data";
import { del, post, put, type ServerEnv, type ServerOut } from "@/lib/api";
import { SERVER_ENV } from "@/lib/labels";
import { useAction, useMe, useServers, useSystems } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/tabs";
import { SearchInput } from "@/components/search-input";
import { Empty, ErrorNote, Loading } from "@/components/feedback";

type Env = "" | ServerEnv;

// 기준정보 > 서버: 모든 시스템의 서버를 한 곳에서 본다 (Gateway 연동 · 방화벽 신청 기준)
export function ServersPage({ role }: { role: Role }) {
  const [q, setQ] = useState("");
  const [env, setEnv] = useState<Env>("");
  const [proc, setProc] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  // Agent 서버 등록 제안(DCM): 추가 양식을 열고 값을 채운다
  const [prefill, setPrefill] = useState<FormSuggestion | null>(null);
  useSuggestion("server", (s) => {
    setPrefill(s);
    setAdding(true);
  });

  const all = useServers().data ?? [];
  const servers = useServers({ q, env, process: proc, mine: mineOnly });
  const mySystemIds = new Set(useMe().data?.managed_system_ids ?? []);
  const remove = useAction((id: number) => del(`/servers/${id}`));
  const list = servers.data ?? [];
  const count = (e: ServerEnv) => all.filter((s) => s.env === e).length;
  const canAdd = role !== "일반 사용자";

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: "전체 서버", value: all.length },
          { label: "운영", value: count("PROD") },
          { label: "검증", value: count("STAGE") },
          { label: "개발", value: count("DEV") },
        ].map((t) => (
          <Card key={t.label}>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">{t.label}</p>
              <p className="mt-2 font-display text-[32px] leading-none font-bold tracking-[-0.025em]">{t.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {adding && <AddServerForm key={prefill ? prefill.values.hostname : "new"} role={role} prefill={prefill} onDone={() => { setAdding(false); setPrefill(null); }} />}

      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>서버 목록</CardTitle>
            <CardDescription>{list.length}대 · 시스템별 서버 정보는 Gateway 연동과 방화벽 신청의 기준이 됩니다.</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Tabs<Env> value={env} onChange={setEnv} items={[{ value: "", label: "전체" }, { value: "PROD", label: "운영" }, { value: "STAGE", label: "검증" }, { value: "DEV", label: "개발" }]} />
            <NativeSelect className="w-36" value={proc} onChange={(e) => setProc(e.target.value)}>
              <option value="">프로세스 전체</option>
              {PROCESSES.map((p) => <option key={p}>{p}</option>)}
            </NativeSelect>
            <label className="flex items-center gap-1.5 px-1 text-sm">
              <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} /> 내 시스템만
            </label>
            <SearchInput value={q} onChange={setQ} placeholder="호스트명, IP, 시스템" className="w-60" />
            {canAdd && (
              <Button size="sm" onClick={() => setAdding(true)} disabled={adding}>
                <Plus /> 서버 추가
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {servers.isLoading && <Loading />}
          <ErrorNote error={servers.error ?? remove.error} className="mb-3" />
          <Table>
            <THead>
              <TR>
                <TH>시스템</TH>
                <TH>프로세스</TH>
                <TH>호스트명</TH>
                <TH>IP</TH>
                <TH>포트</TH>
                <TH>환경</TH>
                <TH>용도</TH>
                <TH className="text-right" />
              </TR>
            </THead>
            <TBody>
              {list.map((s) => {
                const mine = mySystemIds.has(s.system_id) || role === "admin";
                if (editingId === s.id)
                  return (
                    <TR key={s.id}>
                      <ServerEditCells server={s} showSystem onDone={() => setEditingId(null)} />
                    </TR>
                  );
                return (
                  <TR key={s.id}>
                    <TD>
                      <span className="flex items-center gap-2 font-bold">
                        {s.system_name}
                        {mySystemIds.has(s.system_id) && <Badge variant="info">담당</Badge>}
                      </span>
                    </TD>
                    <TD className="text-muted-foreground">{s.process}</TD>
                    <TD className="font-mono text-[13px]">{s.hostname}</TD>
                    <TD className="font-mono text-[13px]">{s.ip}</TD>
                    <TD className="font-mono text-[13px]">{s.port}</TD>
                    <TD><Badge variant={s.env === "PROD" ? "success" : s.env === "STAGE" ? "info" : "warning"}>{SERVER_ENV[s.env]}</Badge></TD>
                    <TD>{s.role}</TD>
                    <TD className="text-right">
                      {mine && (
                        <Button size="icon" variant="ghost" aria-label={`${s.hostname} 수정`} onClick={() => setEditingId(s.id)}>
                          <Pencil />
                        </Button>
                      )}
                      {mine && (
                        <Button size="icon" variant="ghost" aria-label={`${s.hostname} 삭제`} onClick={() => confirm(`${s.hostname} 서버를 삭제할까요?`) && remove.mutate(s.id)}>
                          <Trash2 />
                        </Button>
                      )}
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
          {!servers.isLoading && list.length === 0 && <Empty>해당하는 서버가 없습니다.</Empty>}
        </CardContent>
      </Card>
    </div>
  );
}

function AddServerForm({ role, onDone, prefill }: { role: Role; onDone: () => void; prefill?: FormSuggestion | null }) {
  const mine = useSystems({ mine: role !== "admin" }).data ?? [];
  const v = prefill?.values;
  const [systemId, setSystemId] = useState<number | "">(v?.system_id ?? "");
  const [srv, setSrv] = useState({ hostname: v?.hostname ?? "", ip: v?.ip ?? "", port: v?.port ? String(v.port) : "", env: (v?.env ?? "PROD") as ServerEnv, role: v?.role ?? "" });
  const [note, setNote] = useState(prefill ?? null);
  const bridge = useAgentBridge();
  const sysCode = mine.find((s) => s.id === (systemId || mine[0]?.id))?.code ?? "";
  const add = useAction(() => post(`/systems/${systemId || mine[0]?.id}/servers`, { ...srv, port: Number(srv.port) || 80 }));
  const up = (k: keyof typeof srv, v: string) => setSrv({ ...srv, [k]: v });

  return (
    <Card className={cn(note && agentRing)}>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>서버 추가</CardTitle>
          <CardDescription>내가 담당하는 시스템에 서버를 추가합니다.</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => bridge.ask(`${sysCode} ${srv.hostname} 서버 등록 채워줘`.replace(/\s+/g, " ").trim())} title="DCM(서버 자산)에서 아직 포탈에 없는 서버를 찾아 Agent가 채웁니다">
          <Sparkles /> Agent로 채우기
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {note && <AgentFilledNote s={note} onClose={() => setNote(null)} />}
        <div className="grid gap-3 md:grid-cols-[1.4fr_1.2fr_1.1fr_0.7fr_0.8fr_1fr]">
          <NativeSelect value={systemId || mine[0]?.id || ""} onChange={(e) => setSystemId(Number(e.target.value))}>
            {mine.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </NativeSelect>
          <Input placeholder="호스트명" value={srv.hostname} onChange={(e) => up("hostname", e.target.value)} />
          <Input placeholder="IP" value={srv.ip} onChange={(e) => up("ip", e.target.value)} />
          <Input placeholder="포트" inputMode="numeric" value={srv.port} onChange={(e) => up("port", e.target.value)} />
          <NativeSelect value={srv.env} onChange={(e) => up("env", e.target.value)}>
            {(Object.keys(SERVER_ENV) as ServerEnv[]).map((k) => <option key={k} value={k}>{SERVER_ENV[k]}</option>)}
          </NativeSelect>
          <Input placeholder="용도 (WAS, API, MCP…)" value={srv.role} onChange={(e) => up("role", e.target.value)} />
        </div>
        <ErrorNote error={add.error} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onDone}>취소</Button>
          <Button disabled={!mine.length || !srv.hostname || !srv.ip || add.isPending} onClick={() => add.mutate(undefined, { onSuccess: onDone })}>추가</Button>
        </div>
      </CardContent>
    </Card>
  );
}

type ServerDraftRow = { hostname: string; ip: string; port: string; env: ServerEnv; role: string };

// 서버 한 줄 수정(기준정보 › 서버 · 시스템 상세 공용). 저장하면 목록 쿼리를 새로 읽는다
export function ServerEditCells({ server, onDone, showSystem }: { server: ServerOut & { system_name?: string; process?: string }; onDone: () => void; showSystem?: boolean }) {
  const [d, setD] = useState<ServerDraftRow>({ hostname: server.hostname, ip: server.ip, port: String(server.port), env: server.env, role: server.role });
  const save = useAction(() => put(`/servers/${server.id}`, { ...d, port: Number(d.port) || 80 }));
  const up = (k: keyof ServerDraftRow, v: string) => setD({ ...d, [k]: v });
  return (
    <>
      {showSystem && <TD className="font-bold">{server.system_name}</TD>}
      {showSystem && <TD className="text-muted-foreground">{server.process}</TD>}
      <TD><Input className="h-8 font-mono text-[13px]" value={d.hostname} onChange={(e) => up("hostname", e.target.value)} aria-label="호스트명" /></TD>
      <TD><Input className="h-8 font-mono text-[13px]" value={d.ip} onChange={(e) => up("ip", e.target.value)} aria-label="IP" /></TD>
      <TD><Input className="h-8 w-20 font-mono text-[13px]" inputMode="numeric" value={d.port} onChange={(e) => up("port", e.target.value)} aria-label="포트" /></TD>
      <TD>
        <NativeSelect className="h-8" value={d.env} onChange={(e) => up("env", e.target.value)} aria-label="환경">
          {(Object.keys(SERVER_ENV) as ServerEnv[]).map((k) => <option key={k} value={k}>{SERVER_ENV[k]}</option>)}
        </NativeSelect>
      </TD>
      <TD><Input className="h-8" value={d.role} onChange={(e) => up("role", e.target.value)} aria-label="용도" /></TD>
      <TD className="text-right">
        <div className="flex items-center justify-end gap-1">
          {!!save.error && <span className="max-w-48 truncate text-xs text-destructive" title={String((save.error as Error).message)}>{(save.error as Error).message}</span>}
          <Button size="sm" variant="ghost" onClick={onDone}>취소</Button>
          <Button size="sm" disabled={!d.hostname || !d.ip || save.isPending} onClick={() => save.mutate(undefined, { onSuccess: onDone })}>저장</Button>
        </div>
      </TD>
    </>
  );
}
