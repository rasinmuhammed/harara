# Plan: worker time as a constraint in the scheduler

Status: design, pre-implementation. Written before any change to `src/scheduler.py`
per the task brief. Covers the exact objective and constraint set, the outer
search and its size, every new knob with a default and a one-line justification,
the new summary fields, and the revised results table.

## 1. The defect being corrected

`schedule_cvar` minimises the CVaR of peak retained heat load at a fixed
delivered work total, with `0 <= w_h <= allowed_h` the only shape constraint.
Span, continuity and time-on-site are free. On a hot day the optimiser therefore
buys a lower peak by thinning work into a wide, fragmented plateau: for a
moderate 8 hour request it works 05:00-08:00 full, holds 09:00-17:00 near
0.30-0.38, and finishes 18:00 full. That is 14 hours on site for 8 worked, with
a long shallow midday hole.

For a bussed-in accommodation worker on-site rest is not rest. It extends the
commute-bracketed day, keeps the worker in ambient heat, and fragments recovery.
The calendar rule (17/2021), for all its coarseness, keeps the crew to two
blocks around a single clean 10:00-15:30 off-site break. The optimiser must not
score better by being worse for the worker on the axes the worker feels: hours
on site, hours resting in the heat, number of pieces the day is broken into.

Correction, not re-framing: after the change the study is re-run and the honest
headline is reported, whatever it is. If constraining the optimiser closes most
of the gap to the calendar rule, or the plain earlier-start fixed block matches
it, that is the result.

## 2. New objective and constraint set

The CVaR LP is kept. It is now solved **inside an outer search over contiguous
on-site windows**. No MILP, no integer variables in the solver.

### 2.1 Outer problem

Let the working grid be hours `h = 0 .. H-1` (local 05:00 onward, `H = 14` in
the API, `H = 15` in the study). An on-site window is a contiguous index range
`[t_in, t_out]`, `0 <= t_in <= t_out <= H-1`. Define

```
span_hours(window)        = t_out - t_in + 1
onsite_rest_hours(window) = span_hours - sum_h w_h        (>= 0; work total ~ w_req)
```

Enumerate every window with

```
ceil(w_req) <= span_hours <= span_cap
sum_h ( allowed[h] and t_in <= h <= t_out ) >= w_req      (can physically deliver)
```

For each surviving window solve the inner LP (2.2) and score it

```
outer_score(window) = lp_objective_with_penalties            # 2.2, the LP's own optimum
                    + lambda_rest * onsite_rest_hours(window) # residual heat exposure of on-site rest
```

Then apply the post-solve shape filters (2.3). Among windows that pass, pick the
minimum `outer_score`; break ties toward the smaller `t_in`, then the smaller
`t_out` (earlier and tighter). If no window passes the shape filters, return the
earlier-start reference schedule `w_ref` (2.4) unchanged, with `status =
"ref_fallback"`.

`lambda_rest * onsite_rest_hours` is the only place span enters the score: with
delivered work pinned near `w_req` across feasible windows it is monotone in
span, so it prices each extra on-site hour as the "mild residual exposure" of
resting in the heat rather than off site. It is deliberately light (2.5): the
total-variation and deviation penalties in the LP do most of the work of pulling
the plan toward a compact early block; `lambda_rest` only settles near-ties
toward the shorter day. Physics (`hourly_load`, `_retention_matrix`, `phi`,
`wbgt_ref`, `p`) is untouched.

### 2.2 Inner LP (per window)

Extends the current LP with two linear penalty groups. With the new weights at
their zero defaults and no window/reference passed, it is byte-identical to
today's `schedule_cvar` (the extra variables and rows are only built when their
weight is active), so existing tests are unaffected.

Variables

| block | size | meaning |
|---|---|---|
| `w_h`   | H   | hourly work fraction |
| `m_s`   | S   | per-scenario peak retained load |
| `t`     | 1   | CVaR value-at-risk level (free) |
| `z_s`   | S   | per-scenario tail excess |
| `u_h`   | H-1 | total-variation aux, `u_h >= |w_h - w_{h-1}|` (built only if `lambda_tv > 0`) |
| `d_h`   | H   | deviation aux, `d_h >= |w_h - w_ref_h|` (built only if `lambda_dev > 0` and `w_ref` given) |

