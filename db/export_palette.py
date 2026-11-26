#!/usr/bin/env python3
"""
Maintainer step: export the coloured taxa as the palette committed to the repo,
so users can paint without downloading GTDB.

Reads:  /data/taxa.parquet  (after assign_colours.py)
Writes: palette/gtdb_r232_colours.parquet
"""

import sys
from pathlib import Path

import polars as pl

from paint.palette import BUNDLED_PALETTE, COLUMNS

PARQUET_PATH = Path("/data/taxa.parquet")


def main() -> None:
    if not PARQUET_PATH.exists():
        print(f"ERROR: {PARQUET_PATH} not found — run build-db and assign-colours first", file=sys.stderr)
        sys.exit(1)

    df = pl.read_parquet(PARQUET_PATH)
    if df["hue"].null_count() > 0:
        print("ERROR: taxa have no colours yet — run assign-colours first", file=sys.stderr)
        sys.exit(1)

    # Sorting by lineage puts shared prefixes together, which compresses far better
    BUNDLED_PALETTE.parent.mkdir(parents=True, exist_ok=True)
    df.select(COLUMNS).sort("lineage").write_parquet(
        BUNDLED_PALETTE, compression="zstd", compression_level=19
    )
    size_mb = BUNDLED_PALETTE.stat().st_size / 1e6
    print(f"Wrote {df.height:,} taxa → {BUNDLED_PALETTE} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
