#!/usr/bin/env python3
"""
Phase 2: Walk the GTDB taxonomy tree → assign colour + brush style.

Reads:  /data/gtdb_r232.duckdb  (taxa table with NULL colour columns)
Writes: hue/saturation/lightness/brush_style into taxa table
        refreshes /data/taxa.parquet
"""

import math
from collections import defaultdict
from pathlib import Path

import duckdb
import polars as pl

DATA_DIR = Path("/data")
DB_PATH = DATA_DIR / "gtdb_r232.duckdb"
PARQUET_PATH = DATA_DIR / "taxa.parquet"

RANKS = ["domain", "phylum", "class", "order", "family", "genus", "species"]

BRUSH_BY_RANK = {
    "domain":  "wash",
    "phylum":  "broad",
    "class":   "medium_broad",
    "order":   "medium",
    "family":  "medium_fine",
    "genus":   "fine",
    "species": "hair",
}

# Muted, like mixed oil paint (median tones of example.jpg)
BASE_SATURATION = 0.45
BASE_LIGHTNESS = 0.51

# Largest (lightness, saturation) change a taxon of this rank makes to its parent's tone
TONE_SHIFT = {
    "class":  (0.10, 0.10),
    "order":  (0.07, 0.10),
    "family": (0.04, 0.05),
}

# Golden-ratio steps spread any number of siblings evenly without repeats
GOLDEN = (math.sqrt(5) - 1) / 2


def load_taxa(db_path: Path) -> pl.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(
            "SELECT taxon_id, lineage, rank, parent_lineage FROM taxa ORDER BY taxon_id"
        ).pl()
    finally:
        con.close()


def species_counts(lineages: list[str]) -> dict[str, int]:
    """Number of species under every lineage (a species counts itself)."""
    counts: dict[str, int] = defaultdict(int)
    for lineage in lineages:
        parts = lineage.split(";")
        if len(parts) == len(RANKS):
            for depth in range(1, len(parts) + 1):
                counts[";".join(parts[:depth])] += 1
    return counts


def colour_tree(df: pl.DataFrame) -> tuple[list[float], list[float], list[float]]:
    """
    Share the colour wheel out down the taxonomy, like slices of cake.

    Each taxon owns a slice of hues, which its children divide between them.
    Slices are weighted by the square root of species count, so big clades get
    more range without taking over. A taxon's hue is the middle of its slice.
    Classes, orders and families also shift lightness and saturation, and their
    descendants inherit the shift, so relatives in one slice stay distinguishable.

    Returns (hue, saturation, lightness) lists in df row order.
    """
    counts = species_counts(df["lineage"].to_list())
    children: dict[str, list[str]] = defaultdict(list)
    ranks: dict[str, str] = {}
    roots = []
    for lineage, rank, parent in df.select("lineage", "rank", "parent_lineage").iter_rows():
        ranks[lineage] = rank
        if parent is None:
            roots.append(lineage)
        else:
            children[parent].append(lineage)

    # lineage → (slice start, slice end, saturation, lightness)
    placed = {r: (0.0, 360.0, BASE_SATURATION, BASE_LIGHTNESS) for r in roots}
    queue = list(roots)
    while queue:
        parent = queue.pop()
        kids = children.get(parent)
        if not kids:
            continue
        start, end, p_sat, p_light = placed[parent]
        kids.sort(key=lambda k: (-counts[k], k))
        step = {kid: (i * GOLDEN) % 1 for i, kid in enumerate(kids)}

        # Scatter big phyla around the wheel instead of bunching them together
        in_order = sorted(kids, key=step.get) if ranks[kids[0]] == "phylum" else kids
        total = sum(math.sqrt(counts[k]) for k in kids)
        cursor = start
        for kid in in_order:
            span = (end - start) * math.sqrt(counts[kid]) / total
            d_light, d_sat = TONE_SHIFT.get(ranks[kid], (0.0, 0.0))
            # The biggest child keeps its parent's tone; siblings alternate around it
            offset = 2 * step[kid] if step[kid] < 0.5 else 2 * step[kid] - 2
            placed[kid] = (
                cursor, cursor + span,
                p_sat + d_sat * offset,
                p_light + d_light * offset,
            )
            cursor += span
        queue.extend(kids)

    hue, saturation, lightness = [], [], []
    for lineage in df["lineage"].to_list():
        start, end, sat, light = placed[lineage]
        hue.append(((start + end) / 2) % 360)
        saturation.append(sat)
        lightness.append(light)
    return hue, saturation, lightness


def write_colours(
    db_path: Path,
    df: pl.DataFrame,
    hue: list[float],
    saturation: list[float],
    lightness: list[float],
) -> None:
    brush = df["rank"].map_elements(
        lambda r: BRUSH_BY_RANK.get(r, "medium"), return_dtype=pl.String
    )
    updates = pl.DataFrame({
        "taxon_id":    df["taxon_id"],
        "hue":         pl.Series(hue, dtype=pl.Float64),
        "saturation":  pl.Series(saturation, dtype=pl.Float64),
        "lightness":   pl.Series(lightness, dtype=pl.Float64),
        "brush_style": brush,
    })
    con = duckdb.connect(str(db_path))
    try:
        con.register("updates", updates)
        con.execute("""
            UPDATE taxa
               SET hue         = updates.hue,
                   saturation  = updates.saturation,
                   lightness   = updates.lightness,
                   brush_style = updates.brush_style
              FROM updates
             WHERE taxa.taxon_id = updates.taxon_id
        """)
    finally:
        con.close()


def refresh_parquet(db_path: Path, parquet_path: Path) -> None:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute("SELECT * FROM taxa").pl()
    finally:
        con.close()
    df.write_parquet(str(parquet_path))


def print_sample(db_path: Path) -> None:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("""
            SELECT rank, name, hue, saturation, lightness, brush_style
              FROM taxa
             ORDER BY rank, taxon_id
             LIMIT 14
        """).fetchall()
    finally:
        con.close()
    print(f"\n  {'rank':<12} {'name':<35} {'hue':>7} {'sat':>6} {'lig':>6}  brush")
    for rank, name, h, s, l, b in rows:
        print(f"  {rank:<12} {name:<35} {h:>7.1f} {s:>6.3f} {l:>6.3f}  {b}")


def main() -> None:
    print(f"Loading taxa from {DB_PATH} ...")
    df = load_taxa(DB_PATH)
    print(f"  {len(df):,} taxa loaded")

    print("Sharing out the colour wheel ...")
    hue, saturation, lightness = colour_tree(df)

    print(f"Writing colours to {DB_PATH} ...")
    write_colours(DB_PATH, df, hue, saturation, lightness)

    print(f"Refreshing {PARQUET_PATH} ...")
    refresh_parquet(DB_PATH, PARQUET_PATH)

    print_sample(DB_PATH)
    print("\nDone.")


if __name__ == "__main__":
    main()
