"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { streamChat, type ChatMessageIn } from "@/lib/api";
import type { ChatFrame, ChatTurn } from "@/lib/types";
import { GlossaryText } from "@/components/GlossaryText";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ArtifactCard } from "@/components/artifact/ArtifactCard";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { ClarificationCard } from "./ClarificationCard";
import { SuggestedPrompts } from "./SuggestedPrompts";
import { Composer } from "./Composer";
import { AssumptionsSheet } from "./AssumptionsSheet";

let idc = 0;
const nid = () => `t${++idc}`;

export function ChatApp() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  const send = useCallback(
    async (text: string, prefill?: string) => {
      if (busy) return;
      const history: ChatMessageIn[] = turns
        .filter((t) => t.text || t.clarification)
        .map((t) => ({
          role: t.role,
          content: t.role === "assistant" && t.clarification ? t.clarification.question : t.text,
        }));
      const userTurn: ChatTurn = { id: nid(), role: "user", text };
      const botTurn: ChatTurn = { id: nid(), role: "assistant", text: "", streaming: true, status: "parsing" };
      setTurns((p) => [...p, userTurn, botTurn]);
      setBusy(true);
      abort.current = new AbortController();

      const patch = (fn: (t: ChatTurn) => ChatTurn) =>
        setTurns((p) => p.map((t) => (t.id === botTurn.id ? fn(t) : t)));

      try {
        await streamChat(
          [...history, { role: "user", content: text }],
          (f: ChatFrame) => {
            if (f.type === "status") patch((t) => ({ ...t, status: f.state }));
            else if (f.type === "text") patch((t) => ({ ...t, text: t.text + f.delta, status: undefined }));
            else if (f.type === "clarification") patch((t) => ({ ...t, clarification: { question: f.question, missing_fields: f.missing_fields }, status: undefined }));
            else if (f.type === "artifact") patch((t) => ({ ...t, artifact: f.plan }));
            else if (f.type === "error") patch((t) => ({ ...t, error: f.message, status: undefined }));
            else if (f.type === "done") patch((t) => ({ ...t, streaming: false, status: undefined }));
          },
          abort.current.signal,
        );
      } catch (e) {
        patch((t) => ({ ...t, error: (e as Error).message, streaming: false, status: undefined }));
      } finally {
        setBusy(false);
        abort.current = null;
      }
    },
    [busy, turns],
  );

  const stop = () => {
    abort.current?.abort();
    setBusy(false);
    setTurns((p) => p.map((t) => (t.streaming ? { ...t, streaming: false, status: undefined } : t)));
  };

  return (
    <div className="mx-auto flex h-dvh max-w-3xl flex-col">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight text-ink">
          Harara
        </Link>
        <div className="flex items-center gap-2">
          <AssumptionsSheet />
          <ThemeToggle />
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-6" id="main">
        {turns.length === 0 ? (
          <div className="mx-auto flex max-w-prose flex-col gap-6 pt-6">
            <div>
              <h1 className="text-h3 text-ink">Plan a shift</h1>
              <p className="mt-1 text-ink-secondary">
                Describe the day the way you would to a colleague. The assistant reads it, gets the forecast, plans the hours, and explains the result. Every number comes from the planner, not the model.
              </p>
            </div>
            <SuggestedPrompts onPick={(t) => send(t)} />
          </div>
        ) : (
          <div className="mx-auto flex max-w-prose flex-col gap-5">
            {turns.map((t) =>
              t.role === "user" ? (
                <div key={t.id} className="self-end rounded-lg rounded-br-sm bg-surface-2 px-3.5 py-2.5 text-base text-ink">
                  {t.text}
                </div>
              ) : (
                <div key={t.id} className="flex flex-col gap-3">
                  {t.status && <ThinkingIndicator state={t.status} />}
                  {t.text && (
                    <p className="whitespace-pre-wrap text-base leading-relaxed text-ink">
                      <GlossaryText text={t.text} />
                      {t.streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-accent align-middle" />}
                    </p>
                  )}
                  {t.clarification && (
                    <ClarificationCard question={t.clarification.question} missing={t.clarification.missing_fields} onChip={() => {}} />
                  )}
                  {t.artifact && <ArtifactCard plan={t.artifact} />}
                  {t.error && (
                    <p className="rounded-lg border border-state-stop/40 bg-surface-2 p-3 text-sm text-ink-secondary">
                      {t.error}
                    </p>
                  )}
                </div>
              ),
            )}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <Composer onSend={(t) => send(t)} busy={busy} onStop={stop} />
    </div>
  );
}
