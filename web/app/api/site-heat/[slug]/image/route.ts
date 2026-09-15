import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Proxies the precomputed PNG overlay so the browser only ever talks to this
// origin, consistent with every other API call in the app.
export async function GET(_req: NextRequest, { params }: { params: { slug: string } }) {
  const slug = params.slug;
  if (!/^[a-z0-9-]{1,80}$/.test(slug)) {
    return new NextResponse(null, { status: 404 });
  }
  try {
    const up = await fetch(`${API_BASE}/api/site-heat/${slug}/image`, {
      next: { revalidate: 3600 },
      signal: AbortSignal.timeout(20_000),
    });
    if (!up.ok || !up.body) {
      return new NextResponse(null, { status: up.status === 404 ? 404 : 502 });
    }
    return new NextResponse(up.body, {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=3600",
      },
    });
  } catch {
    return new NextResponse(null, { status: 502 });
  }
}
