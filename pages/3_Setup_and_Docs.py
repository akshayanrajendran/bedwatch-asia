"""Setup & documentation for the BedWatch Asia Streamlit suite."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
GFW_CSV = ROOT / "data" / "gfw_trawl_effort.csv"
ENV_EXAMPLE = ROOT / ".env.example"
OG_CFG = ROOT / "oceanguard-ai" / "config" / "config.yaml"

try:
    st.set_page_config(page_title="Setup & Docs · BedWatch Asia", layout="wide")
except st.errors.StreamlitAPIException:
    pass


def _badge(ok: bool, yes: str, no: str) -> str:
    return f"✅ {yes}" if ok else f"⚠️ {no}"


def main() -> None:
    st.title("Setup & docs")
    st.caption(
        "How to run BedWatch Asia + OceanGuard AI locally, wire Global Fishing Watch data, "
        "and what each page is for."
    )

    gfw_ok = GFW_CSV.is_file()
    env_ok = (ROOT / ".env").is_file()
    st.subheader("This checkout")
    c1, c2, c3 = st.columns(3)
    c1.markdown(_badge(gfw_ok, "GFW CSV present → BedWatch shows **GFW data**", "No GFW CSV → BedWatch uses **synthetic** effort"))
    c2.markdown(_badge(env_ok, "Local `.env` found (token stays off git)", "No `.env` yet — copy from `.env.example` to refetch"))
    c3.markdown(
        _badge(
            OG_CFG.is_file(),
            "OceanGuard config present",
            "OceanGuard config missing",
        )
    )
    if gfw_ok:
        st.caption(f"`{GFW_CSV.relative_to(ROOT)}` — trawler hours for Thailand + South China Sea.")

    st.divider()
    st.subheader("1. What this suite does")
    st.markdown(
        """
| Page | Purpose |
| --- | --- |
| **BedWatch Asia** (home) | Seabed / fishing-bed **risk screening** for the **Gulf of Thailand** and **South China Sea**. Scores pressure × habitat vulnerability, tests a closure (with effort leakage) vs gear/procedure reform, and shows a 10-year relative benthic status path. |
| **Explainer** | Plain-language story: problem, how to read the maps, what the numbers are not. |
| **OceanGuard AI** | **Next-week fishing-pressure** forecast + LOW/MEDIUM/HIGH risk vs seasonal baseline. Same Streamlit app, separate ML pipeline under `oceanguard-ai/`. |
| **Setup & docs** (this page) | Run instructions, GFW token setup, data paths, and honest limits. |

**Framing:** screening and early warning for **SDG 14**. High hours or high risk ≠ proven illegal fishing, overfishing, or stock collapse.
        """
    )

    st.subheader("2. Run the app")
    st.markdown("From the repo root:")
    st.code(
        """python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py""",
        language="bash",
    )
    st.markdown(
        """
Open the URL Streamlit prints (usually `http://localhost:8501`). Use the **sidebar page list** to switch
BedWatch ↔ OceanGuard ↔ this docs page.

**Requirements:** Python 3.9+, packages in `requirements.txt` (Streamlit, pandas, pydeck, scikit-learn, etc.).
        """
    )

    st.subheader("3. Global Fishing Watch token (BedWatch real effort)")
    st.markdown(
        """
BedWatch reads `data/gfw_trawl_effort.csv` if present. To (re)build that file:

