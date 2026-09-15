# Harara site design system

Reference class: the product and marketing sites of Linear, Vercel, Anthropic,
Cursor, Runway, ElevenLabs, Modal. Precise, confident, dark-first, motion used
with intent. No hero gradient, no glassmorphism, no stock illustration, no
emoji. All tokens are CSS custom properties in `app/globals.css`, defined for
both themes; Tailwind is a thin utility layer over them.

## Type

- **Geist Sans** for UI and prose (via `geist/font`, self-hosted).
- **Geist Mono** for every numeral, axis label, and data value.
  `font-variant-numeric: tabular-nums lining-nums`. Applied through `.mono` /
  `.tnum` and the `font-mono` utility.

Scale (`tailwind.config.ts`, rem / px):

```
micro .75/12   sm .8125/13   base .9375/15   lg 1.0625/17
h4 1.25/20   h3 1.5/24   h2 2/32   h1 clamp(2.25rem, 6vw, 3.75rem)
stat 1.75/28
```

Headings: weight 560, `letter-spacing: -0.018em`, `text-wrap: balance`.
Eyebrow labels: `.eyebrow` (Geist Mono, 12px, uppercase, `+0.08em`).

## Colour

Dark is the primary design. Bare `:root` is dark; light is opt-in via
`:root[data-theme="light"]` or, with no attribute, `prefers-color-scheme:
light`. `body` sets `background` from a token.

### Neutrals

| token | dark | light |
|---|---|---|
| `--bg` | `#0b0b0c` | `#fbfaf8` |
| `--bg-raised` | `#141416` | `#ffffff` |
| `--surface` / `--surface-2` | `#161719` / `#1d1e21` | `#ffffff` / `#f4f2ee` |
| `--border` / `--border-strong` | `#26272b` / `#383a3f` | `#e6e3dc` / `#d3cec3` |
| `--text` / `--text-secondary` / `--text-muted` | `#ececee` / `#a1a1a8` / `#8b8c93` | `#17181a` / `#55565c` / `#63646b` |

### Accent

| token | dark | light |
|---|---|---|
| `--accent` (heat amber) | `#e9963e` | `#b4650e` |
| `--accent-ink` (text on accent) | `#1a1206` | `#ffffff` |

`--text-muted` clears AA (>= 4.5:1) on `--bg` and `--surface` in both themes;
`--accent-ink` on `--accent` is >= 6:1 in both. Verified with Lighthouse
(accessibility 99 on both themes).

### WBGT ramp (`lib/ramp.ts`)

Cool to hot, interpolated in OKLab, with a deliberate discontinuity at 32.1 C
(the Decision 17/2021 stop-work line) and a 1 px rule drawn there so the break
survives greyscale. Blue to teal to near-neutral below, a jump to amber to deep
red above. The grey-green at 32.0 is a transition, not a category.

| WBGT C | dark | light |
|---|---|---|
| 24 | `#3c6e8e` | `#22506e` |
| 27 | `#4c93ac` | `#2f7189` |
| 30 | `#87b9ba` | `#6da0a0` |
| 32.0 | `#c4cdbd` | `#aeb8a8` |
| **32.1** | `#f2c066` | `#e9b24c` |
| 34 | `#e79a4f` | `#db8038` |
| 37 | `#d06a54` | `#c04a34` |
| 40 | `#a03e37` | `#6e2420` |

Colour-blindness check (OKLab dE, deuteranopia and protanopia simulated):
adjacent stops separate by dE >= 9 under both, the 32.0 -> 32.1 jump is
dE ~= 12, every below-line vs above-line pair exceeds dE 17. Blue vs amber/red
is the safe axis, so the ramp reads cool-to-hot under both conditions.

### Operational states

Reserved status colours, never carried by hue alone: each state also has a
glyph and a text label, and `stop` adds a 45-degree hatch fill and a top rule.

| state | glyph | dark | light |
|---|---|---|---|
| work | filled circle | `#4fb39a` | `#2e7d6b` |
| reduced | half circle | `#dda63c` | `#b67a12` |
| stop | filled square + hatch | `#d66074` | `#a83246` |

