# Pilot Protocol: Anticipatory Individual Heat-Strain Estimation for Outdoor Labour

Companion code: `src/thermoreg.py`, `src/heat_strain_filter.py`,
`scripts/digital_twin_demo.py`.

## 1. Objective and hypotheses

Objective: estimate, in real time and ahead of time, the heat strain of an
individual outdoor worker from low-cost wearable sensors and the local WBGT
forecast, and validate the estimate against ingestible core-temperature
capsules.

H1 (estimation). A particle filter with a physical process model, fusing heart
rate, accelerometry and a skin-temperature patch, estimates core temperature
with mean bias below 0.10 C and 95% limits of agreement within +/-0.35 C
against capsule temperature, better than a heart-rate-only Kalman filter
(ECTemp class), whose published limits of agreement are about +/-0.6 C.

H2 (anticipation). The filter's forward prediction, driven by the WBGT
forecast, detects "core temperature will exceed 38.5 C within 45 minutes" with
recall at least 0.85 at precision at least 0.5, with a median warning lead time
of at least 20 minutes.

H3 (sensor value). Removing the skin-temperature patch degrades the limits of
agreement by at least 0.15 C. Synthetic pre-check: MAE 0.19 to 0.08 C, coverage
77% to 92%.

H4 (operational value). Substituting the individual risk signal for a
population WBGT threshold in the work/rest scheduler (`src/scheduler.py`)
reduces expected high-strain minutes at equal output, under a chance constraint
on core temperature exceeding 38.5 C.

Hypotheses, endpoints and the analysis plan (section 6) are fixed before data
collection. Deviations are reported.

## 2. Prior art and gap

| Line of work | What exists | Gap for this problem |
|---|---|---|
| USARIEM ECTemp (Buller et al., 2013, 2018) | Kalman filter, core temperature from heart rate alone, random-walk process; fielded in military wearables | Workload-confounded; no environmental forcing; not anticipatory; validated on soldiers |
| Rational and multi-node models (ISO 7933 PHS, Fiala, JOS-3, SCENARIO) | Detailed forward simulators | Run open-loop from assumed inputs; not assimilated to a person's live sensors |
| Wearable "core temperature" products | Proprietary regressions on heart rate and skin temperature | Opaque; no peer-reviewed field validation for this population; no forecast coupling |
| Occupational heat epidemiology (Kjellström and colleagues; Qatar cohort studies) | Population exposure-response, WBGT rules | Environmental index only; no individual state; no anticipation |

No published system performs model-based sequential estimation of an individual
worker's core temperature that is forced by the measured environment,
self-calibrates to the person, and is propagated under the WBGT forecast to
yield a calibrated anticipatory probability, validated against capsule
temperature in a migrant outdoor-labour cohort.

## 3. Method (as implemented)

State: `(T_core, T_skin, m_scale)`, where `m_scale` is a slowly drifting
per-person multiplier on the accelerometry-derived metabolic rate, absorbing
individual efficiency and sensor calibration error.

Process model: the two-node thermoregulation model (`src/thermoreg.py`,
vectorised as `dynamics_vec`): metabolic heat production, respiratory loss,
operative-temperature sensible exchange with clothing resistance,
humidity-limited evaporative cooling with a sweat controller, a skin blood-flow
controller, and a variable core/skin mass split. Forced by measured air
temperature, RH, wind and mean radiant temperature, and by `m_scale` times the
estimated metabolic rate.

Observations: heart rate always, a skin-temperature patch in the primary
configuration, an optional second heart-rate source. Gaussian likelihood on
the innovations.

Filter: a bootstrap particle filter with 500 particles, systematic resampling
when the effective sample size falls below N/2, and post-resample kernel
roughening (Silverman bandwidth). The roughening keeps the credible interval
honest; synthetic coverage improves from 11% to 92% once tuned.

Anticipation: at time t, subsample the particle cloud; for each member of a
WBGT forecast ensemble over the next H minutes, integrate the process model
forward with per-step process noise; report the probability of core temperature
exceeding 38.5 C within H, the time-to-threshold distribution, and predictive
quantiles. In the pilot the ensemble comes from `src/forecast_uncertainty.py`,
and at scale from the GEFS v12 reforecast.