Objective (minimise)

```
t + 1/((1-beta) S) * sum_s z_s
  + lambda_tv  * sum_h u_h
  + lambda_dev * sum_h d_h
```

Constraints

```
sum_k A[h,k] * loads[s,k] * w_k  -  m_s   <= 0        for all s, h   (retained-load peak)
m_s - t - z_s                            <= 0        for all s       (CVaR tail)
- sum_h w_h                              <= -w_req                   (deliver the work)
 (w_h - w_{h-1}) - u_h                   <= 0        for h = 1..H-1   (TV, + side)
-(w_h - w_{h-1}) - u_h                   <= 0        for h = 1..H-1   (TV, - side)
 w_h - d_h                               <= w_ref_h  for h = 0..H-1   (deviation, + side)
-w_h - d_h                               <= -w_ref_h for h = 0..H-1   (deviation, - side)
```

Bounds

```
0 <= w_h <= 1   if allowed[h] and t_in <= h <= t_out
0 <= w_h <= 0   otherwise                              (off-site / banned / over-threshold)
m_s, z_s, u_h, d_h >= 0 ;  t free
```

Work outside `[t_in, t_out]` is forced to zero by the upper bound, so off-site
hours cost nothing and carry no load. `A` is the existing `_retention_matrix`;
`loads` is the existing `hourly_load`. Solver: SciPy/HiGHS `linprog`, same as
now. On `linprog` failure the existing greedy fallback is used for that window
and the window is still scored.

### 2.3 Post-solve shape filters (outer, not LP constraints)

For the LP's returned `w`, with `block_eps = 0.05`:

- **blocks**: a block is a maximal run of consecutive hours with `w_h > block_eps`.
  `n_blocks = number of such runs`. Discard the window if `n_blocks > max_work_blocks`.
- **minimum block size**: for each block, `sum(w_h over the block) >= min_block_hours`.
  Discard the window if any block is smaller. This removes scattered single-hour
  slivers of work.

Discarding is done in the outer loop; the solver never sees these rules, so no
integrality is introduced.

### 2.4 `w_ref`: the earlier-start fixed block

`policy_earlier_start(wbgt, allowed, w_req, hard_stop=32.1)` -> `w (H,)`:
start at the first allowed hour, place `w_h = min(1, remaining)` in each
successive hour that is `allowed` and has `wbgt_h <= hard_stop`, decrementing
`remaining`, until the work is delivered or the grid ends. Result is one compact
early block that pauses only for hours over 32.1 C. This is both the stability
reference for the deviation penalty and a **named baseline policy** in its own
right, reported alongside the calendar rule.

### 2.5 New knobs and defaults

| knob | default | one-line justification |
|---|---|---|
| `span_cap_h` | `required_work_hours + rest_allowance_h` | hard ceiling on on-site hours; ties time on site to work owed, not to the daylight window |
| `rest_allowance_h` | `2.0` | one normal meal break plus short reliefs; enough slack to shift work off the peak without a stretched day |
| `max_work_blocks` | `2` | at most a morning and an afternoon block, matching how the calendar rule already splits the day; more pieces fragment recovery |
| `min_block_hours` | `1.5` | a work block shorter than this is not worth mobilising the crew for; kills sliver hours the plateau solution produces |
| `lambda_tv` | `0.15` | prices total up-and-down movement of `w`; ~0.15 retained-load units per unit of variation, visible against a peak of 6-8 without overriding safety |
| `lambda_dev` | `0.05` | mild pull toward the compact earlier-start block; a stabiliser and tie-breaker, not a driver |
| `lambda_rest` | `0.25` | residual exposure of resting in the heat on site; 2 h of on-site rest ~ 0.5 retained-load units, enough to prefer the tighter window, not enough to force a shortfall |
| `block_eps` | `0.05` | work fractions at or below this are treated as rest for block detection (3 min/h is not a block) |

