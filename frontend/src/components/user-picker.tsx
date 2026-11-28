import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Search, UserPlus } from "lucide-react";
import type { UserBrief } from "@/lib/api";
import { useUsers } from "@/lib/queries";
import { cn } from "@/lib/utils";

// 사용자 목록에서 골라 넣기(이름 · 이메일 검색). 시스템 담당자 추가 · 시스템 등록의 추가 담당자에서 쓴다.
// excludeEmails에 있는 사람은 '이미 담당자'로 표시하고 고를 수 없다.
export function UserPicker({
  onPick,
  excludeEmails = [],
  placeholder = "이름 · 이메일로 사용자 찾기",
  disabled,
  className,
}: {
  onPick: (u: UserBrief) => void;
  excludeEmails?: string[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 250);
    return () => clearTimeout(t);
  }, [text]);
  // 바깥을 누르면 닫는다
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const users = useUsers(q, open);
  const list = users.data ?? [];
  const taken = new Set(excludeEmails.map((e) => e.toLowerCase()));
  const pickable = list.filter((u) => !taken.has(u.email.toLowerCase()));

  const pick = (u: UserBrief) => {
    if (taken.has(u.email.toLowerCase())) return;
    onPick(u);
    setText("");
    setOpen(false);
  };

  return (
    <div ref={box} className={cn("relative", className)}>
      <div className="flex h-8 items-center gap-1.5 rounded-full bg-white px-3 ring-1 ring-black/[0.1] focus-within:ring-2 focus-within:ring-ring">
        <UserPlus className="size-3.5 shrink-0 text-muted-foreground" />
        <input
          value={text}
          disabled={disabled}
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.nativeEvent.isComposing) return;
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((i) => Math.min(i + 1, Math.max(pickable.length - 1, 0)));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              if (pickable[active]) pick(pickable[active]);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          placeholder={placeholder}
          aria-label="사용자 찾기"
          className="w-48 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
        />
        {users.isFetching && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
      </div>

      {open && (
        <div className="absolute left-0 z-50 mt-1 w-72 overflow-hidden rounded-2xl bg-white shadow-[0_16px_40px_rgb(0_0_0/0.14),0_0_0_1px_rgb(0_0_0/0.06)]">
          {users.error ? (
            <p className="px-3 py-2.5 text-xs text-[#d70015]">{(users.error as Error).message}</p>
          ) : list.length === 0 && !users.isFetching ? (
            <p className="flex items-center gap-1.5 px-3 py-2.5 text-xs text-muted-foreground">
              <Search className="size-3.5" /> {q ? `'${q}'에 맞는 사용자가 없습니다.` : "사용자가 없습니다."}
            </p>
          ) : (
            <ul className="max-h-64 overflow-y-auto py-1" role="listbox">
              {list.map((u) => {
                const already = taken.has(u.email.toLowerCase());
                const idx = pickable.indexOf(u);
                return (
                  <li key={u.id} role="option" aria-selected={idx === active} aria-disabled={already}>
                    <button
                      type="button"
                      disabled={already}
                      onMouseEnter={() => idx >= 0 && setActive(idx)}
                      onClick={() => pick(u)}
                      className={cn(
                        "flex w-full items-center gap-2.5 px-3 py-2 text-left",
                        already ? "cursor-default opacity-50" : idx === active ? "bg-accent" : "hover:bg-[#f5f6f8]",
                      )}
                    >
                      <span className="grid size-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#2f6bff] to-[#7d5cf5] text-[11px] font-bold text-white">
                        {u.name[0]}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-bold">{u.name}</span>
                        <span className="block truncate text-[11px] text-muted-foreground">{u.email}</span>
                      </span>
                      {already && (
                        <span className="flex items-center gap-0.5 text-[11px] text-muted-foreground">
                          <Check className="size-3" /> 이미 담당자
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="border-t border-black/[0.06] px-3 py-1.5 text-[10.5px] text-muted-foreground">↑↓로 고르고 Enter. 포탈에 가입한 사용자만 나옵니다.</p>
        </div>
      )}
    </div>
  );
}
