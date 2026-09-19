"""OceanGuard AI — multipage entry linked from BedWatch Asia."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

# Path setup only — do not call st.set_page_config here (oceanguard-ai/app.py owns it).
OG_ROOT = Path(__file__).resolve().parents[1] / "oceanguard-ai"
sys.path.insert(0, str(OG_ROOT))

runpy.run_path(str(OG_ROOT / "app.py"), run_name="__main__")
