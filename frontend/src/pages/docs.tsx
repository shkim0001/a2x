import { useRef, useState } from "react";
import { FlaskConical, Loader2, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { del, get, post, qs, uploadConsultDoc, type ConsultDocOut, type DocSearchOut } from "@/lib/api";
import { DOC_STATUS, fmtDate } from "@/lib/labels";
import { useAction, useConsultDocs } from "@/lib/queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { StatusBadge } from "@/components/status-badge";
import { SearchInput, matches } from "@/components/search-input";
import { ErrorNote, Loading } from "@/components/feedback";

const kb = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

// 관리 › 컨설팅 문서 (admin): 업로드하면 ChromaDB에 색인되어 컨설팅 Agent의 답변 근거가 된다.
export function DocsPage() {
  const [q, setQ] = useState("");
  const docs = useConsultDocs();
  const rows = (docs.data ?? []).filter((d) => matches(q, d.name, d.uploaded_by ?? "", DOC_STATUS[d.status]));
  const file = useRef<HTMLInputElement>(null);

  const upload = useAction((f: File) => uploadConsultDoc(f));
  const reindex = useAction((id: number) => post<ConsultDocOut>(`/consult-docs/${id}/reindex`));
  const remove = useAction((id: number) => del<void>(`/consult-docs/${id}`));
  const busyId = (reindex.isPending ? reindex.variables : undefined) ?? (remove.isPending ? remove.variables : undefined);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>컨설팅 문서</CardTitle>
            <CardDescription>
              업로드한 문서는 청크로 나눠 ChromaDB에 색인되고, 컨설팅 Agent가 답변 근거로 씁니다. MD · TXT · DOCX · PDF(5MB 이하) · {rows.length}건
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <SearchInput value={q} onChange={setQ} placeholder="문서명, 업로드한 사람, 상태" />
            <input
              ref={file}
              type="file"
              accept=".md,.txt,.docx,.pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = "";
              }}
            />
            <Button size="sm" onClick={() => file.current?.click()} disabled={upload.isPending}>
              {upload.isPending ? <Loader2 className="animate-spin" /> : <Upload />} {upload.isPending ? "색인 중…" : "문서 업로드"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorNote error={upload.error ?? reindex.error ?? remove.error ?? docs.error} />
          {upload.isSuccess && upload.data && (
            <p className="rounded-2xl bg-[#e6f6ea] px-4 py-2.5 text-sm text-[#1e6b34]">
              '{upload.data.name}' {upload.data.status === "INDEXED" ? `색인 완료 · ${upload.data.chunk_count}청크` : `색인 실패 — ${upload.data.error}`}
            </p>
          )}
          {docs.isLoading ? (
            <Loading />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>문서</TH>
                  <TH>업로드</TH>
                  <TH>일자</TH>
                  <TH className="text-right">크기</TH>
                  <TH className="text-right">청크</TH>
                  <TH>상태</TH>
                  <TH className="text-right">관리</TH>
                </TR>
              </THead>
              <TBody>
                {rows.map((d) => (
                  <TR key={d.id}>
                    <TD className="font-medium">
                      {d.name} {d.is_sample && <Badge variant="secondary" className="ml-1">샘플</Badge>}
                      {d.status === "FAILED" && d.error && <p className="mt-0.5 text-xs font-normal text-[#d70015]">{d.error}</p>}
                    </TD>
                    <TD className="text-muted-foreground">{d.uploaded_by ?? "-"}</TD>
                    <TD className="text-muted-foreground">{fmtDate(d.created_at)}</TD>
                    <TD className="text-right text-muted-foreground">{kb(d.size_bytes)}</TD>
                    <TD className="text-right">{d.chunk_count}</TD>
                    <TD><StatusBadge status={DOC_STATUS[d.status]} /></TD>
                    <TD className="text-right">
                      <div className="inline-flex gap-1">
                        <Button variant="ghost" size="sm" disabled={busyId === d.id} onClick={() => reindex.mutate(d.id)} title="원본 파일로 다시 색인">
                          {busyId === d.id && reindex.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} 다시 색인
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[#d70015] hover:text-[#d70015]"
                          disabled={busyId === d.id}
                          onClick={() => window.confirm(`'${d.name}'을(를) 삭제할까요? 색인도 함께 지워져 컨설팅 Agent가 더 이상 근거로 쓰지 않습니다.${d.is_sample ? " (샘플 원본 파일은 남습니다)" : ""}`) && remove.mutate(d.id)}
                        >
                          <Trash2 /> 삭제
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
          {!docs.isLoading && rows.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">해당하는 문서가 없습니다.</p>}
          <p className="text-xs text-muted-foreground">PDF는 쪽마다 글자를 뽑아 근거 출처에 쪽 번호(p.N)가 나옵니다. 스캔한 이미지 PDF와 암호가 걸린 PDF는 올릴 수 없습니다. 색인에 실패한 문서는 '다시 색인'으로 재시도할 수 있습니다.</p>
        </CardContent>
      </Card>

      <SearchTest />
    </div>
  );
}

// 근거 검색 시험: 컨설팅 Agent와 같은 판정 규칙(유사도 + 핵심어 포함률)으로 '이 질문에 근거가 잡히는지' 본다.
function SearchTest() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<DocSearchOut | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!q.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      setRes(await get<DocSearchOut>(`/consult-docs/search${qs({ q })}`));
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><FlaskConical className="size-5 text-primary" /> 근거 검색 시험</CardTitle>
        <CardDescription>질문을 넣으면 컨설팅 Agent와 같은 규칙으로 근거 유무를 판정합니다. 근거가 없으면 Agent는 추측하지 않고 담당자 문의를 안내합니다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && run()} placeholder="예: 방화벽 신청 절차가 궁금해요" />
          <Button onClick={run} disabled={busy || !q.trim()}>
            {busy ? <Loader2 className="animate-spin" /> : <Search />} 시험
          </Button>
        </div>
        <ErrorNote error={err} />
        {res && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant={res.ok ? "success" : "danger"}>{res.ok ? "근거 있음 → LLM이 근거로 답변" : "근거 없음 → 담당자 안내"}</Badge>
              <span className="text-muted-foreground">최고 유사도 {res.top_score.toFixed(3)} · 핵심어 포함률 {(res.coverage * 100).toFixed(0)}%</span>
              <span className="text-muted-foreground">
                핵심어 {res.keywords.join(", ") || "-"}
                {res.missing.length > 0 && <> · 문서에 없음 <b className="text-[#d70015]">{res.missing.join(", ")}</b></>}
              </span>
            </div>
            <div className="space-y-2">
              {res.hits.map((h, i) => (
                <div key={i} className="rounded-2xl bg-[#f5f6f8] p-3 text-sm">
                  <p className="flex justify-between gap-2 font-bold">
                    <span>[{i + 1}] {h.doc} › {h.section}</span>
                    <span className="font-mono text-xs font-normal text-muted-foreground">{h.score.toFixed(3)}</span>
                  </p>
                  <p className="mt-1 text-[13px] text-[#3a3a3c]">{h.excerpt}…</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
