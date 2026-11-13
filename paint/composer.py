"""
Decide how many strokes each taxon gets, how big they are, and where they land.

Style: abstract, palette-knife / flat-brush painting — large overlapping
rectangular strokes, mostly vertical or horizontal, layered from coarse to fine.

Strategy:
  1. Underpainting — a grid of very large, translucent strokes covers the whole
     canvas so no bare background shows. Colours are sampled by abundance.
  2. Main strokes — each taxon receives a share of the stroke budget
     proportional to its abundance. Abundant taxa also get *bigger* strokes.
     Each taxon's strokes gather around a few anchor points, so colours form
     blocks/regions rather than an even speckle.
  3. Strokes are painted big-to-small (with some noise), like a painter
     blocking in shapes before adding detail.
"""

import math
import random
from dataclasses import dataclass

import polars as pl

DEFAULT_TOTAL_STROKES = 400
SEED = 7

# Higher-rank taxa (if present in the input) paint with a slightly bigger brush
RANK_SCALE = {
    "domain": 1.6, "phylum": 1.45, "class": 1.35, "order": 1.25,
    "family": 1.15, "genus": 1.05, "species": 1.0,
}

# Stroke size as a fraction of canvas (min, max) before abundance scaling
WIDTH_FRAC = (0.05, 0.13)    # of the canvas's short side
LENGTH_FRAC = (0.12, 0.38)   # of the canvas's long side

VERTICAL_BIAS = 0.6          # share of strokes dragged vertically (rest horizontal)
ANGLE_JITTER = math.radians(7)
DARK_ACCENT = 0.12            # share of main strokes painted in a deep shade of their colour


@dataclass
class Stroke:
    x: float            # centre
    y: float
    angle: float        # drag direction, radians
    length: float       # px along the drag direction
    width: float        # px across the brush
    hue: float          # [0, 360)
    saturation: float   # [0, 1]
    lightness: float    # [0, 1]
    alpha: int          # 0-255 base opacity
    layer: int          # 0 = underpainting, 1 = main


def _jitter_colour(rng: random.Random, taxon: dict, l_amt: float, s_amt: float):
    """Keep the taxon's hue (its identity) but vary tone like real mixed paint."""
    hue = (taxon["hue"] + rng.gauss(0, 4)) % 360
    sat = min(0.95, max(0.15, taxon["saturation"] + rng.uniform(-s_amt, s_amt)))
    light = min(0.85, max(0.18, taxon["lightness"] + rng.uniform(-l_amt, l_amt)))
    return hue, sat, light


def _angle(rng: random.Random) -> float:
    base = math.pi / 2 if rng.random() < VERTICAL_BIAS else 0.0
    if rng.random() < 0.5:
        base += math.pi                      # drag up vs down / left vs right
    return base + rng.gauss(0, ANGLE_JITTER)


def _underpainting(rng, rows, weights, canvas_w, canvas_h) -> list[Stroke]:
    """Cover the canvas with big translucent blocks on a jittered grid."""
    strokes = []
    cols, nrows = 4, 5
    cw, ch = canvas_w / cols, canvas_h / nrows
    for gy in range(nrows):
        for gx in range(cols):
            for _ in range(2):
                taxon = rng.choices(rows, weights=weights)[0]
                hue, sat, light = _jitter_colour(rng, taxon, 0.12, 0.1)
                angle = _angle(rng)
                vertical = abs(math.sin(angle)) > 0.7
                strokes.append(Stroke(
                    x=(gx + rng.uniform(0.2, 0.8)) * cw,
                    y=(gy + rng.uniform(0.2, 0.8)) * ch,
                    angle=angle,
                    length=(ch if vertical else cw) * rng.uniform(1.4, 2.0),
                    width=(cw if vertical else ch) * rng.uniform(1.0, 1.4),
                    hue=hue, saturation=sat, lightness=light,
                    alpha=rng.randint(150, 200),
                    layer=0,
                ))
    rng.shuffle(strokes)
    return strokes


def compose(
    taxa: pl.DataFrame,
    canvas_w: int,
    canvas_h: int,
    total_strokes: int = DEFAULT_TOTAL_STROKES,
) -> list[Stroke]:
    """
    Return a list of Stroke objects in paint order.

    taxa must have columns: count, rank, hue, saturation, lightness
    """
    rng = random.Random(SEED)

    counts = taxa["count"].cast(pl.Float64)
    proportions = (counts / counts.sum()).to_list()
    max_prop = max(proportions)
    rows = taxa.select(["rank", "hue", "saturation", "lightness"]).to_dicts()

    short_side, long_side = min(canvas_w, canvas_h), max(canvas_w, canvas_h)

    strokes = _underpainting(rng, rows, proportions, canvas_w, canvas_h)

    main: list[tuple[float, Stroke]] = []
    for taxon, prop in zip(rows, proportions):
        # Stochastic rounding so rare taxa still sometimes get a stroke
        expected = prop * total_strokes
        n = int(expected) + (1 if rng.random() < expected - int(expected) else 0)
        if n == 0:
            continue

        # Abundant taxa paint with a bigger brush
        size = (0.55 + 0.75 * math.sqrt(prop / max_prop)) * RANK_SCALE.get(taxon["rank"], 1.0)

        # A few anchor regions per taxon → colour blocks instead of speckle
        n_anchors = 1 + min(3, int(prop * 12))
        anchors = [(rng.uniform(0, canvas_w), rng.uniform(0, canvas_h)) for _ in range(n_anchors)]
        spread = 0.16 * short_side

        for _ in range(n):
            ax, ay = rng.choice(anchors)
            hue, sat, light = _jitter_colour(rng, taxon, 0.16, 0.12)
            if rng.random() < DARK_ACCENT:      # occasional deep shadow strokes
                light = max(0.12, light - rng.uniform(0.18, 0.3))
            width = short_side * rng.uniform(*WIDTH_FRAC) * size
            length = long_side * rng.uniform(*LENGTH_FRAC) * size
            stroke = Stroke(
                x=min(canvas_w, max(0, rng.gauss(ax, spread))),
                y=min(canvas_h, max(0, rng.gauss(ay, spread))),
                angle=_angle(rng),
                length=length,
                width=width,
                hue=hue, saturation=sat, lightness=light,
                alpha=rng.randint(185, 245),
                layer=1,
            )
            # Big strokes first, small last — with noise so it isn't too orderly
            main.append((width * length * rng.uniform(0.5, 1.5), stroke))

    main.sort(key=lambda t: t[0], reverse=True)
    strokes.extend(s for _, s in main)
    return strokes
