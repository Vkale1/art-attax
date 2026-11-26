"""
Optional contrast stretch: move a sample's hues apart so closely related taxa are
easier to tell apart. Hue order round the wheel is kept. Colours then depend on the
sample, so they no longer match the colour key or other paintings.
"""

import math

import polars as pl

SPREAD_RANGE = 260.0   # degrees of the wheel a fully spread sample covers


def spread_hues(taxa: pl.DataFrame, amount: float) -> pl.DataFrame:
    """amount: 0 = unchanged, 1 = fully spread."""
    weight: dict[float, float] = {}
    for hue, count in taxa.select("hue", "count").iter_rows():
        weight[hue] = weight.get(hue, 0.0) + math.sqrt(count)
    hues = sorted(weight)
    n = len(hues)
    if amount <= 0 or n < 2:
        return taxa

    # Cut the wheel at its widest gap, so neighbours are never split apart
    gaps = [((hues[(i + 1) % n] - hues[i]) % 360, i) for i in range(n)]
    cut = max(gaps)[1]
    ordered = hues[cut + 1:] + hues[:cut + 1]
    current = [(h - ordered[0]) % 360 for h in ordered]
    target_range = max(SPREAD_RANGE, current[-1])   # never squeeze a varied sample

    # Space neighbours by their combined abundance, so dominant taxa separate most
    steps = [0.0] + [weight[a] + weight[b] for a, b in zip(ordered, ordered[1:])]
    total = sum(steps)
    target, cursor = [], 0.0
    for step in steps:
        cursor += step
        target.append(cursor / total * target_range)

    # Anchor on the most abundant taxon, whose hue stays as it is
    anchor = max(range(n), key=lambda i: weight[ordered[i]])
    new = {}
    for i, hue in enumerate(ordered):
        old_offset = current[i] - current[anchor]
        new_offset = target[i] - target[anchor]
        new[hue] = (ordered[anchor] + (1 - amount) * old_offset + amount * new_offset) % 360

    return taxa.with_columns(pl.Series("hue", [new[h] for h in taxa["hue"].to_list()], dtype=pl.Float64))