All defaults are module constants so the study, the tool layer and the API share
them. Seeds unchanged (`RNG = np.random.default_rng(11)` in the study).

## 3. Outer search space and its size

Windows of length `L` in an `H`-hour grid: `H - L + 1` of them. With
`ceil(w_req) <= L <= min(span_cap, H)`:

**API, 14-hour day (`H = 14`), `w_req = 8`, `rest_allowance_h = 2` -> `span_cap = 10`:**

| L | windows |
|---|---|
| 8  | 7 |
| 9  | 6 |
| 10 | 5 |
| **total** | **18 inner LP solves** |

Point-forecast path, so `S = 1`: each LP is ~ `3H - 1 + 2S = 43` variables and
~ `S*H + S + 1 + 2(H-1) + 2H = 71` rows. 18 trivial solves, milliseconds.

Without the "can physically deliver" filter the loose upper bound is
`sum_{L=1}^{10} (14 - L + 1) = 95` windows; the filter and `L >= ceil(w_req)`
cut it to 18.

**Study, 15-hour day (`H = 15`), `w_req = 9`, `span_cap = 11`:** L in {9, 10, 11}
-> `7 + 6 + 5 = 18` windows. Stochastic path `S = K_SCEN = 120`: each LP ~ `284`
variables, ~ `1979` rows; 18 solves per planned day. Walk-forward is ~130 test
days x 3 leads x 18 ~ 7000 HiGHS LPs for the optimiser column; expected a few
minutes, noted in the script header.

## 4. New / changed public surface in `src/scheduler.py`

- `schedule_cvar(...)` gains optional `window=(t_in, t_out) | None`,
  `lambda_tv=0.0`, `lambda_dev=0.0`, `w_ref=None`. Defaults reproduce today's LP
  exactly (guarded row construction).
- `@dataclass WindowedScheduleResult`: `w, status, obj, t_in, t_out, span_hours,
  onsite_rest_hours, n_blocks, w_ref`.
- `schedule_windowed(wbgt_scenarios, allowed, w_req, *, wbgt_point, local_hour=None,
  beta=BETA, phi, wbgt_ref, p, span_cap_h=None, rest_allowance_h=REST_ALLOWANCE_H,
  max_work_blocks=MAX_WORK_BLOCKS, min_block_hours=MIN_BLOCK_HOURS,
  lambda_tv=LAMBDA_TV, lambda_dev=LAMBDA_DEV, lambda_rest=LAMBDA_REST,
  w_ref=None) -> WindowedScheduleResult`. Builds `w_ref` from
  `policy_earlier_start(wbgt_point, ...)` if not supplied, runs the outer search.
- `policy_windowed(scenarios, allowed, w_req, *, wbgt_point, **kw) -> np.ndarray`
  thin wrapper returning `.w`, for the study.
- `policy_earlier_start(wbgt, allowed, w_req, hard_stop=32.1) -> np.ndarray`.
- `cumulative_exposure(w, wbgt, wbgt_ref=WBGT_REF_DEFAULT) -> float`
  `= sum_h w_h * max(0, wbgt_h - wbgt_ref)`; time-integrated heat dose over
  worked time.
- Module constants: `REST_ALLOWANCE_H = 2.0`, `MAX_WORK_BLOCKS = 2`,
  `MIN_BLOCK_HOURS = 1.5`, `LAMBDA_TV = 0.15`, `LAMBDA_DEV = 0.05`,
  `LAMBDA_REST = 0.25`, `BLOCK_EPS = 0.05`.

`policy_cvar`, `policy_deterministic`, `policy_clairvoyant`, `policy_calendar`,
`policy_reactive` are unchanged.

## 5. Evaluation (`scripts/scheduler_study.py`)

