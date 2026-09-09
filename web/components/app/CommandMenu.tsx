"use client";

import { useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { LOCATION_PRESETS } from "@/lib/types";
import { isoPlusDays, isoToday } from "@/lib/format";

export type Command = { id: string; label: string; hint?: string; run: () => void };

export function CommandMenu({
  open,
  onOpenChange,
  onLocation,
  onDay,
  onOpenAssumptions,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onLocation: (p: { lat: number; lon: number; name: string }) => void;
  onDay: (iso: string) => void;
  onOpenAssumptions: () => void;
}) {
  const [q, setQ] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (open) setQ("");
  }, [open]);

  const commands: Command[] = useMemo(() => {
    const close = () => onOpenChange(false);
    return [
      ...LOCATION_PRESETS.map((p) => ({
        id: `loc-${p.name}`,
        label: `Location: ${p.name}`,
        hint: "set site",
        run: () => {
          onLocation({ lat: p.lat, lon: p.lon, name: p.name });
          close();
        },
      })),
      { id: "day-today", label: "Day: today", run: () => { onDay(isoToday()); close(); } },
      { id: "day-tom", label: "Day: tomorrow", run: () => { onDay(isoPlusDays(1)); close(); } },
      { id: "day-3", label: "Day: in 3 days", run: () => { onDay(isoPlusDays(3)); close(); } },
      { id: "assumptions", label: "Open assumptions and limits", run: () => { close(); onOpenAssumptions(); } },
      {
        id: "method",
        label: "Read the method",
        hint: "opens the technical report",
        run: () => {
          window.open("https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md", "_blank", "noreferrer");
          close();
        },
      },
    ];
  }, [onOpenChange, onLocation, onDay, onOpenAssumptions]);

  const filtered = commands.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()));

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-[18vh] z-[60] w-[min(92vw,520px)] -translate-x-1/2 overflow-hidden rounded-xl border border-border-strong bg-bg-raised shadow-1">
          <Dialog.Title className="sr-only">Command menu</Dialog.Title>
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Jump to a location, change the day, open the method"
            className="w-full border-b border-border bg-transparent px-4 py-3 text-base text-ink outline-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && filtered[0]) filtered[0].run();
            }}
          />
          <ul className="max-h-[46vh] overflow-y-auto p-1.5">
            {filtered.length === 0 && (
              <li className="px-3 py-2 text-sm text-ink-muted">No match.</li>
            )}
            {filtered.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={c.run}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink-secondary hover:bg-surface-2 hover:text-ink"
                >
                  <span>{c.label}</span>
                  {c.hint && <span className="mono text-micro uppercase text-ink-muted">{c.hint}</span>}
                </button>
              </li>
            ))}
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
