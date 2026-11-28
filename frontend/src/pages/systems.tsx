import { useEffect, useState, type ChangeEvent, type ReactNode } from "react";
import { Bot, Pencil, Plus, Server, Trash2, X } from "lucide-react";
import { PROCESSES, type Role } from "@/lib/sample-data";
import { del, patch, post, type DataLevel, type ServerEnv, type SystemKind, type SystemOut, type UserBrief } from "@/lib/api";
import { ASSET_STATUS, DATA_LEVEL, REQ_STATUS, SERVER_ENV, SYSTEM_KIND } from "@/lib/labels";
import { useAction, useAssets, useMe, useSubscriptions, useSystems } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/tabs";
import { StatusBadge } from "@/components/status-badge";
import { SearchInput } from "@/components/search-input";
import { Empty, ErrorNote, Loading } from "@/components/feedback";
import { UserPicker } from "@/components/user-picker";
import { AgentFilledNote, agentRing } from "@/components/agent-filled";
import { useAgentBridge, useSuggestion } from "@/lib/agent-bridge";
import type { FormSuggestion } from "@/lib/api";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { ServerEditCells } from "@/pages/servers";

type Filter = "전체" | "내 시스템" | SystemKind;

export function SystemsPage({ role }: { role: Role }) {
  const [filter, setFilter] = useState<Filter>("전체");
  const [proc, setProc] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  // Agent 시스템 등록 제안(IRP · DCM): 등록 양식을 열고 값을 채운다
  const [prefill, setPrefill] = useState<FormSuggestion | null>(null);
  useSuggestion("system", (s) => {
    setPrefill(s);
    setCreating(true);
  });
  // Agent 서버 정보 제안(DCM): 작성 중인 등록 양식에 서버 행만 더한다(양식이 닫혀 있으면 열고)
  const [serverFill, setServerFill] = useState<FormSuggestion | null>(null);
  useSuggestion("system_servers", (s) => {
    setServerFill(s);
    setCreating(true);
  });

  const systems = useSystems({
    q,
    process: proc,
    mine: filter === "내 시스템",
    kind: filter === "BUSINESS" || filter === "AGENT" ? filter : undefined,
  });
  const list = systems.data ?? [];
  const sys = list.find((s) => s.id === selected) ?? list[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Tabs<Filter>
            value={filter}
            onChange={setFilter}
            items={[
              { value: "전체", label: "전체" },
              { value: "내 시스템", label: "내 시스템" },
              { value: "BUSINESS", label: "업무 시스템" },
              { value: "AGENT", label: "AI Agent" },
            ]}
          />
          <NativeSelect className="w-40" value={proc} onChange={(e) => setProc(e.target.value)}>
            <option value="">프로세스 전체</option>
            {PROCESSES.map((p) => <option key={p}>{p}</option>)}
          </NativeSelect>
          <SearchInput value={q} onChange={setQ} placeholder="시스템명, 코드, 부서" />
          <span className="text-[13px] text-muted-foreground">{list.length}개</span>
        </div>
        <Button size="sm" onClick={() => setCreating(true)} title="누구나 등록할 수 있고, 등록한 사람이 첫 담당자가 됩니다">
          <Plus /> 시스템 등록
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <Card className="h-fit p-2">
          {systems.isLoading && <Loading />}
          <ErrorNote error={systems.error} />
          {list.map((s) => (
            <SystemRow key={s.id} s={s} on={sys?.id === s.id && !creating} onClick={() => { setSelected(s.id); setCreating(false); }} />
          ))}
          {!systems.isLoading && list.length === 0 && <Empty>해당하는 시스템이 없습니다.</Empty>}
        </Card>

        {creating ? (
          <SystemForm key={prefill ? prefill.values.code : "new"} prefill={prefill} serverFill={serverFill} onDone={(id) => { setCreating(false); setPrefill(null); setServerFill(null); if (id) setSelected(id); }} />
        ) : (
          sys && <SystemDetail key={sys.id} sys={sys} role={role} />
        )}
      </div>
    </div>
  );
}

