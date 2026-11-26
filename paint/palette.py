"""
The colour palette: one row per GTDB taxon with its assigned colour.

Palettes ship with the repo as palette/gtdb_r<release>_colours.parquet; the newest
release is used. Set GTDB_PALETTE_PATH to paint with a different file.
"""

import os
import re
from pathlib import Path

import polars as pl

PALETTE_DIR = Path(__file__).resolve().parent.parent / "palette"

COLUMNS = [
    "lineage", "rank", "name", "parent_lineage",
    "hue", "saturation", "lightness", "brush_style",
]


def palette_file(release: int) -> Path:
    return PALETTE_DIR / f"gtdb_r{release}_colours.parquet"


def release_of(path: Path) -> int | None:
    found = re.fullmatch(r"gtdb_r(\d+)_colours\.parquet", Path(path).name)
    return int(found.group(1)) if found else None


def newest_palette() -> Path:
    palettes = [p for p in PALETTE_DIR.glob("gtdb_r*_colours.parquet") if release_of(p)]
    if not palettes:
        raise FileNotFoundError(f"no palette in {PALETTE_DIR} — run build-palette")
    return max(palettes, key=release_of)


PALETTE_PATH = Path(os.environ.get("GTDB_PALETTE_PATH") or newest_palette())


def load_palette(path: Path = PALETTE_PATH) -> pl.DataFrame:
    return pl.read_parquet(path, columns=COLUMNS)
