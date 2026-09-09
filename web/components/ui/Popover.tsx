"use client";

import * as RP from "@radix-ui/react-popover";
import { cn } from "@/lib/cn";

/** Anchored, non-modal popover. Token-styled; opens beside its trigger. */
export const Popover = RP.Root;
export const PopoverTrigger = RP.Trigger;
export const PopoverAnchor = RP.Anchor;

export function PopoverContent({
  className,
  align = "start",
  sideOffset = 8,
  children,
  ...rest
}: React.ComponentProps<typeof RP.Content>) {
  return (
    <RP.Portal>
      <RP.Content
        align={align}
        sideOffset={sideOffset}
        collisionPadding={12}
        className={cn(
          "z-50 rounded-xl border border-border-strong bg-bg-raised p-3 shadow-1",
          "focus:outline-none",
          "data-[state=open]:animate-[rise_160ms_var(--ease)_both]",
          "motion-reduce:animate-none",
          className,
        )}
        {...rest}
      >
        {children}
      </RP.Content>
    </RP.Portal>
  );
}
