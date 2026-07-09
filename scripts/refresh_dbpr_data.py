#!/usr/bin/env python3
"""
Refresh the Ceilings R Us violation map dataset from public FL DBPR records.

Pipeline:
  1. Download the per-district food-service inspection extracts from FL DBPR.
       District 1 -> Miami-Dade (+ Monroe)
       District 2 -> Broward + Palm Beach (+ Martin)
  2. Keep only Broward / Miami-Dade / Palm Beach establishments.
  3. Keep only inspections that cite VIOLATION 36 -- the DBPR code for
     "Floors, walls, ceilings and attached equipment properly constructed and
      clean; rooms and equipment properly vented." (i.e. the ceiling/vent code).
  4. Aggregate per establishment: total violations, high-priority count,
     ceiling/vent (V36) count, latest inspection date + disposition, a priority
     tier, and a synthesized description (the extract carries counts, not text).
  5. Geocode each address (US Census batch geocoder -> Nominatim fallback) with a
     persistent on-disk cache so we never re-query an address we've resolved.
  6. Write ../data.json in the shape the map expects.

Layout note (verified against the live District 2 extract, 82 columns):
  This is the legacy numbered format. Violations are COUNT COLUMNS "Violation 01"
  .. "Violation 58" -- each holds how many times that numbered violation was cited
  in the inspection. There is no free-text description in the file, so popup text
  is synthesized. Column headers are resolved by name (with a contains-fallback)
  so a layout shuffle won't silently break parsing -- it aborts loudly instead.
  Layout reference:
    https://myfloridalicense.com/dbpr/sto/file_download/layout/public-records-hr.html

Run:  python3 scripts/refresh_dbpr_data.py
Deps: standard library only.  No pip install required.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT_PATH = os.path.join(REPO, "data.json")
GEOCACHE_PATH = os.path.join(HERE, "geocode_cache.json")

DBPR_EXTRACT_URL = "https://www2.myfloridalicense.com/sto/file_download/extracts/{n}fdinspi.csv"
DISTRICTS = [1, 2]  # 1 = Miami-Dade, 2 = Broward + Palm Beach

TARGET_COUNTIES = {"BROWARD", "MIAMI-DADE", "MIAMI DADE", "DADE", "PALM BEACH", "MONROE"}
TARGET_ZIP_PREFIXES = ("330", "331", "332", "333", "334")

# The ceiling/wall/vent code in the numbered DBPR scheme.
CEILING_VENT_COLUMN = "Violation 36"
CEILING_VENT_LABEL = (
    "Violation 36 — Floors, walls, ceilings & attached equipment not "
    "properly constructed/clean, or rooms/equipment not properly vented "
    "(ceiling tiles, vent covers, exhaust/HVAC)."
)

RECENT_DAYS = 60  # rolling window: only surface inspections from the last N days

# Show the full picture of recent activity: every establishment with a ceiling/vent
# (V36) citation in the window, across all priority tiers. Narrow PRIORITY_KEEP to
# {"HOT", "WARM"} if you ever want to trim low-signal single-cite records again.
PRIORITY_KEEP = {"HOT", "WARM", "MONITOR"}
MAX_RECORDS = 300                 # cap markers / geocode calls; worst-first

USER_AGENT = "CeilingsRUs-ViolationMap/1.0 (+https://github.com/Jess-tolon-solutions/ceilings-ru-assessment-)"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download_extract(district: int) -> str:
    url = DBPR_EXTRACT_URL.format(n=district)
    print(f"  downloading district {district}: {url}")
    return _get(url).decode("latin-1", errors="replace")


# --------------------------------------------------------------------------- #
# Column resolution (resilient to header reshuffles / whitespace quirks)
# --------------------------------------------------------------------------- #

COLUMN_CANDIDATES = {
    "name": ["businessdbadoesbusinessasname", "businessname", "dbaname", "business"],
    "address": ["locationaddress", "address"],
    "city": ["locationcity", "city"],
    "zip": ["locationzipcode", "zipcode", "zip"],
    "county": ["countyname", "county"],
    "license": ["licensenumber", "license"],
    "inspection_date": ["inspectiondate", "visitdate"],
    "disposition": ["inspectiondisposition", "disposition"],
    "total_violations": ["numberoftotalviolations", "totalviolations"],
    "high_priority": ["numberofhighpriorityviolations", "highpriorityviolations"],
    "intermediate": ["numberofintermediateviolations", "intermediateviolations"],
    "v36": ["violation36"],
}
REQUIRED = ["name", "address", "license", "inspection_date", "v36"]


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def resolve_columns(headers: list[str]) -> dict[str, str]:
    norm_map = {_norm(h): h for h in headers}
    resolved: dict[str, str] = {}
    for logical, candidates in COLUMN_CANDIDATES.items():
        # 1) exact normalized match
        for cand in candidates:
            if cand in norm_map:
                resolved[logical] = norm_map[cand]
                break
        if logical in resolved:
            continue
        # 2) contains-fallback (first header that contains a candidate token)
        for cand in candidates:
            hit = next((orig for nh, orig in norm_map.items() if cand in nh), None)
            if hit:
                resolved[logical] = hit
                break
    return resolved


def abort_with_headers(headers: list[str], resolved: dict[str, str]) -> None:
    print("\nERROR: could not map required DBPR columns.", file=sys.stderr)
    print("Confirm the layout and update COLUMN_CANDIDATES:", file=sys.stderr)
    print("  https://myfloridalicense.com/dbpr/sto/file_download/layout/public-records-hr.html\n",
          file=sys.stderr)
    print("Actual headers:", file=sys.stderr)
    for h in headers:
        print(f"    {h}", file=sys.stderr)
    print("\nResolved:", file=sys.stderr)
    for k, v in resolved.items():
        print(f"    {k:18s} -> {v}", file=sys.stderr)
    print(f"\nMissing required: {[r for r in REQUIRED if r not in resolved]}", file=sys.stderr)
    sys.exit(2)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def to_int(s: str) -> int:
    try:
        return int(float((s or "").strip() or 0))
    except (ValueError, TypeError):
        return 0


def parse_date(s: str):
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return time.strptime(s, fmt)
        except ValueError:
            continue
    return None


def in_target_area(county: str, zipcode: str) -> bool:
    if county and county.strip().upper() in TARGET_COUNTIES:
        return True
    return (zipcode or "").strip()[:3] in TARGET_ZIP_PREFIXES


def priority_tier(hp_count: int, v36_count: int, disposition: str) -> str:
    d = (disposition or "").lower()
    if "emergency" in d or "administrative complaint" in d or hp_count >= 6:
        return "HOT"
    if v36_count >= 2 or hp_count >= 2 or "warning" in d:
        return "WARM"
    return "MONITOR"


def outreach_hook(total: int, hp: int, v36: int, disposition: str) -> str:
    bits = [f"{total} violation{'s' if total != 1 else ''}"]
    if v36:
        bits.append(f"{v36}x ceiling/vent (V36)")
    if hp:
        bits.append(f"{hp} high-priority")
    if disposition:
        bits.append(disposition.lower())
    return " + ".join(bits)


# --------------------------------------------------------------------------- #
# Aggregation: one row per inspection -> one record per establishment
# --------------------------------------------------------------------------- #

def aggregate(rows: list[dict], cols: dict) -> list[dict]:
    cutoff = date.today() - timedelta(days=RECENT_DAYS)

    by_license: dict[str, dict] = {}
    for row in rows:
        g = lambda k: (row.get(cols.get(k, ""), "") or "").strip()
        v36 = to_int(g("v36"))
        if v36 <= 0:
            continue  # not a ceiling/vent inspection
        if not in_target_area(g("county"), g("zip")):
            continue
        d = parse_date(g("inspection_date"))
        if d and date(d.tm_year, d.tm_mon, d.tm_mday) < cutoff:
            continue

        zipcode = g("zip")
        lic = g("license") or g("name")
        total = to_int(g("total_violations"))
        hp = to_int(g("high_priority"))
        disposition = g("disposition")

        rec = by_license.get(lic)
        if rec is None or (d and rec["_date"] and d > rec["_date"]) or (rec and rec["_date"] is None and d):
            # keep the most recent inspection per establishment
            county = g("county").title()
            if county.upper() in ("DADE", "MIAMI DADE"):
                county = "Miami-Dade"
            rec = {
                "name": g("name").title(),
                "address": ", ".join(p for p in [g("address"), g("city").title(),
                                                  f"FL {zipcode}".strip()] if p),
                "city": g("city").title(),
                "county": county,
                "zip": zipcode,
                "license": g("license"),
                "totalViolations": total,
                "hpViolations": hp,
                "v36Count": v36,
                "disposition": disposition,
                "latest_inspection": g("inspection_date"),
                "_date": d,
            }
            by_license[lic] = rec

    out = []
    ranked = sorted(by_license.values(),
                    key=lambda r: (r["hpViolations"] * 3 + r["totalViolations"]),
                    reverse=True)
    ranked = [r for r in ranked
              if priority_tier(r["hpViolations"], r["v36Count"], r["disposition"]) in PRIORITY_KEEP]
    ranked = ranked[:MAX_RECORDS]
    for i, rec in enumerate(ranked, start=1):
        viols = [{
            "description": CEILING_VENT_LABEL if rec["v36Count"] == 1
            else CEILING_VENT_LABEL + f" Cited {rec['v36Count']}x.",
            "severity": "High Priority",
            "date": rec["latest_inspection"],
            "disposition": rec["disposition"],
        }]
        if rec["hpViolations"]:
            viols.append({
                "description": f"{rec['hpViolations']} high-priority violation(s) cited "
                               "— items requiring immediate corrective action per DBPR standards.",
                "severity": "High Priority",
                "date": rec["latest_inspection"],
                "disposition": "",
            })
        out.append({
            "id": i,
            "name": rec["name"],
            "address": rec["address"],
            "county": rec["county"],
            "lat": None,
            "lng": None,
            "totalViolations": rec["totalViolations"],
            "hpViolations": rec["hpViolations"],
            "v36Count": rec["v36Count"],
            "disposition": rec["disposition"],
            "priority": priority_tier(rec["hpViolations"], rec["v36Count"], rec["disposition"]),
            "license": rec["license"],
            "latest_inspection": rec["latest_inspection"],
            "outreach_hook": outreach_hook(rec["totalViolations"], rec["hpViolations"],
                                           rec["v36Count"], rec["disposition"]),
            "violations": viols,
        })
    return out


# --------------------------------------------------------------------------- #
# Geocoding (US Census batch -> Nominatim fallback) with persistent cache
# --------------------------------------------------------------------------- #

def load_cache() -> dict:
    if os.path.exists(GEOCACHE_PATH):
        try:
            return json.load(open(GEOCACHE_PATH))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(cache: dict) -> None:
    json.dump(cache, open(GEOCACHE_PATH, "w"), indent=0)


def census_geocode_one(addr: str):
    base = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
    qs = urllib.parse.urlencode({"address": addr, "benchmark": "Public_AR_Current", "format": "json"})
    try:
        data = json.loads(_get(f"{base}?{qs}", timeout=30))
        matches = data.get("result", {}).get("addressMatches", [])
        if matches:
            c = matches[0]["coordinates"]
            return (round(c["y"], 6), round(c["x"], 6))  # y=lat, x=lng
    except Exception as e:  # noqa: BLE001
        print(f"    census geocode failed for {addr!r}: {e}")
    return None


def nominatim_geocode_one(addr: str):
    base = "https://nominatim.openstreetmap.org/search"
    qs = urllib.parse.urlencode({"q": addr, "format": "json", "limit": 1, "countrycodes": "us"})
    try:
        data = json.loads(_get(f"{base}?{qs}", timeout=30))
        if data:
            return (round(float(data[0]["lat"]), 6), round(float(data[0]["lon"]), 6))
    except Exception as e:  # noqa: BLE001
        print(f"    nominatim geocode failed for {addr!r}: {e}")
    return None


def geocode_records(records: list[dict]) -> None:
    cache = load_cache()
    for rec in records:
        key = rec["address"].upper().strip()
        if cache.get(key):
            rec["lat"], rec["lng"] = cache[key]
            continue
        coords = census_geocode_one(rec["address"])
        if not coords:
            coords = nominatim_geocode_one(rec["address"])
            time.sleep(1.1)  # Nominatim policy: <= 1 req/sec
        if coords:
            rec["lat"], rec["lng"] = coords
            cache[key] = coords
            save_cache(cache)
    save_cache(cache)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    all_rows: list[dict] = []
    cols: dict = {}
    for d in DISTRICTS:
        try:
            text = download_extract(d)
        except Exception as e:  # noqa: BLE001
            print(f"  WARNING: could not download district {d}: {e}", file=sys.stderr)
            continue
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        resolved = resolve_columns(headers)
        if not all(r in resolved for r in REQUIRED):
            abort_with_headers(headers, resolved)
        cols = resolved
        rows = list(reader)
        print(f"  district {d}: {len(rows)} inspection rows")
        all_rows.extend(rows)

    if not all_rows:
        print("No rows downloaded — leaving existing data.json untouched.", file=sys.stderr)
        return 1

    records = aggregate(all_rows, cols)
    print(f"  {len(records)} establishments cited Violation 36 (ceiling/vent)")

    geocode_records(records)
    records = [r for r in records if r["lat"] is not None and r["lng"] is not None]
    for i, r in enumerate(records, start=1):
        r["id"] = i
    print(f"  {len(records)} geocoded successfully")

    out = {
        "updated": date.today().isoformat(),
        "source": "Florida DBPR, Division of Hotels & Restaurants — public inspection extracts (Districts 1 & 2)",
        "coverage": ["Miami-Dade", "Broward", "Palm Beach", "Monroe"],
        "filter": "Inspections citing Violation 36 — floors/walls/ceilings/attached equipment not "
                  "properly constructed or clean, or rooms/equipment not properly vented.",
        "count": len(records),
        "restaurants": records,
    }
    json.dump(out, open(OUT_PATH, "w"), indent=2, ensure_ascii=False)
    print(f"Wrote {OUT_PATH} with {len(records)} restaurants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
