"""
Decide how many strokes each taxon gets and where they land on the canvas.

Strategy: abundance-weighted random placement. Each taxon receives a share of
the total stroke budget proportional to its normalised count. Positions are
drawn uniformly across the canvas — phylogenetic colour relationship creates
visual structure even without explicit spatial clustering.
"""

import math
import random
from dataclasses import dataclass

import polars as pl

DEFAULT_TOTAL_STROKES = 600
SEED = 7


@dataclass
class Stroke:
    x: float
    y: float
    angle: float        # radians
    hue: float          # [0, 360)
    saturation: float   # [0, 1]
    lightness: float    # [0, 1]
    brush_style: str


def compose(
    taxa: pl.DataFrame,
    canvas_w: int,
    canvas_h: int,
    total_strokes: int = DEFAULT_TOTAL_STROKES,
) -> list[Stroke]:
    """
    Return a list of Stroke objects distributed across the canvas.

    taxa must have columns: count, hue, saturation, lightness, brush_style
    """
    rng = random.Random(SEED)

    counts = taxa["count"].cast(pl.Float64)
    total = counts.sum()
    proportions = (counts / total).to_list()

    rows = taxa.select(["hue", "saturation", "lightness", "brush_style"]).to_dicts()

    strokes: list[Stroke] = []

    for taxon, prop in zip(rows, proportions):
        n = round(prop * total_strokes)
        if n == 0:
            continue
        for _ in range(n):
            strokes.append(Stroke(
                x=rng.uniform(0, canvas_w),
                y=rng.uniform(0, canvas_h),
                angle=rng.uniform(0, math.tau),
                hue=taxon["hue"],
                saturation=taxon["saturation"],
                lightness=taxon["lightness"],
                brush_style=taxon["brush_style"],
            ))

    # Shuffle so no single taxon dominates foreground z-order
    rng.shuffle(strokes)
    return strokes
