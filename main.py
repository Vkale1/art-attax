#!/usr/bin/env python3
"""
art-attax — generative paintings from GTDB microbial abundance data.

Commands:
    paint             render a painting from an abundance TSV (uses the bundled palette)

Maintainer commands:
    build-palette     download a GTDB release, colour it, write palette/ and the app
    build-app         rebuild app/art-attax.html after editing app/template.html
"""

import os
import sys
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

OUTPUT_DIR = Path(os.environ.get("OUTPUT_PATH", "/outputs"))


@app.command()
def build_palette(
    release: int = typer.Option(..., help="GTDB release number, e.g. 232"),
    taxonomy: Path = typer.Option(
        None, help="Use this bac120_taxonomy .tsv.gz instead of downloading it (it is kept)",
    ),
) -> None:
    """Download a GTDB release, colour every taxon and write palette/gtdb_r<release>_colours.parquet."""
    from palette.build import main
    main(release, taxonomy)


@app.command()
def build_app() -> None:
    """Rebuild the standalone app (app/art-attax.html) from the template and newest palette."""
    from app.build import main
    main()


@app.command()
def paint(
    abundance: Path = typer.Argument(..., help="Abundance TSV (taxon<TAB>abundance; counts, fractions or percentages)"),
    output: Path = typer.Option(None, help="Output PNG path (default: outputs/<stem>.png)"),
    width: int = typer.Option(2400, help="Canvas width in pixels"),
    height: int = typer.Option(3200, help="Canvas height in pixels"),
    strokes: int = typer.Option(400, help="Number of main brushstrokes (plus a fixed underpainting layer)"),
    spread: float = typer.Option(
        0.0, min=0.0, max=1.0,
        help="Spread the sample's hues apart (0 = off, 1 = most). Colours stop matching the key.",
    ),
    fuzzy: bool = typer.Option(False, "--fuzzy", help="Also paint taxa that aren't exact GTDB names, using the closest match."),
) -> None:
    """Render a painting from an abundance file."""
    from paint.loader import load
    from paint.composer import compose
    from paint.spread import spread_hues
    from paint.brushes import paint as render

    if output is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_DIR / f"{abundance.stem}.png"

    print(f"Loading abundance data from {abundance} ...")
    try:
        taxa = load(abundance, fuzzy=fuzzy)
    except ValueError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        raise typer.Exit(1)
    print(f"  {taxa.height} taxa matched")
    if taxa.is_empty():
        print("ERROR: nothing to paint — no taxa matched", file=sys.stderr)
        raise typer.Exit(1)
    taxa = spread_hues(taxa, spread)

    print(f"Composing layout ({strokes:,} strokes) ...")
    stroke_list = compose(taxa, width, height, strokes)
    print(f"  {len(stroke_list):,} strokes generated")

    print(f"Rendering {width}×{height} painting ...")
    render(stroke_list, width, height, output)


if __name__ == "__main__":
    app()
