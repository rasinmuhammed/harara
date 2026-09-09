// A shift plan is fully described by its request. We pack that into a short
// base64url token so a plan can travel as /app?q=<token> with no server state.

import type { PlanRequestBody, WorkloadClass } from "./types";

type Packed = {
  a: number; // lat
  o: number; // lon
  d: string; // date (ISO)
  h: number; // required work hours
  w: WorkloadClass; // workload class
  c: 0 | 1; // acclimatised
};

const WL: WorkloadClass[] = ["light", "moderate", "heavy", "very_heavy"];

function b64urlEncode(s: string): string {
  const b = typeof btoa === "function" ? btoa(s) : Buffer.from(s, "utf8").toString("base64");
  return b.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(s: string): string {
  const p = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  return typeof atob === "function" ? atob(p) : Buffer.from(p, "base64").toString("utf8");
}

export function encodeShare(r: {
  lat: number; lon: number; date: string; required_work_hours: number;
  workload_class: WorkloadClass; acclimatised: boolean;
}): string {
  const packed: Packed = {
    a: +r.lat.toFixed(4),
    o: +r.lon.toFixed(4),
    d: r.date,
    h: r.required_work_hours,
    w: r.workload_class,
    c: r.acclimatised ? 1 : 0,
  };
  return b64urlEncode(JSON.stringify(packed));
}

export function decodeShare(token: string): PlanRequestBody | null {
  try {
    const p = JSON.parse(b64urlDecode(token)) as Partial<Packed>;
    if (
      typeof p.a !== "number" || typeof p.o !== "number" ||
      typeof p.d !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(p.d) ||
      typeof p.h !== "number" || p.h <= 0 || p.h > 14 ||
      !WL.includes(p.w as WorkloadClass)
    ) {
      return null;
    }
    return {
      lat: p.a, lon: p.o, date: p.d,
      required_work_hours: p.h,
      workload_class: p.w as WorkloadClass,
      acclimatised: p.c === 1,
    };
  } catch {
    return null;
  }
}
