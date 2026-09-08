"""
scripts/work_rest_analysis.py

Turn the 16-year WBGT history into an operational picture and compare a
physiological, role-specific work/rest model (ACGIH TLV) against Qatar's
single calendar rule (Decision 17/2021: outdoor work banned 10:00-15:30
local, 1 Jun - 15 Sep, plus WBGT>32.1 stop anytime).

Questions answered:
  1. How many outdoor working hours (06:00-18:00 local, Apr-Oct) fall in
     each work/rest band, per workload x acclimatization?
  2. UNDER-PROTECTION: hours the calendar ban leaves OPEN that the
     physiological model says are unsafe (stop-work) - by category.
  3. OVER-RESTRICTION: hours the calendar ban CLOSES that are actually
     safe for continuous work at a given workload.

Run:  python scripts/work_rest_analysis.py --data data/doha_wbgt_16yr.csv
"""

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.heat_stress import (
    allowable_work_fraction,
    in_qatar_calendar_ban,
    stop_work,
)

DAY_START, DAY_END = 6.0, 18.0            # local daylight working window
OUTDOOR_MONTHS = (4, 5, 6, 7, 8, 9, 10)  # season with any heat risk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/doha_wbgt_16yr.csv")
    args = ap.parse_args()
    path = pathlib.Path(args.data)
    if not path.is_absolute():
        path = REPO / path

    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    local = df["time"].dt.tz_convert("Asia/Qatar")
    hod = local.dt.hour + local.dt.minute / 60.0

    day = (hod >= DAY_START) & (hod < DAY_END) & local.dt.month.isin(OUTDOOR_MONTHS)
    d = df.loc[day].copy()
    lt = local.loc[day]
    wbgt = d["wbgt_c"].to_numpy()
    n_years = lt.dt.year.nunique()
    print(f"Daylight outdoor hours (06-18 local, Apr-Oct), {n_years} yrs: "
          f"{len(d):,}  ({len(d)/n_years:,.0f}/yr)\n")

    ban = in_qatar_calendar_ban(lt)
    print(f"Qatar calendar ban covers {ban.mean()*100:4.1f}% of those hours "
          f"({int(ban.sum()):,}; {ban.sum()/n_years:,.0f}/yr)\n")

    # ---- 1. work/rest band distribution ----
    print("Share of daylight outdoor hours by allowable work fraction:")
    print(f"  {'workload / state':<26}{'100%':>7}{'75%':>7}{'50%':>7}"
          f"{'25%':>7}{'STOP':>7}")
    scenarios = [
        ("light / acclim", "light", True),
        ("moderate / acclim", "moderate", True),
        ("heavy / acclim", "heavy", True),
        ("moderate / UNacclim", "moderate", False),
        ("heavy / UNacclim", "heavy", False),
    ]
    frac_by_scn = {}
    for label, wl, acc in scenarios:
        fr = allowable_work_fraction(wbgt, wl, acc)
        frac_by_scn[label] = fr
        shares = [np.mean(fr == v) * 100 for v in (1.0, 0.75, 0.5, 0.25, 0.0)]
        print(f"  {label:<26}" + "".join(f"{s:6.1f} " for s in shares))
    print()

    # ---- 2. under-protection: ban OPEN but physiologically STOP ----
    print("UNDER-PROTECTION  (hours the calendar ban leaves open, but the "
          "model says STOP work):")
    print(f"  {'workload / state':<26}{'hours/yr':>10}{'% of open hrs':>15}")
    open_hrs = ~ban
    for label, wl, acc in scenarios:
        stp = stop_work(wbgt, wl, acc)
        gap = stp & open_hrs
        print(f"  {label:<26}{gap.sum()/n_years:10.0f}{gap.sum()/open_hrs.sum()*100:14.1f}%")
    print()

    # also: WBGT>32.1 specifically, outside the ban window
    hot = (wbgt > 32.1) & open_hrs
    print(f"  WBGT>32.1 C outside ban window: {hot.sum()/n_years:.0f} h/yr "
          f"({hot.sum()/open_hrs.sum()*100:.1f}% of open hrs) - these are "
          f"already illegal to work under 17/2021's WBGT clause, but the\n"
          f"  calendar rule alone would not flag them.\n")

    # ---- 3. over-restriction: ban CLOSED but safe for continuous work ----
    print("OVER-RESTRICTION  (hours the calendar ban closes, but continuous "
          "100% work is within the TLV):")
    print(f"  {'workload / state':<26}{'hours/yr':>10}{'% of ban hrs':>14}")
    for label, wl, acc in scenarios:
        fr = frac_by_scn[label]
        safe_full = (fr == 1.0) & ban
        print(f"  {label:<26}{safe_full.sum()/n_years:10.0f}"
              f"{safe_full.sum()/ban.sum()*100:13.1f}%")
    print()

    # ---- headline framing ----
    stp_hu = stop_work(wbgt, "heavy", False)
    miss_hu = (stp_hu & open_hrs).sum() / max((stp_hu).sum(), 1) * 100
    fr_la = frac_by_scn["light / acclim"]
    over_la = ((fr_la == 1.0) & ban).sum() / ban.sum() * 100
    print("Headline:")
    print(f"  - For heavy work by UNacclimatized workers, {miss_hu:.0f}% of all "
          f"physiologically unsafe daylight hours fall OUTSIDE the calendar ban.")
    print(f"  - Of the hours the ban closes, {over_la:.0f}% are safe for "
          f"continuous light work by acclimatized workers.")
    print(f"  - A role- and state-aware signal reallocates both.")


if __name__ == "__main__":
    main()
