"""
Generate a sunburst colour key showing taxa colours by rank.

Rings (inner → outer): phylum → class → order
Wedge size is proportional to number of species descendants.
Phylum names are labelled where the wedge is large enough to read.

Output: /outputs/colour_key.png
"""

import colorsys
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

DATA_DIR = Path("/data")
DB_PATH = DATA_DIR / "gtdb_r232.duckdb"
OUTPUT = Path("/outputs/colour_key.png")

# Radii for each ring (inner, outer)
RINGS = {
    "phylum": (0.25, 0.50),
    "class":  (0.50, 0.70),
    "order":  (0.70, 0.85),
}

MIN_LABEL_SPAN = 0.06   # radians — phyla narrower than this don't get a label
MIN_DRAW_SPAN  = 0.003  # radians — wedges narrower than this are skipped


def load_taxa(db_path: Path) -> pl.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(
            "SELECT lineage, rank, name, parent_lineage, hue, saturation, lightness "
            "FROM taxa"
        ).pl()
    finally:
        con.close()


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
    distributing each parent's arc among children proportionally to species count.
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
                (row["lineage"], counts.get(row["lineage"], 0), row["hue"])
                for row in children
            ]
            child_data.sort(key=lambda x: x[2])  # sort by hue → similar colours stay adjacent

            total = sum(c[1] for c in child_data) or 1
            cursor = p_start
            for lineage, count, _ in child_data:
                span = p_span * count / total
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
            linewidth=0.25,
            align="center",
        )

        if label and span >= MIN_LABEL_SPAN:
            mid = start + span / 2
            deg = np.degrees(mid)
            rotation = deg - 90 if deg <= 180 else deg + 90
            ax.text(
                mid,
                r_outer + 0.03,
                row["name"],
                ha="center",
                va="center",
                fontsize=5.5,
                rotation=rotation,
                rotation_mode="anchor",
            )


def main() -> None:
    print(f"Loading taxa from {DB_PATH} ...")
    df = load_taxa(DB_PATH)
    print(f"  {len(df):,} taxa loaded")

    print("Computing species counts ...")
    counts = species_counts(df)

    print("Assigning angles ...")
    angles = assign_angles(df, counts)

    print("Drawing sunburst ...")
    fig, ax = plt.subplots(figsize=(14, 14), subplot_kw=dict(projection="polar"))
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 1.05)
    ax.axis("off")

    for rank, (r_inner, r_outer) in RINGS.items():
        draw_ring(ax, df, rank, angles, r_inner, r_outer, label=(rank == "phylum"))

    # Ring labels
    label_r = 0.13
    for rank, (r_inner, r_outer) in RINGS.items():
        ax.text(
            0, (r_inner + r_outer) / 2,
            rank,
            ha="center", va="center",
            fontsize=7, color="#555555",
            transform=ax.transData,
        )

    ax.set_title("GTDB Taxonomy Colour Key", pad=24, fontsize=15, fontweight="bold")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(str(OUTPUT), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved → {OUTPUT}")


if __name__ == "__main__":
    main()
