import { Sparkles, X } from "lucide-react";
import type { FormSuggestion } from "@/lib/api";

// Agent 제안 값으로 채운 양식 위에 붙는 안내. 제출은 사용자가 직접 한다(가드레일 1).
export function AgentFilledNote({ s, onClose }: { s: FormSuggestion; onClose: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl bg-[#eef3ff] p-4 text-sm text-[#1f4fd1] ring-1 ring-[#2f6bff]/25">
      <Sparkles className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1 space-y-1">
        <p>
          <b>Agent가 {s.source?.label ?? "마스터 정보"} 값으로 채웠습니다.</b> 파란 테두리로 표시한 값을 확인한 뒤 직접 제출하세요.
        </p>
        {s.notes.map((n) => (
          <p key={n} className="text-[13px] text-[#3a5bbf]">※ {n}</p>
        ))}
      </div>
      <button onClick={onClose} aria-label="안내 닫기" className="rounded p-0.5 hover:bg-white/60">
        <X className="size-4" />
      </button>
    </div>
  );
}

export const agentRing = "ring-2 ring-[#2f6bff]/40";
