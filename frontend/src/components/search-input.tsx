import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// 공통 검색창: 돋보기 + 지우기(×) 버튼
export function SearchInput({
  value,
  onChange,
  placeholder = "검색",
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative w-64", className)}>
      <Search className="pointer-events-none absolute top-3 left-3.5 size-4 text-muted-foreground" />
      <Input className="pr-9 pl-10" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="검색어 지우기"
          className="absolute top-2.5 right-2.5 grid size-5 place-items-center rounded-full bg-[#d1d1d6] text-white hover:bg-[#8e8e93]"
        >
          <X className="size-3" />
        </button>
      )}
    </div>
  );
}

// 여러 값 중 하나라도 검색어를 포함하면 참 (대소문자 무시)
export const matches = (q: string, ...values: (string | undefined)[]) => {
  const s = q.trim().toLowerCase();
  return !s || values.some((v) => v?.toLowerCase().includes(s));
};
