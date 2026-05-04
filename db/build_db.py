#!/usr/bin/env python3
"""
Phase 1: Parse GTDB taxonomy TSV → DuckDB database + Parquet export.

Input:  /data/bac120_taxonomy.tsv.gz
Output: /data/gtdb_r232.duckdb   — two tables: taxa, genomes
        /data/taxa.parquet       — flat export of taxa table for fast bulk reads

Taxa table has one row per unique node at each rank level.
The uniqueness key is the full lineage string up to that rank, not just
the name — GTDB has homonymous names across different clades.

Colour and brush columns are written as NULL here; assign_colours.py fills them.
"""

import gzip
import sys
from pathlib import Path

import duckdb
import polars as pl
from tqdm import tqdm

DATA_DIR = Path("/data")
TSV_GZ = DATA_DIR / "bac120_taxonomy.tsv.gz"
DB_PATH = DATA_DIR / "gtdb_r232.duckdb"
PARQUET_PATH = DATA_DIR / "taxa.parquet"

RANKS = ["domain", "phylum", "class", "order", "family", "genus", "species"]


def read_genomes(path: Path) -> list[tuple[str, str]]:
    """Read TSV.GZ and return list of (accession, lineage_str)."""
    rows = []
    with gzip.open(path, "rt") as fh:
        for line in tqdm(fh, desc="Parsing genomes", unit=" genomes"):
            line = line.rstrip("\n")
            if not line:
                continue
            accession, lineage_str = line.split("\t", 1)
            rows.append((accession, lineage_str))
    return rows


def extract_taxa(genomes: list[tuple[str, str]]) -> list[dict]:
    """
    Walk every genome lineage and emit one record per unique
    (rank, lineage-up-to-rank) node.

    lineage stored as the semicolon-joined string up to and including
    the current rank — this is the uniqueness / join key used everywhere.
    """
    seen: set[str] = set()
    taxa: list[dict] = []
    taxon_id = 1

    for _, lineage_str in genomes:
        parts = lineage_str.split(";")
        if len(parts) != 7:
            continue  # skip malformed rows

        for i, rank in enumerate(RANKS):
            lineage = ";".join(parts[: i + 1])
            if lineage in seen:
                continue
            seen.add(lineage)

            raw = parts[i]
            name = raw.split("__", 1)[1] if "__" in raw else raw
            parent_lineage = ";".join(parts[:i]) if i > 0 else None

            taxa.append(
                {
                    "taxon_id": taxon_id,
                    "lineage": lineage,
                    "rank": rank,
                    "name": name,
                    "parent_lineage": parent_lineage,
                    # filled by assign_colours.py
                    "hue": None,
                    "saturation": None,
                    "lightness": None,
                    "brush_style": None,
                }
            )
            taxon_id += 1

    return taxa


def write_duckdb(
    taxa_df: pl.DataFrame,
    genomes_df: pl.DataFrame,
    db_path: Path,
) -> None:
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    try:
        con.execute("""
            CREATE TABLE taxa (
                taxon_id       INTEGER  PRIMARY KEY,
                lineage        VARCHAR  NOT NULL UNIQUE,
                rank           VARCHAR  NOT NULL,
                name           VARCHAR  NOT NULL,
                parent_lineage VARCHAR,
                hue            DOUBLE,
                saturation     DOUBLE,
                lightness      DOUBLE,
                brush_style    VARCHAR
            )
        """)
        con.execute("""
            CREATE TABLE genomes (
                accession  VARCHAR  PRIMARY KEY,
                lineage    VARCHAR  NOT NULL
            )
        """)
        con.execute("INSERT INTO taxa SELECT * FROM taxa_df")
        con.execute("INSERT INTO genomes SELECT * FROM genomes_df")
    finally:
        con.close()


def print_summary(db_path: Path) -> None:
    rank_order = {r: i for i, r in enumerate(RANKS)}
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT rank, COUNT(*) FROM taxa GROUP BY rank"
        ).fetchall()
        genome_count = con.execute("SELECT COUNT(*) FROM genomes").fetchone()[0]
    finally:
        con.close()

    print("\nTaxa counts by rank:")
    for rank, n in sorted(rows, key=lambda r: rank_order.get(r[0], 99)):
        print(f"  {rank:<12} {n:>10,}")
    print(f"\n  Total genomes: {genome_count:>10,}")


def main() -> None:
    if not TSV_GZ.exists():
        print(f"ERROR: {TSV_GZ} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {TSV_GZ} ...")
    genomes = read_genomes(TSV_GZ)
    print(f"  {len(genomes):,} genome rows read")

    print("Extracting unique taxa ...")
    taxa_records = extract_taxa(genomes)
    print(f"  {len(taxa_records):,} unique taxa across all ranks")

    taxa_df = pl.DataFrame(taxa_records, schema={
        "taxon_id":      pl.Int32,
        "lineage":       pl.String,
        "rank":          pl.String,
        "name":          pl.String,
        "parent_lineage": pl.String,
        "hue":           pl.Float64,
        "saturation":    pl.Float64,
        "lightness":     pl.Float64,
        "brush_style":   pl.String,
    })
    genomes_df = pl.DataFrame({
        "accession": [g[0] for g in genomes],
        "lineage":   [g[1] for g in genomes],
    })

    print(f"Writing {DB_PATH} ...")
    write_duckdb(taxa_df, genomes_df, DB_PATH)
    print("  DuckDB written")

    print(f"Writing {PARQUET_PATH} ...")
    taxa_df.write_parquet(str(PARQUET_PATH))
    print("  Parquet written")

    print_summary(DB_PATH)
    print("\nDone.")


if __name__ == "__main__":
    main()
