"""
Build one curated past week for /api/replay: the hottest seven-day run in the
16-year WBGT record. Each day is planned with that day's actual hourly
conditions and scored against them, so this shows the best the shaping can do
on a real week, not forecast skill (that is in technical_report section 8).

    python scripts/build_replay_weeks.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.scheduler import (
    PHI_DEFAULT, policy_calendar, policy_reactive, retained_load_path,
    schedule_cvar,
)
from src.heat_stress import continuous_work_limit_c
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C

TRUTH = REPO / "data" / "doha_wbgt_16yr.csv"
OUTDIR = REPO / "api" / "data" / "replay"
TZ = "Asia/Qatar"
HOURS = list(range(5, 19))
W_REQ = 8.0
WORKLOAD, ACCLIM = "moderate", True
THR = QATAR_WBGT_STOP_WORK_THRESHOLD_C


def _day_plan(wbgt: np.ndarray) -> dict:
    allowed = np.ones(len(wbgt), dtype=bool)
    ref = continuous_work_limit_c(WORKLOAD, ACCLIM)
    w_plan = schedule_cvar(wbgt[None, :], allowed, W_REQ, wbgt_ref=ref).w
    w_cal = policy_calendar(np.array(HOURS, dtype=float), allowed)
    w_react = policy_reactive(wbgt, allowed, W_REQ)
    out = {"hours": HOURS, "wbgt_c": [round(float(v), 1) for v in wbgt]}
    for name, w in (("plan", w_plan), ("calendar", w_cal), ("reactive", w_react)):
        path = retained_load_path(w, wbgt, phi=PHI_DEFAULT, wbgt_ref=ref)
        out[f"{name}_fraction"] = [round(float(x), 3) for x in w]
        out[f"{name}_peak"] = round(float(path.max()), 3)
        out[f"{name}_tail"] = round(float(np.percentile(path, 90)), 3)
        out[f"{name}_hours"] = round(float(w.sum()), 2)
    return out


def main() -> None:
    t = pd.read_csv(TRUTH, usecols=["time", "wbgt_c"])
    t["time"] = pd.to_datetime(t["time"], utc=True)
    loc = t["time"].dt.tz_convert(TZ)
    t["date"] = loc.dt.date
    t["lh"] = loc.dt.hour
    t["month"] = loc.dt.month
    day = t[t["lh"].isin(HOURS) & t["month"].isin([5, 6, 7, 8, 9])]
    dmax = day.groupby("date")["wbgt_c"].max().sort_index()

    # hottest 7 consecutive calendar days
    dates = pd.to_datetime(pd.Series(dmax.index))
    best_i, best_v = 0, -1.0
    for i in range(len(dmax) - 6):
        if (dates.iloc[i + 6] - dates.iloc[i]).days != 6:
            continue
        v = float(dmax.iloc[i:i + 7].mean())
        if v > best_v:
            best_v, best_i = v, i
    week_dates = list(dmax.index[best_i:best_i + 7])

    days = []
    for d in week_dates:
        rows = day[day["date"] == d].sort_values("lh")
        by_h = dict(zip(rows["lh"], rows["wbgt_c"]))
        if any(h not in by_h for h in HOURS):
            continue
        wbgt = np.array([by_h[h] for h in HOURS], dtype=float)
        rec = _day_plan(wbgt)
        rec["date"] = str(d)
        rec["daily_max_wbgt"] = round(float(wbgt.max()), 1)
        days.append(rec)

    agg = {k: round(float(np.mean([x[k] for x in days])), 3)
           for k in ("plan_peak", "calendar_peak", "reactive_peak",
                     "plan_tail", "calendar_tail", "reactive_tail")}
    pct_peak = round((agg["calendar_peak"] - agg["plan_peak"])
                     / agg["calendar_peak"] * 100, 1)

    y = week_dates[0].year
    out = {
        "slug": f"doha-{y}-hot-week",
        "title": f"Doha, hottest week of {y}",
        "subtitle": (f"{week_dates[0]} to {week_dates[-1]}. Mean daily peak "
                     f"WBGT {best_v:.1f} C."),
        "note": ("Simulated on real past weather. Each day is planned with "
                 "that day's actual hourly conditions, so this shows the best "
                 "the shaping can do on a real week, not forecast skill."),
        "threshold_c": THR,
        "required_work_hours": W_REQ,
        "days": days,
        "mean": agg,
        "pct_peak_reduction": pct_peak,
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    p = OUTDIR / f"{out['slug']}.json"
    p.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {p}  ({len(days)} days, mean peak {agg['plan_peak']} vs "
          f"{agg['calendar_peak']}, {pct_peak}% lower)", file=sys.stderr)


if __name__ == "__main__":
    main()