Green and red collapse toward the same olive under deuteranopia (dE ~= 6.7).
Mitigated by four redundant channels: glyph shape, always-visible label, the
stop hatch and rule (unmistakable in greyscale), staggered luminance, and
position (work at the day's edges, stop in the middle).

## Motion

- **Lenis** for smooth scrolling. Not loaded under `prefers-reduced-motion` or
  `Save-Data`.
- Scroll reveals: `<Reveal>` uses IntersectionObserver + a CSS transition
  (opacity + 12 px rise). SSR renders visible; a 1.5 s safety timeout means
  content is never left hidden.
- Count-ups: `useCountUp`, a rAF cubic ease, first render only.
- The WBGT curve draws on with `stroke-dashoffset` (`.draw-on`).
- The hero is the only place a heavier animation library (GSAP is available in
  that code-split chunk) or WebGL runs. It is off entirely under
  reduced-motion, Save-Data, or a low uncharged battery; the poster is the
  hero in that case.
- `@media (prefers-reduced-motion: reduce)` collapses all of it to instant,
  and the count-up hook and Lenis loader short-circuit in JS.

## The hero visual

React Three Fiber, a full-screen quad with a GLSL fragment shader driven by
the day's WBGT curve (from `/api/plan` for Doha, fetched server-side). It draws
isotherm bands that crowd toward the hot colours where WBGT rises and a faint
ridge where the curve crosses the stop-work level. Slow drift only.

Progressive: a static CSS-and-SVG poster paints first with no 3D in the initial
bundle; after `load` and one idle callback the canvas is dynamically imported
and cross-faded in; an IntersectionObserver stops the frame loop when the hero
is offscreen; DPR is capped at 1.5; `powerPreference: "low-power"`. The landing
route's initial JS is 113 kB; `three` is a separate chunk loaded after paint.
Lighthouse mobile with the hero present: performance 95, accessibility 99,
best practices 100, CLS 0.

## Copy rules

Founder voice. Short sentences, concrete nouns, specific numbers with their
comparison and cost. No em dashes or en dashes as punctuation anywhere. Banned:
"not just X, it is Y", "seamless(ly)", "unlock", "empower", "leverage" (verb),
"revolutionise", "game changer", "cutting edge", "in today's world", "we are on
a mission", "designed to" / "built to" as filler, three-item adjective lists,
rhetorical-question headings, exclamation marks. Plain word over the long one
("use" not "utilise"). Every domain term gets one plain sentence with no jargon
inside it; the `Term` component and `lib/glossary.ts` hold these and are used
in prose and in the artifact.

## Interactive map (`components/map/SiteMap.tsx`, `lib/mapStyle.ts`)

MapLibre GL JS over OpenFreeMap open vector tiles (`tiles.openfreemap.org`, no
API key, no sign-in, nothing about the site stored). Vector, not raster. The
library and its stylesheet are dynamically imported inside an effect, so they
stay out of the first-paint bundle; `/app` first load is unchanged.

Style JSON is built at runtime from the resolved design tokens
(`tokensFromCSS`), so the map matches the current theme exactly and restyles on
theme toggle. It is an instrument, not a tourist map: near-monochrome land,
thin roads, one cool fill for water, sparse uppercase place labels.

| style slot | token |
|---|---|
| land / land alt | `--bg` / `--surface-2` |
| water | `#132a38` dark, `#dfe8ec` light (fixed, cooler than the neutrals) |
| minor / major road | `--border` / `--border-strong` |
| boundary | `--border-strong`, 2 px dash |
| place label | `--text-secondary` with a `--bg` halo |
| forecast grid cell | `--accent` at 0.07 fill, `--accent` 1.25 px dashed line, on-map label |

The forecast grid cell is a 0.25 degree square (`forecastCell`, snapped to the
grid) with the caption "The forecast covers this area, about 25 km across. It is
not specific to one street or one trench." An inland pin (more than 0.18 deg
west of Doha) adds one sentence about drier air reading cooler; no number.

