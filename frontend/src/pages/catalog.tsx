import { useEffect, useState } from "react";
import { useAgentBridge, useRequestOpen, useSuggestion } from "@/lib/agent-bridge";
import type { FormSuggestion } from "@/lib/api";
import { ArrowRight, Check, LayoutGrid, List, Pencil, ShoppingBasket, Trash2 } from "lucide-react";
import type { AssetIcon, Role } from "@/lib/sample-data";
import { del, put, type AssetSummary, type AssetType } from "@/lib/api";
import { ASSET_STATUS } from "@/lib/labels";
import { useAction, useAsset, useAssets, useMe } from "@/lib/queries";
import { RequestScreen } from "@/pages/catalog-request";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs } from "@/components/tabs";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Modal } from "@/components/modal";
import { StatusBadge } from "@/components/status-badge";
import { AssetIconPicker, AssetIconTile, normalizeIcon, toIconIn } from "@/components/asset-icon";
import { SearchInput } from "@/components/search-input";
import { Empty, ErrorNote, Loading } from "@/components/feedback";
import { cn } from "@/lib/utils";

type Filter = "" | AssetType;

export function CatalogPage({ role }: { role: Role }) {
  const [q, setQ] = useState("");
  const [type, setType] = useState<Filter>("");
  const [view, setView] = useState<"card" | "list">("card");
  // 사용 신청: 여러 개를 담아 한 번에 신청 화면으로 간다(바로 신청은 그 하나만)
  const [cart, setCart] = useState<number[]>([]);
  const [requesting, setRequesting] = useState<number[] | null>(null);
  // Agent: 구독 신청 제안이 오면 그 자산의 신청 화면을 채워서 연다
  const bridge = useAgentBridge();
  const [prefill, setPrefill] = useState<FormSuggestion | null>(null);
  useSuggestion("subscription", (s) => {
    setPrefill(s);
    setRequesting([s.values.asset_id]);
  });
  const { setFocus } = bridge;
  useEffect(() => {
    if (!requesting) setFocus({});
  }, [requesting, setFocus]);
  // 내 권한 '더 신청' · Agent의 Tool 신청 안내: 그 자산을 담은 사용 신청 화면으로
  useRequestOpen((ids) => setRequesting(ids));
  const toggleCart = (id: number) => setCart((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const [editingIcon, setEditingIcon] = useState<AssetSummary | null>(null);

  const assets = useAssets({ q, type });
  const me = useMe().data!;
  const managed = new Set(me.managed_system_ids);
  const list = assets.data ?? [];
  const canEdit = (a: AssetSummary) => role === "admin" || managed.has(a.system.id);

  // 등록정보 수정: 직접 등록한 API · MCP만(변환 MCP는 원본 API에서 다시 변환)
  const canEditSpec = (a: AssetSummary) => canEdit(a) && a.source !== "MCP_CONVERTED";
  const editSpec = (a: AssetSummary) => bridge.edit({ type: a.type, id: a.id });
  // 삭제: 진행 중인 구독 · 변환 MCP가 있으면 서버가 막고 이유를 알려 준다
  const remove = useAction((id: number) => del(`/assets/${id}`));
  const askRemove = (a: AssetSummary) => {
    if (!confirm(`${a.name}을(를) 삭제할까요?\n진행 중인 구독이 있거나 이 API로 만든 변환 MCP가 있으면 삭제되지 않습니다. 호출 로그는 남습니다.`)) return;
    remove.mutate(a.id, { onSuccess: () => setCart((c) => c.filter((x) => x !== a.id)) });
  };

  // 신청 화면 전환은 모든 훅 다음에 둔다(훅 개수가 렌더마다 같아야 함)
  if (requesting)
    return (
      <RequestScreen
        ids={requesting}
        role={role}
        prefill={prefill?.values.asset_id && requesting.includes(prefill.values.asset_id) ? prefill : null}
        onBack={() => {
          setRequesting(null);
          setPrefill(null);
          window.scrollTo({ top: 0 });
        }}
        onRemove={(id) => {
          setRequesting((r) => r && r.filter((x) => x !== id));
          setCart((c) => c.filter((x) => x !== id));
        }}
        onSent={(okIds) => setCart((c) => c.filter((x) => !okIds.includes(x)))}
      />
    );
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput value={q} onChange={setQ} placeholder="API · MCP 이름, 시스템, 부서" className="w-80" />
        <Tabs<Filter> value={type} onChange={setType} items={[{ value: "", label: "전체" }, { value: "API", label: "API" }, { value: "MCP", label: "MCP" }]} />
        <span className="text-[13px] text-muted-foreground">{list.length}개</span>
        <div className="ml-auto inline-flex gap-1 rounded-full bg-white p-1 ring-1 ring-black/[0.06]">
          {([
            ["card", LayoutGrid, "카드로 보기"],
            ["list", List, "리스트로 보기"],
          ] as const).map(([v, Icon, label]) => (
            <button
              key={v}
              type="button"
              title={label}
              aria-label={label}
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={cn(
                "grid size-8 place-items-center rounded-full transition-all",
                view === v ? "bg-primary text-white shadow-[0_4px_12px_rgb(0_113_227/0.3)]" : "text-muted-foreground hover:bg-[#f0f0f2] hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
            </button>
          ))}
        </div>
      </div>

      {assets.isLoading && <Loading />}
      <ErrorNote error={assets.error ?? remove.error} />

      {view === "list" ? (
        <Card>
          <CardContent className="p-3">
            <Table>
              <THead>
                <TR>
                  <TH className="w-10" />
                  <TH className="w-[36%]">이름</TH>
                  <TH>유형</TH>
                  <TH>상태</TH>
                  <TH>프로바이더 시스템</TH>
                  <TH className="text-right">Tool · 오퍼레이션</TH>
                  <TH className="text-right">연계</TH>
                  <TH className="text-right" />
                </TR>
              </THead>
              <TBody>
                {list.map((a) => (
                  <TR key={a.id}>
                    <TD>
                      <input type="checkbox" aria-label={`${a.name} 담기`} disabled={a.status !== "LIVE"} checked={cart.includes(a.id)} onChange={() => toggleCart(a.id)} />
                    </TD>
                    <TD>
                      <div className="flex items-center gap-3">
                        <IconButton a={a} editable={canEdit(a)} size={36} onEdit={() => setEditingIcon(a)} />
                        <div className="min-w-0">
                          <p className="flex items-center gap-1.5 font-bold">
                            <span className="truncate">{a.name}</span>
                            {a.source === "MCP_CONVERTED" && <Badge variant="secondary">API에서 변환</Badge>}
                          </p>
                          <p className="truncate text-[12.5px] text-muted-foreground">{a.description}</p>
                        </div>
                      </div>
                    </TD>
                    <TD><Badge variant={a.type === "MCP" ? "violet" : "info"}>{a.type}</Badge></TD>
                    <TD><StatusBadge status={ASSET_STATUS[a.status]} /></TD>
                    <TD>
                      <p>{a.system.name}</p>
                      <p className="text-[12px] text-muted-foreground">{a.system.dept}</p>
                    </TD>
                    <TD className="text-right">{a.type === "MCP" ? `Tool ${a.tool_count}` : `오퍼레이션 ${a.operation_count}`}</TD>
                    <TD className="text-right text-muted-foreground">{a.type === "MCP" ? `Agent ${a.subscriber_count}` : `시스템 ${a.subscriber_count}`}</TD>
                    <TD className="text-right">
                      <div className="flex justify-end gap-1.5">
                        {canEditSpec(a) && (
                          <Button size="sm" variant="outline" onClick={() => editSpec(a)}>
                            <Pencil /> 수정
                          </Button>
                        )}
                        {canEdit(a) && (
                          <Button size="icon" variant="ghost" className="size-8 text-muted-foreground hover:text-destructive" aria-label={`${a.name} 삭제`} title="삭제" onClick={() => askRemove(a)}>
                            <Trash2 />
                          </Button>
                        )}
                        <Button size="sm" disabled={a.status !== "LIVE"} onClick={() => setRequesting([a.id])}>
                          사용 신청 <ArrowRight />
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            {!assets.isLoading && list.length === 0 && <Empty>해당하는 항목이 없습니다.</Empty>}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {list.map((a) => (
            <CatalogCard key={a.id} a={a} editable={canEdit(a)} onEditIcon={() => setEditingIcon(a)} onRequest={() => setRequesting([a.id])} onEdit={canEditSpec(a) ? () => editSpec(a) : undefined} onDelete={canEdit(a) ? () => askRemove(a) : undefined} inCart={cart.includes(a.id)} onToggleCart={() => toggleCart(a.id)} />
          ))}
          {!assets.isLoading && list.length === 0 && <Empty>해당하는 항목이 없습니다.</Empty>}
        </div>
      )}

      {/* 담은 항목: 화면 아래에 떠 있는 신청 바 */}
      {cart.length > 0 && (
        <div className="sticky bottom-4 z-20 flex flex-wrap items-center gap-3 rounded-[22px] bg-[#1d1d1f] px-5 py-3 text-white shadow-[0_16px_40px_rgb(0_0_0/0.25)]">
          <ShoppingBasket className="size-5" />
          <span className="font-bold">{cart.length}개 담음</span>
          <span className="min-w-0 flex-1 truncate text-[13px] text-white/70">
            {cart.map((id) => list.find((a) => a.id === id)?.name ?? (assets.data ?? []).find((a) => a.id === id)?.name).filter(Boolean).join(", ")}
          </span>
          <Button size="sm" variant="ghost" className="text-white hover:bg-white/10 hover:text-white" onClick={() => setCart([])}>비우기</Button>
          <Button size="sm" onClick={() => setRequesting(cart)}>
            한 번에 사용 신청 <ArrowRight />
          </Button>
        </div>
      )}
      {editingIcon && <IconEditModal asset={editingIcon} onClose={() => setEditingIcon(null)} />}
    </div>
  );
}

function IconButton({ a, editable, size, onEdit }: { a: AssetSummary; editable: boolean; size: number; onEdit: () => void }) {
  if (!editable) return <AssetIconTile asset={a} size={size} />;
  return (
    <button type="button" onClick={onEdit} title="대표 이미지 변경" className="group relative shrink-0">
      <AssetIconTile asset={a} size={size} />
      <span className="absolute -right-1 -bottom-1 grid size-5 place-items-center rounded-full bg-white text-muted-foreground opacity-0 shadow ring-1 ring-black/10 transition-opacity group-hover:opacity-100">
        <Pencil className="size-3" />
      </span>
    </button>
  );
}

function CatalogCard({ a, editable, onEditIcon, onRequest, onEdit, onDelete, inCart, onToggleCart }: { a: AssetSummary; editable: boolean; onEditIcon: () => void; onRequest: () => void; onEdit?: () => void; onDelete?: () => void; inCart: boolean; onToggleCart: () => void }) {
  // 카드 미리보기에 오퍼레이션 · Tool 이름을 보여주기 위해 상세를 읽는다(캐시됨)
  const d = useAsset(a.id).data;
  const items = d ? (a.type === "MCP" ? d.tools.filter((t) => t.exposed).map((t) => t.name) : d.operations.map((o) => `${o.method} ${o.path}`)) : [];
  return (
    <Card className={cn("flex flex-col transition-transform duration-300 hover:-translate-y-1", inCart && "ring-2 ring-primary")}>
      <CardHeader>
        <div className="flex items-start gap-3.5">
          <IconButton a={a} editable={editable} size={52} onEdit={onEditIcon} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant={a.type === "MCP" ? "violet" : "info"}>{a.type}</Badge>
              <StatusBadge status={ASSET_STATUS[a.status]} />
              {a.source === "MCP_CONVERTED" && <Badge variant="secondary">API에서 변환</Badge>}
            </div>
            <CardTitle className="mt-1.5 truncate">{a.name}</CardTitle>
          </div>
          {onDelete && (
            <Button size="icon" variant="ghost" className="size-8 shrink-0 text-muted-foreground hover:text-destructive" aria-label={`${a.name} 삭제`} title="삭제" onClick={onDelete}>
              <Trash2 />
            </Button>
          )}
        </div>
        <CardDescription className="mt-1.5">{a.description}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto space-y-4">
        <div className="flex min-h-6 flex-wrap gap-1.5">
          {items.slice(0, 4).map((x) => (
            <span key={x} className="rounded-lg bg-[#f5f6f8] px-2 py-0.5 font-mono text-[11.5px] text-[#3a3a3c]">{x}</span>
          ))}
          {items.length > 4 && <span className="px-1 text-[11.5px] text-muted-foreground">+{items.length - 4}</span>}
        </div>
        <div className="flex items-center justify-between gap-2 border-t border-black/[0.05] pt-4 text-[13px] text-muted-foreground">
          <span className="truncate">
            {a.system.name} · {a.type === "MCP" ? `Agent 연계 ${a.subscriber_count}` : `구독 시스템 ${a.subscriber_count}`}
          </span>
          <div className="flex shrink-0 gap-1.5">
            {onEdit && (
              <Button size="sm" variant="outline" onClick={onEdit} aria-label={`${a.name} 수정`}>
                <Pencil /> 수정
              </Button>
            )}
            <Button
              size="sm"
              variant={inCart ? "default" : "outline"}
              disabled={a.status !== "LIVE"}
              onClick={onToggleCart}
              aria-pressed={inCart}
              title="여러 개를 담아 한 번에 신청합니다"
            >
              {inCart ? <Check /> : <ShoppingBasket />} {inCart ? "담음" : "담기"}
            </Button>
            <Button size="sm" variant={inCart ? "outline" : "default"} disabled={a.status !== "LIVE"} onClick={onRequest}>
              사용 신청 <ArrowRight />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function IconEditModal({ asset, onClose }: { asset: AssetSummary; onClose: () => void }) {
  const [icon, setIcon] = useState<AssetIcon | undefined>(normalizeIcon(asset.icon));
  const save = useAction(() => put(`/assets/${asset.id}/icon`, toIconIn(icon)));
  return (
    <Modal onClose={onClose} title={`${asset.name} · 대표 이미지`}>
      <div className="space-y-5 text-sm">
        <AssetIconPicker value={icon} onChange={setIcon} fallback={{ type: asset.type }} />
        <ErrorNote error={save.error} />
        <div className="flex justify-end gap-2 border-t border-black/[0.06] pt-4">
          <Button variant="ghost" onClick={onClose}>취소</Button>
          <Button disabled={save.isPending} onClick={() => save.mutate(undefined, { onSuccess: onClose })}>저장</Button>
        </div>
      </div>
    </Modal>
  );
}
