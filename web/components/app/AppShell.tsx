"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { fetchPlan, parsePlan, streamChat, type ChatMessageIn } from "@/lib/api";
import type { ChatFrame, ChatTurn, PlanResponse, WorkloadClass } from "@/lib/types";
import { DOHA, LOCATION_PRESETS } from "@/lib/types";
import { isoPlusDays } from "@/lib/format";
import { decodeShare } from "@/lib/share";
import dynamic from "next/dynamic";
import { useDeferredMount, usePrefersReducedMotion, useTheme } from "@/lib/hooks";
import { warmBackend } from "@/lib/warm";
import { BackendNotice } from "@/components/BackendNotice";
import { ThemeToggle } from "@/components/ThemeToggle";

const HeatField = dynamic(
  () => import("@/components/visual/HeatField").then((m) => m.HeatField),
  { ssr: false },
);
import { AssumptionsSheet } from "@/components/chat/AssumptionsSheet";
import { Composer } from "@/components/chat/Composer";
import { ArtifactCard } from "@/components/artifact/ArtifactCard";
import { ThinkingIndicator } from "@/components/chat/ThinkingIndicator";
import { Button } from "@/components/ui/Button";
import { ControlBar, type PlanReq } from "./ControlBar";
import { ChatPanel } from "./ChatPanel";
import { CommandMenu } from "./CommandMenu";
import type { Intent } from "@/components/chat/ConfirmCard";

let idc = 0;
const nid = () => `a${++idc}`;

const DEFAULT_REQ: PlanReq = {
  lat: DOHA.lat,
  lon: DOHA.lon,
  date: isoPlusDays(1),
  required_work_hours: 8,
  workload_class: "moderate",
  acclimatised: true,
  tz: "Asia/Qatar",
};

type FlashKey = "location" | "work" | "day" | "hours";

