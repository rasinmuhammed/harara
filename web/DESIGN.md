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