1. Register and request a key at [Global Fishing Watch APIs](https://globalfishingwatch.org/our-apis/).
2. Copy the template and paste the key **only** into a local `.env` (gitignored — never commit, never paste into chat):
        """
    )
    st.code(
        """cp .env.example .env
# edit .env — either name works:
#   GFW_API_KEY=your_key_here
#   GFW_API_TOKEN=your_key_here""",
        language="bash",
    )
    if ENV_EXAMPLE.is_file():
        with st.expander("`.env.example` contents"):
            st.code(ENV_EXAMPLE.read_text(encoding="utf-8"), language="bash")
    st.markdown(
        """
3. Fetch year-by-year trawler reports (bbox **lat 2–23, lon 99–121**, years 2018–2023):
        """
    )
    st.code("python3 model/fetch_gfw.py", language="bash")
    st.markdown(
        """
The script POSTs to GFW **4Wings report**, flattens nested vessel rows into grid cells
(`date,lat,lon,fishing_hours`), and retries HTTP 429 (one concurrent report per token).

4. Restart Streamlit. Sidebar badge should switch from **Synthetic data** to **GFW data**.

**AIS caveat:** many small Thai / Vietnamese trawlers lack AIS — true pressure is often higher than the map.
        """
    )

    st.subheader("4. Optional inputs")
    st.markdown(
        """
| File | Effect if present |
| --- | --- |
| `data/gfw_trawl_effort.csv` | Real trawler hours for BedWatch |
| `data/gebco.nc` | Bathymetry instead of synthetic depth |
| `data/seagrass_unep_palk_pts.geojson` | Seagrass proximity tags on cells |
| `oceanguard-ai/data/raw/*.csv` | Real effort for OceanGuard training (else DEMO CSV) |

Without these, BedWatch still runs on **synthetic** coastal hotspots so demos never hard-crash.
        """
    )

    st.subheader("5. OceanGuard AI")
    st.markdown(
        """
- Open **OceanGuard AI** in the sidebar.
- If no trained artifacts exist, click **Train models now** (uses DEMO or any CSV in `oceanguard-ai/data/raw/`).
- Region and grid are set in `oceanguard-ai/config/config.yaml` (edit `region:` then retrain).
- To reuse BedWatch’s Asia GFW file, copy or symlink it into `oceanguard-ai/data/raw/` as a
  `date,lat,lon,fishing_hours` CSV (annual cells work after weekly aggregation / expansion in the pipeline).

OceanGuard predicts **apparent fishing hours next week** vs a seasonal baseline. It does **not** claim IUU or ecological damage.
        """
    )

    st.subheader("6. Repo layout (quick map)")
    st.code(
        """bedwatch-asia/
  app.py                      # BedWatch home page
  pages/
    1_Explainer.py            # product explainer
    2_OceanGuard_AI.py        # launches oceanguard-ai/app.py
    3_Setup_and_Docs.py       # this page
  model/fetch_gfw.py          # GFW → data/gfw_trawl_effort.csv
  data/                       # effort, optional GEBCO / seagrass
  oceanguard-ai/              # ML forecast pipeline + its own app
  .env.example                # token template (commit)
  .env                        # real token (local only)""",
        language="text",
    )

    st.subheader("7. Deploy notes")
    st.markdown(
        """
- **GitHub:** public repo is fine; keep secrets out of git (`.env` is gitignored).
- **Streamlit Community Cloud:** point at `app.py`. Add `GFW_API_TOKEN` only if you run fetch in CI;
  for the live demo, commit the CSV (no token needed at runtime) or accept synthetic fallback.
- Rotate any API token that was ever pasted into chat or committed by mistake.
        """
    )

    with st.expander("Methodology (short)"):
        st.markdown(
            """
- **BedWatch risk:** min–max normalize fishing hours → pressure; multiply by depth/habitat
  vulnerability and `(1 − recovery)`; scale 0–100. Inspired by Hiddink-style depletion/recovery ideas;
  parameters are illustrative.
- **Closure test:** zero effort inside a box; move a share of hours to neighboring cells; warn if a
  neighbor’s risk jumps by more than 20 points (**leakage**).
- **OceanGuard risk:** predicted hours vs cell×week-of-year historical median → pressure ratio
  percentile → LOW / MEDIUM / HIGH.
            """
        )

    with st.expander("Limitations"):
        st.markdown(
            """
- AIS undercounts dark / small fleets.
- Habitat is a depth proxy plus sparse seagrass points, not a full substrate map.
- Vulnerability and recovery tables are placeholders for a hackathon screen, not a stock assessment.
- OceanGuard DEMO DATA is for UI/pipeline testing only until real effort CSVs are trained.
            """
        )

    st.info(
        "Need the code path again? README at the repo root mirrors this page for terminal workflows."
    )


if __name__ == "__main__":
    main()
