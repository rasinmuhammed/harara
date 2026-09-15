import { NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Static, precomputed satellite surface-heat sites (climatological, advisory
// only, never part of the WBGT or scheduler response). Long cache: the
// backend refreshes this only when scripts/build_site_heat_presets.py reruns.
export async function GET() {
  try {
    const up = await fetch(`${API_BASE}/api/site-heat`, {
      next: { revalidate: 3600 },
      signal: AbortSignal.timeout(20_000),
    });
    const data = await up.json().catch(() => null);
    if (!up.ok) {
      return NextResponse.json({ error: `Site-heat index error ${up.status}` }, { status: 502 });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ sites: [] });
  }
}
