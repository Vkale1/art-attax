"""
Give every GTDB taxon a colour by walking the taxonomy tree. Deterministic, no training.

Each taxon owns a slice of the colour wheel that its children divide, weighted by
sqrt(species count); hue is the middle of the slice. Classes, orders and families
shift lightness and saturation, and their descendants inherit the shift.
"""

import math
from collections import defaultdict

import polars as pl

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
