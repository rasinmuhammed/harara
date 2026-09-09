"use client";

import { forwardRef } from "react";
import { Slot } from "@/lib/slot";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const BASE =
  "inline-flex select-none items-center justify-center gap-1.5 rounded-lg font-medium " +
  "transition-[background-color,border-color,color,transform] duration-150 ease-out " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)] " +
  "active:translate-y-px disabled:pointer-events-none disabled:opacity-45";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-ink hover:bg-accent-hover",
  secondary:
    "border border-border text-ink-secondary hover:border-border-strong hover:text-ink",
  ghost:
    "text-ink-secondary hover:bg-surface-2 hover:text-ink",
  danger:
    "border border-[var(--state-stop)] text-[var(--state-stop)] hover:bg-[color-mix(in_oklab,var(--state-stop),transparent_88%)]",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-2.5 text-sm",
  md: "h-10 px-4 text-sm",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", asChild, className, type, ...rest },
  ref,
) {
  const Comp: any = asChild ? Slot : "button";
  return (
    <Comp
      ref={ref}
      type={asChild ? undefined : type ?? "button"}
      className={cn(BASE, VARIANTS[variant], SIZES[size], className)}
      {...rest}
    />
  );
});
