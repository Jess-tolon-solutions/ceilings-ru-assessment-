# Violation data pipeline

Keeps `data.json` (the dataset behind `violation-map.html`) current with public
**Florida DBPR** restaurant inspection records, so the lead-magnet map delivers on
its promise of *live* "what DBPR found near you" data.

## How it works

```
FL DBPR inspection extracts        refresh_dbpr_data.py            data.json
(Districts 1 & 2, CSV)      ──►   download → filter → aggregate   ──►  (map fetches it)
                                  → geocode (cached)
```

- **Source:** `https://www2.myfloridalicense.com/sto/file_download/extracts/{n}fdinspi.csv`
  - District **1** = Miami-Dade · District **2** = Broward + Palm Beach
  - One row per inspection; violations are count columns `Violation 01`–`Violation 58`.
- **Filter:** inspections citing **Violation 36** — *"floors, walls, ceilings &
  attached equipment properly constructed and clean; rooms and equipment properly
  vented"* — i.e. the ceiling/vent code. Limited to the 3 South FL counties and the
  last 18 months.
- **Focus:** keeps `HOT` + `WARM` priority establishments, worst-first, capped at
  `MAX_RECORDS` (default 300). Tune both knobs at the top of `refresh_dbpr_data.py`.
- **Geocode:** US Census batch geocoder → Nominatim fallback, with a persistent
  `geocode_cache.json` so repeat addresses are never re-queried.
- **Output:** `../data.json` — `{ updated, source, coverage, filter, count, restaurants[] }`.
  The map fetches this; if it's missing (e.g. opened from `file://`), the map falls
  back to the inline snapshot baked into `violation-map.html`.

## Run it manually

```bash
python3 scripts/refresh_dbpr_data.py   # stdlib only, no pip install
```

## Automation

`.github/workflows/refresh-data.yml` runs the script every **Monday 08:00 UTC**
(and on-demand via the Actions tab), committing `data.json` + `geocode_cache.json`
only when something changed.

## Maintenance notes

- The DBPR column layout isn't guaranteed stable. The parser resolves columns by
  name (with a contains-fallback) and **aborts loudly listing the real headers** if a
  required column goes missing — so a layout change is obvious, not silent.
- `data.sample.json` is the original hand-curated 46-record snapshot, kept for
  reference / as a known-good shape.
- Verify the code list against the authoritative PDF if filtering ever looks off:
  `https://www2.myfloridalicense.com/hr/food-lodging/food-violations.pdf`.
