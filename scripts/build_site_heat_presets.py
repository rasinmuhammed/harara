"""
Precompute the satellite surface-heat layer for the app's known location
presets and publish them where the API serves static content from
(api/data/site_heat/), the same pattern as api/data/replay/.

This runs offline, not inside a web request: each site is a multi-minute
job (dozens of remote satellite reads), which is not something a free-tier
host should do synchronously on a request. The API only ever serves what
this script has already written.

Run whenever the preset list changes, or every few months to refresh the
climatology (docs/technical_report.md's satellite-heat section states the
refresh cadence).

Usage:
    python scripts/build_site_heat_presets.py
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.build_site_heat_map import build  # noqa: E402

PRESETS = [
    {"name": "Doha", "lat": 25.2854, "lon": 51.531},
    {"name": "Lusail", "lat": 25.43, "lon": 51.49},
    {"name": "Industrial Area", "lat": 25.19, "lon": 51.44},
    {"name": "Al Wakrah", "lat": 25.171, "lon": 51.603},
    {"name": "Mesaieed", "lat": 24.99, "lon": 51.55},
]

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "api" / "data" / "site_heat"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-scenes", type=int, default=None,
                    help="cap per collection per site; omit for the full "
                         "climatology (slow: dozens of remote reads per site)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for p in PRESETS:
        slug = slugify(p["name"])
        print(f"--- {p['name']} ({slug}) ---", file=sys.stderr)
        try:
            summary = build(p["lat"], p["lon"], radius_m=2000, max_scenes=args.max_scenes)
        except Exception as exc:
            print(f"  skipped: {exc}", file=sys.stderr)
            continue

        shutil.copy(summary["png"], OUT_DIR / f"{slug}.png")
        served = {k: v for k, v in summary.items() if k not in ("geotiff", "png")}
        (OUT_DIR / f"{slug}.json").write_text(json.dumps({**served, "name": p["name"]}, indent=2))
        index.append({
            "slug": slug, "name": p["name"], "lat": p["lat"], "lon": p["lon"],
            "typical_difference_c": summary.get("zones", {}).get("typical_difference_c"),
            "cv_rmse_c": summary["cv_rmse_c"],
        })
        print(f"  ok: cv_rmse {summary['cv_rmse_c']} C, "
             f"zones {summary.get('zones', {})}", file=sys.stderr)

    (OUT_DIR / "index.json").write_text(json.dumps({"sites": index}, indent=2))
    print(f"wrote {len(index)} sites to {OUT_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
