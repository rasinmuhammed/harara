import type { ChatFrame, PlanRequestBody, PlanResponse } from "./types";

export type ChatMessageIn = { role: "user" | "assistant"; content: string };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * The demo backend is on Render's free tier and can be cold. A 502 or a
 * transport failure on the first hit usually means it is still booting, and
 * that same request has just woken it, so we retry a couple of times with a
 * gap. `onSlow` fires once the wait crosses a few seconds so the UI can say so.
 */
async function withWake<T>(
  run: () => Promise<T>,
  opts: { onSlow?: () => void; retries?: number } = {},
): Promise<T> {
  const retries = opts.retries ?? 2;
  const slowTimer = opts.onSlow ? setTimeout(opts.onSlow, 3500) : null;
  try {
    for (let attempt = 0; ; attempt++) {
      try {
        return await run();
      } catch (e) {
        const msg = (e as Error).message || "";
        const cold = /502|503|504|wak|did not respond|Failed to fetch|network/i.test(msg);
        if (attempt >= retries || !cold) throw e;
        await sleep(4000 + attempt * 3000);
      }
    }
  } finally {
    if (slowTimer) clearTimeout(slowTimer);
  }
}

/** POST /api/plan through the same-origin Next route handler. */
export async function fetchPlan(
  body: PlanRequestBody,
  opts: { onSlow?: () => void } = {},
): Promise<PlanResponse> {
  return withWake(async () => {
    const r = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d?.error || d?.detail || `Planner returned ${r.status}`);
    }
    return r.json() as Promise<PlanResponse>;
  }, opts);
}

/**
 * Stream POST /api/chat. Calls `onFrame` for each SSE frame. Returns when the
 * stream ends. Throws on transport failure or a 429.
 */
export async function parsePlan(text: string): Promise<
  | { outcome: "parsed"; intent: Record<string, any> }
  | { outcome: "clarification"; missing_fields: string[]; question: string }
> {
  return withWake(async () => {
    const r = await fetch("/api/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error(`Parser returned ${r.status}`);
    return r.json();
  });
}

export async function streamChat(
  messages: ChatMessageIn[],
  onFrame: (f: ChatFrame) => void,
  opts: {
    signal?: AbortSignal;
    intent?: Record<string, any>;
    context?: Record<string, any>;
  } = {},
): Promise<void> {
  const body: Record<string, any> = { messages };
  if (opts.intent) body.intent = opts.intent;
  if (opts.context) body.context = opts.context;
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  if (r.status === 429) {
    const d = await r.json().catch(() => ({}));
    throw new Error(
      d?.detail?.error || "Too many requests. Wait a minute and try again.",
    );
  }
  if (!r.ok || !r.body) throw new Error(`Chat returned ${r.status}`);

  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const raw of frames) {
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onFrame(JSON.parse(line.slice(5).trim()) as ChatFrame);
      } catch {
        /* ignore a partial frame */
      }
    }
  }
}