Coupling: the anticipatory probability enters `src/scheduler.py` as a per-crew
chance constraint in place of the population WBGT threshold.

## 4. Synthetic proof of concept (completed)

`scripts/digital_twin_demo.py`, 30 real Doha summer days, the two-node model as
synthetic ground truth, realistic sensor noise (heart rate +/-4 bpm with 3%
dropout, accelerometry metabolic estimate lognormal sigma 0.18):

- Estimation: heart-rate-only ECTemp MAE 0.36 C; physics filter with heart rate
  and activity 0.19 C (coverage 77%); with a skin patch 0.083 C (coverage 92%).
- Anticipation: recall 0.91 at probability 0.35; forward probability rises from
  0.34 (more than 90 minutes out) to 0.54 (45 to 60 minutes) to 0.86 (0 to 15
  minutes); about 45 minutes of median warning at probability 0.5. Probability
  calibration is over-confident on synthetic data and is a pilot objective.

These numbers are indicative only; the process and target models share a
family, and the pilot quantifies the model-mismatch gap.

## 5. Pilot study design

Design: a prospective observational agreement study with an embedded crossover
of task intensity and cooling conditions.

Population: migrant outdoor workers (construction and last-mile delivery) in
Qatar, aged 18 to 55, with no contraindication to an ingestible capsule (no
known gastrointestinal stricture, not pregnant, no MRI during transit). Target
30 participants, each over at least 4 work sessions spanning the
acclimatisation window (days 1 to 3, 7 to 10, and 14 onward), plus a subset of
controlled heat-chamber sessions if a partner facility is available.

Sample size: for a Bland-Altman limits-of-agreement study, about 30
participants times at least 4 sessions times at least 60 paired minute-samples
per session gives more than 7000 paired observations and a 95% interval
half-width on the limits of agreement of about 0.05 C (Bland-Altman 1999,
allowing for within-subject repeats through a mixed model). Power for H1
against an ECTemp limits of agreement of +/-0.6 C is above 0.9.

Instrumentation:

| Signal | Device class | Rate | Role |
|---|---|---|---|
| Core temperature | Ingestible telemetric capsule (e-Celsius / CorTemp class) | 1/min | Ground truth |
| Heart rate | Chest strap (ECG) and optical watch (redundant) | 1 Hz to 1/min | Filter input |
| Skin temperature | Adhesive patch, upper arm or scapula | 1/min | Filter input |
| Activity | Wrist and hip tri-axial accelerometer | 25 to 50 Hz to 1/min metabolic estimate | Filter input |
| Micro-environment | Worn WBGT logger and fixed site station | 1/min | Measured forcing and forecast verification |
| Context | Shift log, PPE, fluid intake, shade use, self-reported strain (RPE, thermal sensation) | Per event or 30 min | Covariates |

Session protocol: the capsule is ingested at least 5 hours before the session.
A 15-minute seated baseline in shade precedes normal supervised work with the
crew. A standardised 20-minute moderate-load block and a 10-minute shaded
recovery block are inserted once per session for a controlled input. The
session ends at shift end or on any stop criterion (section 8). All streams are
timestamped to a common NTP-synced clock; alignment is checked on the recovery
block's heart-rate inflection.

## 6. Statistical analysis plan

Primary endpoint (H1): mixed-effects Bland-Altman of estimate minus capsule
over all paired minute-samples, with a random intercept per participant and per
session. Report mean bias, 95% limits of agreement, and their intervals. Pass:
absolute bias below 0.10 C and limits of agreement within +/-0.35 C.

Secondary endpoints:

- Anticipation (H2): for each minute with a valid forward run, the label is
  whether core temperature crosses 38.5 C in the following 45 minutes. Report
  the precision-recall curve, PR-AUC, recall at precision 0.5, and the
  warning-lead-time distribution, with the alarm threshold chosen on the
  training fold. Report a reliability diagram, Brier score and Spiegelhalter's
  z for probability calibration.
