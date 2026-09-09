# AI weather models and Gulf humid-heat stop-work decisions

Draft summary, suitable as the basis of a preprint introduction. Numbers
from `scripts/aiwp_humid_heat_study.py`; figures 6-10 in `docs/figures/`.

## What was asked

Kong et al. (2025, arXiv 2504.21195, "Turning Up the Heat") show that the
machine-learning weather models GraphCast and Pangu-Weather, and NOAA's GEFS,
carry a consistent regional cold bias in 2 m temperature in the 5-10 days
before heat-wave onset over the contiguous United States. A cold bias ahead of
extreme heat is the operationally dangerous direction: it delays protective
action.

That result is about dry-bulb air temperature over a mid-latitude land mass.
The question here is whether it transfers to the quantity that governs outdoor-
work safety in the Gulf -- wet-bulb globe temperature (WBGT) -- and whether it
would cause missed stop-work decisions at Qatar's regulatory threshold of
32.1 C. No published work evaluates AI weather models as humid-heat forecasts
for this region, or against a work-stoppage threshold.

We evaluate four forecast systems for the Doha grid point at leads of 1 to 7
days: ECMWF IFS-HRES (conventional physics), ECMWF AIFS Single (ECMWF's
operational AI model), NOAA GraphCast (AI), and NOAA GFS (conventional physics,
the deterministic sibling of GEFS). Forecast fields come from Open-Meteo's
Previous Runs archive; GraphCast on that feed serves only 2 m temperature and
cloud, so it is limited to a temperature-only track. WBGT is computed from each
model's fields with the Liljegren energy-balance method, the same pipeline used
for the observational truth (a WMO-station METAR series, wind-patched). Scoring
follows the project's existing convention: walk-forward, warm-season (May to
September) daylight hours, and the miss rate at 32.1 C as the headline metric
rather than average error. Heat-wave onsets are defined from the truth with a
threshold taken only from prior years. Confidence intervals are one-day moving-
block bootstrap. Because AIFS is only available from February 2025 on this feed
(about 1.5 warm seasons), the headline tables score every model on the common
window of valid hours per lead, so the comparison is like for like.

## What was found

**The AI model matches the best conventional model on the humid-heat
decision.** On identical hours, ECMWF IFS and AIFS each place 6 to 15% of true
32.1 C exceedance hours below the threshold across leads 1 to 7. NOAA GFS
places 40 to 44% below it -- at every lead, including day one. The paired
AIFS - IFS difference in miss rate is +0.03 at leads 1 to 3 and not
significant beyond; the paired IFS - GFS and AIFS - GFS differences are about
-0.33 at every lead, with intervals far from zero. Stratified by observed WBGT
band, GFS bias runs from +1.0 C in the coolest band to -2.4 C in the hottest,
i.e. worst precisely where the stop-work rule binds; IFS holds between +0.4 and
+1.0 C throughout.

**The published cold bias is real in air temperature, and not unique to AI.**
On the 2 m-temperature track, AIFS runs 1.4 to 1.7 C cold and misses almost
every hour above the local 95th-percentile temperature. GFS -- a physics model
-- is cold by a similar margin. IFS runs warm. GraphCast, on this feed, runs
warm by 0.4 to 1.0 C, the opposite of the published sign, though its coverage
is sparse.

**The air-temperature cold bias does not carry through to WBGT for AIFS,
because of humidity compensation.** On the common window, AIFS air temperature
is 1.5 C low but its relative humidity is 6.2 percentage points high. The
natural wet-bulb term is 70% of WBGT, so the humidity error more than cancels
the temperature error, leaving AIFS WBGT 0.66 C warm -- safe-side. GFS has the
same temperature cold bias but almost no humidity offset, so it stays 0.7 C
cold in WBGT.

**Before heat waves, GFS gets colder still.** In the five days before an onset,
GFS WBGT bias is -0.85 to -1.05 C against an all-days -0.25 to -0.73 C. IFS and
AIFS show no pre-onset excursion. Leads here stop at 7 days, so the 8 to 10 day
part of the published window is not tested.

## Why it matters

For humid-heat work-stoppage decisions in the Gulf, the operational risk is not
the AI model. ECMWF IFS and AIFS are safe to use at the 32.1 C threshold; NOAA
GFS is not -- it misses roughly four in ten stop-work hours at all lead times
and worsens ahead of heat waves. More generally, a cold-bias finding in 2 m
temperature does not by itself establish a humid-heat forecasting hazard:
humidity error can offset temperature error in either direction, and the
evaluation has to be done on WBGT at the decision threshold, not on dry-bulb
temperature. This is, to our knowledge, the first evaluation of AI weather
models as humid-heat forecasts for an occupational stop-work threshold.

## Limits

About 1.5 warm seasons for AIFS; a single-station truth; GraphCast assessable
only on temperature and on a gappy feed; leads capped at 7 days. The 2000-2019
GEFS reforecast held in this repository is the decade-scale complement for the
GFS family and is consistent with the deterministic-GFS error measured here.
