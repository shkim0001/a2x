import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// 덱의 알약 태그 색 (t-blue, t-green, t-violet, t-red, t-orange, t-gray)
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11.5px] font-bold whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-[#f0f0f2] text-[#6e6e73]",
        outline: "bg-white text-foreground ring-1 ring-black/10",
        success: "bg-[#e6f6ea] text-[#1e8e3e]",
        warning: "bg-[#fff3e0] text-[#b06d00]",
        danger: "bg-[#fdecee] text-[#d70015]",
        info: "bg-[#e8f2fd] text-[#0066cc]",
        violet: "bg-[#f1ecff] text-[#6e4ff6]",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
