# Product site summary

Plain-language account of what was built, what it leaves out, and why.

## What the site shows

Three surfaces over the same deterministic scheduler.

**Landing page.** One scroll. It states what the product does in a sentence,
then explains the problem in three short beats with small diagrams: humid heat
is harder on the body than the thermometer number, Qatar's rule is a fixed
clock that ignores the forecast, and the dangerous hours move and often fall
outside the banned window. A scrubbable day chart, with numbers pulled live
from the API for Doha, shows the plan working the cool morning, easing through
the peak, and resuming late, at the same total hours as the calendar ban. Then
four plain steps, an honest panel on what is proven (the 14 percent peak and 16
to 20 percent tail reduction over 236 simulated days; the forecast check where
ECMWF places the stop-work hours and NOAA GFS misses about 40 percent of them)
and what is not (the individual-worker sensing work, which is synthetic and not
on the site), and a close.

**Chat app at `/app`.** You type a request the way you would tell a colleague,
for example "moderate work at the Industrial Area the day after tomorrow,
acclimatised crew, 6 work-hours". The assistant reads it, gets the forecast,
plans the day, and streams back a plain-language explanation with a result
artifact card in the thread. If a safety-relevant field is missing, the day,
the hours, how hard the work is, whether the crew is used to the heat, or
where, it asks one clear question instead of guessing. Domain terms in the
reply are underlined and explain themselves in one sentence on hover or tap.
An assumptions and limits panel is reachable from the header on every screen.

**Artifacts.** The day chart draws the forecast WBGT over a cool-to-hot colour
ramp with a hard break at the 32.1 C stop-work line, and beneath it the
optimiser plan and the calendar ban as hour blocks that carry the same total
work in different shapes. A strip of numbers, worst retained heat load, the p90
tail, stop hours, hours delivered, counts up on first paint and shows plan
against ban with the reduction called out. The card expands to full screen and
has the raw hourly table behind a disclosure. Everything is keyboard operable
and carries a text description of the colour encoding.

## The rule that holds everywhere

The language model never produces a number that reaches the user. It turns a
request into a validated call to the deterministic API (`get_forecast`,
`compute_wbgt`, `run_scheduler`), and it turns the API result into sentences.
The numeric guard in `src/agent/brief.py` scans any generated text and rejects
it if a figure is not present in the tool output. Offline, with no model key,
the assistant composes the explanation directly from the plan's own numbers, so
the site runs and demonstrates the full flow without a network.

## What it leaves out, and why

- **The individual digital twin.** It runs on synthetic physiology and has not
  been tested on people. Putting it on the site would imply a capability that
  no pilot supports. It is absent from the API and the site.
- **Accounts, login, saved history.** Not needed to show the decision, and
  they add privacy and security obligations to a demo.
- **A hard 32.1 C stop inside the optimiser.** The plan minimises retained heat
  load at equal output, following the walk-forward study. Hours where it still
  schedules work above 32.1 C are flagged on the chart and in the text; the
  operator applies Decision 17/2021's hard stop on top. This is stated in the
  assumptions panel and the artifact footnote.
- **Any claim the results ledger does not support.** The 14 percent figure is
  cited as a 236-day simulation on real past weather, and the live per-day
  figure is labelled as that day's.

## Deploy URLs

- Site (Vercel): _to be set after deploy_
- API (Render): _to be set after deploy_

`api/render.yaml` and `web/vercel.json` are in the repo; `api/README.md` and
`web/README.md` carry the steps. After the first site deploy, set the API's
`ALLOWED_ORIGINS` to the Vercel origin.

## Lighthouse

Local production build (`next start`), mobile profile, simulated throttling,
landing route with the hero shader present:

| category | score |
|---|---|
| Performance | 95 |
| Accessibility | 99 |
| Best practices | 100 |
| SEO | 100 |

CLS 0, LCP about 2.4 s, TBT 200 ms. Landing route initial JS 113 kB; `three`
is a separate chunk loaded after first paint. Deployed-URL scores to be
recorded once the site is on Vercel; the local build is representative.

## Tests

`tests/test_api_chat.py`: a clarification streams a question and no artifact; a
complete request streams text then an artifact whose numbers match a direct
plan call; a follow-up completes an earlier request while a vague one still
asks back; the endpoint rate-limits per IP. Full suite: 95 passing.

## Known limitation

The day chart on the landing page and inside the chat artifact scales its SVG
down on a phone rather than switching to a purpose-built vertical layout. It
stays legible and the raw hourly table is one tap away, but a stacked mobile
chart is the next improvement.
