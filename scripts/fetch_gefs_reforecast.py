"""
scripts/fetch_gefs_reforecast.py

Pull the NOAA GEFS v12 **reforecast** for the Doha point across 2000-2019:
a homogeneous, frozen-model, 5-member forecast archive, free on the
`noaa-gefs-retrospective` S3 bucket. This is the substrate the technical
report (S6) names for (a) a real multi-year forecast-reliability study and
(b) a calibrated ensemble for the scheduler - the public operational
archive carries only temperature before 2024.

WHY MAY-SEPTEMBER
    Qatar Decision 17/2021 runs 1 Jun - 15 Sep; the 16-year WBGT
    climatology puts effectively all WBGT>32.1 C exceedance in Jun-Sep.
    We fetch May-Sep so the shoulder month (May) exists for EMOS pooling
    and so the report can show its thinness; the reliability analysis
    focuses on Jun-Sep.

WHY THESE LEADS
    00 UTC init; Doha = UTC+3. Leads 33/36/39 h land at 12/15/18 local on
    forecast day +1; +57..63 on day +2; +81..87 on day +3 - three
    CONSECUTIVE messages per forecast day (one coalesced range-GET),
    covering the afternoon + humid-evening hours that dominate WBGT.
    09:00 local is extrapolated downstream. Verified by
    tests/test_gefs_alignment.py.

EFFICIENCY
    Each variable file is a global 0.25 deg GRIB2 with a `.idx` sidecar
    of per-message byte offsets. We range-GET only the target-lead
    messages (and, for height-level winds, only the "10 m" ones),
    COALESCING adjacent messages into one request. ~25x less transfer
    than whole files.

RESUMABLE
    One year -> data/gefs/gefs_doha_YYYY.parquet. An init date counts as
    done only when all requested members are present. The year file is
    rewritten after every batch, so a crash loses at most the current
    batch. Re-run the same command to continue.

GEFS v12 layout is consistent across 2000-2019 (members c00,p01..p04;
`Days:1-10` subdir; `{var}_{YYYYMMDD}00_{member}.grib2`) - checked, no
year special-casing needed.

Usage:
    python scripts/fetch_gefs_reforecast.py                 # full backfill
    python scripts/fetch_gefs_reforecast.py --start-year 2015 --end-year 2015
    python scripts/fetch_gefs_reforecast.py --slice 2015-07-01 2015-07-08 \
        --out data/_gefs_probe.csv                          # ad-hoc CSV slice
"""

import argparse
import pathlib
import sys
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import s3fs
import xarray as xr

BUCKET = "noaa-gefs-retrospective/GEFSv12/reforecast"
DOHA_LAT, DOHA_LON = 25.27, 51.61          # GEFS lon is 0-360
# 3 CONSECUTIVE leads per forecast day (12, 15, 18 local): the afternoon
# and humid-evening hours that dominate WBGT and the ban-window decision.
# Consecutive => one coalesced range-GET per forecast day per variable.
# 09:00 local is extrapolated downstream (a mild morning ramp). Transfer
# is the binding cost on this network path (~0.2 MB/s single-connection).
LEADS = (33, 36, 39,             # forecast day +1  (12, 15, 18 local)
         57, 60, 63,             # forecast day +2
         81, 84, 87)             # forecast day +3
