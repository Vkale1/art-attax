"""
Load an abundance TSV and join to the taxa DB to produce a colour-enriched DataFrame.

Abundance TSV format (tab-separated, optional header):
    lineage_or_name  <TAB>  count

Matching strategy: try exact join on full lineage string first,
then fall back to name match at species level.
Unmatched rows are dropped with a warning.
"""

from pathlib import Path

import duckdb
import polars as pl

RANKS = ["domain", "phylum", "class", "order", "family", "genus", "species"]


def load(abundance_tsv: Path, db_path: Path) -> pl.DataFrame:
    """
    Returns a DataFrame with columns:
        lineage, rank, name, count, hue, saturation, lightness, brush_style
    Sorted by count descending.
    """
    raw = _read_abundance(abundance_tsv)
    taxa = _read_taxa(db_path)

    # Exact lineage join
    joined = raw.join(taxa, left_on="taxon", right_on="lineage", how="left")

    unmatched = joined.filter(pl.col("hue").is_null())
    matched = joined.filter(pl.col("hue").is_not_null())

    if unmatched.height > 0:
        # Fallback: join on name (species level)
        fallback = (
            unmatched
            .select("taxon", "count")
            .join(taxa.filter(pl.col("rank") == "species"), left_on="taxon", right_on="name", how="left")
        )
        still_missing = fallback.filter(pl.col("hue").is_null())
        if still_missing.height > 0:
            print(f"  Warning: {still_missing.height} taxa could not be matched and will be skipped:")
            for row in still_missing["taxon"].to_list()[:5]:
                print(f"    {row}")
            if still_missing.height > 5:
                print(f"    ... and {still_missing.height - 5} more")

        fallback = fallback.filter(pl.col("hue").is_not_null())
        matched = pl.concat([matched, fallback], how="diagonal")

    return (
        matched
        .select(["lineage", "rank", "name", "count", "hue", "saturation", "lightness", "brush_style"])
        .sort("count", descending=True)
    )


def _read_abundance(path: Path) -> pl.DataFrame:
    raw = pl.read_csv(path, separator="\t", has_header=False, new_columns=["taxon", "count"])

    # If first row looks like a header, drop it
    if raw["count"].dtype == pl.String:
        raw = raw.slice(1)
        raw = raw.with_columns(pl.col("count").cast(pl.Int64))
    else:
        raw = raw.with_columns(pl.col("count").cast(pl.Int64))

    return raw.filter(pl.col("count") > 0)


def _read_taxa(db_path: Path) -> pl.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(
            "SELECT lineage, rank, name, hue, saturation, lightness, brush_style FROM taxa"
        ).pl()
    finally:
        con.close()
