"use client";

import * as RSelect from "@radix-ui/react-select";
import * as RSwitch from "@radix-ui/react-switch";
import * as RSlider from "@radix-ui/react-slider";
import { useId } from "react";
import {
  LOCATION_PRESETS,
  WORKLOADS,
  type WorkloadClass,
} from "@/lib/types";
import { fmtHour, isoToday, isoPlusDays } from "@/lib/format";

export interface FormState {
  locationName: string;
  lat: number;
  lon: number;
  date: string;
  workHours: number;
  workload: WorkloadClass;
  acclimatised: boolean;
}

export const DEFAULT_FORM: FormState = {
  locationName: "Doha",
  lat: 25.2854,
  lon: 51.531,
  date: isoPlusDays(1),
  workHours: 8,
  workload: "moderate",
  acclimatised: true,
};

const fieldLabel =
  "text-caption uppercase text-ink-muted";
const control =
  "w-full rounded border border-border bg-surface px-3 py-2 text-base text-ink outline-none transition-colors duration-[var(--dur-1)] focus:border-accent";

export function InputPanel({
  value,
  onChange,
  onSubmit,
  busy,
}: {
  value: FormState;
  onChange: (next: FormState) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    onChange({ ...value, [k]: v });

  const locId = useId();
  const dateId = useId();
  const hoursId = useId();

  function onLocationInput(name: string) {
    const preset = LOCATION_PRESETS.find(
      (p) => p.name.toLowerCase() === name.trim().toLowerCase(),
    );
    if (preset) onChange({ ...value, locationName: preset.name, lat: preset.lat, lon: preset.lon });
    else set("locationName", name);
  }

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div className="flex flex-col gap-2">
        <label htmlFor={locId} className={fieldLabel}>
          Location
        </label>
        <input
          id={locId}
          list={`${locId}-presets`}
          className={control}
          value={value.locationName}
          onChange={(e) => onLocationInput(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <datalist id={`${locId}-presets`}>
          {LOCATION_PRESETS.map((p) => (
            <option key={p.name} value={p.name} />
          ))}
        </datalist>
        <p className="tnum text-sm text-ink-muted">
          {value.lat.toFixed(3)}, {value.lon.toFixed(3)}
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor={dateId} className={fieldLabel}>
          Day to plan
        </label>
        <input
          id={dateId}
          type="date"
          className={`${control} tnum`}
          value={value.date}
          min={isoToday()}
          max={isoPlusDays(15)}
          onChange={(e) => set("date", e.target.value || isoPlusDays(1))}
        />
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between">
          <label htmlFor={hoursId} className={fieldLabel}>
            Effective work-hours
          </label>
          <span className="tnum text-stat font-semibold text-ink">
            {value.workHours}
          </span>
        </div>
        <RSlider.Root
          id={hoursId}
          className="relative flex h-6 w-full touch-none select-none items-center"
          min={1}
          max={14}
          step={1}
          value={[value.workHours]}
          onValueChange={([v]) => set("workHours", v)}
          aria-label="Effective work-hours to deliver"
        >
          <RSlider.Track className="relative h-1 grow rounded-full bg-surface-sunken">
            <RSlider.Range className="absolute h-full rounded-full bg-accent" />
          </RSlider.Track>
          <RSlider.Thumb
            className="block h-5 w-5 rounded-full border-2 border-accent bg-surface shadow-card outline-none focus-visible:ring-2 focus-visible:ring-accent"
          />
        </RSlider.Root>
        <p className="text-sm text-ink-muted">
          The calendar ban naturally yields 8 h over 05:00–19:00.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <label className={fieldLabel}>Workload class</label>
        <RSelect.Root
          value={value.workload}
          onValueChange={(v) => set("workload", v as WorkloadClass)}
        >
          <RSelect.Trigger
            className={`${control} flex items-center justify-between`}
            aria-label="Workload class"
          >
            <RSelect.Value />
            <RSelect.Icon>
              <Chevron />
            </RSelect.Icon>
          </RSelect.Trigger>
          <RSelect.Portal>
            <RSelect.Content
              position="popper"
              sideOffset={6}
              className="z-50 overflow-hidden rounded border border-border-strong bg-surface shadow-card"
            >
              <RSelect.Viewport className="p-1">
                {WORKLOADS.map((w) => (
                  <RSelect.Item
                    key={w.value}
                    value={w.value}
                    className="flex cursor-pointer flex-col rounded-sm px-3 py-2 text-base text-ink outline-none data-[highlighted]:bg-accent-weak"
                  >
                    <RSelect.ItemText>{w.label}</RSelect.ItemText>
                    <span className="text-sm text-ink-muted">{w.hint}</span>
                  </RSelect.Item>
                ))}
              </RSelect.Viewport>
            </RSelect.Content>
          </RSelect.Portal>
        </RSelect.Root>
      </div>

      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col">
          <span className={fieldLabel}>Heat-acclimatised</span>
          <span className="text-sm text-ink-muted">
            Newly-arrived crews: switch off.
          </span>
        </div>
        <RSwitch.Root
          checked={value.acclimatised}
          onCheckedChange={(v) => set("acclimatised", v)}
          className="relative h-6 w-11 shrink-0 rounded-full border border-border bg-surface-sunken outline-none transition-colors duration-[var(--dur-1)] focus-visible:ring-2 focus-visible:ring-accent data-[state=checked]:bg-accent"
          aria-label="Heat-acclimatised"
        >
          <RSwitch.Thumb className="block h-5 w-5 translate-x-[2px] rounded-full bg-surface shadow-card transition-transform duration-[var(--dur-1)] data-[state=checked]:translate-x-[22px]" />
        </RSwitch.Root>
      </div>

      <button
        type="submit"
        disabled={busy}
        className="mt-1 rounded bg-accent px-4 py-3 text-base font-semibold text-white transition-colors duration-[var(--dur-1)] hover:bg-accent-hover disabled:opacity-60"
      >
        {busy ? "Planning…" : "Plan the day"}
      </button>
    </form>
  );
}

function Chevron() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="m6 9 6 6 6-6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
