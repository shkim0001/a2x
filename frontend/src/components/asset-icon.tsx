import { useRef, useState } from "react";
import {
  Bot,
  Building2,
  CreditCard,
  Database,
  Factory,
  FileText,
  Globe,
  Network,
  Package,
  Receipt,
  Search,
  ShieldCheck,
  ShoppingCart,
  Truck,
  Upload,
  Users,
  Warehouse,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { AssetIcon } from "@/lib/sample-data";
import type { IconOut } from "@/lib/api";

type AssetType = "API" | "MCP";
type IconLike = AssetIcon | IconOut | null | undefined;

// API 응답({kind: "PRESET", name, color})과 화면용 아이콘을 같은 형태로 맞춘다
export function normalizeIcon(i: IconLike): AssetIcon | undefined {
  if (!i) return undefined;
  if (i.kind === "preset" || i.kind === "image") return i as AssetIcon;
  const o = i as IconOut;
  return o.kind === "PRESET" && o.name && o.color ? { kind: "preset", name: o.name, color: o.color } : undefined;
}

// 저장 요청용: 백엔드는 아직 준비 아이콘만 받는다(이미지 올리기는 파일 저장소 결정 후)
export const toIconIn = (i: AssetIcon | undefined) => (i?.kind === "preset" ? { name: i.name, color: i.color } : null);
import { cn } from "@/lib/utils";

// 준비된 아이콘 (업무 성격별)
export const PRESET_ICONS: Record<string, { icon: LucideIcon; label: string }> = {
  cart: { icon: ShoppingCart, label: "주문" },
  warehouse: { icon: Warehouse, label: "재고" },
  truck: { icon: Truck, label: "물류" },
  users: { icon: Users, label: "고객" },
  org: { icon: Network, label: "조직" },
  card: { icon: CreditCard, label: "결제" },
  receipt: { icon: Receipt, label: "정산" },
  package: { icon: Package, label: "상품" },
  building: { icon: Building2, label: "기업" },
  database: { icon: Database, label: "데이터" },
  factory: { icon: Factory, label: "생산" },
  doc: { icon: FileText, label: "문서" },
  search: { icon: Search, label: "검색" },
  workflow: { icon: Workflow, label: "프로세스" },
  shield: { icon: ShieldCheck, label: "보안" },
  globe: { icon: Globe, label: "외부" },
  bot: { icon: Bot, label: "AI" },
};

// 색은 차분한 몇 가지만. 기본은 유형별: API 파랑, MCP 보라
export const TYPE_COLOR = { API: "#0071e3", MCP: "#6e4ff6" } as const;
export const ICON_COLORS = ["#0071e3", "#6e4ff6", "#1f8a8a", "#c46a1a", "#64748b", "#1d1d1f"];

const MAX_IMAGE_BYTES = 200 * 1024;

// 이미지가 없을 때: 유형 기본 아이콘 + 유형 색
function autoIcon(asset: { type: AssetType }): AssetIcon {
  return { kind: "preset", name: asset.type === "MCP" ? "bot" : "database", color: TYPE_COLOR[asset.type] };
}

export function AssetIconTile({ asset, icon, size = 48, className }: { asset?: { type: AssetType; icon?: IconLike }; icon?: AssetIcon; size?: number; className?: string }) {
  const ic: AssetIcon = icon ?? normalizeIcon(asset?.icon) ?? (asset ? autoIcon(asset) : { kind: "preset", name: "package", color: "#8e8e93" });
  const radius = Math.round(size * 0.3);
  if (ic.kind === "image") {
    return (
      <img
        src={ic.src}
        alt=""
        className={cn("shrink-0 bg-white object-cover ring-1 ring-black/[0.06]", className)}
        style={{ width: size, height: size, borderRadius: radius }}
      />
    );
  }
  const Icon = (PRESET_ICONS[ic.name] ?? PRESET_ICONS.package).icon;
  // 차분한 스타일: 연한 바탕 + 색 아이콘 (진한 면 · 색 그림자 없음)
  return (
    <span
      className={cn("grid shrink-0 place-items-center", className)}
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        color: ic.color,
        background: `color-mix(in srgb, ${ic.color} 9%, #fff)`,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${ic.color} 14%, transparent)`,
      }}
    >
      <Icon style={{ width: size * 0.46, height: size * 0.46 }} strokeWidth={1.9} />
    </span>
  );
}

// 대표 이미지 고르기: 준비된 아이콘 + 색 / 이미지 올리기
export function AssetIconPicker({ value, onChange, fallback, allowImage = false }: { value?: AssetIcon; onChange: (v: AssetIcon | undefined) => void; fallback: { type: AssetType; systemId?: unknown }; allowImage?: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState("");
  const preset = value?.kind === "preset" ? value : undefined;
  const color = preset?.color ?? TYPE_COLOR[fallback.type];

  const onFile = (f: File) => {
    setErr("");
    if (!/^image\/(png|jpeg|svg\+xml|webp)$/.test(f.type)) return setErr("PNG, JPG, SVG, WEBP 이미지만 올릴 수 있습니다.");
    if (f.size > MAX_IMAGE_BYTES) return setErr("이미지는 200KB 이하여야 합니다.");
    const r = new FileReader();
    r.onload = () => onChange({ kind: "image", src: String(r.result) });
    r.readAsDataURL(f);
  };

  return (
    <div className="flex flex-wrap items-start gap-5">
      <div className="flex flex-col items-center gap-2">
        <AssetIconTile asset={{ ...fallback, icon: value }} size={72} />
        <span className="text-[11.5px] text-muted-foreground">{value ? "미리보기" : "자동 (미지정)"}</span>
      </div>

      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(PRESET_ICONS).map(([name, { icon: Icon, label }]) => (
            <button
              key={name}
              type="button"
              title={label}
              onClick={() => onChange({ kind: "preset", name, color })}
              className={cn(
                "grid size-9 place-items-center rounded-xl ring-1 transition-all",
                preset?.name === name ? "bg-accent text-primary ring-2 ring-primary" : "bg-white text-[#3a3a3c] ring-black/[0.08] hover:ring-primary/40",
              )}
            >
              <Icon className="size-[18px]" />
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {ICON_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              aria-label={`색 ${c}`}
              onClick={() => onChange({ kind: "preset", name: preset?.name ?? (fallback.type === "MCP" ? "bot" : "database"), color: c })}
              className={cn("size-6 rounded-full ring-offset-2 transition-transform hover:scale-110", preset?.color === c && "ring-2 ring-primary")}
              style={{ background: c }}
            />
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
          {allowImage && (
            <>
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
              <button type="button" onClick={() => fileRef.current?.click()} className="inline-flex h-8 items-center gap-1.5 rounded-full bg-white px-3 font-bold ring-1 ring-black/[0.08] hover:ring-primary/40">
                <Upload className="size-3.5" /> 이미지 올리기
              </button>
            </>
          )}
          {value && (
            <button type="button" onClick={() => onChange(undefined)} className="h-8 rounded-full px-3 font-bold text-muted-foreground hover:bg-[#f0f0f2]">
              자동으로 되돌리기
            </button>
          )}
          <span className="text-muted-foreground">
            {allowImage ? "PNG · JPG · SVG · WEBP, 200KB 이하, 정사각형 권장" : "이미지 올리기는 파일 저장소가 정해지면 추가됩니다."}
          </span>
        </div>
        {err && <p className="text-[12.5px] text-[#d70015]">{err}</p>}
      </div>
    </div>
  );
}

