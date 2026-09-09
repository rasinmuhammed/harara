import { cn } from "@/lib/cn";

/**
 * Surface container. `tone="raised"` for the primary result surface,
 * `"flat"` for a quieter inset. Border and shadow are spent deliberately:
 * one radius, one shadow, only where an object needs lifting.
 */
export function Card({
  tone = "flat",
  className,
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { tone?: "flat" | "raised" }) {
  return (
    <div
      className={cn(
        "rounded-xl border",
        tone === "raised"
          ? "border-border-strong bg-bg-raised shadow-1"
          : "border-border bg-surface",
        className,
      )}
      {...rest}
    />
  );
}
