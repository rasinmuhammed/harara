"use client";

import { useEffect, useRef } from "react";
import { GlossaryText } from "@/components/GlossaryText";
import { ThinkingIndicator } from "@/components/chat/ThinkingIndicator";
import { ClarificationCard } from "@/components/chat/ClarificationCard";
import { ConfirmCard, type Intent } from "@/components/chat/ConfirmCard";
import { Button } from "@/components/ui/Button";
import type { ChatTurn } from "@/lib/types";

/** The conversation, shown as a panel above the docked composer. */
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
    if (open) endRef.current?.scrollIntoView({ block: "end" });
  }, [turns, open]);

  if (!open || turns.length === 0) return null;

  return (
    <div className="border-t border-border bg-bg-raised">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-4 pt-3">
        <p className="eyebrow">Conversation</p>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Hide
        </Button>
      </div>
      <div className="mx-auto flex max-h-[42vh] max-w-3xl flex-col gap-4 overflow-y-auto px-4 py-3">
        {turns.map((t) =>
          t.role === "user" ? (
            <div
              key={t.id}
              className="self-end rounded-lg rounded-br-sm bg-surface-2 px-3.5 py-2 text-base text-ink"
            >
              {t.text}
            </div>
          ) : (
            <div key={t.id} className="flex flex-col gap-2.5">
              {t.status && <ThinkingIndicator state={t.status} />}
              {t.text && (
                <p className="whitespace-pre-wrap text-base leading-relaxed text-ink">
                  <GlossaryText text={t.text} />
                  {t.streaming && (
                    <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-accent align-middle" />
                  )}
                </p>
              )}
              {t.clarification && (
                <ClarificationCard
                  question={t.clarification.question}
                  missing={t.clarification.missing_fields}
                  onChip={() => {}}
                />
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
          ),
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
