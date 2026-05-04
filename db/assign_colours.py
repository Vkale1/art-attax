#!/usr/bin/env python3
"""
Phase 2: Train Poincaré embeddings on GTDB taxa → assign colour + brush style.

Reads:  /data/gtdb_r232.duckdb  (taxa table with NULL colour columns)
Writes: hue/saturation/lightness/brush_style into taxa table
        refreshes /data/taxa.parquet
"""

import math
import random
from pathlib import Path

import duckdb
import geoopt
import numpy as np
import polars as pl
import torch
from tqdm import trange

DATA_DIR = Path("/data")
DB_PATH = DATA_DIR / "gtdb_r232.duckdb"
PARQUET_PATH = DATA_DIR / "taxa.parquet"

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

EMBED_DIM = 2
EPOCHS = 200
LR = 0.05
NEG_SAMPLES = 10
BATCH_SIZE = 1024
SEED = 42


def load_taxa(db_path: Path) -> pl.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(
            "SELECT taxon_id, lineage, rank, parent_lineage FROM taxa ORDER BY taxon_id"
        ).pl()
    finally:
        con.close()


def build_pairs(df: pl.DataFrame) -> tuple[list[int], list[int]]:
    """Return (child_indices, parent_indices) index pairs into df."""
    lineage_to_idx = {row["lineage"]: i for i, row in enumerate(df.iter_rows(named=True))}
    children, parents = [], []
    for i, row in enumerate(df.iter_rows(named=True)):
        parent_lin = row["parent_lineage"]
        if parent_lin is not None and parent_lin in lineage_to_idx:
            children.append(i)
            parents.append(lineage_to_idx[parent_lin])
    return children, parents


def train_poincare(n: int, children: list[int], parents: list[int]) -> torch.Tensor:
    """Train Poincaré embeddings and return (n, 2) coordinate tensor."""
    torch.manual_seed(SEED)
    random.seed(SEED)

    ball = geoopt.PoincareBall(c=1.0)
    raw = torch.randn(n, EMBED_DIM) * 0.01
    embeddings = geoopt.ManifoldParameter(raw, manifold=ball)
    optimizer = geoopt.optim.RiemannianSGD([embeddings], lr=LR, stabilize=10)

    pos_children = torch.tensor(children, dtype=torch.long)
    pos_parents = torch.tensor(parents, dtype=torch.long)
    n_pairs = len(children)

    for epoch in trange(EPOCHS, desc="Training Poincaré embeddings"):
        perm = torch.randperm(n_pairs)
        pos_children = pos_children[perm]
        pos_parents = pos_parents[perm]

        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, n_pairs, BATCH_SIZE):
            end = min(start + BATCH_SIZE, n_pairs)
            batch_c = pos_children[start:end]
            batch_p = pos_parents[start:end]
            bsz = len(batch_c)

            optimizer.zero_grad()

            u = embeddings[batch_c]      # (bsz, 2)
            v_pos = embeddings[batch_p]  # (bsz, 2)

            neg_idx = torch.randint(0, n, (bsz, NEG_SAMPLES))
            v_neg = embeddings[neg_idx]  # (bsz, neg, 2)

            d_pos = ball.dist(u, v_pos)  # (bsz,)

            u_exp = u.unsqueeze(1).expand_as(v_neg)
            d_neg = ball.dist(
                u_exp.reshape(-1, EMBED_DIM),
                v_neg.reshape(-1, EMBED_DIM),
            ).reshape(bsz, NEG_SAMPLES)   # (bsz, neg)

            # Cross-entropy loss: -log(e^{-d_pos} / (e^{-d_pos} + Σ e^{-d_neg}))
            log_denom = torch.logsumexp(
                torch.cat([-d_pos.unsqueeze(1), -d_neg], dim=1), dim=1
            )
            loss = (d_pos + log_denom).mean()

            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        if (epoch + 1) % 50 == 0:
            avg = epoch_loss / max(n_batches, 1)
            print(f"  epoch {epoch + 1}/{EPOCHS}  loss={avg:.4f}")

    return embeddings.detach()


def coords_to_hsl(coords: torch.Tensor) -> tuple[list[float], list[float], list[float]]:
    """Map (n, 2) Poincaré disk coords to HSL lists."""
    x = coords[:, 0].numpy()
    y = coords[:, 1].numpy()

    # Angle → hue [0, 360)
    hue = (np.degrees(np.arctan2(y, x)) % 360).tolist()

    # Radius → saturation [0.3, 0.9]
    # Species cluster near boundary (high radius), root near origin (low radius)
    radius = np.sqrt(x**2 + y**2)
    saturation = np.clip(0.3 + 0.6 * radius, 0.3, 0.9).tolist()

    lightness = [0.5] * len(hue)

    return hue, saturation, lightness


def write_colours(
    db_path: Path,
    df: pl.DataFrame,
    hue: list[float],
    saturation: list[float],
    lightness: list[float],
) -> None:
    brush = df["rank"].map_elements(
        lambda r: BRUSH_BY_RANK.get(r, "medium"), return_dtype=pl.String
    )
    updates = pl.DataFrame({
        "taxon_id":    df["taxon_id"],
        "hue":         pl.Series(hue, dtype=pl.Float64),
        "saturation":  pl.Series(saturation, dtype=pl.Float64),
        "lightness":   pl.Series(lightness, dtype=pl.Float64),
        "brush_style": brush,
    })
    con = duckdb.connect(str(db_path))
    try:
        con.register("updates", updates)
        con.execute("""
            UPDATE taxa
               SET hue         = updates.hue,
                   saturation  = updates.saturation,
                   lightness   = updates.lightness,
                   brush_style = updates.brush_style
              FROM updates
             WHERE taxa.taxon_id = updates.taxon_id
        """)
    finally:
        con.close()


def refresh_parquet(db_path: Path, parquet_path: Path) -> None:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute("SELECT * FROM taxa").pl()
    finally:
        con.close()
    df.write_parquet(str(parquet_path))


def print_sample(db_path: Path) -> None:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("""
            SELECT rank, name, hue, saturation, lightness, brush_style
              FROM taxa
             ORDER BY rank, taxon_id
             LIMIT 14
        """).fetchall()
    finally:
        con.close()
    print(f"\n  {'rank':<12} {'name':<35} {'hue':>7} {'sat':>6} {'lig':>6}  brush")
    for rank, name, h, s, l, b in rows:
        print(f"  {rank:<12} {name:<35} {h:>7.1f} {s:>6.3f} {l:>6.3f}  {b}")


def main() -> None:
    print(f"Loading taxa from {DB_PATH} ...")
    df = load_taxa(DB_PATH)
    print(f"  {len(df):,} taxa loaded")

    print("Building parent-child pairs ...")
    children, parents = build_pairs(df)
    print(f"  {len(children):,} edges")

    print("Training Poincaré embeddings ...")
    coords = train_poincare(len(df), children, parents)

    print("Mapping coordinates to HSL ...")
    hue, saturation, lightness = coords_to_hsl(coords)

    print(f"Writing colours to {DB_PATH} ...")
    write_colours(DB_PATH, df, hue, saturation, lightness)

    print(f"Refreshing {PARQUET_PATH} ...")
    refresh_parquet(DB_PATH, PARQUET_PATH)

    print_sample(DB_PATH)
    print("\nDone.")


if __name__ == "__main__":
    main()
