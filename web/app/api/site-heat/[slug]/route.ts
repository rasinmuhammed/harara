import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: NextRequest, { params }: { params: { slug: string } }) {
  const slug = params.slug;
  if (!/^[a-z0-9-]{1,80}$/.test(slug)) {
    return NextResponse.json({ error: "no such site" }, { status: 404 });
  }
  try {
    const up = await fetch(`${API_BASE}/api/site-heat/${slug}`, {
      next: { revalidate: 3600 },
      signal: AbortSignal.timeout(20_000),
    });
    const data = await up.json().catch(() => null);
    if (!up.ok) {
      return NextResponse.json({ error: "no such site" }, { status: up.status === 404 ? 404 : 502 });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "The satellite-heat service did not respond." }, { status: 502 });
  }
}
