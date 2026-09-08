"""
Tests for the forecast-scenario models. The GEFS test runs only if a
reforecast slice has been fetched (data/_gefs_probe.csv or data/gefs_*.csv).
"""

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.forecast_uncertainty import AnalogResidualModel, GEFSEnsembleModel

HOURS = np.arange(5, 20)


def test_analog_model_shapes_and_leak_free():
    rng = np.random.default_rng(0)
    n_days = 60
    dates = pd.date_range("2022-06-01", periods=n_days, freq="D")
    rows = {"date": dates.values, "month": dates.month.values}
    for h in HOURS:
        rows[f"fc_{h}"] = 30 + rng.normal(0, 2, n_days)
        rows[f"resid_{h}"] = rng.normal(0, 1.5, n_days)
    tab = pd.DataFrame(rows)
    m = AnalogResidualModel(HOURS).fit(tab)
    fc = np.full(len(HOURS), 31.0)
    scen = m.scenarios(np.datetime64("2022-07-15"), 7, fc, k=20)
    assert scen.shape[1] == len(HOURS)
    assert 1 <= scen.shape[0] <= 20
    # a target early in the record has fewer usable (strictly earlier) analogs
    early = m.scenarios(np.datetime64("2022-06-10"), 6, fc, k=50)
    late = m.scenarios(np.datetime64("2022-07-28"), 7, fc, k=50)
    assert early.shape[0] < late.shape[0]


_GEFS = next((REPO / "data" / f for f in
              ("gefs_2015.csv", "gefs_2018.csv", "_gefs_probe.csv")
              if (REPO / "data" / f).exists()), None)


@pytest.mark.skipif(_GEFS is None, reason="no GEFS reforecast slice fetched")
def test_gefs_ensemble_model():
    ens = GEFSEnsembleModel(_GEFS)
    assert {"wbgt", "fday", "member", "vdate"}.issubset(ens.df.columns)
    # spread must be non-negative and (over the slice) grow with forecast day
    sd = ens.df.groupby(["vdate", "fday"])["wbgt"].std().groupby("fday").mean()
    assert (sd.dropna() >= 0).all()
    a_date = sorted(ens.df["vdate"].unique())[len(ens.df["vdate"].unique()) // 2]
    scen = ens.scenarios(a_date, HOURS)
    assert scen.ndim == 2 and scen.shape[1] == len(HOURS)
    assert scen.shape[0] >= 1
    assert np.isfinite(scen).all()
    # WBGT plausibility for a Doha summer working day
    assert 15 < np.nanmean(scen) < 42


def test_gefs_ensemble_model_with_emos_ecc():
    """EMOS + Ensemble Copula Coupling: calibrated scenarios keep the
    member count, stay finite, and preserve the per-hour rank order of the
    raw members (that is what ECC guarantees)."""
    import numpy as np, pandas as pd
    from src.emos import EMOS
    from src.forecast_uncertainty import GEFSEnsembleModel

    rng = np.random.default_rng(0)
    # tiny synthetic GEFS point frame: one working day, 5 members, 3 leads
    recs = []
    for mi, m in enumerate(["c00", "p01", "p02", "p03", "p04"]):
        for lead, lh in [(33, 12), (36, 15), (39, 18)]:
            recs.append(dict(
                init_time=pd.Timestamp("2015-07-01"),
                valid_time=pd.Timestamp("2015-07-01") + pd.Timedelta(hours=lead),
                lead_h=lead, fday=1, member=m,
                temp_c=40 + mi * 0.6 + rng.normal(0, 0.3),
                rh_pct=25 + rng.normal(0, 2), wind_ms=4 + rng.normal(0, 0.5),
                dswrf_wm2=[300.0, 900.0, 350.0][[33, 36, 39].index(lead)]))
    df = pd.DataFrame(recs)

    # trivial EMOS: identity mean, fixed spread
    em = EMOS(min_cell=1)
    em.cells[(36, 7)] = dict(a=0.0, b=1.0, c=1.0, d=0.0, n=99, crps=0.1)
    em.lead_only[36] = em.cells[(36, 7)]
    for L in (33, 39):
        em.lead_only[L] = em.cells[(36, 7)]

    raw = GEFSEnsembleModel(df).scenarios("2015-07-02", np.arange(5, 20), fday=1)
    cal = GEFSEnsembleModel(df, emos=em).scenarios("2015-07-02", np.arange(5, 20), fday=1)
    assert raw.shape == cal.shape and cal.shape[0] == 5
    assert np.isfinite(cal).all()
    # rank order preserved column-wise
    for j in range(cal.shape[1]):
        assert np.array_equal(np.argsort(raw[:, j]), np.argsort(cal[:, j]))
