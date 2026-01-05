import React from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "default" | "outline";
export type ButtonSize = "default" | "sm" | "lg";

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export function Button({
  className,
  variant = "default",
  size = "default",
  type,
  ...props
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center whitespace-nowrap rounded-xl text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 disabled:pointer-events-none disabled:opacity-50";

  const variantClass =
    variant === "outline"
      ? "border border-border bg-transparent hover:bg-muted"
      : "bg-foreground text-background hover:opacity-90";

  const sizeClass =
    size === "sm" ? "h-9 px-4" : size === "lg" ? "h-11 px-6" : "h-10 px-5";

  return (
    <button
      type={type ?? "button"}
      className={cn(base, variantClass, sizeClass, className)}
      {...props}
    />
  );
}
