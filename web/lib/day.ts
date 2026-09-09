import type { PlanResponse } from "./types";
import { DOHA } from "./types";

const API_BASE =
  process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

/** Server-side: today's Doha plan for the landing page. Null if unreachable. */
export async function getDohaPlan(): Promise<PlanResponse | null> {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + 1);
  const date = d.toISOString().slice(0, 10);
  try {
    const r = await fetch(`${API_BASE}/api/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: DOHA.lat,
        lon: DOHA.lon,
        date,
        required_work_hours: 8,
        workload_class: "moderate",
        acclimatised: true,
      }),
      next: { revalidate: 1800 },
    });
    if (!r.ok) return null;
    return (await r.json()) as PlanResponse;
  } catch {
    return null;
  }
}
