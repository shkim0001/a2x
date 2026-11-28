import { cn } from "@/lib/utils";

// 덱의 알약형 전환 버튼. 선택되면 파랑으로 채운다.
export function Tabs<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: string; count?: number }[];
}) {
  return (
    <div className="inline-flex gap-1 rounded-full bg-white p-1 ring-1 ring-black/[0.06]">
      {items.map((it) => {
        const on = value === it.value;
        return (
          <button
            key={it.value}
            type="button"
            onClick={() => onChange(it.value)}
            className={cn(
              "rounded-full px-3.5 py-1.5 text-[14px] transition-all duration-200",
              on ? "bg-primary text-white shadow-[0_4px_12px_rgb(0_113_227/0.3)]" : "text-muted-foreground hover:bg-[#f0f0f2] hover:text-foreground",
            )}
          >
            {it.label}
            {it.count !== undefined && (
              <span className={cn("ml-1.5 rounded-full px-1.5 text-[11px]", on ? "bg-white/25" : "bg-[#f0f0f2]")}>{it.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
