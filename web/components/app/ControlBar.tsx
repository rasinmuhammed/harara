"use client";

import { LocationControl } from "./controls/LocationControl";
import { WorkTypeControl } from "./controls/WorkTypeControl";
import { DayControl } from "./controls/DayControl";
import { HoursControl } from "./controls/HoursControl";
import type { WorkloadClass } from "@/lib/types";

export interface PlanReq {
  lat: number;
  lon: number;
  date: string;
  required_work_hours: number;
  workload_class: WorkloadClass;
  acclimatised: boolean;
  tz: string;
}

export function ControlBar({
  req,
  locName,
  flash,
  onLocation,
  onWorkload,
  onAcclimatised,
  onDay,
  onHours,
}: {
  req: PlanReq;
  locName: string;
  flash: Partial<Record<"location" | "work" | "day" | "hours", boolean>>;
  onLocation: (v: { lat: number; lon: number; name?: string }) => void;
  onWorkload: (w: WorkloadClass) => void;
  onAcclimatised: (v: boolean) => void;
  onDay: (iso: string) => void;
  onHours: (h: number) => void;
}) {
  return (
    <div
      className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-4 py-2.5"
      role="group"
      aria-label="Plan inputs"
    >
      <LocationControl
        value={{ lat: req.lat, lon: req.lon, name: locName }}
        label={locName}
        onChange={onLocation}
        flash={flash.location}
      />
      <WorkTypeControl
        workload={req.workload_class}
        acclimatised={req.acclimatised}
        onWorkload={onWorkload}
        onAcclimatised={onAcclimatised}
        flash={flash.work}
      />
      <DayControl value={req.date} onChange={onDay} flash={flash.day} />
      <HoursControl value={req.required_work_hours} onChange={onHours} flash={flash.hours} />
    </div>
  );
}
