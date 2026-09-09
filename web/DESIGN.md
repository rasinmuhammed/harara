# Harara web — design system

The reference class is the editorial / instrument-panel end of product design
(Linear, the Vercel dashboard, FT data journalism), not generic SaaS. Confident
whitespace, precise typography, the data carries the page. No hero gradient, no
glassmorphism, no illustration, no emoji. The warmth in the palette is a
restrained nod to the region (honey, date, cardamom) held to the neutral scale
and a single saffron accent.

## Type

| role | face | why |
|---|---|---|
| headings, the two hero numbers | **Fraunces** (variable serif, `opsz`) | editorial gravitas; distinctive without shouting |
| UI, body, every figure | **Inter** (variable) | screen-tuned; first-class `tabular-nums` |

Scale — major third (1.25), in `rem`, defined in `tailwind.config.ts`:

```
caption .75  ·  sm .875  ·  base 1  ·  lead 1.125
stat 1.5  ·  h3 1.5  ·  h2 2  ·  title 2.75  ·  hero 3.75
```

Every number the reader is meant to trust carries `.tnum`
(`font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1`). Titles
and the hero number clamp ~30% smaller below 640px.

## Colour

All tokens live as CSS custom properties in `app/globals.css`, defined for
three theme states: bare `:root` (light), `@media (prefers-color-scheme: dark)
:root:not([data-theme="light"])` (system dark), and `:root[data-theme="dark"]`
(explicit toggle, wins over a light OS). `body` sets `background` from a token
so the page never borrows the host ground.

### Neutrals (warm-biased toward the accent)

| token | light | dark |
|---|---|---|
| `--bg` | `#fbf9f5` | `#15120e` |
| `--surface` | `#ffffff` | `#1d1913` |
| `--surface-sunken` | `#f3efe7` | `#110f0b` |
| `--border` / `--border-strong` | `#e7e1d5` / `#d7cdbb` | `#2c261d` / `#3f372b` |
| `--text` / `--text-secondary` / `--text-muted` | `#211c15` / `#5b5348` / `#8a8073` | `#f4eee3` / `#b6ac99` / `#847a69` |

### Accent + comparison

| token | light | dark |
|---|---|---|
| `--accent` (saffron) | `#b56f14` | `#e0a343` |
| `--compare` (calendar ban, recessive slate) | `#6e7e8c` | `#7c8b98` |

The optimiser plan is the accent; the calendar ban is drawn in `--compare` as a
hatched outline so it visually recedes.

### Operational states (work / reduced / stop)

Reserved status colours. Never carried by hue alone — every state ships a
**glyph** (● ◐ ■), a **text label**, and STOP additionally gets a 45° hatch
fill and a top edge rule.

| state | glyph | light | dark |
|---|---|---|---|
| work | ● | `#2e7d6b` | `#4fb39a` |
| reduced | ◐ | `#b67a12` | `#dda63c` |
| stop | ■ | `#a83246` | `#d66074` |

**CVD rationale.** Checked in OKLab with simulated deuteranopia/protanopia. All
pairs separate by dE ≥ 18 under normal vision. Green↔red collapses toward the
same olive under deuteranopia (dE ≈ 6.7) — this is unavoidable for a
green/amber/red semantic that carries strong learned meaning, so it is
mitigated by four redundant channels: the distinct glyph shape, the always-on
label, the STOP hatch + rule (unmistakable in greyscale), a staggered
luminance (L\* 53.6 / 62.6 / 49.9), and positional separation (work at the
day's edges, stop in the middle). A greyscale or forced-colours reader loses no
information.

### WBGT ramp

Perceptual cool → hot with a **deliberate discontinuity at 32.1 °C** (the
Decision 17/2021 stop-work line). Blue → teal → near-neutral below; a hard jump
to amber → red above. Blue↔amber/red is the CVD-safe axis; the grey-green just
under the line is a transition, not a category. Interpolated in OKLab
(`lib/ramp.ts`), also drawn as a 1px rule so the break survives greyscale.

| °C | light | dark | | °C | light | dark |
|---|---|---|---|---|---|---|
| 24 | `#22506e` | `#3c6e8e` | | **32.1** | `#e9b24c` | `#f2c066` |
| 27 | `#2f7189` | `#4c93ac` | | 34 | `#db8038` | `#e79a4f` |
| 30 | `#6da0a0` | `#87b9ba` | | 37 | `#c04a34` | `#d06a54` |
| 32.0 | `#aeb8a8` | `#c4cdbd` | | 40 | `#6e2420` | `#a03e37` |

Adjacent stops separate by dE ≥ 10 (normal) / ≥ 9 (deuter/protan); the
32.0 → 32.1 jump is dE ≈ 12.

## Space, radius, elevation

Tailwind's default 4px scale (unmodified). Radius `--r-sm` 6 / `--r` 10 /
`--r-lg` 16 — cards use `lg`, controls use the default. One elevation token
`--shadow-card`; dark leans on `--border-strong` instead of shadow.

## Motion

CSS-only, no animation library, for bundle weight and Lighthouse. Durations
`--dur-1` 120ms / `--dur-2` 220ms / `--dur-3` 420ms; easing
`cubic-bezier(.16,1,.3,1)`.

- results entrance: `animate-rise` (fade + 8px), `--dur-3`
- WBGT curve: `draw-on` stroke-dashoffset, 640ms
- stat count-ups: `useCountUp`, 900ms, first render only
- skeletons: 1.5s shimmer sweep

Everything collapses to instant under
`@media (prefers-reduced-motion: reduce)` — the count-up hook and the shimmer
also short-circuit in JS.

## The four non-happy states

`components/states/` — `EmptyState` (ghosted axes sketch + instruction, always
with the assumptions panel visible), `ResultsSkeleton` (layout-matched blocks,
`aria-busy`, no spinner), `ErrorState` (broken-line glyph, "your inputs are
kept", retry re-fires the last request), `ClarificationState` (the NL parser's
question verbatim, missing fields as chips, framed as "won't guess a
safety-relevant value").

## Accessibility

Semantic landmarks (`header`/`main`/`aside`/`section`/`footer`), a skip link,
`:focus-visible` rings on every control from one token. The hand-built chart is
`role="application"` `tabindex=0` with arrow-key hour navigation, a `<desc>` and
`<figcaption>` text alternative that spells out the colour encoding, and a live
readout region. Colour is never the only encoding (glyph + label everywhere).
Contrast is AA or better on both themes.
