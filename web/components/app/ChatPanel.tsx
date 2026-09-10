"use client";

import { useEffect, useRef } from "react";
import { GlossaryText } from "@/components/GlossaryText";
import { ThinkingIndicator } from "@/components/chat/ThinkingIndicator";
import { ConfirmCard, type Intent } from "@/components/chat/ConfirmCard";
import type { ChatTurn } from "@/lib/types";

const FIELD_LABEL: Record<string, string> = {
  target_local_date: "the day",
  required_work_hours: "the work-hours",
  workload: "the kind of work",
  "crew.workload": "the kind of work",
  acclimatised: "whether the crew is used to the heat",
  "crew.acclimatised": "whether the crew is used to the heat",
  location: "the site",
};

/** The conversation list. Assistant on the left with an avatar mark, you on
 *  the right in an accent bubble. Sits in the left pane above the composer. */
export function ChatPanel({
  turns,
  onConfirm,
  onCancelConfirm,
}: {
  turns: ChatTurn[];
  onConfirm: (id: string, intent: Intent) => void;
  onCancelConfirm: (id: string) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns]);

  if (turns.length === 0) {
    return (
      <div className="flex h-full flex-col items-start justify-center gap-3 px-4 py-6 text-ink-muted">
        <div
          aria-hidden
          className="grid h-8 w-8 place-items-center rounded-full border border-border-strong text-sm font-semibold text-ink-secondary"
        >
          H
        </div>
        <p className="max-w-[36ch] text-base leading-relaxed">
          Talk to the planner like a colleague. Ask why an hour is a rest hour,
          what WBGT means, or describe the shift you need and it will build the
          plan.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 px-4 py-4">
      {turns.map((t) =>
        t.role === "user" ? (
          <div key={t.id} className="flex justify-end">
            <div className="max-w-[88%] rounded-2xl rounded-br-md bg-accent-weak px-3.5 py-2 text-base text-ink">
              {t.text}
            </div>
          </div>
        ) : (
          <div key={t.id} className="flex gap-2.5">
            <div
              aria-hidden
              className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-border-strong text-[11px] font-semibold text-ink-secondary"
            >
              H
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              {t.status && <ThinkingIndicator state={t.status} />}
              {t.text && (
                <div className="whitespace-pre-wrap text-base leading-relaxed text-ink">
                  <GlossaryText text={t.text} />
                  {t.streaming && (
                    <span className="ml-0.5 inline-block h-4 w-[3px] animate-pulse rounded-sm bg-accent align-middle" />
                  )}
                </div>
              )}
              {t.clarification && (
                <div className="text-base leading-relaxed text-ink">
                  <p>{t.clarification.question}</p>
                  {t.clarification.missing_fields.length > 0 && (
                    <p className="mt-1 text-sm text-ink-muted">
                      Add{" "}
                      {t.clarification.missing_fields
                        .map((f) => FIELD_LABEL[f] ?? f)
                        .join(", ")}{" "}
                      and send again. Nothing safety-relevant is assumed.
                    </p>
                  )}
                </div>
              )}
              {t.confirm && (
                <ConfirmCard
                  intent={t.confirm.intent}
                  locationSource={t.confirm.locationSource}
                  onConfirm={(i) => onConfirm(t.id, i)}
                  onCancel={() => onCancelConfirm(t.id)}
                />
              )}
              {t.error && (
                <p className="rounded-lg border border-[var(--state-stop)]/40 bg-surface-2 p-3 text-sm text-ink-secondary">
                  {t.error}
                </p>
              )}
            </div>
          </div>
        ),
      )}
      <div ref={endRef} />
    </div>
  );
}
