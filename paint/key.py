"""
Generate a sunburst colour key showing taxa colours by rank.

Rings (inner → outer): phylum → class → order
Wedge size follows the square root of the number of species descendants, so small
phyla stay visible and wedges match each taxon's share of the colour wheel.
Phylum names are labelled inside wedges wide enough to read (4° or more).

Output: /outputs/colour_key.png
"""

import colorsys
import math
from pathlib import Path

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from paint.palette import PALETTE_PATH, load_palette

OUTPUT = Path("/outputs/colour_key.png")

# Radii for each ring (inner, outer)
RINGS = {
    "phylum": (0.25, 0.50),
    "class":  (0.50, 0.70),
    "order":  (0.70, 0.85),
}

MIN_LABEL_SPAN = 0.07   # radians (4°) — phyla narrower than this don't get a label
MIN_DRAW_SPAN  = 0.0008 # radians — wedges narrower than this are skipped


def species_counts(df: pl.DataFrame) -> dict[str, int]:
    """Count species descendants for every lineage node."""
    counts: dict[str, int] = {}
    for lineage in df.filter(pl.col("rank") == "species")["lineage"].to_list():
        parts = lineage.split(";")
        for depth in range(1, len(parts) + 1):
            ancestor = ";".join(parts[:depth])
            counts[ancestor] = counts.get(ancestor, 0) + 1
    return counts


def assign_angles(
    df: pl.DataFrame,
    counts: dict[str, int],
) -> dict[str, tuple[float, float]]:
    """
    Return {lineage: (start_angle, end_angle)} for all nodes,
    distributing each parent's arc among children by the square root of species count.
    """
    angles: dict[str, tuple[float, float]] = {}

    domain_rows = df.filter(pl.col("rank") == "domain")
    for row in domain_rows.iter_rows(named=True):
        angles[row["lineage"]] = (0.0, 2 * np.pi)

    for rank in ["phylum", "class", "order"]:
        rank_df = df.filter(pl.col("rank") == rank)
        for parent_lin in rank_df["parent_lineage"].unique().to_list():
            if parent_lin not in angles:
                continue
            p_start, p_end = angles[parent_lin]
            p_span = p_end - p_start

            children = (
                rank_df
                .filter(pl.col("parent_lineage") == parent_lin)
                .iter_rows(named=True)
            )
            child_data = [
                (row["lineage"], math.sqrt(counts.get(row["lineage"], 0)), row["hue"])
                for row in children
            ]
            child_data.sort(key=lambda x: x[2])  # sort by hue → similar colours stay adjacent

            total = sum(c[1] for c in child_data) or 1
            cursor = p_start
            for lineage, weight, _ in child_data:
                span = p_span * weight / total
                angles[lineage] = (cursor, cursor + span)
                cursor += span

    return angles


def draw_ring(
    ax,
    df: pl.DataFrame,
    rank: str,
    angles: dict[str, tuple[float, float]],
    r_inner: float,
    r_outer: float,
    label: bool,
) -> None:
    for row in df.filter(pl.col("rank") == rank).iter_rows(named=True):
        lin = row["lineage"]
        if lin not in angles:
            continue
        start, end = angles[lin]
        span = end - start
        if span < MIN_DRAW_SPAN:
            continue

        h, s, l = row["hue"] / 360.0, row["saturation"], row["lightness"]
        colour = colorsys.hls_to_rgb(h, l, s)

        ax.bar(
            x=start + span / 2,
            height=r_outer - r_inner,
            width=span,
            bottom=r_inner,
            color=colour,
            edgecolor="white",
            linewidth=0.25 if span > 0.017 else 0,   # outlines would hide thin wedges
            align="center",
        )

        if label and span >= MIN_LABEL_SPAN:
            # Angles run clockwise from the top; turn text to read along the radius,
            # flipping it on the left half so it is never upside down
            mid = start + span / 2
            deg = np.degrees(mid) % 360
            rotation = 90 - deg if deg < 180 else 270 - deg
            ax.text(
                mid,
                (r_inner + r_outer) / 2,
                row["name"],
                ha="center",
                va="center",
                fontsize=9,
                color="white",
                rotation=rotation,
                rotation_mode="anchor",
                path_effects=[pe.withStroke(linewidth=2, foreground="black")],
            )


def main() -> None:
    print(f"Loading taxa from {PALETTE_PATH} ...")
    df = load_palette()
    print(f"  {len(df):,} taxa loaded")

    print("Computing species counts ...")
    counts = species_counts(df)

    print("Assigning angles ...")
    angles = assign_angles(df, counts)

    print("Drawing sunburst ...")
    fig, ax = plt.subplots(figsize=(14, 14), subplot_kw=dict(projection="polar"))
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_ylim(0, RINGS["order"][1])
    ax.axis("off")

    for rank, (r_inner, r_outer) in RINGS.items():
        draw_ring(ax, df, rank, angles, r_inner, r_outer, label=(rank == "phylum"))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(str(OUTPUT), dpi=150, bbox_inches="tight", pad_inches=0.1, facecolor="white")
    plt.close()
    print(f"Saved → {OUTPUT}")


if __name__ == "__main__":
    main()