Policies scored: `calendar`, `reactive`, `earlier_start` (new),
`optimiser` (= `policy_windowed` on the analog/GEFS scenarios; replaces the bare
`stochastic` column in the headline), `clairvoyant` (= `policy_windowed` on
realised WBGT). The `deterministic` vs `stochastic` split is kept only as a
secondary paired line.

Per policy, per lead, over the test days:

| column | definition |
|---|---|
| mean peak load | `mean_d realized_strain(w, truth)` |
| p90 peak load | `p90_d realized_strain` |
| mean heat dose | `mean_d cumulative_exposure(w, truth)` |
| mean span h | `mean_d (last worked hour - first worked hour + 1)` |
| mean on-site rest h | `mean_d (span - sum w)` |
| mean work blocks | `mean_d n_blocks(w)` |
| work delivered / shortfall | `mean sum w` / `mean max(0, w_req - sum w)` |

**Hard guarantee check.** For every scored day: `span_optimiser <=
span_calendar`, `onsite_rest_optimiser <= onsite_rest_calendar`,
`blocks_optimiser <= blocks_calendar`. Count and list any violation. Expected
zero by construction (`span_cap = 11 <= calendar's ~14`, `blocks <= 2 <=
calendar's 2`, `rest <= 2 <= calendar's ~5.5`). The check is a real assertion in
the script, not a comment.

**Headline.** Re-computed and reported plainly:
- optimiser mean-peak reduction vs calendar, with block-bootstrap interval;
- optimiser mean-peak reduction vs earlier_start, with interval;
- whether earlier_start alone already captures most of the calendar gap;
- heat-dose and span/rest/block comparison in the same table.

No number is carried over from the current report unshown. If the 14 percent
shrinks, the new figure stands.

## 6. New summary fields (API)

`PlanRequest` (all optional, back-compatible):

| field | type | default |
|---|---|---|
| `max_span_hours` | `float \| None` | `None` (-> `required_work_hours + rest_allowance_hours`) |
| `rest_allowance_hours` | `float` | `2.0` |
| `earlier_start` | `bool` | `true` |

`PlanSummary` gains:

| field | meaning |
|---|---|
| `span_hours_plan` | on-site hours the plan implies (`t_out - t_in + 1`) |
| `span_hours_calendar` | on-site hours the calendar rule implies |
| `onsite_rest_hours_plan` | plan span minus delivered work |
| `onsite_rest_hours_calendar` | calendar span minus delivered work |
| `cumulative_exposure_plan` | `cumulative_exposure(w_plan, wbgt)` |
| `cumulative_exposure_calendar` | `cumulative_exposure(w_cal, wbgt)` |
| `work_blocks_plan` | number of work blocks in the plan |
| `work_blocks_calendar` | number of work blocks in the calendar rule |
| `earlier_start_fixed` | sub-object `{ peak, tail, span_hours }` for `policy_earlier_start` |

`HourRow` gains `on_site: bool` (`t_in <= hour_index <= t_out`),
`earlier_start_work_fraction: float`, `retained_load_earlier: float` so the web
chart can draw the earlier-start line and shade the window.

`RunSchedulerResponse` (tool layer) gains `plan_window` (`[t_in, t_out]` local
hour strings), `plan_span_hours`, `plan_work_blocks`, `onsite_rest_hours`,
`earlier_start_peak_strain`, `earlier_start_tail_strain`,
`earlier_start_span_hours`, `cumulative_exposure_plan`,
`cumulative_exposure_calendar`.

`api/README.md`: document the three request fields, the new summary block, the
`on_site` per-hour flag, and that the optimiser is now span-capped and
block-limited so it can never keep a crew on site longer, resting in the heat
longer, or in more pieces than the calendar rule.

## 7. Revised results table (technical report S8)

