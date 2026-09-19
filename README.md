# BedWatch Asia

Hackathon product for **SDG 14**: a screening forecast of where inappropriate bottom trawling degrades fishing beds, and whether a closure leaks effort versus reforming gear, depth, and season.

Live app: **[https://bedwatch-asia.streamlit.app](https://bedwatch-asia.streamlit.app)**  
Local: `streamlit run app.py` (Gulf of Thailand + South China Sea). Sidebar: **Explainer**, **OceanGuard AI**, **Setup & docs**.

### Global Fishing Watch (Thailand + South China Sea)

1. Open [GFW APIs](https://globalfishingwatch.org/our-apis/) → **Register** → **Request an API key**.
2. Copy the key into a local `.env` only (never commit it; never paste it into chat):

```bash
cp .env.example .env
# edit .env and set either:
#   GFW_API_KEY=paste_here
#   GFW_API_TOKEN=paste_here   # alias — same value
```

3. Fetch trawler hours into the CSV the risk model already reads:

```bash
python3 model/fetch_gfw.py
streamlit run app.py
```

Or without `.env`: `export GFW_API_TOKEN=your_token` then run the same fetch. The script POSTs a 4Wings report for bbox **lat 2–23, lon 99–121**, filter `geartype in ('trawlers')`, years 2018–2023. The sidebar badge switches from **Synthetic data** to **GFW data**. AIS still undercounts small Thai and Vietnamese boats.

**What it does**
1. Maps annual trawl hours onto 0.25 degree cells.
2. Scores risk = pressure x vulnerability x (1 - recovery), 0-100.
3. Predicts 10-year relative benthic status (Hiddink-style depletion/recovery).
4. Tests two actions: a closure box with effort displacement, and a procedure reform (drop ticklers, no tow on seagrass).
5. Warns if a neighboring cell's risk jumps more than 20 points (leakage).

## Trawl Risk Index (Streamlit)

## Data sources (use these)

| What | Source | Demo website | How we use it |
| --- | --- | --- | --- |
| Seagrass / fishing beds | [UNEP-WCMC seagrass v7.1](https://doi.org/10.34892/x6r3-d211) | [Ocean Data Viewer](https://data.unep-wcmc.org/datasets/7) | Live extract for Palk Bay–Gulf of Mannar is in `data/seagrass_unep_palk.geojson` (10 polygons) and `_pts.geojson` (35 points). REST: [FeatureServer](https://data-gis.unep-wcmc.org/server/rest/services/HabitatsAndBiotopes/Global_Distribution_of_Seagrasses/FeatureServer) (layer 0 points, 1 polygons). No API key. |
| 10 m meadow extent | Allen Coral Atlas seagrass maps | [Atlas zoomed to Palk Bay](https://allencoralatlas.org/atlas/#8.00/9.4500/79.1500) | Best visual for judges; download after accepting Atlas terms. |
| Trawl effort | GFW AIS apparent fishing effort, `geartype in ('trawlers')` | [Global Fishing Watch Map](https://globalfishingwatch.org/map) | Filter Trawlers, search India EEZ / Palk Bay, share a workspace. Tiles/reports need a free [API token](https://globalfishingwatch.org/our-apis/). AIS **undercounts** small Asian trawlers. |
| MPAs | WDPA | [Protected Planet](https://www.protectedplanet.net/en/search-areas?search=Mannar) | Query [WDPA marine FeatureServer](https://data-gis.unep-wcmc.org/server/rest/services/ProtectedSites/WDPA_Marine_and_Coastal/FeatureServer). Mannar shows up as the Ramsar site *Mannar Valaiguda in Tamil*. |
| Depletion / recovery rates | [Hiddink et al. 2017](https://www.pnas.org/doi/10.1073/pnas.1618858114) | paper | Parameters in `model.js` and `model/rbs.py`. |

Palk–Mannar envelope used for the UNEP extract: **78.0–81.5°E, 8.0–11.0°N**.

## Run this demo

```bash
cd ~/bedwatch-asia
python3 -m http.server 8080
```

Open [http://localhost:8080](http://localhost:8080). Left panel **Data & live demos** jumps to GFW, the Atlas, and Ocean Data Viewer.

```bash
python3 -m unittest model/test_rbs.py
python3 model/rbs.py   # regenerates data/palk_forecast.geojson
```

## Trawl Risk Index (Streamlit)

Gulf of Thailand screening demo (bbox lat 5-14, lon 99-106). Grid is 0.25 degree cells.

```bash
pip install -r requirements.txt
streamlit run app.py
```

With a local venv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Optional data files (drop them here; the app falls back to synthetic data if missing):

- `data/gfw_trawl_effort.csv` - columns `date, lat, lon, fishing_hours` (already filtered to trawlers)
- `data/gebco.nc` - GEBCO bathymetry NetCDF, regridded to the 0.25 degree grid

## Publish (Streamlit Community Cloud)

1. Push this repo to GitHub (public).
2. Open [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, and create an app:
   - repository: this repo
   - branch: `main`
   - main file path: `app.py`
3. The live URL is **[https://bedwatch-asia.streamlit.app](https://bedwatch-asia.streamlit.app)** (redeploys from `main` after each push).

## Model (short)

Yearly RBS: `status ← status × (1 − d)^F + r × (1 − status)`.

Inappropriate procedures raise `d` or `F`: tickler chains, towing too shallow on the bed, repeating the same tracks, spawn-season tows, high tow speed. Seagrass `d` is much higher than mud fauna (uprooting).