Controls: navigation (no compass, rotation disabled), a metric scale bar, a
coordinate + distance-from-Doha overlay chip, and a "Back to the pin" button
that appears only when the pin is off-screen. The pin is a draggable teardrop
with a slow accent pulse; a click drops it with a 380 ms fall. Keyboard: the
map container is focusable, arrow keys nudge the pin 0.01 deg, Shift+arrow
0.002 deg; the search box is a combobox with arrow-key results and an
`aria-live` announcement of each new location. Text search (keyless Nominatim,
debounced, degrades to nothing) and manual lat/lon entry are both always
present. Under `prefers-reduced-motion` or `Save-Data` the pulse stops and the
camera snaps instead of easing.

### Satellite surface-heat overlay

An opt-in raster image layer (MapLibre `image` source), off by default, shown
only where a precomputed layer exists (`/api/site-heat`, see technical report
5.9). It uses matplotlib's `inferno` colormap, not the app's WBGT ramp: this
is a deliberate, visible difference, since the two are different quantities
(a climatological satellite pattern versus a live WBGT forecast) and must
never look like the same kind of number. Opacity 0.62 so the street layout
stays legible underneath. The toggle button and its caption both state
"satellite images over recent summers... not today's forecast" so the
distinction is never left to color alone.

## Plain-language work types (`lib/worktypes.ts`)

The ACGIH categories (`light` / `moderate` / `heavy` / `very_heavy`) are kept
unchanged in the request and the solver. Only the display changes: a plain
label and one example drawn from `src/heat_stress.py`.

| class | label | example shown |
|---|---|---|
| light | Light | standing, light hand or arm work, for example inspection or light assembly |
| moderate | Moderate | steady hand and leg work and walking, for example carrying light loads or plastering |
| heavy | Heavy | hard sustained effort, for example digging, shovelling, carrying heavy loads, pouring concrete |
| very_heavy | Very heavy | near maximal effort, for example breaking ground by hand or climbing stairs with a load |

"Used to the heat" toggle: "Has the crew been working in this heat for more
than two weeks", with one sentence on why it matters (an acclimatised body
sweats sooner and holds less heat). Never inferred silently; if it is missing
the assistant asks.

## Chart annotations (`components/artifact/DayChart.tsx`)

Annotations are drawn in place on the plot, never in a legend key:

- "Forecast peak, about HH:MM" sits above the WBGT curve at its maximum.
- "32.1 C stop-work" labels the threshold rule at the right edge.
- "Plan rests through the hottest hours" sits over the rest block, in the
  `stop` colour.
- "Fixed rule works the crew until here" sits under the x-axis at 16:00, in the
  compare colour.
- A thin accent vertical line plus a "now" tick marks the current local time,
  only when the chart's day is today.
- Borderline hours (forecast band straddles 32.1) carry a small dot on the
  state strip; "dot = forecast uncertain here" is the only note for it.

The uncertainty band is the p10-p90 of past forecast error at this lead
(`api/data/wbgt_residuals.json`), drawn as a faint `--text` ribbon behind the
curve. The plan itself stays on the point forecast.

### Progressive build (landing "one chart, four reveals")

`DayChart` takes `stage` 1-4. 1: forecast and band only, short viewBox. 2: adds
the 32.1 rule. 3: adds the fixed-rule bars and its annotation. 4: adds the plan
bars, the state strip, the live-now marker, the hover readout and the legend.
The landing renders the same chart four times, once per stage, each in its own
scroll reveal.

## Headline number pattern

Every artifact leads with one sentence, stated once, largest text in the card:
"Worst point of the day: heat load X, down from Y under the fixed rule, same N
hours worked." X and Y are `summary.peak_plan` and `summary.peak_calendar`
straight from the solver. The same shape is reused on the landing idea section
and the replay section. No second framing of the same number anywhere in the
card; the comparison strip below carries the breakdown.

## Methods drawer

Every artifact carries a `<details>` titled "What produced these numbers":
forecast source, model run, lead days, grid cell, the WBGT method, the solver,
the lead-time caveat, and the generation timestamp. All of it reads from
`plan.meta`. A second drawer lists the raw hourly table.

## Shareable link and print

A plan is fully described by its request, so "Copy link" packs
`{lat, lon, date, hours, workload, acclimatised}` into a base64url token
(`lib/share.ts`) and writes `/app?q=<token>`. Opening that URL auto-plans those
exact parameters with a one-line note that it came from a shared link. "Print"
calls `window.print()`; a `@media print` block in `globals.css` drops the
header, composer, map and controls, flattens the card, and opens the drawers so
one clean page of the shift card prints.