- Sensor ablation (H3): re-run the filter offline with the sensor subsets {HR},
  {HR, accelerometry}, {HR, accelerometry, skin}, {HR, skin}; compare limits of
  agreement with a paired test clustered by participant.
- Model mismatch: decompose the estimate error into filter/observation error
  and process-model error by also running the filter with the capsule
  temperature as a held-out pseudo-observation.
- Acclimatisation: fit the `m_scale` and sweat-gain trajectories against
  days-in-heat and compare with the 9 to 14 day time course.
- Operational (H4): simulation only. Feed per-worker anticipatory probabilities
  into `scheduler_study.py` and compare high-strain minutes and output against
  the population-threshold policy, with block-bootstrap intervals.

Validation discipline: per-participant leave-one-out for all tuned quantities
(process-noise scale, roughening bandwidth, likelihood standard deviations); no
parameter is tuned on the test participant. Forecast-ensemble parameters are
fit only on data preceding each scored day.

Missing data: heart-rate dropouts are carried forward for up to 3 minutes,
after which the step runs on the process model alone with inflated variance.
Capsule gaps longer than 2 minutes are excluded from the paired analysis.
Sessions with fewer than 30 minutes of paired data are excluded and reported.

## 7. Ethics and governance

- Approval: institutional review board and national research ethics committee
  approval before enrolment. The study is registered.
- Consent: written informed consent in the participant's first language (Hindi,
  Nepali, Bengali, Malayalam, Tagalog, Urdu as needed), delivered by an
  independent facilitator rather than the employer. Participation is voluntary,
  work time is compensated, and non-participation carries no consequence.
- Data governance: individual physiological data and the derived risk signal
  are not shared with the employer at the individual level. The employer
  receives only aggregate, de-identified crew-level summaries and the schedule
  recommendation. Participants can withdraw and have their data deleted at any
  time. Data minimisation applies; data is encrypted at rest and in transit;
  access is logged.
- Non-punitive use: a contractual commitment that the signal is used only to
  protect the worker (rest, cooling, rotation) and never for productivity
  monitoring, discipline or pay.
- Safety oversight: an independent occupational-health physician reviews all
  stop events and adverse events weekly and can halt the study.
- Capsule safety: screening per the manufacturer's instructions for use; single
  use; no MRI during transit; retrieval is not required.

## 8. Real-time stop criteria

Any of the following triggers immediate rest and a medical check: capsule core
temperature at or above 38.7 C; heart rate at or above 90% of the
age-predicted maximum for more than 3 minutes at rest; the participant reports
dizziness, nausea, confusion, cramp, or cessation of sweating; supervisor or
medic judgement. The estimate is never used to withhold rest, only to prompt it
earlier.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Recruitment and retention of a mobile workforce | Partner through the contractor's welfare office; over-recruit by 40%; compensate time |
| Capsule acceptability | Optional; sensor-only sessions still support H2 and H3, with a controlled sub-study for validation |
| Process-model mismatch in real heat | Pre-registered model-mismatch decomposition; the two-node model is a starting point, with PHS and JOS-3 coded against the same interface |
| Forecast ensemble too crude at pilot scale | Analog model initially; GEFS v12 reforecast as a parallel workstream |
| Over-confident probabilities eroding trust | Calibration is a secondary endpoint; deployment follows only after it passes |
| Drift toward surveillance | Governance commitments in the contract and the IRB submission; independent facilitator; individual data firewalled from the employer |

## 10. Deliverables and timeline (12 months)

1. Months 0 to 2: ethics approval, contracts, device procurement, clock-sync
   harness, data pipeline, pre-registration.
2. Months 2 to 3: controlled shakedown (about 5 participants); finalise the
   protocol.
3. Months 3 to 8: field data collection across the summer, with rolling quality
   control.
4. Months 6 to 10: analysis of H1 (agreement), H3 (ablation) and acclimatisation.
5. Months 8 to 11: H2 (anticipation) with the forecast-uncertainty model; the
   H4 simulation coupling to the scheduler.
6. Months 10 to 12: manuscript, open code and de-identified data, and a
   deployment specification for the wearable-to-scheduler loop.
