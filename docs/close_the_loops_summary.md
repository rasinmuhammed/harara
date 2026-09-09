# Closing the three open loops: what changed

Plain-language summary of the work on ledger rows 12c/12d/18 (Loop A),
16/17 (Loop B), and 20/21 (Loop C).

## Loop A: GEFS backfill, calibration, reliability, stochastic scheduling

**Status: in progress.** The 2000-2019 May-September GEFS v12 reforecast
backfill was started and is running. On the development network path it moves at
about 0.2 MB/s single-connection, so the full 20 years take roughly 15 hours; a
second worker was added for the older years to roughly halve that. The fetch is
resumable (one Parquet file per year, an init day counts as done only when all
five members are present), so it continues cleanly across restarts and
`run_all.sh` re-runs.

What is verified now:

- `tests/test_gefs_alignment.py` passes over the archive as it grows: every
  fetched lead lands on the intended local hour and forecast day.
- The calibration, reliability and stochastic-scheduling chain runs end to end
  on the years present. With only the first two to three years it is not yet a
  multi-year result: EMOS lifts CRPS over the raw ensemble (CRPSS about +0.15 to
  +0.17 at forecast days 1 to 3) and the raw ensemble is under-dispersed
  (spread-to-RMSE about 0.46 to 0.51), consistent with the single-year figure
  already in the report, but with only one scored year the intervals are not
  meaningful.

What is still open: the walk-forward EMOS scores, the reliability-study PR-AUC,
and the stochastic-vs-deterministic scheduling verdict all need the backfill to
reach enough years for a real leave-one-year-out. `run_all.sh` with
`GEFS_BACKFILL=1` completes the fetch and re-runs the chain; report sections 6.4
and 8 and ledger rows 12c/12d/18 are updated the moment those numbers exist.
Nothing in the current report conclusions depends on this loop: section 8's
finding that hedging did not help was made on analog scenarios, and the GEFS run
tests whether a genuine calibrated ensemble changes that.

## Loop B: external validation of the heat-strain filter on real physiology

**Status: done. One conclusion changed.**

Step 0 (data search) is written up in `docs/twin_external_data_memo.md`. Of the
candidate datasets with a gold-standard core-temperature reference, only PROSPIE
(Havenith et al., Loughborough, figshare `10.17028/rd.lboro.26076577`,
CC BY-NC 4.0) is openly downloadable: 40 subjects, 154 treadmill-in-chamber
trials, rectal probe, heart rate, 11-site skin temperature, 1-minute resolution.
Eggenberger 2018 and Falcone 2024 are "available on request" only.

`scripts/twin_external_validation.py` runs the particle filter on library
defaults (nothing fitted) against an ECTemp-class heart-rate-only Kalman filter
whose population curve is fit leave-one-subject-out. Result:

| Method | bias | RMSE | MAE | 95% CI coverage |
|---|---|---|---|---|
| ECTemp-class HR-only EKF | -0.45 C | 0.52 C | 0.48 C | - |
| Physics filter, HR + activity | +0.10 C | 0.54 C | 0.45 C | 42% |
| Physics filter, HR + activity + skin | +0.00 C | 0.41 C | 0.35 C | 36% |

The ordering claim from the synthetic study holds on real bodies: the physics
filter with a skin-temperature channel beats heart rate alone, RMSE 0.41 vs
0.52 C, with the bias removed and the limits of agreement halved. The skin
channel is what does it: with heart rate and activity only, the filter merely
matches the baseline.

Two things did not hold, and the report now says so. The synthetic 0.083 C MAE
does not transfer; on real bodies the best configuration is 0.35 C MAE, four
times worse. And the filter's credible intervals are badly calibrated out of
domain, covering the rectal temperature only 36 to 42 percent of the time
against a nominal 95. The point estimate is usable; the stated uncertainty is
not, and fixing that is a pilot task. The ledger's "about four times more
accurate than heart rate alone" line is replaced with the measured real-data
picture (row 30).

## Loop C: score the agent layer against a real model

**Status: done. The uncommitted work is committed. The safety invariant held.**

The dangling WIP in `eval/agent_eval.py`, `src/agent/brief.py` and
`src/agent/llm.py` was reviewed and kept: it hardens the eval harness (each
section runs independently; a refused briefing is recorded as the guard
working, not a crash), tightens the briefing guard (the model is no longer shown
rule threshold values, and the guard strips dates, times and identifiers before
scanning), and registers the K2 adapter. Three tests were added; the suite is
108 passing.

`eval/agent_eval.py --model k2` was run twice against K2-Horizon-375B at
temperature zero. Anthropic could not be scored (SDK and key absent from this
environment); the hardened harness records that as a per-section error rather
than failing. K2 on the IFM endpoint is not reproducible at temperature zero, so
the two runs are a range.

- Stable across both runs: every ambiguous request asked back (none guessed);
  parsed-field accuracy 1.0; banned-hour-window extraction P/R 1.0; every quote
  verbatim, so citation validity 1.0 and the store accepted only locatable
  values; every rule reference resolved.
- Variable: the stop-work-threshold and seasonal-window recall were 0.67 in one
  run and 1.0 in the other (one run did not return the 32.1 C value from the
  Qatar Decision 17 text); outcome exact-match 0.89 to 0.94; raw ungrounded-
  number rate 0.02 to 0.09.
- One consistent weakness: rest ratios came back at precision 0.57 in both runs
  (extra ratios from the ACGIH table that are not in the gold set).
- The safety invariant held on every run: the guard caught every injected
  foreign number, and the guarded briefing path either returned a fully grounded
  briefing or refused. No run produced a number that reached a caller without
  passing the guard.

Ledger rows 20, 21 and a new row 31 carry the real-model numbers; report
section 10 states the measured extraction quality and the failure modes, not
just the guard design.

## Did any report conclusion change?

- **Section 9 (heat-strain filter): yes.** The synthetic error magnitude is
  refuted on real data; the ordering claim (physics filter with skin beats
  heart rate alone) survives. Interval calibration is now a stated open problem.
- **Section 10 (language-model layer): strengthened, not reversed.** The
  fail-closed properties hold with a real model; extraction quality is now
  measured (and uneven) rather than assumed.
- **Sections 6 and 8 (GEFS): unchanged pending the backfill.** The chain runs;
  the multi-year numbers are not in yet.
