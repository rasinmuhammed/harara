export function fmt(n: number, digits = 2): string {
  return n.toLocaleString("en", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtPct(n: number): string {
  const s = Math.abs(n).toLocaleString("en", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  });
  return `${n < 0 ? "+" : "−"}${s}%`; // reduction shown as −X%, an increase as +X%
}

export function fmtHour(h: number): string {
  return `${String(h).padStart(2, "0")}:00`;
}

export function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

export function isoPlusDays(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function prettyDate(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}
