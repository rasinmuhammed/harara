import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid request body.", retryable: false },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(`${API_BASE}/api/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });

    const data = await upstream.json().catch(() => null);
    if (!upstream.ok) {
      return NextResponse.json(
        {
          error:
            data?.detail?.toString() ||
            `The planner rejected the request (${upstream.status}).`,
          retryable: upstream.status >= 500,
        },
        { status: upstream.status === 400 || upstream.status === 422 ? 400 : 502 },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      {
        error: "The forecast service didn't respond. Your inputs are kept.",
        retryable: true,
      },
      { status: 502 },
    );
  }
}