export function AppShell() {
  const reduced = usePrefersReducedMotion();
  const [theme] = useTheme();
  const [req, setReq] = useState<PlanReq>(DEFAULT_REQ);
  const [locName, setLocName] = useState("Doha");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [phase, setPhase] = useState<"planning" | "ready" | "error">("planning");
  const [waking, setWaking] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<Partial<Record<FlashKey, boolean>>>({});

  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [cmdk, setCmdk] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const reqRef = useRef(req);
  reqRef.current = req;
  const runId = useRef(0);

  const patchTurn = (id: string, fn: (t: ChatTurn) => ChatTurn) =>
    setTurns((p) => p.map((t) => (t.id === id ? fn(t) : t)));

  const doFlash = (k?: FlashKey) => {
    if (!k) return;
    setFlash((f) => ({ ...f, [k]: true }));
    setTimeout(() => setFlash((f) => ({ ...f, [k]: false })), 450);
  };

  const replan = useCallback(
    async (patch: Partial<PlanReq>, flashKey?: FlashKey) => {
      const next = { ...reqRef.current, ...patch };
      setReq(next);
      doFlash(flashKey);
      const id = ++runId.current;
      setPhase("planning");
      setErr(null);
      try {
        const p = await fetchPlan(next as any, {
          onSlow: () => id === runId.current && setWaking(true),
        });
        if (id === runId.current) {
          setPlan(p);
          setPhase("ready");
          setWaking(false);
        }
      } catch (e) {
        if (id === runId.current) {
          setErr((e as Error).message);
          setPhase("error");
          setWaking(false);
        }
      }
    },
    [],
  );

  // first paint: a shared link, or the default plan in zero clicks
  useEffect(() => {
    warmBackend();
    const slow = () => setWaking(true);
    const token = new URLSearchParams(window.location.search).get("q");
    const shared = token ? decodeShare(token) : null;
    const body = shared ?? DEFAULT_REQ;
    if (shared) {
      setReq((r) => ({ ...r, ...shared }));
      setLocName(shared.lat === DOHA.lat && shared.lon === DOHA.lon ? "Doha" : "Custom site");
    }
    fetchPlan(body, { onSlow: slow })
      .then((p) => { setPlan(p); setPhase("ready"); setWaking(false); })
      .catch((e) => { setErr((e as Error).message); setPhase("error"); setWaking(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- control handlers -------------------------------------------------
  const onLocation = (v: { lat: number; lon: number; name?: string }) => {
    setLocName(v.name && v.name !== "custom" ? v.name : "Custom site");
    replan({ lat: v.lat, lon: v.lon }, "location");
  };
  const onWorkload = (w: WorkloadClass) => replan({ workload_class: w }, "work");
  const onAcclimatised = (v: boolean) => replan({ acclimatised: v }, "work");
  const onDay = (iso: string) => replan({ date: iso }, "day");
  const onHours = (h: number) => replan({ required_work_hours: h }, "hours");

  // ---- chat -----------------------------------------------------------
  const history = (): ChatMessageIn[] =>
    turns
      .filter((t) => t.text || t.clarification)
      .map((t) => ({
        role: t.role,
        content: t.role === "assistant" && t.clarification ? t.clarification.question : t.text,
      }));

  const applyIntent = useCallback(
    async (botId: string, intent: Intent) => {
      const patch: Partial<PlanReq> = {};
      if (intent.target_local_date) patch.date = intent.target_local_date;
      if (typeof intent.required_work_hours === "number") patch.required_work_hours = intent.required_work_hours;
      if (intent.crew?.workload) patch.workload_class = intent.crew.workload;
      if (typeof intent.crew?.acclimatised === "boolean") patch.acclimatised = intent.crew.acclimatised;
      if (intent.location) {
        patch.lat = intent.location.lat;
        patch.lon = intent.location.lon;
        setLocName(intent.location.name && intent.location.name !== "custom" ? intent.location.name : "Custom site");
      }
      patchTurn(botId, (t) => ({ ...t, confirm: undefined, streaming: true, status: "forecasting", text: "" }));
      await replan(patch);

      // the model's plain-language explanation, streamed into the same turn
      setBusy(true);
      abort.current = new AbortController();
      try {
        await streamChat(
          history(),
          (f: ChatFrame) => {
            if (f.type === "status") patchTurn(botId, (t) => ({ ...t, status: f.state }));
            else if (f.type === "text") patchTurn(botId, (t) => ({ ...t, text: t.text + f.delta, status: undefined }));
            else if (f.type === "error") patchTurn(botId, (t) => ({ ...t, error: f.message, status: undefined }));
            else if (f.type === "done") patchTurn(botId, (t) => ({ ...t, streaming: false, status: undefined }));
          },
          { signal: abort.current.signal, intent: intent as any },
        );
      } catch (e) {
        patchTurn(botId, (t) => ({ ...t, error: (e as Error).message, streaming: false, status: undefined }));
      } finally {
        setBusy(false);
        abort.current = null;
      }
    },
    [replan, turns],
  );

  const send = useCallback(
    async (text: string) => {
      if (busy) return;
      const u: ChatTurn = { id: nid(), role: "user", text };
      const b: ChatTurn = { id: nid(), role: "assistant", text: "", status: "parsing" };
      setTurns((p) => [...p, u, b]);
      setBusy(true);
      try {
        const res = await parsePlan(text);
        if (res.outcome === "parsed") {
          const it = res.intent as Intent;
          const named = it.location?.name && it.location.name !== "custom";
          if (!named) {
            it.location = { name: "custom", lat: reqRef.current.lat, lon: reqRef.current.lon };
          }
          patchTurn(b.id, (t) => ({
            ...t,
            confirm: { intent: it, locationSource: named ? "your message" : "map pin" },
            status: undefined,
          }));
          setBusy(false);
          return;
        }
        // not a complete plan request: let the assistant handle it. It answers
        // a question, updates the controls, or streams a clarification.
        abort.current = new AbortController();
        const hist: ChatMessageIn[] = [...history(), { role: "user", content: text }];
        const gathering = turns.some((t) => t.role === "assistant" && t.clarification);
        const cur = {
          name: locName,
          lat: reqRef.current.lat,
          lon: reqRef.current.lon,
          date: reqRef.current.date,
          workload: reqRef.current.workload_class,
          acclimatised: reqRef.current.acclimatised,
          hours: reqRef.current.required_work_hours,
        };
        await streamChat(
          hist,
          (f: ChatFrame) => {
            if (f.type === "status") patchTurn(b.id, (t) => ({ ...t, status: f.state }));
            else if (f.type === "text")
              patchTurn(b.id, (t) => ({ ...t, text: t.text + f.delta, status: undefined, streaming: true }));
            else if (f.type === "clarification")
              patchTurn(b.id, (t) => ({
                ...t,
                clarification: { question: f.question, missing_fields: f.missing_fields },
                status: undefined,
              }));
            else if (f.type === "artifact") {
              setPlan(f.plan);
              setPhase("ready");
              // keep the control bar in step with what the chat just planned
              const rq = f.plan.meta?.request;
              if (rq) {
                setReq((p) => ({
                  ...p,
                  lat: rq.lat, lon: rq.lon, date: rq.date,
                  required_work_hours: rq.required_work_hours,
                  workload_class: rq.workload_class, acclimatised: rq.acclimatised,
                }));
                const preset = LOCATION_PRESETS.find(
                  (p) => Math.abs(p.lat - rq.lat) < 0.02 && Math.abs(p.lon - rq.lon) < 0.02,
                );
                setLocName(preset?.name ?? "Custom site");
              }
            } else if (f.type === "error")
              patchTurn(b.id, (t) => ({ ...t, error: f.message, status: undefined }));
            else if (f.type === "done")
              patchTurn(b.id, (t) => ({ ...t, streaming: false, status: undefined }));
          },
          {
            signal: abort.current.signal,
            context: {
              req: cur,
              ...(plan ? { plan: { summary: plan.summary, meta: plan.meta } } : {}),
              ...(gathering ? { gathering: true } : {}),
            },
          },
        );
      } catch (e) {
        patchTurn(b.id, (t) => ({ ...t, error: (e as Error).message, status: undefined, streaming: false }));
      } finally {
        setBusy(false);
        abort.current = null;
      }
    },
    [busy, plan, turns],
  );

  const stopChat = () => {
    abort.current?.abort();
    setBusy(false);
    setTurns((p) => p.map((t) => (t.streaming ? { ...t, streaming: false, status: undefined } : t)));
  };

  // ---- render --------------------------------------------------------
  return (
    <div className="mx-auto flex h-dvh max-w-[1280px] flex-col">
      {/* top bar, full width */}
      <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <Link href="/" className="text-base font-semibold tracking-tight text-ink">
          Harara
        </Link>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCmdk(true)}
            className="hidden items-center gap-1.5 rounded border border-border px-2 py-1 text-sm text-ink-muted hover:border-border-strong hover:text-ink sm:flex"
          >
            <span className="mono text-micro">⌘K</span>
          </button>
          <AssumptionsSheet />
          <ThemeToggle />
        </div>
      </header>

      <BackendNotice />

      {/* two panes: conversation on the left, the plan on the right */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* LEFT: conversation + composer. Bottom on mobile, left on desktop. */}
        <aside className="flex h-[46vh] shrink-0 flex-col border-t border-border lg:order-first lg:h-auto lg:w-[400px] lg:border-r lg:border-t-0 xl:w-[440px]">
          <div className="flex items-center justify-between border-b border-border px-4 py-2">
            <p className="eyebrow">Assistant</p>
            {turns.length > 0 && (
              <button
                type="button"
                onClick={() => setTurns([])}
                className="text-sm text-ink-muted transition-colors hover:text-ink"
              >
                Clear
              </button>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <ChatPanel
              turns={turns}
              onConfirm={applyIntent}
              onCancelConfirm={(id) =>
                patchTurn(id, (t) => ({ ...t, confirm: undefined, text: "Cancelled." }))
              }
            />
          </div>
          <Composer
            onSend={send}
            busy={busy}
            onStop={stopChat}
            showHints={turns.length === 0}
          />
        </aside>

        {/* RIGHT: control bar + result canvas */}
        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <ControlBar
            req={req}
            locName={locName}
            flash={flash}
            onLocation={onLocation}
            onWorkload={onWorkload}
            onAcclimatised={onAcclimatised}
            onDay={onDay}
            onHours={onHours}
          />
          <main id="main" className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
            <div className="mx-auto max-w-3xl">
              {phase === "planning" && !plan && <PlanningState theme={theme} waking={waking} />}
              {phase === "error" && <ErrorState message={err} onRetry={() => replan({})} />}
              {plan && (
                <div
                  className={
                    phase === "planning" && !reduced
                      ? "opacity-60 transition-opacity duration-200"
                      : "transition-opacity duration-200"
                  }
                  aria-busy={phase === "planning"}
                >
                  <ArtifactCard key={plan.meta.date + plan.meta.location.lat} plan={plan} embedded />
                </div>
              )}
            </div>
          </main>
        </section>
      </div>

      <CommandMenu
        open={cmdk}
        onOpenChange={setCmdk}
        onLocation={(p) => onLocation(p)}
        onDay={onDay}
        onOpenAssumptions={() => document.querySelector<HTMLElement>('[data-assumptions-trigger]')?.click()}
      />
    </div>
  );
}

function PlanningState({ theme, waking }: { theme: "light" | "dark"; waking?: boolean }) {
  const showField = useDeferredMount();
  return (
    <div className="relative overflow-hidden rounded-xl border border-border-strong bg-bg-raised p-5 shadow-1">
      {showField && (
        <div aria-hidden className="fade-in pointer-events-none absolute inset-0 opacity-70">
          <HeatField theme={theme} variant="panel" />
        </div>
      )}
      <div className="relative">
        <p className="text-h4 text-ink">
          {waking ? "Waking the demo server" : "Building the plan"}
        </p>
        <p className="mt-1 text-sm text-ink-secondary">
          {waking
            ? "It runs on a free tier and spins down when idle. This first request can take up to a minute, then it is quick."
            : "Every number comes from the planner, not the language model."}
        </p>
        <div className="mt-4">
          <ThinkingIndicator state="forecasting" />
        </div>
        <div className="skeleton mt-4 h-56 w-full rounded-lg" />
      </div>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-[var(--state-stop)]/40 bg-surface p-5">
      <p className="text-h4 text-ink">The plan could not be built</p>
      <p className="mt-1 text-sm text-ink-secondary">
        {message || "The forecast service did not respond."} You can try again, or
        change the location and day above.
      </p>
      <div className="mt-3">
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    </div>
  );
}