function SystemRow({ s, on, onClick }: { s: SystemOut; on: boolean; onClick: () => void }) {
  const me = useMe().data;
  const mine = !!me && s.managers.some((m) => m.id === me.user.id);
  return (
    <button onClick={onClick} className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm", on ? "bg-accent" : "hover:bg-muted")}>
      {s.kind === "AGENT" ? <Bot className="size-4 text-primary" /> : <Server className="size-4 text-muted-foreground" />}
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{s.name}</p>
        <p className="text-xs text-muted-foreground">{s.code !== s.name && `${s.code} · `}{s.process} · {s.dept}</p>
      </div>
      {mine && <Badge variant="secondary">담당</Badge>}
    </button>
  );
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm">{value || "-"}</p>
    </div>
  );
}

function SystemDetail({ sys, role }: { sys: SystemOut; role: Role }) {
  const me = useMe().data!;
  const isMine = sys.managers.some((m) => m.id === me.user.id);
  const editable = role === "admin" || isMine;

  const assets = (useAssets().data ?? []).filter((a) => a.system.id === sys.id);
  const outgoing = (useSubscriptions({ scope: "requested" }).data ?? []).filter((s) => s.client_system.id === sys.id);

  const [editingInfo, setEditingInfo] = useState(false);
  const [editingServer, setEditingServer] = useState<number | null>(null);
  const addManager = useAction((e: string) => post(`/systems/${sys.id}/managers`, { email: e }));
  const removeManager = useAction((userId: number) => del(`/systems/${sys.id}/managers/${userId}`));
  const removeSystem = useAction(() => del(`/systems/${sys.id}`));
  const askRemove = () =>
    confirm(`${sys.code} 시스템을 삭제할까요?\n서버 ${sys.servers.length}대와 담당자 연결도 함께 지워집니다. 등록한 API · MCP나 진행 중인 구독이 있으면 삭제되지 않습니다.`) &&
    removeSystem.mutate(undefined);

  return (
    <div className="space-y-4">
      {editingInfo && <SystemInfoForm sys={sys} onDone={() => setEditingInfo(false)} />}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{SYSTEM_KIND[sys.kind]}</Badge>
            <Badge variant="secondary">{sys.process} 프로세스</Badge>
            {editable && !editingInfo && (
              <div className="ml-auto flex gap-1.5">
                <Button size="sm" variant="outline" onClick={() => setEditingInfo(true)}>
                  <Pencil /> 정보 수정
                </Button>
                <Button size="sm" variant="outline" className="text-destructive hover:text-destructive" disabled={removeSystem.isPending} onClick={askRemove}>
                  <Trash2 /> 삭제
                </Button>
              </div>
            )}
          </div>
          <ErrorNote error={removeSystem.error} className="mt-2" />
          <CardTitle className="mt-2 text-lg">{sys.name}</CardTitle>
          <CardDescription>{sys.description}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <Field label="시스템 코드" value={sys.code} />
          <Field label="소속 부서" value={sys.dept} />
          <Field label="데이터 등급" value={DATA_LEVEL[sys.data_level]} />
          <Field label="서비스 URL" value={<span className="font-mono text-xs">{sys.url}</span>} />
          <div className="sm:col-span-2">
            <p className="text-xs text-muted-foreground">담당자 ({sys.managers.length})</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {sys.managers.map((m) => (
                <Badge key={m.id} variant={m.id === me.user.id ? "default" : "secondary"} className="gap-1" title={m.email}>
                  {m.name}
                  {editable && sys.managers.length > 1 && (
                    <button onClick={() => removeManager.mutate(m.id)} aria-label={`${m.name} 담당자에서 빼기`}>
                      <X className="size-3" />
                    </button>
                  )}
                </Badge>
              ))}
              {editable && (
                <UserPicker
                  placeholder="담당자 추가: 이름 · 이메일 검색"
                  excludeEmails={sys.managers.map((m) => m.email)}
                  disabled={addManager.isPending}
                  onPick={(u) => addManager.mutate(u.email)}
                />
              )}
            </div>
            <ErrorNote error={addManager.error ?? removeManager.error} className="mt-2" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>서버 정보</CardTitle>
          <CardDescription>이 시스템을 구성하는 서버. Gateway 연동 · 방화벽 신청에 사용합니다. (추가는 기준정보 › 서버{editable && ", 수정은 연필 버튼"})</CardDescription>
        </CardHeader>
        <CardContent>
          {sys.servers.length ? (
            <Table>
              <THead>
                <TR>
                  <TH>호스트명</TH>
                  <TH>IP</TH>
                  <TH>포트</TH>
                  <TH>환경</TH>
                  <TH>용도</TH>
                  <TH className="text-right" />
                </TR>
              </THead>
              <TBody>
                {sys.servers.map((s) =>
                  editingServer === s.id ? (
                    <TR key={s.id}>
                      <ServerEditCells server={s} onDone={() => setEditingServer(null)} />
                    </TR>
                  ) : (
                    <TR key={s.id}>
                      <TD className="font-mono text-xs">{s.hostname}</TD>
                      <TD className="font-mono text-xs">{s.ip}</TD>
                      <TD className="font-mono text-xs">{s.port}</TD>
                      <TD><Badge variant={s.env === "PROD" ? "success" : s.env === "STAGE" ? "info" : "warning"}>{SERVER_ENV[s.env]}</Badge></TD>
                      <TD>{s.role}</TD>
                      <TD className="text-right">
                        {editable && (
                          <Button size="icon" variant="ghost" aria-label={`${s.hostname} 수정`} onClick={() => setEditingServer(s.id)}>
                            <Pencil />
                          </Button>
                        )}
                      </TD>
                    </TR>
                  ),
                )}
              </TBody>
            </Table>
          ) : (
            <Empty>등록된 서버가 없습니다.</Empty>
          )}
        </CardContent>
      </Card>

      {sys.kind === "BUSINESS" && (
        <Card>
          <CardHeader>
            <CardTitle>제공 API · MCP 서버</CardTitle>
            <CardDescription>이 시스템이 등록한 연계 대상. 구독과 Tool 신청은 이 시스템 담당자(또는 admin)가 승인합니다.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {assets.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-2 rounded-2xl bg-[#f5f6f8] p-3.5 text-sm">
                <Badge variant={a.type === "MCP" ? "violet" : "info"}>{a.type}</Badge>
                <span className="font-medium">{a.name}</span>
                <StatusBadge status={ASSET_STATUS[a.status]} />
                {a.source === "MCP_CONVERTED" && <Badge variant="secondary">API 변환</Badge>}
                <span className="ml-auto text-xs text-muted-foreground">
                  {a.type === "MCP" ? `Tool ${a.tool_count}` : `오퍼레이션 ${a.operation_count}`} · 구독 시스템 {a.subscriber_count}
                </span>
              </div>
            ))}
            {assets.length === 0 && <Empty>등록된 API · MCP 서버가 없습니다.</Empty>}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>이 시스템의 구독 (연계)</CardTitle>
          <CardDescription>이 시스템이 다른 시스템의 MCP 서버 · API를 구독한 내역</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {!editable ? (
            <Empty>구독 내역은 이 시스템 담당자에게만 보입니다.</Empty>
          ) : (
            <>
              {outgoing.map((s) => (
                <div key={s.id} className="flex items-center justify-between rounded-2xl bg-[#f5f6f8] p-3.5 text-sm">
                  <div>
                    <p className="font-medium">
                      {sys.name} – A2X – {s.provider_system.name} <span className="text-muted-foreground">({s.asset.name})</span>
                    </p>
                    <p className="text-muted-foreground">{s.purpose}</p>
                  </div>
                  <StatusBadge status={REQ_STATUS[s.status]} />
                </div>
              ))}
              {outgoing.length === 0 && <Empty>구독 내역이 없습니다.</Empty>}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// 시스템 기본정보 수정: 코드 · 구분은 바꾸지 않는다(이름은 코드와 같은 약어 규칙)
function SystemInfoForm({ sys, onDone }: { sys: SystemOut; onDone: () => void }) {
  const [f, setF] = useState({ process: sys.process, dept: sys.dept, url: sys.url, data_level: sys.data_level, description: sys.description });
  const save = useAction(() => patch<SystemOut>(`/systems/${sys.id}`, f));
  const up = (k: keyof typeof f) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Card>
      <CardHeader>
        <CardTitle>시스템 정보 수정 · {sys.code}</CardTitle>
        <CardDescription>시스템 코드와 구분은 바꿀 수 없습니다. 담당자는 아래 담당자 목록에서 바로 추가 · 뺄 수 있습니다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <section className="grid gap-4 sm:grid-cols-2">
          <Lbl label="업무 프로세스">
            <NativeSelect value={f.process} onChange={up("process")}>
              {[...new Set([f.process, ...PROCESSES])].map((p) => <option key={p}>{p}</option>)}
            </NativeSelect>
          </Lbl>
          <Lbl label="소속 부서"><Input value={f.dept} onChange={up("dept")} /></Lbl>
          <Lbl label="데이터 등급">
            <NativeSelect value={f.data_level} onChange={up("data_level")}>
              {(Object.keys(DATA_LEVEL) as DataLevel[]).map((k) => <option key={k} value={k}>{DATA_LEVEL[k]}</option>)}
            </NativeSelect>
          </Lbl>
          <Lbl label="서비스 URL"><Input value={f.url} onChange={up("url")} /></Lbl>
          <Lbl label="설명"><Input value={f.description} onChange={up("description")} /></Lbl>
        </section>
        <ErrorNote error={save.error} />
        <div className="flex justify-end gap-2 border-t pt-4">
          <Button variant="outline" onClick={onDone}>취소</Button>
          <Button disabled={!f.process || save.isPending} onClick={() => save.mutate(undefined, { onSuccess: onDone })}>저장</Button>
        </div>
      </CardContent>
    </Card>
  );
}

type ServerDraft = { hostname: string; ip: string; port: string; env: ServerEnv; role: string };
const EMPTY_SERVER: ServerDraft = { hostname: "", ip: "", port: "", env: "PROD", role: "" };

function SystemForm({ onDone, prefill, serverFill }: { onDone: (id?: number) => void; prefill?: FormSuggestion | null; serverFill?: FormSuggestion | null }) {
  const v = prefill?.values;
  const [f, setF] = useState({
    code: v?.code ?? "", name: v?.name ?? "", kind: (v?.kind ?? "BUSINESS") as SystemKind, process: (v?.process ?? PROCESSES[0]) as string,
    dept: v?.dept ?? "", url: v?.url ?? "", data_level: (v?.data_level ?? "INTERNAL") as DataLevel, description: v?.description ?? "",
  });
  const me = useMe().data!;
  const [extra, setExtra] = useState<UserBrief[]>(((v?.managers ?? []) as UserBrief[]).filter((u) => u.email !== me.user.email));
  const [servers, setServers] = useState<ServerDraft[]>(
    v?.servers?.length
      ? (v.servers as { hostname: string; ip: string; port: number; env: ServerEnv; role: string }[]).map((s) => ({ ...s, port: String(s.port) }))
      : [{ ...EMPTY_SERVER }],
  );
  const [note, setNote] = useState(prefill ?? null);
  // 서버 정보만 채우는 제안: 입력한 행은 두고, 빈 행은 버리고, 같은 호스트명은 건너뛴다
  const [serverNote, setServerNote] = useState<FormSuggestion | null>(null);
  useEffect(() => {
    if (!serverFill) return;
    const incoming = (serverFill.values.servers ?? []) as { hostname: string; ip: string; port: number; env: ServerEnv; role: string }[];
    setServers((prev) => {
      const kept = prev.filter((s) => s.hostname || s.ip);
      const have = new Set(kept.map((s) => s.hostname));
      const added = incoming.filter((s) => !have.has(s.hostname)).map((s) => ({ ...s, port: String(s.port) }));
      return [...kept, ...added].length ? [...kept, ...added] : [{ ...EMPTY_SERVER }];
    });
    setF((cur) => (cur.code ? cur : { ...cur, code: serverFill.values.code ?? "" }));
    setServerNote(serverFill);
  }, [serverFill]);
  const bridge = useAgentBridge();
  const create = useAction((body: unknown) => post<SystemOut>("/systems", body));

  const up = (k: keyof typeof f) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const upServer = (i: number, k: keyof ServerDraft, v: string) => setServers((s) => s.map((x, j) => (j === i ? { ...x, [k]: v } : x)));

  const submit = () =>
    create.mutate(
      {
        ...f,
        manager_emails: extra.map((u) => u.email),
        servers: servers.filter((s) => s.hostname && s.ip).map((s) => ({ ...s, port: Number(s.port) || 80 })),
      },
      { onSuccess: (s) => onDone(s.id) },
    );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>시스템 등록</CardTitle>
            <CardDescription>AI Agent도 시스템으로 등록합니다. 등록한 사람이 첫 담당자가 되고, 담당자 추가는 승인 없이 바로 반영됩니다.</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => bridge.ask(`${f.code} 시스템 등록 채워줘`.trim())} title="IRP(시스템 마스터) · DCM(서버 자산)에서 읽어 채울 값을 Agent가 제안합니다">
            <Sparkles /> Agent로 채우기
          </Button>
        </div>
      </CardHeader>
      <CardContent className={cn("space-y-6", note && agentRing, note && "rounded-b-[22px]")}>
        {note && <AgentFilledNote s={note} onClose={() => setNote(null)} />}
        <section className="grid gap-4 sm:grid-cols-2">
          <Lbl label="시스템 코드 (영문으로 시작)"><Input value={f.code} onChange={up("code")} placeholder="예: QMS" /></Lbl>
          <Lbl label="시스템 이름"><Input value={f.name} onChange={up("name")} /></Lbl>
          <Lbl label="구분">
            <NativeSelect value={f.kind} onChange={up("kind")}>
              <option value="BUSINESS">업무 시스템</option>
              <option value="AGENT">AI Agent</option>
            </NativeSelect>
          </Lbl>
          <Lbl label="업무 프로세스">
            <NativeSelect value={f.process} onChange={up("process")}>
              {PROCESSES.map((p) => <option key={p}>{p}</option>)}
            </NativeSelect>
          </Lbl>
          <Lbl label="소속 부서"><Input value={f.dept} onChange={up("dept")} /></Lbl>
          <Lbl label="데이터 등급">
            <NativeSelect value={f.data_level} onChange={up("data_level")}>
              {(Object.keys(DATA_LEVEL) as DataLevel[]).map((k) => <option key={k} value={k}>{DATA_LEVEL[k]}</option>)}
            </NativeSelect>
          </Lbl>
          <Lbl label="서비스 URL"><Input value={f.url} onChange={up("url")} /></Lbl>
          <Lbl label="설명"><Input value={f.description} onChange={up("description")} /></Lbl>
        </section>

        <section className="space-y-2">
          <p className="text-sm font-medium">추가 담당자 (나는 자동으로 담당자)</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {extra.map((u) => (
              <Badge key={u.id} variant="secondary" className="gap-1" title={u.email}>
                {u.name}
                <button onClick={() => setExtra(extra.filter((x) => x.id !== u.id))} aria-label={`${u.name} 빼기`}>
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
            <UserPicker
              placeholder="이름 · 이메일로 담당자 찾기"
              excludeEmails={[me.user.email, ...extra.map((u) => u.email)]}
              onPick={(u) => setExtra([...extra, u])}
            />
          </div>
        </section>

        <section className={cn("space-y-2", serverNote && cn(agentRing, "rounded-2xl p-3"))}>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">서버 정보</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => bridge.ask(`${f.code} 시스템 서버 채워줘`.trim())} title="입력한 시스템 코드로 DCM(서버 자산)에서 서버를 찾아 Agent가 채웁니다">
                <Sparkles /> Agent로 서버 채우기
              </Button>
              <Button variant="outline" size="sm" onClick={() => setServers([...servers, { ...EMPTY_SERVER }])}>
                <Plus /> 서버 추가
              </Button>
            </div>
          </div>
          {serverNote && <AgentFilledNote s={serverNote} onClose={() => setServerNote(null)} />}
          {servers.map((s, i) => (
            <div key={i} className="grid grid-cols-[1.3fr_1.2fr_0.7fr_0.8fr_1fr_auto] gap-2">
              <Input placeholder="호스트명" value={s.hostname} onChange={(e) => upServer(i, "hostname", e.target.value)} />
              <Input placeholder="IP" value={s.ip} onChange={(e) => upServer(i, "ip", e.target.value)} />
              <Input placeholder="포트" inputMode="numeric" value={s.port} onChange={(e) => upServer(i, "port", e.target.value)} />
              <NativeSelect value={s.env} onChange={(e) => upServer(i, "env", e.target.value)}>
                {(Object.keys(SERVER_ENV) as ServerEnv[]).map((k) => <option key={k} value={k}>{SERVER_ENV[k]}</option>)}
              </NativeSelect>
              <Input placeholder="용도 (WAS, API, MCP…)" value={s.role} onChange={(e) => upServer(i, "role", e.target.value)} />
              <Button variant="ghost" size="icon" onClick={() => setServers(servers.filter((_, j) => j !== i))} aria-label="서버 삭제">
                <Trash2 />
              </Button>
            </div>
          ))}
        </section>

        <ErrorNote error={create.error} />
        <div className="flex justify-end gap-2 border-t pt-4">
          <Button variant="outline" onClick={() => onDone()}>취소</Button>
          <Button onClick={submit} disabled={!f.code || !f.name || create.isPending}>등록</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Lbl({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="font-medium">{label}</span>
      {children}
    </label>
  );
}
