#!/usr/bin/env python3
"""
art-attax — generative paintings from GTDB microbial abundance data.

Commands:
    build-db          Phase 1: parse GTDB taxonomy TSV → DuckDB + Parquet
    assign-colours    Phase 2: train Poincaré embeddings → colour + brush map
    paint             Phase 3: render a painting from an abundance TSV
"""

import os
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

DB_PATH = Path(os.environ.get("GTDB_DB_PATH", "/data/gtdb_r232.duckdb"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_PATH", "/outputs"))


@app.command()
def build_db() -> None:
    """Phase 1 — parse GTDB taxonomy TSV into DuckDB."""
    from db.build_db import main
    main()


@app.command()
def assign_colours() -> None:
    """Phase 2 — train Poincaré embeddings and write colour/brush values."""
    from db.assign_colours import main
    main()


@app.command()
def paint(
    abundance: Path = typer.Argument(..., help="Abundance TSV (taxon<TAB>count)"),
    output: Path = typer.Option(None, help="Output PNG path (default: outputs/<stem>.png)"),
    width: int = typer.Option(2400, help="Canvas width in pixels"),
    height: int = typer.Option(3200, help="Canvas height in pixels"),
    strokes: int = typer.Option(400, help="Number of main brushstrokes (plus a fixed underpainting layer)"),
) -> None:
    """Phase 3 — render a painting from an abundance file."""
    from paint.loader import load
    from paint.composer import compose
    from paint.brushes import paint as render

    if output is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_DIR / f"{abundance.stem}.png"

    print(f"Loading abundance data from {abundance} ...")
    taxa = load(abundance, DB_PATH)
    print(f"  {taxa.height} taxa matched")

    print(f"Composing layout ({strokes:,} strokes) ...")
    stroke_list = compose(taxa, width, height, strokes)
    print(f"  {len(stroke_list):,} strokes generated")

    print(f"Rendering {width}×{height} painting ...")
    render(stroke_list, width, height, output)


if __name__ == "__main__":
    app()
