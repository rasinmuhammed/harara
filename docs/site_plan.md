# Plan: Harara product site (landing + chat app + artifacts)

Replaces the single-screen MVP UI. `api/` stays the deterministic backend and
gains one streaming endpoint. `web/` is rebuilt as three surfaces: a landing
page, a chat product app at `/app`, and animated result artifacts that render
inside the chat and expand full screen.

Carried-over hard rules: the model never emits a number that reaches the user
(every number is from `get_forecast` / `compute_wbgt` / `run_scheduler`, and
`src/agent/brief.py`'s numeric guard stays in force on generated text); the
assistant fails closed and asks one question when a safety-relevant field is
missing; nothing on the site claims what the results ledger does not support,
and the synthetic individual-twin work does not appear anywhere.

`src/` is not modified. `api/` and `web/` are additive. Code stays under the
MIT `LICENSE` already in the repo.

---

## 1. `POST /api/chat` — event sequence

Request body: `{ "messages": [{ "role": "user" | "assistant", "content": str }],
"context": { "today"?: "YYYY-MM-DD" } | null }`.

Response: `text/event-stream`. Each frame is `data: <json>\n\n`. Frame shapes:

| `type` | payload | when |
|---|---|---|
| `status` | `{ state: "parsing" \| "forecasting" \| "planning" \| "writing" }` | progress; drives the thinking indicator |
| `clarification` | `{ question: str, missing_fields: string[] }` | parse returned `ClarificationNeeded` |
| `text` | `{ delta: str }` | one word-chunk of the guarded assistant explanation |
| `artifact` | `{ plan: <full /api/plan PlanResponse> }` | after the text, so the chart draws from real numbers |
| `error` | `{ message: str }` | forecast upstream failed, or the explanation could not be grounded |
| `done` | `{}` | stream end (always last) |

Server flow:

1. Rate-limit by client IP (fixed window, 20 requests / 300 s). Over limit →
   HTTP `429` with `{ "error": "...", "retry_after": <seconds> }`, no stream.
2. `data: {"type":"status","state":"parsing"}`.
   Call `src.agent.parse.parse_scheduling_request(latest_user_text, today=...)`.
   If it returns `ClarificationNeeded` on the latest turn alone, retry once on
   `previous_user_turn + "\n" + latest_user_turn` (lets "8 hours" answer a
   prior "plan tomorrow for a heavy crew at Lusail"). Still ambiguous →
   `data: {"type":"clarification", ...}` then `done`. Stop.
3. Valid `PlanIntent`:
   `status forecasting` → build a `PlanRequest` from the intent
   (`lat`/`lon` from `intent.location`, date, hours, workload, acclimatised) →
   `status planning` → `api.planning.plan_with_sched(req)` returns
   `(PlanResponse, RunSchedulerResponse)` (new helper; `build_plan` becomes a
   one-liner over it — additive to `api/`).
4. `status writing` → `src.agent.brief.generate_briefing(sched,
   location_name=intent.location.name, llm=get_llm(HARARA_LLM))`. It runs the
   numeric and rule guards and raises `UngroundedBriefing` if the text cannot
   be grounded after one retry. On raise → emit a deterministic fallback
   sentence built only from `PlanResponse.summary` values (grounded by
   construction), otherwise use `Briefing.text`.
5. Stream the explanation word by word as `text` frames.
6. `data: {"type":"artifact","plan": <PlanResponse>}`.
7. `data: {"type":"done"}`.

Any exception in 3-4 → `error` frame + `done`, HTTP 200 (the stream carries the
error).

Model provider: `get_llm(os.environ.get("HARARA_LLM", "mock"))`. Mock needs no
key and runs offline, so the whole site works in development. `ANTHROPIC_API_KEY`
/ `IFM_API_KEY` are read server-side by the adapters only.

`POST /api/plan` and `POST /api/parse` are unchanged. The landing page's
interactive pieces call `/api/plan` directly (no model).

Tests (`tests/test_api_chat.py`, `HARARA_FORECAST_SOURCE=mock`, `HARARA_LLM`
unset):
- ambiguous request → frames include one `clarification`, no `artifact`.
- complete request → frames include `text` then `artifact`; the artifact's
  `summary` equals `plan_with_sched(same req)[0].summary`.
- 21st call inside the window → `429` with `retry_after`.

Open-Meteo: the forecast cache from `api/cache.py` is reused; the CC-BY
attribution string is already in every `/api/plan` response and is shown in the
site footer and the artifact card.

---

## 2. Design tokens

Dark-first. Both themes are complete token sets; manual toggle plus
`prefers-color-scheme` (no attribute = follow the OS).

### Type

- **Geist Sans** — UI and prose. Fallback `ui-sans-serif, system-ui`.
- **Geist Mono** — every numeral, axis label, code, and data value.
  Fallback `ui-monospace, SFMono-Regular, monospace`.
  All numbers: `font-variant-numeric: tabular-nums lining-nums`, weight 500.

Scale (rem / px), minor third-ish, tuned tight for a product UI:

| token | size | use |
|---|---|---|
| `--fs-micro` | .75 / 12 | labels, legends, chat meta |
| `--fs-sm` | .8125 / 13 | secondary UI |
| `--fs-base` | .9375 / 15 | body, chat messages |
| `--fs-lg` | 1.0625 / 17 | landing lead paragraphs |
| `--fs-h4` | 1.25 / 20 | card titles |
| `--fs-h3` | 1.5 / 24 | sub-headings |
| `--fs-h2` | 2.0 / 32 | section headlines |
| `--fs-h1` | `clamp(2.25rem, 6vw, 3.75rem)` | hero |
| stat value | 1.75 / 28, mono 500 | artifact numbers |

Line-height 1.15 headings, 1.55 prose, 1.3 data. One weight axis: 400 / 500 /
600. Uppercase micro-labels get `letter-spacing: .04em`.

### Colour — neutrals

| token | dark (primary) | light |
|---|---|---|
| `--bg` | `#0b0b0c` | `#fbfaf8` |
| `--bg-raised` | `#141416` | `#ffffff` |
| `--surface` | `#161719` | `#ffffff` |
| `--surface-2` | `#1d1e21` | `#f4f2ee` |
| `--border` | `#26272b` | `#e6e3dc` |
| `--border-strong` | `#383a3f` | `#d3cec3` |
| `--text` | `#ececee` | `#17181a` |
| `--text-secondary` | `#a1a1a8` | `#55565c` |
| `--text-muted` | `#7c7d84` | `#6b6c73` |
| `--accent` (heat amber) | `#e9963e` | `#b4650e` |
| `--accent-ink` (text on accent) | `#1a1206` | `#1a1206` |
| `--focus` | `= --accent` | `= --accent` |

`--text-muted` clears AA (>= 4.5:1) on both `--bg` and `--surface` in both
themes. `--accent-ink` on `--accent` is >= 6:1 in both.

### WBGT ramp (cool to hot, hard break at 32.1 C)

Interpolated in OKLab (`lib/ramp.ts`, already in the repo). Blue to teal to
near-neutral below the line; a discontinuity to amber to deep red above. The
grey-green at 32.0 is a transition, not a category. A 1 px rule is drawn at
32.1 C so the break survives greyscale.

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
adjacent stops separate by dE >= 9 in both simulations; the 32.0 -> 32.1 jump
is dE ~= 12; every below-line vs above-line pair exceeds dE 17. Blue vs
amber/red is the safe axis, so the ramp reads as cool-to-hot under both
conditions. Verified with an OKLab + Viénot dichromacy script.

### Operational states

Reserved status colours, never carried by hue alone: each state also has a
glyph and a text label, and `stop` adds a 45-degree hatch fill and a top rule.

| state | glyph | dark | light |
|---|---|---|---|
| work | filled circle | `#4fb39a` | `#2e7d6b` |
| reduced | half circle | `#dda63c` | `#b67a12` |
| stop | filled square + hatch | `#d66074` | `#a83246` |

CVD note: green vs red collapse toward the same olive under deuteranopia
(dE ~= 6.7). This is intrinsic to a green/amber/red semantic and is mitigated
by four redundant channels: the glyph shape, the always-visible label, the
stop hatch and rule (unmistakable in greyscale), a staggered luminance
(L\* 53.6 / 62.6 / 49.9), and position (work at the day's edges, stop in the
middle). A greyscale or forced-colours reader loses nothing.

### Space, radius, motion

Tailwind default 4 px spacing scale, unmodified. Radius `--r-sm` 6 / `--r` 10 /
`--r-lg` 14 / `--r-xl` 20. One elevation token `--shadow-1`
(`0 1px 2px rgba(0,0,0,.4), 0 16px 40px -24px rgba(0,0,0,.5)` dark). Motion:
one easing family (`power3.out` enters, `power2.inOut` transitions),
durations 200 / 400 / 600 ms; see section 5.

---

## 3. Landing page — sections, headline, first sentence

Single scroll. Copy follows the voice rules: short sentences, concrete nouns,
no em or en dashes, none of the banned words, no rhetorical-question headings,
no exclamation marks, terms explained in one plain sentence, numbers given
their comparison and cost.

### Section 1 — Hero

- **Headline:** Decide when to work by the forecast, not the clock.
- **First sentence:** Harara reads the weather forecast for your site, works
  out how hard the heat will be on the body hour by hour, and tells you when
  the crew should work, ease off, or stop.
- Primary action: `Open the planner` -> `/app`. Secondary: `Read the method`
  -> technical report. Live hero visual (section 5) sits behind and to the
  right; the headline block is fully readable at rest with the visual as a
  static poster.

### Section 2 — The problem (three beats, each a small animated diagram, one line)

- **Section headline:** A thermometer does not tell you how dangerous the heat
  is.
- **Beat 1 headline:** Humid heat is harder on the body than the number
  suggests.
  **Line:** Your body cools by sweating, and sweat only cools when it
  evaporates, which it barely does when the air is already damp.
  *Diagram:* a droplet evaporating fast over dry ground, slowly over wet.
- **Beat 2 headline:** The rule is a fixed clock.
  **Line:** Qatar bans outdoor work from 10:00 to 15:30 in summer, every day,
  whatever the forecast for that day says.
  *Diagram:* a fixed grey band while a WBGT curve slides underneath, day to
  day.
- **Beat 3 headline:** The dangerous hours move, and many fall outside the
  ban.
  **Line:** On a check against the published heat-stress tables, about 60
  percent of the unsafe hours for heavy work by crews new to the heat land
  before 10:00, after 15:30, or in April and October.
  *Diagram:* unsafe hours lighting up on a day strip, outside the banned band.

### Section 3 — The idea (interactive scrub day-chart, live Doha numbers from `/api/plan`)

- **Headline:** Same hours of work, less of the worst heat.
- **First sentence:** Drag across the day to see a working shift for Doha
  today, where the plan works the cool morning at full rate, eases through the
  forecast peak, and picks the work back up as it drops, while still hitting
  the target hours.
- Live caption under the chart, numbers from `/api/plan`: `For Doha today the
  plan lowers the worst retained heat load by {peak}% and the p90 tail by
  {tail}%, with the same {hours} hours worked.` If the API is unreachable at
  build and request time, the section falls back to a fixed recent example
  clearly labelled as such.

### Section 4 — How it works (four steps, one line each)

- **Headline:** Four steps, all on public data.
- **Read the forecast.** Hourly temperature, humidity, wind, and sun for your
  grid cell, from the Open-Meteo API.
- **Convert it to heat stress.** The Liljegren method turns those into WBGT,
  the wet-bulb globe temperature, one number for how hard it is for the body
  to cool itself.
- **Plan the day.** A solver chooses the hour-by-hour work rate that delivers
  the required hours at the lowest peak retained heat load.
- **Explain it.** The assistant writes the plan in plain language. Every
  number in it comes from the solver, not the model.

### Section 5 — What is proven, what is not

- **Headline:** What we can show, and what we cannot yet.
- **Proven, in simulation:** Over 236 held-out days of real past weather, the
  scheduler lowered the mean peak heat load by 14 percent and the p90 tail by
  16 to 20 percent, with no drop in hours worked.
- **Proven, and current:** In a forecast check for Doha, ECMWF's models place
  the 32.1 C stop-work hours well. NOAA's GFS runs about 0.7 C cold on WBGT
  and misses roughly 40 percent of those hours at every lead.
- **Not proven:** The individual-worker sensing work runs on synthetic
  physiology and has not been tested on people. It is not part of this
  product.
- Links: technical report, results ledger.

### Section 6 — Close

- **Headline:** Try it on a real day.
- **First sentence:** Open the planner, describe a shift the way you would to
  a colleague, and read the plan back.
- Primary action `Open the planner`. Links: report, ledger, source, contact.

Footer on every section: Open-Meteo CC BY 4.0 attribution, MIT licence, a line
that this is decision support and screening, not medical advice.

---

## 4. Chat app component tree (`/app`)

```
app/app/page.tsx  (server: renders the shell + suggested prompts, no data fetch)
  <ChatApp>                         'use client' — owns the message thread + SSE
    <AppHeader>                     wordmark, ThemeToggle, GlossaryHint,
                                    AssumptionsSheet trigger, "raw data" pref
    <ThreadScroll aria-live="polite">
      <SuggestedPrompts>            chips, shown only when the thread is empty;
                                    written as a site manager would type
      thread.map(turn =>
        <UserMessage>              plain bubble, mono for any figures the user typed
        <AssistantTurn>
          <ThinkingIndicator>      while status frames arrive (parsing / forecasting / …)
          <StreamedText>           append-on-arrival, 120 ms fade per chunk;
                                   <Term> wraps glossary words inline
          <ClarificationCard>      one question; quick-reply chips for the
                                   missing field where the choice is small
                                   (workload, acclimatised)
          <ArtifactCard expandable>
            <DayChart>             D3 scales + SVG: WBGT curve over the ramp,
                                   32.1 C rule, plan vs calendar-ban hour
                                   blocks, hover + arrow-key hour navigation,
                                   <desc> + <figcaption> text alternative
            <ComparisonStrip>      mono count-ups: peak load, p90 tail, stop
                                   hours, hours delivered — plan vs ban, with
                                   the reduction and "same hours worked"
            <ExpandButton> -> <ArtifactModal>   full-screen, focus-trapped
            <details><RawHourlyTable></details>
            <ArtifactFootnote>     forecast source, lead, CC-BY
      )
    <Composer>                     textarea; Enter sends, Shift+Enter newline;
                                   disabled while a stream is open; Stop button
    <GlossaryProvider>             context; <Term> renders a Radix Popover with
                                   one plain sentence (WBGT, acclimatised, work
                                   fraction, retained load, p90 tail, forecast
                                   lead)
    <AssumptionsSheet>             Radix Dialog, reachable from the header on
                                   every screen: single-point forecast,
                                   screening model on published tables,
                                   decision support not medical advice,
                                   forecast source and lead
```

SSE consumption: `fetch("/api/chat", { method: "POST", body })` ->
`res.body.getReader()` -> a small parser splits on `\n\n`, strips `data: `,
`JSON.parse`, and dispatches by `type` into the thread reducer. A `text` frame
appends to the current assistant turn's text; an `artifact` frame attaches the
plan; `clarification` renders the card; `error` shows a retry line; `done`
closes the turn and re-enables the composer.

Suggested prompts (first load):
- "Plan tomorrow for 12 people doing heavy work near Lusail. They arrived last
  week and we need 8 hours."
- "We have moderate work at the Industrial Area on Friday, crew is used to the
  heat, 6 hours."
- "What does the plan look like for light work in Doha today, 9 hours?"

---

## 5. Hero visual — approach and fallbacks

An abstract field of the day's heat, driven by real numbers, that reads like
an instrument rather than a screensaver.

- **What it shows.** A horizontal time axis for the working window (05:00 to
  19:00). A shader field whose vertical structure is a set of isotherm bands;
  the bands crowd and shift toward the hot colours where the day's WBGT curve
  rises, and a bright ridge line marks where the curve crosses 32.1 C. The
  curve comes from `/api/plan` for Doha today, fetched server-side and passed
  in as a `Float32` array uniform (or a 1 x 24 data texture). Slow drift only;
  no particles, no bloom.
- **Renderer.** React Three Fiber. `WebGPURenderer` from `three/webgpu`, which
  falls back to a WebGL2 backend on its own when WebGPU is absent. One
  material written in TSL so the same node graph runs on both. `drei` for the
  full-screen quad and viewport helpers.
- **Progressive load.**
  1. First paint: a static poster (a pre-rendered PNG of the field for a
     typical Doha day, plus a CSS radial wash as its own fallback) with the
     headline on top. No 3D code in the initial bundle.
  2. After `window` `load` and one `requestIdleCallback`: dynamic-import
     `<HeroCanvas>` (code-split), mount it under the poster, cross-fade in
     once the first frame renders.
  3. `IntersectionObserver`: stop the RAF loop when the hero leaves the
     viewport, resume on return.
  4. `prefers-reduced-motion: reduce` or `navigator.connection.saveData`:
     never mount the canvas; the poster is the hero.
  5. Battery: `navigator.getBattery()` where available; if not charging and
     level < 0.2, keep the poster.
  6. `devicePixelRatio` capped at 1.5. Canvas capped at 1600 px wide. Frame
     loop capped at 60 fps and throttled to 30 on coarse-pointer devices.
- **Bundle.** `three` + R3F + drei are code-split into the hero chunk, loaded
  after first paint, and never on `/app`. Target: the landing route's initial
  JS stays small enough for Lighthouse mobile performance >= 90 with the
  poster; the shader is a post-load enhancement that does GPU work, not main-
  thread work.
- **Accessibility.** The canvas has `role="img"` and an `aria-label`
  describing the day in one sentence with the peak WBGT figure (from the same
  API data). It is not focusable and carries no interaction; the scrubbable
  version of the chart lives in section 3.

---

## 6. Build order (small, scoped commits)

1. `api/`: `plan_with_sched` helper, `api/ratelimit.py`, `api/chat.py`,
   `POST /api/chat` in `main.py`, `ChatRequest` schema.
2. `tests/test_api_chat.py`.
3. `web/`: scaffold rebuild, tokens (`globals.css`), `tailwind.config.ts`,
   Geist fonts, theme toggle, `DESIGN.md`.
4. Landing sections 1 and 4-6 (static), copy in place.
5. The hero visual (poster first, then the R3F/TSL canvas + all fallbacks).
6. Landing sections 2-3 (animated diagrams, the scrub chart, live `/api/plan`).
7. The chat app: thread, SSE client, composer, suggested prompts,
   clarification card, glossary, assumptions sheet.
8. The artifact: `DayChart`, `ComparisonStrip`, expand modal, raw table.
9. States and polish: reduced-motion and Save-Data paths, keyboard, aria,
   metadata, OG image from the real day chart.
10. Deploy config (`vercel.json`, env), `web/README.md`, README "Live demo"
    update, `docs/results_ledger.md` one-liner, the written summary.

## 7. Deliverables

- `api/` with `POST /api/chat` (streaming) and its tests.
- `web/` rebuilt: landing page, chat app at `/app`, animated D3 artifacts,
  both themes, Vercel-deployable.
- `web/DESIGN.md`, `web/README.md`.
- `LICENSE` (MIT, already present), README "Live demo" section, ledger line.
- A short plain-language written summary: what the site shows, what it leaves
  out and why, the deploy URLs, the Lighthouse scores.
