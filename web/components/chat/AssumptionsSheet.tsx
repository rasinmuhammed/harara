"use client";
import * as Dialog from "@radix-ui/react-dialog";

export function AssumptionsSheet() {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button type="button" data-assumptions-trigger className="rounded border border-border px-2.5 py-1.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink">
          Assumptions
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed right-0 top-0 z-50 h-full w-full max-w-md overflow-y-auto border-l border-border bg-bg-raised p-5 shadow-1">
          <div className="mb-3 flex items-center justify-between">
            <Dialog.Title className="text-h4 text-ink">Assumptions and limits</Dialog.Title>
            <Dialog.Close asChild>
              <button type="button" className="rounded border border-border px-2 py-1 text-sm text-ink-secondary hover:text-ink">Close</button>
            </Dialog.Close>
          </div>
          <ul className="flex list-disc flex-col gap-3 pl-4 text-sm leading-relaxed text-ink-secondary">
            <li><strong className="text-ink">Screening tool.</strong> Work and rest fractions come from the ACGIH TLV tables (ACGIH 2017, ISO 7243), which protect a population, not an individual. This is decision support, not medical advice, and not a substitute for on-site monitoring.</li>
            <li><strong className="text-ink">Single-point forecast.</strong> One Open-Meteo grid cell, hourly, for the chosen day. WBGT is computed with the Liljegren method through ECMWF thermofeel.</li>
            <li><strong className="text-ink">The 32.1 C line is drawn, not enforced.</strong> The plan minimises retained heat load at equal output. Hours where it still schedules work above 32.1 C are flagged. Decision 17/2021 requires the hard stop on top.</li>
            <li><strong className="text-ink">Retained-load model.</strong> A one-state passive integrator, load = max(0, WBGT minus reference), hourly retention 0.8. Peak is the highest retained load reached, tail is its 90th percentile over the day.</li>
            <li><strong className="text-ink">Evidence.</strong> Over 236 held-out days the scheduler lowered the mean peak by 14 percent and the p90 tail by 16 to 20 percent at equal output. A single day varies. See the <a className="underline" href="https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md" target="_blank" rel="noreferrer">technical report</a> and <a className="underline" href="https://github.com/rasinmuhammed/harara/blob/main/docs/results_ledger.md" target="_blank" rel="noreferrer">results ledger</a>.</li>
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
