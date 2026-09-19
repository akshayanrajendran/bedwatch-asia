# Place Global Fishing Watch apparent fishing effort files here

## Preferred (official static download)

Version 3 AIS-based apparent fishing effort (2012–2024):

- Portal: https://globalfishingwatch.org/dataset-and-code-fishing-effort/
- Zenodo v3: https://zenodo.org/records/14982712

Recommended MVP file for Atlantic Canada:

1. Download **fleet-daily-csvs-10-v3-YYYY.zip** (0.1° daily by flag/gear) for years 2020–2024
   OR monthly fleet CSVs at 0.1°.
2. Unzip into this folder, or place a filtered CSV named:

   `gfw_effort_gulf_st_lawrence.csv`

### Expected GFW fleet schema (v3)

| column | meaning |
| --- | --- |
| date | YYYY-MM-DD |
| lat_bin | southern edge of cell (degrees or 10ths/100ths depending on product) |
| lon_bin | western edge of cell |
| flag | ISO3 flag (optional for MVP) |
| geartype | e.g. trawlers, drifting_longlines (optional) |
| vessel_hours | presence hours |
| fishing_hours | apparent fishing hours |
| mmsi_present | count of MMSIs |

The loader also accepts a simplified schema already filtered to the study region:

`date, lat, lon, fishing_hours`

where `lat`/`lon` are cell centers in WGS84.

## API alternative (BedWatch / Thailand–SCS fetch)

From the **repo root**, put the key in `.env` (`GFW_API_KEY` or `GFW_API_TOKEN` — see `.env.example`), then:

```bash
python3 model/fetch_gfw.py
```

That writes `data/gfw_trawl_effort.csv` for Thailand + South China Sea (trawlers, 2018–2023).
For OceanGuard’s Atlantic Canada pipeline, prefer the static Zenodo download above, or copy a filtered
CSV into this folder with columns `date,lat,lon,fishing_hours`.

## Demo data

`demo_gfw_effort.csv` is **DEMO DATA** for UI and pipeline testing when you do not
yet have a GFW download. It uses the simplified schema and is clearly labeled
`source=DEMO` in the pipeline. Do not treat demo results as real forecasts.
