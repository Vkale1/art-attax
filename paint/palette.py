"""
The colour palette: one row per GTDB taxon with its assigned colour.

A prebuilt palette ships with the repo. Set GTDB_PALETTE_PATH to paint with a
different one (e.g. /data/taxa.parquet from your own assign-colours run).
"""

import os
from pathlib import Path

import polars as pl

BUNDLED_PALETTE = Path(__file__).resolve().parent.parent / "palette" / "gtdb_r232_colours.parquet"
PALETTE_PATH = Path(os.environ.get("GTDB_PALETTE_PATH") or BUNDLED_PALETTE)

COLUMNS = [
    "lineage", "rank", "name", "parent_lineage",
    "hue", "saturation", "lightness", "brush_style",
]


def load_palette(path: Path = PALETTE_PATH) -> pl.DataFrame:
    return pl.read_parquet(path, columns=COLUMNS)
