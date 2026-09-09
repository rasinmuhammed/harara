import { NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const up = await fetch(`${API_BASE}/api/replay`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const data = await up.json().catch(() => null);
    if (!up.ok) {
      return NextResponse.json({ error: `Replay index error ${up.status}` }, { status: 502 });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "The replay service did not respond." }, { status: 502 });
  }
}
