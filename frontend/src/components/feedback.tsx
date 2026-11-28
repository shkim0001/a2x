import { Loader2 } from "lucide-react";
import { errText } from "@/lib/queries";
import { cn } from "@/lib/utils";

export function Loading({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground", className)}>
      <Loader2 className="size-4 animate-spin" /> 불러오는 중…
    </div>
  );
}

export function ErrorNote({ error, className }: { error: unknown; className?: string }) {
  if (!error) return null;
  return <p className={cn("rounded-xl bg-[#fdecee] px-3 py-2 text-[13px] text-[#d70015]", className)}>{errText(error)}</p>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-8 text-center text-sm text-muted-foreground">{children}</p>;
}

export function SampleNote({ children = "샘플 데이터입니다. 실제 호출 로그는 T1-2(모니터링 데이터)에서 연결됩니다." }: { children?: React.ReactNode }) {
  return <span className="inline-flex items-center gap-1.5 rounded-full bg-[#fff3e0] px-2.5 py-0.5 text-[11.5px] font-bold text-[#b06d00]">● {children}</span>;
}
