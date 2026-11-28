import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { cn } from "@/lib/utils";

// 목록 아래 페이지 이동: 전체 건수 · 보고 있는 범위 · 페이지 번호(앞뒤 2쪽) · 페이지당 건수
export function Pager({
  page,
  size,
  total,
  onPage,
  onSize,
  sizes = [20, 50, 100],
  loading,
}: {
  page: number;
  size: number;
  total: number;
  onPage: (p: number) => void;
  onSize?: (s: number) => void;
  sizes?: number[];
  loading?: boolean;
}) {
  const last = Math.max(1, Math.ceil(total / size));
  const from = total === 0 ? 0 : (page - 1) * size + 1;
  const to = Math.min(page * size, total);
  const start = Math.max(1, Math.min(page - 2, last - 4));
  const pages = Array.from({ length: Math.min(5, last) }, (_, i) => start + i);
  const btn = "grid size-8 place-items-center rounded-full text-[13px] transition-colors disabled:opacity-30 disabled:hover:bg-transparent";

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-black/[0.06] pt-3 text-[13px] text-muted-foreground">
      <span>
        총 <b className="text-foreground">{total.toLocaleString()}</b>건 · {from.toLocaleString()}–{to.toLocaleString()}
        {loading && <span className="ml-2 text-[12px]">불러오는 중…</span>}
      </span>
      <nav className="flex items-center gap-0.5" aria-label="페이지 이동">
        <button className={cn(btn, "hover:bg-[#f0f0f2]")} onClick={() => onPage(1)} disabled={page <= 1} aria-label="첫 페이지"><ChevronsLeft className="size-4" /></button>
        <button className={cn(btn, "hover:bg-[#f0f0f2]")} onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="이전 페이지"><ChevronLeft className="size-4" /></button>
        {pages.map((p) => (
          <button
            key={p}
            onClick={() => onPage(p)}
            aria-current={p === page ? "page" : undefined}
            className={cn(btn, "w-auto min-w-8 px-2", p === page ? "bg-primary font-bold text-primary-foreground" : "text-foreground hover:bg-[#f0f0f2]")}
          >
            {p}
          </button>
        ))}
        <button className={cn(btn, "hover:bg-[#f0f0f2]")} onClick={() => onPage(page + 1)} disabled={page >= last} aria-label="다음 페이지"><ChevronRight className="size-4" /></button>
        <button className={cn(btn, "hover:bg-[#f0f0f2]")} onClick={() => onPage(last)} disabled={page >= last} aria-label="마지막 페이지"><ChevronsRight className="size-4" /></button>
      </nav>
      {onSize && (
        <label className="flex items-center gap-1.5">
          페이지당
          <select value={size} onChange={(e) => onSize(Number(e.target.value))} className="rounded-full bg-[#f0f0f2] px-2 py-1 text-[12.5px] text-foreground outline-none">
            {sizes.map((s) => <option key={s} value={s}>{s}건</option>)}
          </select>
        </label>
      )}
    </div>
  );
}
