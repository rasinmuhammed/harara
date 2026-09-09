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
