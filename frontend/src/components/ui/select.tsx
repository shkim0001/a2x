import * as React from "react";
import { cn } from "@/lib/utils";

// 샘플용 기본 select. 필요하면 shadcn/ui Select(Radix)로 교체한다.
export function NativeSelect({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "flex h-10 w-full cursor-pointer rounded-xl border-0 bg-[#f5f6f8] px-3 py-1 text-sm ring-1 ring-black/[0.06] transition-all hover:bg-[#eef1f6] focus-visible:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
