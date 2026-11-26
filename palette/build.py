#!/usr/bin/env python3
"""
Build the palette for a GTDB release, start to finish (maintainer only).

    python main.py build-palette --release 232

1. Download the GTDB bacterial taxonomy for that release (to a temporary folder)
2. Split every genome's lineage into one row per unique taxon (domain → species)
3. Colour the tree (palette/colours.py)
4. Write palette/gtdb_r<release>_colours.parquet
5. Rebuild the app so it uses the new palette
6. Delete the download

Use --taxonomy to build from a file you've already downloaded; that file is kept.
The uniqueness key for a taxon is its full lineage, not its name: GTDB has
homonymous names in different clades.
"""

import gzip
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

import polars as pl

from palette.colours import BRUSH_BY_RANK, RANKS, colour_tree
from paint.palette import COLUMNS, palette_file

URL = "https://data.gtdb.aau.ecogenomic.org/releases/release{r}/{r}.0/bac120_taxonomy_r{r}.tsv.gz"


def download(release: int, folder: Path) -> Path:
    url = URL.format(r=release)
    path = folder / Path(url).name
    print(f"Downloading {url} ...")
    try:
        with urllib.request.urlopen(url) as response, open(path, "wb") as out:
            shutil.copyfileobj(response, out)
    except OSError as err:
        raise SystemExit(f"ERROR: couldn't download release {release}: {err}")
    print(f"  {path.stat().st_size / 1e6:.1f} MB")
    return path


def read_taxa(taxonomy: Path) -> tuple[pl.DataFrame, int]:
    """One row per unique taxon (lineage, rank, name, parent_lineage), and the genome count."""
    seen: set[str] = set()
    rows: list[tuple[str, str, str, str | None]] = []
    genomes = 0
    with gzip.open(taxonomy, "rt") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t", 1)[1].split(";")
            if len(parts) != len(RANKS):
                continue  # malformed
            genomes += 1
            for i, rank in enumerate(RANKS):
                lineage = ";".join(parts[: i + 1])
                if lineage in seen:
                    continue
                seen.add(lineage)
                name = parts[i].split("__", 1)[-1]
                parent = ";".join(parts[:i]) if i else None
                rows.append((lineage, rank, name, parent))
    df = pl.DataFrame(
        rows, orient="row",
        schema={"lineage": pl.String, "rank": pl.String, "name": pl.String, "parent_lineage": pl.String},
    )
    return df, genomes


def build(release: int, taxonomy: Path) -> Path:
    print(f"Reading {taxonomy.name} ...")
    taxa, genomes = read_taxa(taxonomy)
    print(f"  {genomes:,} genomes, {taxa.height:,} taxa")
    counts = dict(taxa.group_by("rank").len().iter_rows())
    print("  " + ", ".join(f"{counts.get(r, 0):,} {r}" for r in RANKS[1:]))

    print("Colouring the tree ...")
    hue, saturation, lightness = colour_tree(taxa)
    taxa = taxa.with_columns(
        hue=pl.Series(hue, dtype=pl.Float64),
        saturation=pl.Series(saturation, dtype=pl.Float64),
        lightness=pl.Series(lightness, dtype=pl.Float64),
        brush_style=pl.col("rank").replace_strict(BRUSH_BY_RANK, return_dtype=pl.String),
    )

    # Sorting by lineage puts shared prefixes together, which compresses far better
    out = palette_file(release)
    out.parent.mkdir(parents=True, exist_ok=True)
    taxa.select(COLUMNS).sort("lineage").rechunk().write_parquet(out, compression="zstd", compression_level=19)
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def main(release: int, taxonomy: Path | None = None) -> None:
    if taxonomy is not None:
        if not taxonomy.exists():
            raise SystemExit(f"ERROR: {taxonomy} not found")
        out = build(release, taxonomy)
    else:
        with tempfile.TemporaryDirectory() as folder:
            out = build(release, download(release, Path(folder)))
        print("Deleted the download")

    from app.build import main as build_app
    build_app(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m palette.build <release>")
    main(int(sys.argv[1]))
