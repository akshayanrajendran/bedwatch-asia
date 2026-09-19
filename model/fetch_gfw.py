"""Download GFW AIS apparent fishing effort (trawlers) for Thailand + South China Sea.

Requires a token from https://globalfishingwatch.org/our-apis/
Never commit the token. Put it in a local .env (gitignored):

  cp .env.example .env   # paste into GFW_API_KEY= or GFW_API_TOKEN=
  python3 model/fetch_gfw.py

Writes data/gfw_trawl_effort.csv (date,lat,lon,fishing_hours) for app.py.
API allows max 366 days per report, so this fetches one year at a time.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "gfw_trawl_effort.csv"
ENV_FILE = ROOT / ".env"

LAT_MIN, LAT_MAX = 2.0, 23.0
LON_MIN, LON_MAX = 99.0, 121.0
DATE_START_YEAR = 2018
DATE_END_YEAR = 2023
API = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"


def load_dotenv(path: Path = ENV_FILE) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def resolve_token() -> Optional[str]:
    return (
        os.environ.get("GFW_API_TOKEN")
        or os.environ.get("GFW_API_KEY")
        or os.environ.get("GFW_TOKEN")
    )


def bbox_geojson():
    ring = [
        [LON_MIN, LAT_MIN],
        [LON_MAX, LAT_MIN],
        [LON_MAX, LAT_MAX],
        [LON_MIN, LAT_MAX],
        [LON_MIN, LAT_MIN],
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        ],
    }


def flatten_entries(payload):
    """GFW returns entries as [{dataset: [rows...]}] or {dataset: [rows...]} or [rows]."""
    rows = payload.get("entries") if isinstance(payload, dict) else payload
    if rows is None:
        rows = payload.get("data") if isinstance(payload, dict) else payload
    out = []
    if isinstance(rows, dict):
        for v in rows.values():
            if isinstance(v, list):
                out.extend(v)
        return out
    if isinstance(rows, list):
        for item in rows:
            if isinstance(item, dict) and ("lat" in item or "latitude" in item):
                out.append(item)
            elif isinstance(item, dict):
                for v in item.values():
                    if isinstance(v, list):
                        out.extend(v)
                    elif isinstance(v, dict) and ("lat" in v or "latitude" in v):
                        out.append(v)
        return out
    return []


def parse_table(raw: bytes):
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".csv", ".json"))]
            if not names:
                raise SystemExit("GFW zip had no csv/json payload")
            raw = zf.read(names[0])
    text = raw.decode("utf-8", errors="replace")
    if text.lstrip().startswith("{") or text.lstrip().startswith("["):
        return flatten_entries(json.loads(text))
    return list(csv.DictReader(io.StringIO(text)))


def to_csv_rows(entries):
    """Sum vessel hours into date/lat/lon cells for the Streamlit app."""
    buckets: dict[tuple, float] = defaultdict(float)
    for e in entries:
        lat = e.get("lat", e.get("latitude"))
        lon = e.get("lon", e.get("longitude"))
        hours = e.get("hours", e.get("fishing_hours") or e.get("value"))
        date = e.get("date") or e.get("time") or e.get("year")
        if lat is None or lon is None or hours is None or date is None:
            continue
        date_s = str(date)
        if len(date_s) == 4:
            date_s = f"{date_s}-01-01"
        else:
            date_s = date_s[:10]
        key = (date_s, round(float(lat), 2), round(float(lon), 2))
        buckets[key] += float(hours)
    return [
        {"date": d, "lat": lat, "lon": lon, "fishing_hours": hrs}
        for (d, lat, lon), hrs in sorted(buckets.items())
    ]


def fetch_year(token: str, year: int) -> bytes:
    date_range = f"{year}-01-01,{year}-12-31"
    q = urllib.parse.urlencode(
        {
            "spatial-resolution": "LOW",
            "format": "JSON",
            "temporal-resolution": "YEARLY",
            "datasets[0]": "public-global-fishing-effort:latest",
            "filters[0]": "geartype in ('trawlers')",
            "date-range": date_range,
            "spatial-aggregation": "false",
            "group-by": "FLAG",
        }
    )
    req = urllib.request.Request(
        f"{API}?{q}",
        data=json.dumps({"geojson": bbox_geojson()}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Content-Language": "en-EN",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; bedwatch-asia/1.0; +https://github.com/)",
        },
    )
    # One concurrent report per token — retry 429 until the prior report clears.
    delay = 5.0
    for attempt in range(12):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < 11:
                print(f"  rate-limited; sleep {delay:.0f}s…", flush=True)
                time.sleep(delay)
                delay = min(delay * 1.5, 60.0)
                continue
            print(f"GFW HTTP {exc.code}: {body[:800]}", file=sys.stderr)
            raise SystemExit(1) from exc
    raise SystemExit("GFW still rate-limited after retries")


def main() -> None:
    load_dotenv()
    token = resolve_token()
    if not token:
        print(
            "No GFW token. Put GFW_API_TOKEN=... in .env (gitignored).",
            file=sys.stderr,
        )
        sys.exit(1)
    all_rows = []
    for year in range(DATE_START_YEAR, DATE_END_YEAR + 1):
        print(f"fetching {year}…", flush=True)
        raw = fetch_year(token, year)
        year_rows = to_csv_rows(parse_table(raw))
        print(f"  {len(year_rows)} cells from raw", flush=True)
        all_rows.extend(year_rows)
        time.sleep(5.0)  # let gateway clear concurrent-report lock
    if not all_rows:
        print("GFW returned no trawler cells.", file=sys.stderr)
        sys.exit(1)
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "lat", "lon", "fishing_hours"])
        w.writeheader()
        w.writerows(all_rows)
    print(f"wrote {OUT} ({len(all_rows)} rows)")


if __name__ == "__main__":
    main()