```
Walk-forward over <N> held-out days, all policies delivering the same <w_req>
work-hours with no shortfall:

| Policy            | Peak load | p90  | Heat dose | On-site span h | On-site rest h | Work blocks |
|-------------------|-----------|------|-----------|----------------|----------------|-------------|
| Calendar 17/2021  |   x.xx    | x.xx |   xx.x    |     xx.x        |      x.x        |     2.0     |
| Earlier-start fix |   x.xx    | x.xx |   xx.x    |     x.x         |      x.x        |     1.0     |
| Reactive          |   x.xx    | x.xx |   xx.x    |     xx.x        |      x.x        |     x.x     |
| Optimiser (capped)|   x.xx    | x.xx |   xx.x    |     x.x         |      x.x        |     x.x     |
| Clairvoyant       |   x.xx    | x.xx |   xx.x    |     x.x         |      x.x        |     x.x     |

Guarantee: on every scored day the optimiser's on-site span, on-site rest hours
and work-block count are each <= the calendar rule's. Violations: 0 / <N>.

Headline: <optimiser peak reduction vs calendar> [interval], and
<optimiser peak reduction vs earlier-start fixed> [interval]. <one sentence on
whether the earlier-start block alone already closes the gap>.
```

S12 limitations gains: the constrained scheduler still does not model commute
time, heat in the accommodation before and after the shift, split-shift fatigue,
or whether an earlier start or a night shift is operationally feasible at a given
site.

`results_ledger.md` new row (after 26):

> Does the optimiser's advantage over the calendar rule survive once worker time
> on site, day fragmentation and cumulative heat dose are constrained? Method:
> outer search over on-site windows with the CVaR LP inner solve, TV and
> deviation penalties, `span_cap = w_req + 2`, `max_work_blocks = 2`; walk-forward
> vs realised WBGT; block-bootstrap intervals; earlier-start fixed block added as
> a baseline. Result: <peak reduction vs calendar and vs earlier-start with
> intervals; heat-dose and span deltas; violation count>. Verdict: <supported /
> shrunk / matched by the fixed block>. Consequence: <the daily layer is a
> bounded improvement that is never worse for the worker than the fixed rule;
> the structural choices carry most of the gain>.

Plus a short framing paragraph: the largest safety gains are structural (which
hours are workable at all, acclimatisation, an earlier start, shelter and
hydration); the daily optimiser is a bounded refinement on top, and after this
change it is constrained to be never worse for the worker than the rule it is
compared against.

## 8. Web (`web/components/artifact/*`)

- `ComparisonStrip`: two new cells, "Time on site" (`span_hours_plan` vs
  `span_hours_calendar`) and "Heat dose" (`cumulative_exposure_plan` vs
  `_calendar`), same 4-up grid style.
- `ArtifactCard` headline: append one plain sentence, no em dash, e.g. "The crew
  is on site N hours, no longer than the M the fixed rule would keep them, and
  the day stays in K work blocks."
- `DayChart`: shade `[t_in, t_out]` as the on-site window; dim the hour labels
  outside it and label them "off site"; add an `earlier start` line to the
  policy toggle beside "fixed rule" and "stop when hot", drawn from
  `earlier_start_work_fraction`.
- `lib/types.ts`: add the new `HourRow` and `PlanSummary` fields.
- Copy keeps 17/2021 as the enforceable baseline the plan works within, not "the
  rule that misses danger".

## 9. Commit order

1. `src/scheduler.py` core + `tests/test_scheduler.py` cases for: window
   enumeration size, `span_cap` respected, `max_work_blocks`/`min_block_hours`
   discard, `policy_earlier_start` shape and 32.1 pause, `cumulative_exposure`
   value, `schedule_cvar` unchanged when new args absent, `w_ref` fallback.
2. `scripts/scheduler_study.py` + honest re-run, guarantee assertion.
3. `api/planning.py`, `api/schemas.py`, `src/agent/schedule_service.py`,
   `src/agent/schemas.py`, `api/README.md` + tests for every new guarantee.
4. `web/components/artifact/*` + `lib/types.ts`.
5. `docs/technical_report.md` S8/S12, `docs/results_ledger.md`, this file's
   framing paragraph.

Discipline: physics numbers unchanged; fixed seeds; all existing tests stay
green; small scoped commits.
