import React from "react";
import { cn } from "@/lib/cn";

export type BadgeProps = React.HTMLAttributes<HTMLSpanElement>;

export function Badge({ className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full bg-black/5 px-3 py-1 text-xs font-semibold text-black",
        className
      )}
      {...props}
    />
  );
}
