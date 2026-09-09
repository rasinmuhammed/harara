"use client";

import { useState } from "react";
import { fetchParse } from "@/lib/api";
import type { ParseResponse } from "@/lib/types";

export function NLBox({
  onParsed,
  onClarify,
}: {
  onParsed: (intent: Record<string, unknown>) => void;
  onClarify: (question: string, missing: string[]) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    if (!text.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const res: ParseResponse = await fetchParse(text.trim());
      if (res.outcome === "clarification") {
        onClarify(res.question, res.missing_fields);
      } else {
        onParsed(res.intent);
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
      <label htmlFor="nl" className="text-caption uppercase text-ink-muted">
        Or describe it
      </label>
      <textarea
        id="nl"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="plan tomorrow for a heavy unacclimatised crew needing 8 work-hours near Lusail"
        className="w-full resize-none rounded border border-border bg-surface px-3 py-2 text-base text-ink outline-none transition-colors duration-[var(--dur-1)] focus:border-accent"
      />
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={run}
          disabled={busy || !text.trim()}
          className="rounded border border-border-strong px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-[var(--dur-1)] hover:border-accent hover:text-accent disabled:opacity-50"
        >
          {busy ? "Reading…" : "Interpret"}
        </button>
        {err && <span className="text-sm text-state-stop">{err}</span>}
      </div>
      <p className="text-sm text-ink-muted">
        Parsed by the fail-closed interpreter — it asks back rather than guess a
        safety-relevant value.
      </p>
    </div>
  );
}
