import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-10 w-full rounded-xl border-0 bg-[#f5f6f8] px-3.5 py-1 text-sm ring-1 ring-black/[0.06] transition-all placeholder:text-[#a1a1a6] hover:bg-[#eef1f6] focus-visible:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
