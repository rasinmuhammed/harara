// Wire types. Mirror api/schemas.py.

export type WorkloadClass = "light" | "moderate" | "heavy" | "very_heavy";
export type PlanState = "work" | "reduced" | "stop";

export interface PlanRequestBody {
  lat: number;
  lon: number;
  date: string;
  required_work_hours: number;
  workload_class: WorkloadClass;
  acclimatised: boolean;
  tz?: string;
}

export interface HourRow {
  local_time: string;
  hour: number;
  wbgt_c: number;
  wbgt_lo: number;
  wbgt_hi: number;
  uncertain: boolean;
  plan_work_fraction: number;
  calendar_work_fraction: number;
  reactive_work_fraction: number;
  earlier_start_work_fraction: number;
  retained_load_plan: number;
  retained_load_calendar: number;
  retained_load_reactive: number;
  retained_load_earlier: number;
  plan_state: PlanState;
  over_threshold: boolean;
  on_site: boolean;
  cycle: string;
}

export interface PlanSummary {
  peak_plan: number;
  peak_calendar: number;
  peak_reactive: number;
  tail_plan: number;
  tail_calendar: number;
  tail_reactive: number;
  pct_peak_reduction: number;
  pct_tail_reduction: number;
  pct_peak_reduction_vs_reactive: number;
  work_hours_delivered_plan: number;
  work_hours_delivered_calendar: number;
  work_shortfall_plan: number;
  stop_hours_plan: number;
  stop_hours_calendar: number;
  wbgt_ref_c: number;
  threshold_c: number;
  solver_status: string;
  span_hours_plan: number;
  span_hours_calendar: number;
  onsite_rest_hours_plan: number;
  onsite_rest_hours_calendar: number;
  cumulative_exposure_plan: number;
  cumulative_exposure_calendar: number;
  work_blocks_plan: number;
  work_blocks_calendar: number;
  earlier_start_fixed: { peak: number; tail: number; span_hours: number };
}

export interface PlanMeta {
  model: string;
  forecast_source: string;
  forecast_run: string;
  lead_days: number;
  lead_time_note: string;
  uncertainty_note: string;
  wide_band: boolean;
  dry_hot_day: boolean;
  dry_hot_note: string;
  generated_at: string;
  date: string;
  location: { lat: number; lon: number; grid_note: string };
  request: {
    lat: number; lon: number; date: string; required_work_hours: number;
    workload_class: WorkloadClass; acclimatised: boolean; tz: string;
  };
  attribution: string;
}

export interface PlanResponse {
  hours: HourRow[];
  summary: PlanSummary;
  meta: PlanMeta;
}

// chat SSE frames
export type ChatFrame =
  | { type: "status"; state: "parsing" | "forecasting" | "planning" | "writing" }
  | { type: "clarification"; question: string; missing_fields: string[] }
  | { type: "text"; delta: string }
  | { type: "artifact"; plan: PlanResponse }
  | { type: "error"; message: string }
  | { type: "done" };

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: string;
  clarification?: { question: string; missing_fields: string[] };
  confirm?: { intent: any; locationSource: "map pin" | "your message" };
  artifact?: PlanResponse;
  error?: string;
  streaming?: boolean;
}

export const DOHA = { name: "Doha", lat: 25.2854, lon: 51.531 };

export const LOCATION_PRESETS = [
  DOHA,
  { name: "Lusail", lat: 25.43, lon: 51.49 },
  { name: "Industrial Area", lat: 25.19, lon: 51.44 },
  { name: "Al Wakrah", lat: 25.171, lon: 51.603 },
  { name: "Mesaieed", lat: 24.99, lon: 51.55 },
];

export const SUGGESTED_PROMPTS = [
  "Plan tomorrow for a heavy, newly-arrived crew of 12 near Lusail. We need 8 work-hours.",
  "Moderate work at the Industrial Area the day after tomorrow, acclimatised crew, 6 work-hours.",
  "Light work in Doha tomorrow, acclimatised crew, 9 work-hours.",
];
