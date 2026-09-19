"""Explainer — what BedWatch Asia is and how to read the demo."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
GFW_CSV = ROOT / "data" / "gfw_trawl_effort.csv"

try:
    st.set_page_config(page_title="Explainer · BedWatch Asia", layout="wide")
except st.errors.StreamlitAPIException:
    pass


def main() -> None:
    st.title("Explainer")
    st.caption("SDG 14 · fishing-bed risk screening for Thailand and the South China Sea")

    st.markdown(
        """
## The problem in one sentence

Bottom trawls can scrape **fishing beds** — seagrass, nurseries, soft-bottom habitat —
while managers often draw a closure line and hope boats simply leave. In practice, effort
often **moves next door**.
        """
    )

    c1, c2, c3 = st.columns(3)
    c1.markdown("**BedWatch**\n\nWhere is seabed risk high *today*, and does a closure leak?")
    c2.markdown("**OceanGuard AI**\n\nWhere may fishing pressure rise *next week*?")
    c3.markdown(
        "**Data badge**\n\n"
        + (
            "This build has **GFW trawler hours** on disk."
            if GFW_CSV.is_file()
            else "No GFW CSV yet — BedWatch falls back to **synthetic** effort."
        )
    )

    st.divider()
    st.subheader("How to read the BedWatch maps")
    st.markdown(
        """
1. Pick **Gulf of Thailand** or **South China Sea** in the sidebar.
2. **Now** — heat is a 0–100 **risk index**: trawl pressure × habitat vulnerability × (1 − recovery).
3. **Closure + displacement** — hours inside the box go to zero; a share is moved to neighbors.
   A warning means **leakage** (a neighbor gained >20 risk points).
4. **Reform procedures** — lighter / bed-safer practices (e.g. no tow on seagrass cells) without
   moving the fleet.
5. **10-year RBS** — illustrative relative benthic status path (Hiddink-style depletion then recovery).

Seagrass-tagged cells are treated as much more sensitive than open mud or sand.
        """
    )

    st.subheader("What the numbers are *not*")
    st.warning(
        "High risk or high hours ≠ proof of illegal fishing, overfishing, or ecological collapse. "
        "This is a **screening** tool for conversation and prioritization — not a stock assessment."
    )
    st.markdown(
        """
- **AIS gaps:** many small Asian trawlers never appear in Global Fishing Watch; true pressure is often higher.
- **Habitat** is a depth proxy plus sparse seagrass points, not a full substrate map.
- **Vulnerability / recovery** tables are hackathon placeholders inspired by published benthic work.
        """
    )

    st.subheader("OceanGuard in one paragraph")
    st.markdown(
        """
OceanGuard trains models on weekly fishing hours to forecast **next week’s apparent effort**,
then scores cells LOW / MEDIUM / HIGH versus that cell’s seasonal historical median.
Open **OceanGuard AI** in the sidebar; train there if artifacts are missing.
        """
    )

    st.subheader("Where to go next")
    st.markdown(
        """
| Page | Use it for |
| --- | --- |
| **BedWatch Asia** | Live risk maps and policy what-ifs |
| **OceanGuard AI** | Pressure forecast dashboard |
| **Setup & docs** | Install, GFW token, fetch script, deploy notes |
        """
    )
    st.info("Live demo repo: https://github.com/akshayanrajendran/bedwatch-asia")


if __name__ == "__main__":
    main()
