"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { fetchPlan, parsePlan, streamChat, type ChatMessageIn } from "@/lib/api";
import type { ChatFrame, ChatTurn } from "@/lib/types";
import { DOHA } from "@/lib/types";
import { GlossaryText } from "@/components/GlossaryText";
import { useDohaPlan } from "@/lib/hooks";
import { decodeShare } from "@/lib/share";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ArtifactCard } from "@/components/artifact/ArtifactCard";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { ClarificationCard } from "./ClarificationCard";
import { ConfirmCard, type Intent } from "./ConfirmCard";
import { SuggestedPrompts } from "./SuggestedPrompts";
import { Composer } from "./Composer";
import { AssumptionsSheet } from "./AssumptionsSheet";

const SiteMap = dynamic(() => import("@/components/map/SiteMap").then((m) => m.SiteMap), {
  ssr: false,
  loading: () => <div className="skeleton h-64 rounded-lg" />,
});

let idc = 0;
const nid = () => `t${++idc}`;
type Loc = { lat: number; lon: number; name?: string };

export function ChatApp() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [loc, setLoc] = useState<Loc>({ ...DOHA });
  const [mapOpen, setMapOpen] = useState(false);
  const example = useDohaPlan(null);
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const locRef = useRef(loc);
  locRef.current = loc;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  // a shared link: /app?q=<token> auto-plans those exact parameters
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("q");
    if (!token) return;
    const req = decodeShare(token);
    if (!req) return;
    const bot: ChatTurn = { id: nid(), role: "assistant", text: "", status: "forecasting" };
    setTurns([bot]);
    setBusy(true);
    fetchPlan(req)
      .then((plan) =>
        patch(bot.id, (t) => ({
          ...t,
          artifact: plan,
          status: undefined,
          text: "This plan came from a shared link. Change anything below, or start a new request.",
        })),
      )
      .catch((e) => patch(bot.id, (t) => ({ ...t, status: undefined, error: (e as Error).message })))
      .finally(() => setBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const history = (): ChatMessageIn[] =>
    turns
      .filter((t) => t.text || t.clarification)
      .map((t) => ({
        role: t.role,
        content:
          t.role === "assistant" && t.clarification ? t.clarification.question : t.text,
      }));

  const patch = (id: string, fn: (t: ChatTurn) => ChatTurn) =>
    setTurns((p) => p.map((t) => (t.id === id ? fn(t) : t)));

  const runIntent = useCallback(
    async (botId: string, intent: Intent) => {
      setBusy(true);
      patch(botId, (t) => ({ ...t, confirm: undefined, streaming: true, status: "forecasting", text: "" }));
      abort.current = new AbortController();
      try {
        await streamChat(
          history(),
          (f: ChatFrame) => {
            if (f.type === "status") patch(botId, (t) => ({ ...t, status: f.state }));
            else if (f.type === "text") patch(botId, (t) => ({ ...t, text: t.text + f.delta, status: undefined }));
            else if (f.type === "artifact") patch(botId, (t) => ({ ...t, artifact: f.plan }));
            else if (f.type === "error") patch(botId, (t) => ({ ...t, error: f.message, status: undefined }));
            else if (f.type === "done") patch(botId, (t) => ({ ...t, streaming: false, status: undefined }));
          },
          { signal: abort.current.signal, intent: intent as any },
        );
      } catch (e) {
        patch(botId, (t) => ({ ...t, error: (e as Error).message, streaming: false, status: undefined }));
      } finally {
        setBusy(false);
        abort.current = null;
      }
    },
    [turns],
  );

  const send = useCallback(
    async (text: string) => {
      if (busy) return;
      const userTurn: ChatTurn = { id: nid(), role: "user", text };
      const botTurn: ChatTurn = { id: nid(), role: "assistant", text: "", status: "parsing" };
      setTurns((p) => [...p, userTurn, botTurn]);
      setBusy(true);
      try {
        const res = await parsePlan(text);
        if (res.outcome === "clarification") {
          patch(botTurn.id, (t) => ({
            ...t,
            clarification: { question: res.question, missing_fields: res.missing_fields },
            status: undefined,
          }));
          setBusy(false);
          return;
        }
        // merge the map pin when the message did not name a known place
        const it = res.intent as Intent;
        const messageNamedPlace = it.location?.name && it.location.name !== "custom";
        const pinIsCustom = locRef.current.name === undefined;
        let locationSource: "map pin" | "your message" = "your message";
        if (!messageNamedPlace || (pinIsCustom && locRef.current)) {
          it.location = { name: "custom", lat: locRef.current.lat, lon: locRef.current.lon };
          locationSource = "map pin";
        }
        patch(botTurn.id, (t) => ({ ...t, confirm: { intent: it, locationSource }, status: undefined }));
        setBusy(false);
      } catch (e) {
        patch(botTurn.id, (t) => ({ ...t, error: (e as Error).message, status: undefined }));
        setBusy(false);
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
        <Link href="/" className="text-lg font-semibold tracking-tight text-ink">Harara</Link>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setMapOpen((o) => !o)}
            className="rounded border border-border px-2.5 py-1.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink"
          >
            {mapOpen ? "Hide map" : "Set location"}
          </button>
          <AssumptionsSheet />
          <ThemeToggle />
        </div>
      </header>

      {mapOpen && (
        <div data-print-hide className="border-b border-border bg-bg-raised px-4 py-3">
          <SiteMap value={loc} onChange={setLoc} />
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-6" id="main">
        {turns.length === 0 ? (
          <div className="mx-auto flex max-w-prose flex-col gap-6 pt-6">
            <div>
              <h1 className="text-h3 text-ink">Plan a shift</h1>
              <p className="mt-1 text-ink-secondary">
                Describe the day the way you would to a colleague, and set the site on the map. The assistant reads it, gets the forecast, plans the hours, and explains the result. Every number comes from the planner, not the model.
              </p>
            </div>
            <SuggestedPrompts onPick={(t) => send(t)} />
            {example && (
              <div className="flex flex-col gap-2">
                <p className="mono text-micro uppercase tracking-wide text-ink-muted">
                  Example · Doha, tomorrow · a moderate, acclimatised crew, 8 work-hours
                </p>
                <div aria-hidden className="pointer-events-none select-none opacity-55 [filter:saturate(0.7)]">
                  <ArtifactCard plan={example} />
                </div>
                <p className="text-sm text-ink-muted">
                  This is a worked example, not your site. Send a request above to make your own.
                </p>
              </div>
            )}
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
                  {t.confirm && (
                    <ConfirmCard
                      intent={t.confirm.intent}
                      locationSource={t.confirm.locationSource}
                      onConfirm={(i) => runIntent(t.id, i)}
                      onCancel={() => patch(t.id, (x) => ({ ...x, confirm: undefined, text: "Cancelled." }))}
                    />
                  )}
                  {t.artifact && <ArtifactCard plan={t.artifact} />}
                  {t.error && (
                    <p className="rounded-lg border border-state-stop/40 bg-surface-2 p-3 text-sm text-ink-secondary">{t.error}</p>
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
