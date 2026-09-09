import { NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// A cheap proxy to the backend health check. Used to wake the Render free-tier
// service while the visitor reads the page, and to show a status hint.
export async function GET() {
  const t0 = Date.now();
  try {
    const up = await fetch(`${API_BASE}/api/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    return NextResponse.json({ ok: up.ok, ms: Date.now() - t0 });
  } catch {
    // A timeout here usually means the service is cold and still booting.
    return NextResponse.json({ ok: false, waking: true, ms: Date.now() - t0 });
  }
}
