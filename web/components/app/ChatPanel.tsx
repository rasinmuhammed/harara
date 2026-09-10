"use client";

import { useEffect, useRef } from "react";
import { GlossaryText } from "@/components/GlossaryText";
import { ThinkingIndicator } from "@/components/chat/ThinkingIndicator";
import { ConfirmCard, type Intent } from "@/components/chat/ConfirmCard";
import { Button } from "@/components/ui/Button";
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

/** The conversation. Reads like a chat: assistant on the left, you on the
 *  right, one streaming reply at a time. */
export function ChatPanel({
  turns,
  open,
  onClose,
  onConfirm,
  onCancelConfirm,
}: {
  turns: ChatTurn[];
  open: boolean;
  onClose: () => void;
  onConfirm: (id: string, intent: Intent) => void;
  onCancelConfirm: (id: string) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns, open]);

  if (!open || turns.length === 0) return null;

  return (
    <div className="border-t border-border bg-bg-raised">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-4 pt-2.5">
        <p className="eyebrow">Assistant</p>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Hide
        </Button>
      </div>
      <div className="mx-auto flex max-h-[46vh] max-w-3xl flex-col gap-3.5 overflow-y-auto px-4 py-3">
        {turns.map((t) =>
          t.role === "user" ? (
            <div key={t.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent-weak px-3.5 py-2 text-base text-ink">
                {t.text}
              </div>
            </div>
          ) : (
            <div key={t.id} className="flex gap-2.5">
              <div
                aria-hidden
                className="mt-1 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-border-strong text-[11px] font-semibold text-ink-secondary"
              >
                H
              </div>
              <div className="min-w-0 flex-1 space-y-2">
                {t.status && (
                  <div className="pt-1">
                    <ThinkingIndicator state={t.status} />
                  </div>
                )}
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
    </div>
  );
}