## Motion budget

- One shader hero. Everything else is transform / opacity only, <= 400 ms,
  eased `cubic-bezier(0.22, 1, 0.36, 1)`.
- Offscreen loops pause (hero frame loop, via IntersectionObserver).
- Count-ups run once, on first render, and settle on the exact value.
- The map pin pulse is the only ambient loop; it stops under reduced-motion.
- `prefers-reduced-motion` and `Save-Data` turn all of it off: no hero canvas,
  no Lenis, no pin pulse, camera snaps, reveals and count-ups are instant.

## Loading and empty states

- The chat "thinking" indicator is the four real steps in order (read the
  request, get the forecast, plan the day, write it up), each ticked as it
  completes.
- `/app` before the first request shows a real, dimmed Doha-tomorrow artifact
  labelled as a worked example, so the screen is never blank.
- The replay section shows a seven-card skeleton while loading and a plain
  "needs the API" line on failure.

---

# v2: abstract visual system and the enterprise /app

This section supersedes "The hero visual" above: the hero no longer runs a
WebGL fragment shader. `three` and `@react-three/fiber` were removed. The
motif is now one Canvas-2D module used everywhere, which cut the landing's
lazy JS and removed the headless-WebGL fragility, with the visual language
unchanged.

## Spacing scale

A 4 px base. Use Tailwind's default steps, which are already 4 px multiples,
and stay on this ladder:

```
4  8  12  16  24  32  48  64  96      (px)
1  2  3   4   6   8   12  16  24      (tailwind step)
```

Component internals use 8 to 16. Section rhythm on the landing is `py-20`
(80 px) with `py-24` (96 px) on the closing section. The /app frame uses 10
to 16 for the bars and 24 for the result canvas gutter. Gaps, not per-element
margins, set the spacing between siblings.

## The heat-field motif

One scalar field `f(x, y) = y - curve(x)`, where `curve(x)` is the day's WBGT
profile normalised to 0..1 over 24..40 C. Iso-lines of `f` are isotherm
bands; where the curve is high (hot midday) the bands crowd toward the top.
Each band takes its colour from the WBGT ramp at the temperature it marks, and
a brighter ridge sits where the field crosses 32.1 C.

| module | role |
|---|---|
| `lib/heatField.ts` | pure: `sampleCurve`, `curveAt` (Catmull-Rom), `bandColor`, the per-variant constants. No React, no canvas. |
| `components/visual/HeatField.tsx` | the Canvas-2D renderer. Props `wbgt`, `theme`, `variant`, `animate`. |
| `components/visual/HeatFieldSVG.tsx` | the same motif as static SVG, for `opengraph-image.tsx` and `icon.tsx` (rendered by `next/og`, no canvas). |
| `components/visual/ContourDivider.tsx` | one contour line as a section rule; draws in once on scroll, holds. |

Variants (`VARIANTS` in `lib/heatField.ts`):

| variant | bands | alpha ceiling | where |
|---|---|---|---|
| `hero` | 15 | 0.72 | landing hero backdrop |
| `panel` | 11 | 0.60 | /app loading and empty states |
| `divider` | 3 | 0.85 | (reserved) |

Rules, enforced in the component:

- **Never competes with text.** Per-band fill alpha is `ceiling x (0.05..0.08)`
  and line alpha `ceiling x 0.22` (ridge `x 0.62`); a radial vignette fades the
  field into `--bg` at the edges. Effective contrast against the background
  stays under 8%.
- **Pauses offscreen.** An `IntersectionObserver` stops the RAF loop when the
  canvas leaves the viewport.
- **Static under reduced conditions.** `prefers-reduced-motion` or `Save-Data`
  (or `animate={false}`) means a single paint, no loop.
- **DPR capped at 1.5.**
- The OG/favicon SVG uses slightly higher fill opacity (`0.06..0.09`) because
  it is a deliberate graphic, not an ambient layer.

## The /app frame

Three zones, top to bottom, in `components/app/AppShell.tsx`:

1. **Top bar**: wordmark, a `Cmd/Ctrl-K` command-menu button, Assumptions, theme
   toggle. `py-2.5`, one border.
2. **Control bar** (`ControlBar.tsx`): four value chips, each opening an
   in-place popover, never a blocking modal. Each chip shows its current value
   inline so the plan's inputs are always readable without opening anything.
   The chip flashes on change.

   | control | chip reads | popover |
   |---|---|---|
   | Location | `Doha` / `Custom site` | wide panel with the full `SiteMap` (the one control that opens wide) |
   | Work type | `Heavy` / `Heavy · new crew` | the four plain-label cards + the acclimatisation switch |
   | Day | `Today` / `Tomorrow` / `12 Sep` | today / +1 / +3 presets + a date input |
   | Hours | `8 hours` | a `Stepper`, 1 to 12 |

3. **Result canvas**: the artifact (`ArtifactCard embedded`), which hides its
   own day and what-if rows because the control bar owns those. The app
   auto-plans Doha / tomorrow / moderate / acclimatised / 8 h on load, so there
   is a real result in zero clicks. A `?q=` share link hydrates it instead.

Below the canvas: the `Composer` is docked; a collapsible `ChatPanel` holds the
conversation, the confirm card, and the clarification card. A natural-language
request updates the control chips, then plans, then streams the model's
plain-language explanation into the panel. `Cmd/Ctrl-K` opens the command menu
(jump to a preset location, change the day, open assumptions or the method).

## Motion values

| token | value | used for |
|---|---|---|
| `--dur-1` | 200 ms | control feedback, chip flash, popover open |
| `--dur-2` | 400 ms | fades |
| `--dur-3` | 600 ms | scroll reveals, the contour draw-in |
| `--ease` | `cubic-bezier(0.22, 1, 0.36, 1)` | everything |

The result canvas cross-fades between plan states (`opacity` 200 ms) rather
than hard-cutting. The artifact expands to full screen through the existing
Radix Dialog. All of it collapses to the final state under
`prefers-reduced-motion` (the global rule in `globals.css` plus JS
short-circuits in `useCountUp`, the `SmoothScroll` loader, and `HeatField`).

## Component catalogue

`components/ui/`, each designed for both themes. `/styleguide` (noindex, not
linked) renders every one of these in its states.

| component | file | variants / props | states |
|---|---|---|---|
| Button | `ui/Button.tsx` | `primary` \| `secondary` \| `ghost` \| `danger`; `sm` \| `md`; `asChild` | default, hover, focus-visible, active (translate-y), disabled |
| Chip | `ui/Chip.tsx` | `as="button"` \| `"span"`; `active`, `flash` | default, hover, open (`active`), flash-on-change, focus-visible |
| Popover | `ui/Popover.tsx` | Radix Popover; `align`, `sideOffset` | closed, open (rise 160 ms), collision-flipped |
| Card | `ui/Card.tsx` | `tone="flat"` \| `"raised"` | static |
| Switch | `ui/Switch.tsx` | `label`, `hint` | off, on, focus-visible, disabled |
| Stepper | `ui/Stepper.tsx` | `min`, `max`, `step`, `unit` | default, at-min (dec disabled), at-max (inc disabled), active |
| ThinkingIndicator | `chat/ThinkingIndicator.tsx` | `state` = parsing \| forecasting \| planning \| writing | step pending, current (pulse), done (check) |
| ClarificationCard | `chat/ClarificationCard.tsx` | `question`, `missing[]` | static (fail-closed notice) |
| ConfirmCard | `chat/ConfirmCard.tsx` | editable `Intent` | complete (Plan enabled), missing fields (Plan disabled, fields ringed) |
| ArtifactCard | `artifact/ArtifactCard.tsx` | `embedded` | ready, re-planning (dimmed), error, expanded (full screen) |
| HeadlineNumber | inside `ArtifactCard` | one sentence, `peak_plan` vs `peak_calendar` | static |
| HeatField | `visual/HeatField.tsx` | `hero` \| `panel` \| `divider`; `animate` | animating (in view), paused (offscreen), static (reduced / Save-Data) |
| ContourDivider | `visual/ContourDivider.tsx` | no props | pre-view (drawn, held), draw-in on first view |
