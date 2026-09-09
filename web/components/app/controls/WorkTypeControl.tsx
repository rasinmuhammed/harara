"use client";

import { useState } from "react";
import { Chip } from "@/components/ui/Chip";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/Popover";
import { Switch } from "@/components/ui/Switch";
import { WORKLOADS, ACCLIM_LABEL, ACCLIM_HINT } from "@/lib/worktypes";
import type { WorkloadClass } from "@/lib/types";

export function WorkTypeControl({
  workload,
  acclimatised,
  onWorkload,
  onAcclimatised,
  flash,
}: {
  workload: WorkloadClass;
  acclimatised: boolean;
  onWorkload: (w: WorkloadClass) => void;
  onAcclimatised: (v: boolean) => void;
  flash?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const current = WORKLOADS.find((w) => w.value === workload)!;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Chip label="Work type" value={`${current.label}${acclimatised ? "" : " · new crew"}`} active={open} flash={flash} />
      </PopoverTrigger>
      <PopoverContent className="w-[22rem] max-w-[calc(100vw-24px)]">
        <div className="flex flex-col gap-1.5">
          {WORKLOADS.map((w) => (
            <button
              key={w.value}
              type="button"
              onClick={() => onWorkload(w.value)}
              aria-pressed={w.value === workload}
              className={`rounded-lg border p-2.5 text-left transition-colors ${
                w.value === workload
                  ? "border-accent bg-accent-weak"
                  : "border-border hover:border-border-strong"
              }`}
            >
              <span className="text-sm font-medium text-ink">{w.label}</span>
              <span className="mt-0.5 block text-sm text-ink-muted">{w.hint}</span>
            </button>
          ))}
        </div>
        <div className="mt-3 border-t border-border pt-3">
          <Switch
            checked={acclimatised}
            onCheckedChange={onAcclimatised}
            label={ACCLIM_LABEL}
            hint={ACCLIM_HINT}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
