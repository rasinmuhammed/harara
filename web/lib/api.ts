import type { ChatFrame, PlanRequestBody, PlanResponse } from "./types";

export type ChatMessageIn = { role: "user" | "assistant"; content: string };

/** POST /api/plan through the same-origin Next route handler. */
export async function fetchPlan(body: PlanRequestBody): Promise<PlanResponse> {
  const r = await fetch("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d?.error || d?.detail || `Planner returned ${r.status}`);
  }
  return r.json();
}

/**
 * Stream POST /api/chat. Calls `onFrame` for each SSE frame. Returns when the
 * stream ends. Throws on transport failure or a 429.
 */
export async function parsePlan(text: string): Promise<
  | { outcome: "parsed"; intent: Record<string, any> }
  | { outcome: "clarification"; missing_fields: string[]; question: string }
> {
  const r = await fetch("/api/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`Parser returned ${r.status}`);
  return r.json();
}

export async function streamChat(
  messages: ChatMessageIn[],
  onFrame: (f: ChatFrame) => void,
  opts: { signal?: AbortSignal; intent?: Record<string, any> } = {},
): Promise<void> {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts.intent ? { messages, intent: opts.intent } : { messages }),
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
