"""Shared config loader for OceanGuard AI."""
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Optional[Path] = None) -> dict:
    cfg_path = path or (ROOT / "config" / "config.yaml")
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def abs_path(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p
