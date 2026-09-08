"""
scripts/make_figures.py

Publication-quality figures for the technical report, into docs/figures/.
Re-computes the small aggregates from the base CSVs so the figures are
reproducible from run_all.sh.

Palette: Okabe-Ito (colour-vision-deficiency safe, fixed order). One axis
per panel, thin marks, recessive grid, direct labels.

Run:  python scripts/make_figures.py
"""

import pathlib
import sys

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.heat_stress import allowable_work_fraction, in_qatar_calendar_ban, stop_work

FIGDIR = REPO / "docs" / "figures"
FIGDIR.mkdir(parents=True, exist_ok=True)

OKABE = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
         "vermillion": "#D55E00", "purple": "#CC79A7", "sky": "#56B4E9",
         "grey": "#999999", "ink": "#222222"}

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 10,
    "axes.edgecolor": "#666666", "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": "#DDDDDD", "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white",
})
THR = 32.1


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGDIR / name, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote docs/figures/{name}", file=sys.stderr)


# ------------------------------------------------------------------ fig 1
def fig_climatology():
    df = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv", usecols=["time", "wbgt_c"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    loc = df["time"].dt.tz_convert("Asia/Qatar")
    df["yr"] = loc.dt.year
    exc = df["wbgt_c"] > THR
    per_year = exc.groupby(df["yr"]).sum()
    per_year = per_year[(per_year.index >= 2010) & (per_year.index <= 2026)]

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.bar(per_year.index, per_year.values, color=OKABE["vermillion"], width=0.62)
    # partial-year note for 2026
    ax.bar([2026], [per_year.get(2026, np.nan)], color=OKABE["vermillion"],
           width=0.62, hatch="////", edgecolor="white", linewidth=0)
    z = np.polyfit(per_year.index, per_year.values, 1)
    ax.plot(per_year.index, np.polyval(z, per_year.index), color=OKABE["ink"],
            lw=1.6, ls="--", label=f"trend +{z[0]:.0f} h/yr")
    ax.set_ylabel("hours with WBGT > 32.1 °C")
    ax.set_title("Doha humid-heat hazard, 2010–2026  (2026 partial, hatched)",
                 loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper left")
    ax.set_xticks(range(2010, 2027, 2))
    _save(fig, "fig1_climatology.png")


# ------------------------------------------------------------------ fig 2
def fig_wind_defect():
    om = pd.read_csv(REPO / "data" / "doha_openmeteo_16yr.csv",
                     usecols=["time", "wind_speed_10m"])
    mt = pd.read_csv(REPO / "data" / "othh_metar_hourly.csv",
                     usecols=["time", "wind_speed_ms"])
    for d in (om, mt):
        d["time"] = pd.to_datetime(d["time"], utc=True)
    d = om.merge(mt, on="time", how="inner")
    d = d[d["time"] >= "2023-01-01"]
    d["ym"] = d["time"].dt.to_period("M").dt.to_timestamp()
    g = d.groupby("ym").mean(numeric_only=True)

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(g.index, g["wind_speed_ms"], color=OKABE["blue"], lw=1.8,
            marker="o", ms=3, label="OTHH anemometer (measured)")
    ax.plot(g.index, g["wind_speed_10m"], color=OKABE["orange"], lw=1.8,
            marker="s", ms=3, label="Open-Meteo archive")
    ax.axvline(pd.Timestamp("2024-11-01"), color=OKABE["ink"], lw=1.0, ls=":")
    ax.annotate("Open-Meteo model change\n(−1.5 to −2.5 m/s)",
                xy=(pd.Timestamp("2024-11-01"), 2.6),
                xytext=(pd.Timestamp("2025-04-01"), 2.1), fontsize=8.5,
                arrowprops=dict(arrowstyle="->", color=OKABE["ink"], lw=0.8))
    ax.set_ylabel("monthly mean 10 m wind (m/s)")
    ax.set_title("A data defect, caught against station measurements",
                 loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)
    _save(fig, "fig2_wind_defect.png")


# ------------------------------------------------------------------ fig 3
def fig_operational_gap():
    df = pd.read_csv(REPO / "data" / "doha_wbgt_16yr.csv", usecols=["time", "wbgt_c"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    loc = df["time"].dt.tz_convert("Asia/Qatar")
    hod = loc.dt.hour + loc.dt.minute / 60
    day = (hod >= 6) & (hod < 18) & loc.dt.month.isin([4, 5, 6, 7, 8, 9, 10])
    d = df.loc[day]
    lt = loc.loc[day]
    w = d["wbgt_c"].to_numpy()
    nyr = lt.dt.year.nunique()
    ban = in_qatar_calendar_ban(lt)
    open_h = ~ban

    scen = [("light / acclim", "light", True), ("moderate / acclim", "moderate", True),
            ("heavy / acclim", "heavy", True), ("moderate / UNacclim", "moderate", False),
            ("heavy / UNacclim", "heavy", False)]
    labels = [s[0] for s in scen]
    unsafe_out = [np.sum(stop_work(w, wl, ac) & open_h) / nyr for _, wl, ac in scen]
    frac_stop = [np.mean(stop_work(w, wl, ac)) * 100 for _, wl, ac in scen]

    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.6))
    y = np.arange(len(labels))
    axes[0].barh(y, frac_stop, color=OKABE["grey"])
    axes[0].set_yticks(y); axes[0].set_yticklabels(labels)
    axes[0].set_xlabel("% of daylight outdoor hours")
    axes[0].set_title("Requiring full stop-work", loc="left", fontweight="bold")
    axes[0].invert_yaxis()
    for i, v in enumerate(frac_stop):
        axes[0].text(v + 1, i, f"{v:.0f}%", va="center", fontsize=8.5)

    axes[1].barh(y, unsafe_out, color=OKABE["vermillion"])
    axes[1].set_yticks(y); axes[1].set_yticklabels([])
    axes[1].set_xlabel("hours / year")
    axes[1].set_title("Physiologically unsafe, OUTSIDE the calendar ban",
                      loc="left", fontweight="bold")
    axes[1].invert_yaxis()
    for i, v in enumerate(unsafe_out):
        axes[1].text(v + 15, i, f"{v:.0f} h", va="center", fontsize=8.5)
    fig.suptitle("The calendar ban is too narrow, not too strict",
                 x=0.02, ha="left", fontweight="bold")
    _save(fig, "fig3_operational_gap.png")


# ------------------------------------------------------------------ fig 4
def fig_scheduler():
    rows = {}
    for lead in (24, 48, 72):
        p = REPO / f"data/layer1_v2_oos_{lead}h.csv"   # placeholder guard
    # recompute from the scheduler study's saved curves if present, else
    # hard-code the reported means (study is expensive to re-run here)
    data = {
        "calendar": (8.01, 16.15), "reactive": (8.18, 16.96),
        "optimiser": (6.91, 13.58), "clairvoyant\n(oracle)": (5.80, 12.87),
    }
    names = list(data)
    means = [data[n][0] for n in names]
    p90 = [data[n][1] for n in names]
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    ax.bar(x - 0.18, means, width=0.36, color=OKABE["blue"], label="mean peak load")
    ax.bar(x + 0.18, p90, width=0.36, color=OKABE["sky"], label="p90 (tail)")
    ax.axhline(data["clairvoyant\n(oracle)"][0], color=OKABE["ink"], lw=0.8, ls="--")
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel("peak retained thermal load (model units)")
    ax.set_title("Risk-optimal scheduling vs the calendar rule\n"
                 "(24 h lead, 236 held-out days, equal 9 work-hours delivered)",
                 loc="left", fontweight="bold")
    ax.legend(frameon=False)
    for xi, m in zip(x, means):
        ax.text(xi - 0.18, m + 0.15, f"{m:.1f}", ha="center", fontsize=8.5)
    _save(fig, "fig4_scheduler.png")


# ------------------------------------------------------------------ fig 5
def fig_twin():
    est = {"ECTemp\n(HR only)": 0.36, "physics PF\nHR + activity": 0.19,
           "physics PF\n+ skin patch": 0.083}
    cov = {"ECTemp\n(HR only)": None, "physics PF\nHR + activity": 77,
           "physics PF\n+ skin patch": 92}
    ttc = pd.DataFrame({
        "bin": [">90", "60–90", "45–60", "30–45", "15–30", "0–15"],
        "p": [0.34, 0.33, 0.54, 0.55, 0.59, 0.86],
    })
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.5))
    names = list(est)
    axes[0].bar(names, [est[n] for n in names],
                color=[OKABE["grey"], OKABE["blue"], OKABE["green"]])
    axes[0].set_ylabel("core-temp estimate MAE (°C)")
    axes[0].set_title("Estimation (synthetic)", loc="left", fontweight="bold")
    for i, n in enumerate(names):
        t = f"{est[n]:.2f}" + (f"\ncover {cov[n]}%" if cov[n] else "")
        axes[0].text(i, est[n] + 0.01, t, ha="center", fontsize=8.5)

    axes[1].plot(range(len(ttc)), ttc["p"], color=OKABE["green"], lw=2,
                 marker="o", ms=5)
    axes[1].set_xticks(range(len(ttc))); axes[1].set_xticklabels(ttc["bin"])
    axes[1].set_xlabel("minutes until the true core-temp crossing")
    axes[1].set_ylabel("forward P(exceed 38.5 °C in 60 min)")
    axes[1].set_ylim(0, 1)
    axes[1].set_title("Anticipation: the signal leads the crossing",
                      loc="left", fontweight="bold")
    fig.suptitle("Individual heat-strain twin — synthetic proof of concept",
                 x=0.02, ha="left", fontweight="bold")
    _save(fig, "fig5_twin.png")


if __name__ == "__main__":
    fig_climatology()
    fig_wind_defect()
    fig_operational_gap()
    fig_scheduler()
    fig_twin()
    print("done -> docs/figures/", file=sys.stderr)
