import type { PlanRequestBody, PlanResponse, ParseResponse } from "./types";

/** Both calls go to same-origin Next route handlers, which proxy to the API. */

export async function fetchPlan(body: PlanRequestBody): Promise<PlanResponse> {
  const r = await fetch("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(
      detail?.error || detail?.detail || `Planner returned ${r.status}`,
    );
  }
  return r.json();
}

export async function fetchParse(text: string): Promise<ParseResponse> {
  const r = await fetch("/api/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.error || `Parser returned ${r.status}`);
  }
  return r.json();
}
