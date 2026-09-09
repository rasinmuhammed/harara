"use client";

import { useState } from "react";
import { Chip } from "@/components/ui/Chip";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/Popover";
import { isoPlusDays, isoToday } from "@/lib/format";

const PRESETS: [string, number][] = [
  ["Today", 0],
  ["Tomorrow", 1],
  ["In 3 days", 3],
];

function leadOf(iso: string) {
  return Math.round((+new Date(iso + "T00:00:00Z") - +new Date(isoToday() + "T00:00:00Z")) / 86400000);
}

function labelFor(iso: string) {
  const l = leadOf(iso);
  const hit = PRESETS.find(([, d]) => d === l);
  if (hit) return hit[0];
  return new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", {
    day: "numeric", month: "short", timeZone: "UTC",
  });
}

export function DayControl({
  value,
  onChange,
  flash,
}: {
  value: string;
  onChange: (iso: string) => void;
  flash?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const lead = leadOf(value);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Chip label="Day" value={labelFor(value)} active={open} flash={flash} />
      </PopoverTrigger>
      <PopoverContent className="w-60">
        <div className="flex flex-col gap-1.5">
          {PRESETS.map(([lbl, d]) => (
            <button
              key={lbl}
              type="button"
              onClick={() => {
                onChange(d === 0 ? isoToday() : isoPlusDays(d));
                setOpen(false);
              }}
              className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                lead === d
                  ? "border-accent bg-accent-weak text-ink"
                  : "border-border text-ink-secondary hover:border-border-strong hover:text-ink"
              }`}
            >
              {lbl}
            </button>
          ))}
          <label className="mt-1 flex items-center justify-between gap-2 text-sm text-ink-secondary">
            <span className="mono text-micro uppercase">Or pick</span>
            <input
              type="date"
              value={value}
              min={isoToday()}
              max={isoPlusDays(15)}
              onChange={(e) => e.target.value && onChange(e.target.value)}
              className="rounded border border-border bg-surface px-2 py-1 text-ink"
            />
          </label>
          <p className="mt-1 text-sm text-ink-muted">
            The forecast horizon is 15 days. Further out is less certain.
          </p>
        </div>
      </PopoverContent>
    </Popover>
  );
}
