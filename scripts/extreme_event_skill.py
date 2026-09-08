"""
scripts/extreme_event_skill.py

Aggregate MAE hides the question that matters: does the NWP forecast keep
its skill on the DANGEROUS days, or does it fall apart exactly when a
threshold crossing is at stake?

Three views, using the forecast archive (what was forecast 24/48/72 h
ahead) vs the patched-reanalysis WBGT truth:

  1. Error stratified by truth WBGT band - is bias / MAE worse in the
     hot bins?
  2. Threshold-crossing detection - of true WBGT>32.1 hours, what
     fraction did the forecast also put over 32.1, split by how far over
     truth actually was.
  3. Event level: group true exceedances into heat events (runs of
     consecutive hours). Did the forecast issued before onset catch the
     event at all, get onset timing right, and get peak WBGT right?

Run:  python scripts/extreme_event_skill.py
"""

import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.solar import cos_solar_zenith_angle
from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C as THR
from src.wbgt import wbgt_liljegren_c

DOHA_LAT, DOHA_LON = 25.27, 51.61
LEADS = [1, 2, 3]
BANDS = [(-99, 28), (28, 30), (30, 31), (31, 32), (32, 32.1),
         (32.1, 33), (33, 34), (34, 99)]


def wbgt_from(df, suffix):
    g = lambda b: df[f"{b}{suffix}"].to_numpy()
    return wbgt_liljegren_c(
        temp_c=g("temperature_2m"), rh_pct=g("relative_humidity_2m"),
        pressure_hpa=g("surface_pressure"), wind_speed_10m_ms=g("wind_speed_10m"),
        shortwave_wm2=np.nan_to_num(g("shortwave_radiation")),
        direct_wm2=np.nan_to_num(g("direct_radiation")),
        cos_zenith=df["cos_zenith"].to_numpy())


def events_from(mask: np.ndarray, times, wbgt_true, min_len=2):
    """Contiguous runs where mask is True -> list of (start_i, end_i, peak)."""
    out = []
    i = 0
    n = len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            if j - i + 1 >= min_len:
                out.append((i, j, float(np.nanmax(wbgt_true[i:j + 1]))))
            i = j + 1
        else:
            i += 1
    return out


def main():
    fc = pd.read_csv(REPO / "data" / "doha_forecast_archive.csv")
    fc["time"] = pd.to_datetime(fc["time"], utc=True)
    fc["cos_zenith"] = cos_solar_zenith_angle(pd.DatetimeIndex(fc["time"]),
                                              DOHA_LAT, DOHA_LON)
    tr = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv")[["time", "wbgt_c"]]
    tr["time"] = pd.to_datetime(tr["time"], utc=True)
    df = fc.merge(tr.rename(columns={"wbgt_c": "truth"}), on="time", how="inner")
    df = df.sort_values("time").reset_index(drop=True)

    truth = df["truth"].to_numpy()
    print(f"rows: {len(df):,}   true WBGT>32.1 hours: {int((truth > THR).sum()):,}\n")

    for n in LEADS:
        h = 24 * n
        fcw = wbgt_from(df, f"_fc{n}")
        ok = ~np.isnan(fcw) & ~np.isnan(truth)
        t, f = truth[ok], fcw[ok]
        err = f - t                                   # forecast minus truth

        print(f"================  LEAD {h}h  ================")
        print(f"  overall: MAE {np.mean(np.abs(err)):.2f}  bias {np.mean(err):+.2f}"
              f"  RMSE {np.sqrt(np.mean(err**2)):.2f}  "
              f"p99|err| {np.percentile(np.abs(err),99):.2f}")

        print(f"\n  {'truth WBGT band':<18}{'n':>8}{'MAE':>7}{'bias':>7}"
              f"{'p95|e|':>8}{'caught>32.1':>12}")
        for lo, hi in BANDS:
            m = (t >= lo) & (t < hi)
            if m.sum() == 0:
                continue
            e = err[m]
            caught = np.mean(f[m] > THR) * 100 if lo >= THR else np.nan
            lab = f"{lo:g}-{hi:g}" if lo > -99 else f"<{hi:g}"
            cs = f"{caught:11.1f}%" if not np.isnan(caught) else f"{'--':>12}"
            print(f"  {lab:<18}{m.sum():>8}{np.mean(np.abs(e)):7.2f}"
                  f"{np.mean(e):+7.2f}{np.percentile(np.abs(e),95):8.2f}{cs}")

        # event level
        true_exc = truth > THR
        evs = events_from(true_exc, df["time"].to_numpy(), truth, min_len=2)
        fcw_full = wbgt_from(df, f"_fc{n}")
        det, onset_err, peak_err = 0, [], []
        for a, b, peak in evs:
            win = slice(max(a - 3, 0), b + 1)          # forecast near/at onset..end
            fev = fcw_full[win]
            if np.nanmax(fev) > THR:
                det += 1
                # onset timing: first forecast hour over THR vs first true hour
                fo = np.argmax(fcw_full[a - 0:b + 1] > THR) if np.nanmax(fcw_full[a:b+1] > THR) else None
                if fo is not None:
                    onset_err.append(fo)
                peak_err.append(np.nanmax(fcw_full[a:b + 1]) - peak)
        print(f"\n  heat events (>=2 h over 32.1): {len(evs)}   "
              f"forecast caught: {det} ({det/max(len(evs),1)*100:.0f}%)")
        if peak_err:
            pe = np.array(peak_err)
            print(f"  event peak WBGT error: mean {pe.mean():+.2f} C  "
                  f"MAE {np.mean(np.abs(pe)):.2f}  "
                  f"under-forecast peak by >1C: {np.mean(pe < -1)*100:.0f}% of events")
        print()

    # worst single misses
    n = 1
    fcw = wbgt_from(df, "_fc1")
    ok = ~np.isnan(fcw) & ~np.isnan(truth)
    dd = pd.DataFrame({"time": df["time"][ok], "truth": truth[ok],
                       "fc24": fcw[ok], "err": (fcw - truth)[ok]})
    dd["day"] = dd["time"].dt.tz_convert("Asia/Qatar").dt.date
    daily = (dd.assign(abserr=dd["err"].abs())
               .groupby("day")
               .agg(max_truth=("truth", "max"),
                    mean_abserr=("abserr", "mean"),
                    worst_err=("err", lambda s: s.loc[s.abs().idxmax()]))
               .sort_values("mean_abserr", ascending=False))
    print("10 worst forecast days (24h lead, by mean |error|):")
    print(daily.head(10).round(2).to_string())


if __name__ == "__main__":
    main()
