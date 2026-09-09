# Site v2: abstract visual system + Apple-grade /app

Build order. Restrained instrument aesthetic held throughout; premium = precision,
hierarchy, whitespace, one accent, motion with intent. Voice carries the user's
in-flight reframe: **Qatar Ministerial Decision 17/2021 is the foundation; data
makes it precise.** Not "the ban misses danger."

## 0. Base
- Commit the in-flight working-tree changes (regulation-as-foundation copy in
  Problem/Idea, hosted OpenFreeMap map styles, layout hydration guard) as one
  scoped commit so the rest sits on a clean base.

## 1. The motif: one shared module
- `web/lib/heatField.ts`: pure: sample a WBGT curve to N points, normalise to
  0..1, isotherm band geometry, the 32.1 ridge position, ramp-colour lookup
  (reuses `lib/ramp.ts`). No React.
- `web/components/visual/HeatField.tsx`: one Canvas-2D renderer. Props
  `{ curve, variant: "hero" | "divider" | "panel", animate?, className? }`.
  Draws smooth isotherm bands + a faint hot ridge where WBGT crosses 32.1,
  coloured from the WBGT ramp. Always < 8% contrast vs background. Pauses via
  IntersectionObserver when offscreen. Static single paint under
  `prefers-reduced-motion` / `Save-Data`. DPR capped at 1.5.
- `web/components/visual/HeatFieldSVG.tsx`: the same motif as inline SVG bands,
  for the OG image and favicon (which render in the OG runtime, no canvas).
- Hero: replace the R3F/`three` shader backdrop with `<HeatField variant="hero">`.
  Same motif, driven by the real Doha curve; drops `three` +
  `@react-three/fiber` from the landing bundle (helps the perf budget) and the
  headless-WebGL fragility. Documented in DESIGN.md as a deliberate renderer
  swap, motif unchanged.
- Section dividers: a single contour line component, animated once on scroll in.
- OG (`app/opengraph-image.tsx`) + favicon (`app/icon.tsx`): regenerate from
  `HeatFieldSVG`, copy updated to the new framing.

## 2. Component set: `web/components/ui/`
One of each, light + dark, states default/hover/focus/active/disabled:
- `Button` (primary | secondary | ghost | danger)
- `Chip` (the control-bar value chip; static + button variants)
- `Popover` (anchored, non-modal; Radix Popover under the hood, token-styled)
- `Card`, `Switch` (labelled, with one-line hint), `Stepper` (hours)
- Re-home the existing artifact card, headline-number block, confirm card,
  clarification card as documented members of the set (no rewrite, just
  catalogue + state polish).
- `web/app/styleguide/page.tsx`: every component, every state, both themes.
  Not linked from the site. `robots: noindex`.

## 3. /app: three-zone enterprise frame
- `web/components/app/AppShell.tsx` replaces the chat-first layout:
  - **Top bar** (slim): wordmark, theme toggle, Assumptions, Method link.
  - **Control bar** (persistent, <= 4 controls, each a value chip opening an
    in-place popover): Location (chip "Doha", popover = wide SiteMap panel),
    Work type (chip "Heavy work", popover = the plain-label cards + acclimatised
    switch), Day (chip "Tomorrow", popover = today / +1 / +3 / date), Hours
    (chip "8 hours", popover = Stepper). Each shows its current value inline.
  - **Result canvas**: the artifact (headline number + DayChart + comparison +
    drawers). Auto-plans Doha / tomorrow / moderate / acclimatised / 8h on load
    so there is a real result in zero clicks. `?q=` share links still hydrate it.
  - **Chat**: `Composer` docked at the bottom; a slide-up panel holds the
    conversation, confirm and clarification cards. Chat edits the same control
    state (a parsed request updates the chips, then plans).
- Motion: 200-300ms spring transitions; the chart + headline animate between
  states (no hard cut); chips flash on change; artifact expands to full screen
  with a shared-element transition. All gated on `prefers-reduced-motion`.
- Loading state = the four real pipeline steps in sequence (existing
  `ThinkingIndicator`, restyled). Empty/error/offline states each offer a next
  step. Faded example artifact before first result.
- Keyboard: full tab order, visible focus, arrow-key hour navigation on the
  chart (exists), and a Cmd/Ctrl-K command menu (jump to preset location,
  change day, open assumptions, open method).

## 4. DESIGN.md: real spec
Spacing scale (4px), type scale, colour tokens + WBGT ramp hex both themes +
CVD check (already computed in `lib/ramp.ts`), motion values, the motif rules,
and a table: every component x its states.

## 5. Discipline
- Clean build; Lighthouse mobile: perf >= 90, a11y + best-practices >= 95, with
  the motif present. Motif + any 3D code-split, loaded after first paint. No CLS
  when the result renders.
- No em dashes. Regulation-as-foundation framing in every new surface.
- Full test suite stays green (108).
