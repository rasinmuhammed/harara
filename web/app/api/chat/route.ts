import { NextRequest } from "next/server";

const API_BASE =
  process.env.API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Proxy the SSE stream from the FastAPI service straight through.
export async function POST(req: NextRequest) {
  const body = await req.text();
  const up = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
    // no timeout: the stream is long-lived
  }).catch(() => null);

  if (!up) {
    return new Response(
      `data: ${JSON.stringify({ type: "error", message: "The assistant is offline. Try again in a moment." })}\n\n` +
        `data: ${JSON.stringify({ type: "done" })}\n\n`,
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );
  }
  if (up.status === 429) {
    const j = await up.json().catch(() => ({}));
    return new Response(JSON.stringify(j), {
      status: 429,
      headers: { "Content-Type": "application/json" },
    });
  }
  return new Response(up.body, {
    status: up.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
