"use client";

import { useState } from "react";
import { Chip } from "@/components/ui/Chip";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/Popover";
import { Stepper } from "@/components/ui/Stepper";

export function HoursControl({
  value,
  onChange,
  flash,
}: {
  value: number;
  onChange: (h: number) => void;
  flash?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Chip label="Hours" value={`${value} ${value === 1 ? "hour" : "hours"}`} active={open} flash={flash} />
      </PopoverTrigger>
      <PopoverContent className="w-72">
        <p className="mb-2 text-sm text-ink">Work-hours the crew must deliver</p>
        <Stepper value={value} onChange={onChange} min={1} max={12} unit="h" label="work-hours" />
        <p className="mt-2 text-sm text-ink-muted">
          The plan spreads these hours across the working window. If they will not
          fit, it reports the shortfall rather than pushing into the worst heat.
        </p>
      </PopoverContent>
    </Popover>
  );
}
