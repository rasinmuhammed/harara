"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Card } from "@/components/ui/Card";
import { Switch } from "@/components/ui/Switch";
import { Stepper } from "@/components/ui/Stepper";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/Popover";
import { HeatField } from "@/components/visual/HeatField";
import { ClarificationCard } from "@/components/chat/ClarificationCard";
import { ThinkingIndicator } from "@/components/chat/ThinkingIndicator";

/** Internal component catalogue. Not linked from the site; noindex. */
export default function Styleguide() {
  return (
    <div className="min-h-dvh bg-bg px-6 py-10 text-ink">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-h2">Harara style guide</h1>
        <p className="mt-2 text-ink-secondary">
          Every component, both themes. Internal reference and visual regression
          surface. Not linked from the site.
        </p>

        <Section title="Button">
          <Pane>
            {(["primary", "secondary", "ghost", "danger"] as const).map((v) => (
              <div key={v} className="flex flex-wrap items-center gap-3">
                <span className="mono w-20 text-micro uppercase text-ink-muted">{v}</span>
                <Button variant={v}>Default</Button>
                <Button variant={v} disabled>Disabled</Button>
                <Button variant={v} size="sm">Small</Button>
              </div>
            ))}
          </Pane>
        </Section>

        <Section title="Chip (control-bar value)">
          <Pane>
            <div className="flex flex-wrap gap-2">
              <Chip label="Location" value="Doha" />
              <Chip label="Work type" value="Heavy" active />
              <Chip label="Day" value="Tomorrow" flash />
              <Chip label="Hours" value="8 hours" as="span" />
            </div>
          </Pane>
        </Section>

        <Section title="Popover (anchored, non-modal)">
          <Pane>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="secondary" size="sm">Open popover</Button>
              </PopoverTrigger>
              <PopoverContent className="w-56">
                <p className="text-sm text-ink">Anchored to the trigger.</p>
                <p className="mt-1 text-sm text-ink-muted">Dismiss on outside click or Escape.</p>
              </PopoverContent>
            </Popover>
          </Pane>
        </Section>

        <Section title="Card">
          <Pane>
            <div className="grid gap-3 sm:grid-cols-2">
              <Card className="p-4"><p className="text-sm text-ink">tone = flat</p></Card>
              <Card tone="raised" className="p-4"><p className="text-sm text-ink">tone = raised</p></Card>
            </div>
          </Pane>
        </Section>

        <Section title="Switch">
          <Pane>
            <SwitchDemo />
          </Pane>
        </Section>

        <Section title="Stepper">
          <Pane>
            <StepperDemo />
          </Pane>
        </Section>

        <Section title="Loading state, the four pipeline steps">
          <Pane>
            <div className="flex flex-col gap-4">
              <ThinkingIndicator state="parsing" />
              <ThinkingIndicator state="planning" />
            </div>
          </Pane>
        </Section>

        <Section title="Clarification card (fail-closed)">
          <Pane>
            <ClarificationCard
              question="How many work-hours does the crew need, and is it used to the heat?"
              missing={["required_work_hours", "acclimatised"]}
              onChip={() => {}}
            />
          </Pane>
        </Section>

        <Section title="Heat-field motif">
          <Pane>
            <div className="grid gap-3">
              <div className="h-28 overflow-hidden rounded-lg border border-border">
                <HeatField theme="dark" variant="panel" animate={false} />
              </div>
              <div className="h-10 overflow-hidden rounded-lg border border-border">
                <HeatField theme="dark" variant="divider" animate={false} />
              </div>
            </div>
          </Pane>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10 border-t border-border pt-6">
      <h2 className="mono text-micro uppercase tracking-wide text-ink-muted">{title}</h2>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">{children}</div>
    </section>
  );
}

/** Renders its children twice: once in a dark pane, once in a light pane. */
function Pane({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="theme-dark rounded-xl border border-border bg-bg p-4">
        <p className="mb-3 mono text-micro uppercase text-ink-muted">dark</p>
        {children}
      </div>
      <div className="theme-light rounded-xl border border-border bg-bg p-4">
        <p className="mb-3 mono text-micro uppercase text-ink-muted">light</p>
        {children}
      </div>
    </>
  );
}

function SwitchDemo() {
  const [a, setA] = useState(true);
  return (
    <div className="flex flex-col gap-4">
      <Switch checked={a} onCheckedChange={setA} label="Used to the heat" hint="Two weeks or more in these conditions." />
      <Switch checked={false} onCheckedChange={() => {}} label="Disabled, off" disabled />
    </div>
  );
}

function StepperDemo() {
  const [n, setN] = useState(8);
  return <Stepper value={n} onChange={setN} min={1} max={12} unit="h" label="work-hours" />;
}
