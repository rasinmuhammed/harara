import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }
  try {
    const up = await fetch(`${API_BASE}/api/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      // Render free tier can cold-start for ~30-60s; allow for it.
      signal: AbortSignal.timeout(75_000),
    });
    const data = await up.json().catch(() => null);
    if (!up.ok) {
      return NextResponse.json(
        { error: data?.detail?.toString() || `Planner error ${up.status}` },
        { status: up.status === 400 || up.status === 422 ? 400 : 502 },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "The forecast service did not respond. It may still be waking up." },
      { status: 502 },
    );
  }
}
