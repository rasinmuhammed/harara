# Loop B, Step 0: open physiology data for external validation of the heat-strain filter

Date: 2026-09-09. Question: is there real, downloadable human data with a
gold-standard core-temperature reference (rectal probe or ingestible capsule)
synchronised with heart rate, and ideally skin temperature, during exercise or
heat exposure, that can validate `src/heat_strain_filter.py` outside the
synthetic study (ledger rows 16/17)?

## Candidates checked

| Dataset | Source / access | N | Signals | Reference | Licence | Verdict |
|---|---|---|---|---|---|---|
| **PROSPIE (Loughborough)** | figshare DOI `10.17028/rd.lboro.26076577.v1`, direct file `ndownloader.figshare.com/files/47227096`, **downloaded, md5 verified** | 21 (study 1: 12 M, 9 F) + 36 (study 2: 21 M, 15 F), 136 trials | HR (Polar), rectal temp, 11-site skin temp, insulated skin temp, breathing rate, microclimate T/RH, treadmill speed/grade, VO2 (sparse), sweat rate, RPE | **Rectal probe, 10 cm, "gold standard"** | **CC BY-NC 4.0** | **USABLE.** Open, gold reference, HR + skin present, 1-min resolution, wide range of climates (25/35/40 C) and clothing (permeable / impermeable / +solar). |
| Eggenberger et al. 2018, *Front. Physiol.* (PMC6295644) | "available on request to the authors", no repository | 13 M | HR, rectal temp, multi-site skin temp, skin heat flux, 0.1 Hz | Rectal | CC BY (paper only) | Not open. On-request only. |
| Falcone et al. 2024, *Front. Public Health* (PMC10961439) | "available on request", no repository | 13 (7 M, 6 F) | HR (Polar), ingestible capsule (CorTemp), **no skin temp** | Ingestible capsule | CC BY (paper only) | Not open; also no skin channel. |
| Richmond et al. treadmill set (Dataset 1 in the 2026 *Build. Environ.* review, PMC13328076) | none given | 16 (8 M, 8 F) | HR, rectal, 11-site skin | Rectal | — | This is the same PROSPIE lineage (Havenith / Richmond); the openly posted PROSPIE workbook is the usable instance. |
| 2026 *Build. Environ.* standardized-evaluation review | no data-availability statement, no benchmark release | — | — | — | — | Review only; neither of its two datasets is posted. |
| "Degrees of uncertainty" 2025, *Commun. Eng.* (PMC12727793) | Uses PROSPIE (FACT domain) openly; five other operational domains (wildland fire, race car, mine, nuclear, EOD) are **third-party restricted**; code proprietary | 251 pooled, PROSPIE part is the open slice | CBT (pill or rectal), HR, chest skin T, ambient T/RH, work intensity, clo | Mixed | CC BY 4.0 (paper); PROSPIE slice CC BY-NC | Confirms PROSPIE is the open, citable core-temp benchmark. Gives a published baseline point: their model RMSE 0.29 C vs ECTemp (HR-only EKF) 0.34 C on this data. |
| PhysioNet thermoregulation search | — | — | wrist/ambient temp only in the near matches | not gold | — | No gold core-temp + HR exercise set found on PhysioNet. |

## Recommendation

Proceed with Loop B using the **PROSPIE dataset** (`data/prospie/prospie.xlsx`,
already downloaded, md5 `cdbdb0795d3c5d2923d199466513c163`).

- It meets the gold-standard bar the brief set (rectal reference), carries HR
  and 11-site skin temperature, and is openly downloadable under a stated
  licence.
- The licence is **CC BY-NC 4.0** (non-commercial). Use here is non-commercial
  research validation for the technical report; the workbook is not
  redistributed in the repo as anything other than an input, and the report
  will cite the DOI. If Harara is later commercialised, this validation would
  need re-running on a differently licensed set or a pilot.
- Published baseline to beat / match: **ECTemp-class HR-only Kalman filter**,
  ~0.34 C RMSE on this data (Commun. Eng. 2025). Our filter target is to beat
  HR-only; the synthetic 0.083 C MAE is not expected to transfer.

## Domain shift to state plainly in the report

- Population: European lab volunteers, not Gulf outdoor workers.
- Protocol: treadmill walking in a climate chamber, 40-60 min bouts with a rest
  break, clothing-focused (permeable / impermeable / CBRN-style). Not
  free-living construction work.
- Reference: rectal probe, not the ingestible capsule the twin brief assumes;
  equivalent gold standard, slightly slower response.
- Sensors: research thermistors, not the cheap wearable patch the product
  assumes. Skin channel is better than a product patch would be.
- No solar load on the body core model beyond what the chamber provides; some
  trials add 600 W/m^2 radiant.

## Data-availability line for the ledger

Checked Zenodo, PhysioNet, figshare, OSF, and the datasets behind Eggenberger
2018 and the 2026 Building and Environment review. One openly downloadable
gold-standard set exists: PROSPIE (Loughborough, `10.17028/rd.lboro.26076577`),
rectal reference plus HR and 11-site skin temperature, CC BY-NC 4.0. Loop B
proceeds on it.
