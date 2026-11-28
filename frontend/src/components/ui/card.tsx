import * as React from "react";
import { cn } from "@/lib/utils";

// 덱의 흰 카드: 큰 라운드, 부드러운 그림자, 왼쪽 위 파란 빛
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-[22px] bg-card bg-[radial-gradient(520px_320px_at_0%_0%,rgb(0_113_227/0.07),transparent_70%)] text-card-foreground shadow-[0_20px_60px_rgb(0_0_0/0.05),0_0_0_1px_rgb(0_0_0/0.03)]",
        className,
      )}
      {...props}
    />
  );
}
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 p-6 pb-3", className)} {...props} />;
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("font-display font-bold tracking-[-0.025em] text-[22px] leading-tight", className)} {...props} />;
}
export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-[14.5px] text-muted-foreground", className)} {...props} />;
}
export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6 pt-0", className)} {...props} />;
}