LEAD_TO_FDAY = {L: (L // 24) for L in LEADS}
DEFAULT_MONTHS = (5, 6, 7, 8, 9)
MEMBERS = ("c00", "p01", "p02", "p03", "p04")
# Pressure is dropped: WBGT changes < 0.05 C over the 990-1010 hPa Doha
# summer range, so a fixed 1000 hPa is used downstream.
GRIB_VARS = ("tmp_2m", "spfh_2m", "ugrd_hgt", "vgrd_hgt", "dswrf_sfc")
FIXED_PRESSURE_HPA = 1000.0
OUTDIR = pathlib.Path("data/gefs")
S3_RETRIES = 4

# botocore-level timeouts so one stalled connection cannot wedge a worker.
FS = s3fs.S3FileSystem(anon=True, config_kwargs={
    "connect_timeout": 10, "read_timeout": 40,
    "retries": {"max_attempts": 2, "mode": "standard"}})


# --------------------------------------------------------------------------
# GRIB .idx handling
# --------------------------------------------------------------------------
def _idx_ranges(idx_text, want_leads, level_filter=None, averaged=False):
    """{lead_h: (byte_start, byte_end)} from a GRIB .idx listing."""
    recs = []
    for ln in idx_text.splitlines():
        if not ln.strip():
            continue
        p = ln.split(":")
        recs.append((int(p[1]), p[3], p[4], p[5]))            # off, var, level, ftime
    ranges = {}
    for i, (off, var, level, ftime) in enumerate(recs):
        if level_filter and level_filter not in level:
            continue
        ft = ftime.strip()
        if averaged:
            hit = next((L for L in want_leads
                        if ft.endswith(f"-{L} hour ave fcst")), None)
        else:
            hit = next((L for L in want_leads if ft == f"{L} hour fcst"), None)
        if hit is None or hit in ranges:
            continue
        end = recs[i + 1][0] if i + 1 < len(recs) else None
        ranges[hit] = (off, end)
    return ranges


def _coalesce(lead_spans):
    """lead_spans: {lead_h: (start, end)}. GRIB2 messages sit back-to-back
    with NO gaps, so byte-adjacency is always true; we may only merge
    spans whose LEADS are consecutive 3-hourly steps (== consecutive
    messages) - i.e. within one forecast day. Leads separated by unwanted
    messages stay as separate GETs. Returns [(start, end_or_None), ...]."""
    items = sorted(lead_spans.items())                      # by lead
    out = []
    for lead, (s, e) in items:
        if out and out[-1][2] == lead - 3 and out[-1][1] == s:
            out[-1][1], out[-1][2] = e, lead
        else:
            out.append([s, e, lead])
    return [(s, e) for s, e, _ in out]


def _s3(fn, *a, **kw):
    for k in range(S3_RETRIES):
        try:
            return fn(*a, **kw)
        except (FileNotFoundError, PermissionError):
            raise
        except Exception:                                    # noqa: BLE001
            if k == S3_RETRIES - 1:
                raise
            time.sleep(1.5 * (k + 1))


def _fetch_var_point(day_key, member, gribname):
    """{lead_h: scalar} for one variable at the Doha nearest grid point."""
    base = (f"{BUCKET}/{day_key[:4]}/{day_key}/{member}/Days:1-10/"
            f"{gribname}_{day_key}_{member}.grib2")
    idx = _s3(FS.cat, base + ".idx").decode("latin-1")
    averaged = gribname == "dswrf_sfc"
    lvl = "10 m above ground" if gribname in ("ugrd_hgt", "vgrd_hgt") else None
    rngs = _idx_ranges(idx, LEADS, level_filter=lvl, averaged=averaged)
    if not rngs:
        return {}
    blob = b"".join(_s3(FS.cat_file, base, start=s, end=e)
                    for s, e in _coalesce(rngs))
    out = {}
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tf:
        tf.write(blob)
        tf.flush()
        ds = xr.open_dataset(tf.name, engine="cfgrib",
                             backend_kwargs={"indexpath": ""})
        vname = list(ds.data_vars)[0]
        pt = ds[vname].sel(latitude=DOHA_LAT, longitude=DOHA_LON % 360,
                           method="nearest")
        for st, v in zip(np.atleast_1d(ds["step"].values),
                         np.atleast_1d(pt.values)):
            out[int(pd.to_timedelta(st).total_seconds() // 3600)] = float(v)
        ds.close()
    return out


def _rh_from_spfh(t_k, sph, p_pa):
    e = sph * p_pa / (0.622 + 0.378 * sph)
    es = 611.2 * np.exp(17.67 * (t_k - 273.15) / (t_k - 273.15 + 243.5))
    return float(np.clip(100.0 * e / es, 0.0, 100.0))


def fetch_day_member(day_key, member):
    """List of row dicts for one (init day, member), or [] if unavailable."""
    try:
        cols = {g: _fetch_var_point(day_key, member, g) for g in GRIB_VARS}
    except FileNotFoundError:
        return []
    init = pd.Timestamp(day_key[:8]) + pd.Timedelta(hours=int(day_key[8:10]))
    rows = []
    for lead in LEADS:
        try:
            t_k = cols["tmp_2m"][lead]
            sph = cols["spfh_2m"][lead]
            u, v = cols["ugrd_hgt"][lead], cols["vgrd_hgt"][lead]
        except KeyError:
            continue
        dsw = cols["dswrf_sfc"].get(lead, np.nan)
        rows.append(dict(
            init_time=init, valid_time=init + pd.Timedelta(hours=lead),
            lead_h=lead, fday=LEAD_TO_FDAY[lead], member=member,
            temp_c=t_k - 273.15,
            rh_pct=_rh_from_spfh(t_k, sph, FIXED_PRESSURE_HPA * 100.0),
            pressure_hpa=FIXED_PRESSURE_HPA, wind_ms=float(np.hypot(u, v)),
            dswrf_wm2=max(0.0, dsw),
        ))
    return rows


# --------------------------------------------------------------------------
# Resumable per-year backfill
# --------------------------------------------------------------------------
def _year_path(year):
    return OUTDIR / f"gefs_doha_{year}.parquet"


def _done_dates(year, members):
    p = _year_path(year)
    if not p.exists():
        return set()
    df = pd.read_parquet(p, columns=["init_time", "member"])
    df["d"] = pd.to_datetime(df["init_time"]).dt.strftime("%Y%m%d00")
    by = df.groupby("d")["member"].apply(set)
    need = set(members)
    return {d for d, ms in by.items() if need.issubset(ms)}


def _flush(year, rows_all):
    if not rows_all:
        return
    p = _year_path(year)
    new = pd.DataFrame(rows_all)
    if p.exists():
        old = pd.read_parquet(p)
        new = pd.concat([old, new], ignore_index=True)
    new = (new.drop_duplicates(["init_time", "member", "lead_h"])
              .sort_values(["valid_time", "member", "lead_h"])
              .reset_index(drop=True))
    p.parent.mkdir(parents=True, exist_ok=True)
    new.to_parquet(p, index=False)


def backfill(start_year, end_year, months, members, workers, batch, limit_days,
             newest_first=False):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    years = range(start_year, end_year + 1)
    if newest_first:
        years = list(reversed(list(years)))
    for year in years:
        days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
        days = [d for d in days if d.month in months]
        done = _done_dates(year, members)
        keys = [d.strftime("%Y%m%d00") for d in days]
        todo = [(k, m) for k in keys if k not in done for m in members]
        if limit_days:
            todo = [t for t in todo if t[0] in keys[:limit_days]]
        if not todo:
            print(f"{year}: complete ({len(done)}/{len(keys)} dates)", file=sys.stderr)
            continue
        print(f"{year}: {len(done)}/{len(keys)} dates done, {len(todo)} "
              f"(date x member) to fetch", file=sys.stderr)
        buf, n_ok = [], 0
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(fetch_day_member, *t): t for t in todo}
            for i, fut in enumerate(as_completed(futs)):      # as they finish
                try:
                    r = fut.result()
                except Exception as e:                        # noqa: BLE001
                    r = []
                    print(f"  {year}: {futs[fut]} failed: {e}", file=sys.stderr)
                buf.extend(r)
                n_ok += bool(r)
                if (i + 1) % batch == 0:
                    _flush(year, buf); buf = []
                    rate = (i + 1) / max(time.time() - t0, 1e-6)
                    print(f"  {year}: {i + 1}/{len(todo)}  "
                          f"({rate:.2f}/s, {n_ok} non-empty)", file=sys.stderr)
        _flush(year, buf)
        print(f"{year}: done in {time.time() - t0:.0f}s", file=sys.stderr)


def compute_gefs_wbgt(df, lat=DOHA_LAT, lon=DOHA_LON):
    """Liljegren WBGT from a GEFS point frame (columns temp_c, rh_pct,
    wind_ms, dswrf_wm2). The reforecast reports shortwave as a 3-6 h
    AVERAGE ending at the lead, so at the 18:00-local lead it carries the
    afternoon mean while the sun is nearly set - that inflated the globe
    term by ~+5 C. We clip shortwave to the clear-sky ceiling for the
    actual solar geometry (1361 * cos(zenith) * 0.82); this leaves the
    12:00/15:00 leads unchanged and removes the evening bias.
    Returns (wbgt, cos_zenith).
    """
    from src.solar import cos_solar_zenith_angle
    from src.wbgt import wbgt_liljegren_c

    cz = cos_solar_zenith_angle(pd.DatetimeIndex(df["valid_time"]), lat, lon)
    sw = np.minimum(np.asarray(df["dswrf_wm2"], float),
                    1361.0 * np.clip(cz, 0.0, 1.0) * 0.82)
    p = df["pressure_hpa"] if "pressure_hpa" in df else FIXED_PRESSURE_HPA
    w = wbgt_liljegren_c(temp_c=np.asarray(df["temp_c"], float),
                         rh_pct=np.asarray(df["rh_pct"], float),
                         pressure_hpa=p,
                         wind_speed_10m_ms=np.asarray(df["wind_ms"], float),
                         shortwave_wm2=sw, direct_wm2=0.75 * sw, cos_zenith=cz)
    return w, cz


def verify_lead_alignment(tz_offset_h=3, day_lo=9, day_hi=18):
    """Check every (lead, forecast-day) lands on the intended local working
    window. Returns (ok: bool, table: list[dict]). Also called by
    tests/test_gefs_alignment.py - a silent off-by-one here invalidates
    everything downstream.
    """
    rows, ok = [], True
    for lead in LEADS:
        valid_utc_hour = lead % 24                      # 00Z init
        local_hour = (valid_utc_hour + tz_offset_h) % 24
        fday = LEAD_TO_FDAY[lead]
        in_window = day_lo <= local_hour <= day_hi
        # forecast day: lead 30-47 -> +1, 54-71 -> +2, 78-95 -> +3
        exp_fday = 1 + (lead - 24) // 24
        fday_ok = fday == exp_fday
        ok &= in_window and fday_ok
        rows.append(dict(lead_h=lead, valid_utc_hour=valid_utc_hour,
                         local_hour=local_hour, fday=fday, exp_fday=exp_fday,
                         in_working_window=in_window, fday_ok=fday_ok))
    return ok, rows


def load_gefs(outdir=OUTDIR):
    """Concatenate every gefs_doha_YYYY.parquet -> one DataFrame."""
    files = sorted(pathlib.Path(outdir).glob("gefs_doha_*.parquet"))
    if not files:
        raise SystemExit(f"no GEFS parquet in {outdir} - run fetch_gefs_reforecast.py")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    for c in ("init_time", "valid_time"):
        df[c] = pd.to_datetime(df[c])
    return df.sort_values(["valid_time", "member", "lead_h"]).reset_index(drop=True)


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2000)
    ap.add_argument("--end-year", type=int, default=2019)
    ap.add_argument("--months", type=int, nargs="+", default=list(DEFAULT_MONTHS))
    ap.add_argument("--members", nargs="+", default=list(MEMBERS))
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--batch", type=int, default=60)
    ap.add_argument("--newest-first", action="store_true")
    ap.add_argument("--limit-days", type=int, default=0,
                    help="only the first N init days of each year (testing)")
    ap.add_argument("--slice", nargs=2, metavar=("START", "END"),
                    help="ad-hoc: fetch this date range to a single CSV (--out)")
    ap.add_argument("--out", default="data/_gefs_slice.csv")
    args = ap.parse_args()

    ok, tbl = verify_lead_alignment()
    print("lead / forecast-day / local-hour alignment:", file=sys.stderr)
    for r in tbl:
        print(f"  lead {r['lead_h']:>3}h -> valid {r['valid_utc_hour']:02d}Z "
              f"= {r['local_hour']:02d}:00 local, fday {r['fday']} "
              f"{'OK' if r['in_working_window'] and r['fday_ok'] else 'BAD'}",
              file=sys.stderr)
    if not ok:
        raise SystemExit("lead alignment check FAILED - fix LEADS before fetching")

    if args.slice:
        days = pd.date_range(*args.slice, freq="D")
        days = days[days.month.isin(args.months)]
        tasks = [(d.strftime("%Y%m%d00"), m) for d in days for m in args.members]
        rows = []
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(lambda t: fetch_day_member(*t), tasks):
                rows.extend(r)
        pd.DataFrame(rows).to_csv(args.out, index=False)
        print(f"wrote {len(rows)} rows -> {args.out}", file=sys.stderr)
        return

    backfill(args.start_year, args.end_year, set(args.months), args.members,
             args.workers, args.batch, args.limit_days,
             newest_first=args.newest_first)


if __name__ == "__main__":
    main()
