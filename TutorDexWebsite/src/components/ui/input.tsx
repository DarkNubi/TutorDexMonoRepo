import React from "react";
import { cn } from "@/lib/cn";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, type = "text", ...props },
  ref
) {
  return (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-10 w-full rounded-xl border border-black/15 bg-white px-4 py-2 text-sm outline-none transition focus:border-black/30 focus:ring-2 focus:ring-black/10",
        className
      )}
      {...props}
    />
  );
});
