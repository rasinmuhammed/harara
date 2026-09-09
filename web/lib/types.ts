// Wire types — mirror api/schemas.py. Keep in sync with the backend.

export type WorkloadClass = "light" | "moderate" | "heavy" | "very_heavy";
export type PlanState = "work" | "reduced" | "stop";

export interface PlanRequestBody {
  lat: number;
  lon: number;
  date: string; // ISO yyyy-mm-dd
  required_work_hours: number;
  workload_class: WorkloadClass;
  acclimatised: boolean;
  tz?: string;
}

export interface HourRow {
  local_time: string;
  hour: number;
  wbgt_c: number;
  plan_work_fraction: number;
  calendar_work_fraction: number;
  retained_load_plan: number;
  retained_load_calendar: number;
  plan_state: PlanState;
  over_threshold: boolean;
}

export interface PlanSummary {
  peak_plan: number;
  peak_calendar: number;
  tail_plan: number;
  tail_calendar: number;
  pct_peak_reduction: number;
  pct_tail_reduction: number;
  work_hours_delivered_plan: number;
  work_hours_delivered_calendar: number;
  work_shortfall_plan: number;
  stop_hours_plan: number;
  stop_hours_calendar: number;
  wbgt_ref_c: number;
  threshold_c: number;
  solver_status: string;
}

export interface PlanMeta {
  model: string;
  forecast_source: string;
  lead_time_note: string;
  generated_at: string;
  date: string;
  location: { lat: number; lon: number; grid_note: string };
  attribution: string;
}

export interface PlanResponse {
  hours: HourRow[];
  summary: PlanSummary;
  meta: PlanMeta;
}

export type ParseResponse =
  | { outcome: "parsed"; intent: Record<string, unknown> }
  | { outcome: "clarification"; missing_fields: string[]; question: string };

export interface ApiError {
  error: string;
  retryable: boolean;
}

export interface LocationPreset {
  name: string;
  lat: number;
  lon: number;
}

export const LOCATION_PRESETS: LocationPreset[] = [
  { name: "Doha", lat: 25.2854, lon: 51.531 },
  { name: "Lusail", lat: 25.43, lon: 51.49 },
  { name: "Industrial Area", lat: 25.19, lon: 51.44 },
  { name: "Al Wakrah", lat: 25.171, lon: 51.603 },
  { name: "Mesaieed", lat: 24.99, lon: 51.55 },
  { name: "Al Rayyan", lat: 25.29, lon: 51.42 },
];

export const WORKLOADS: { value: WorkloadClass; label: string; hint: string }[] = [
  { value: "light", label: "Light", hint: "standing, light hand work (~180 W)" },
  { value: "moderate", label: "Moderate", hint: "sustained arm + leg work, walking (~300 W)" },
  { value: "heavy", label: "Heavy", hint: "pick / shovel work, carrying loads (~415 W)" },
  { value: "very_heavy", label: "Very heavy", hint: "intense digging, stairs with load (~520 W)" },
];
