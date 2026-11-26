"""
Load an abundance TSV and join to the palette to produce a colour-enriched DataFrame.

Abundance TSV format (tab-separated, optional header):
    lineage_or_name  <TAB>  count

Only exact GTDB names are painted by default: a full lineage (blank trailing ranks
like g__;s__ are fine), or a single name such as "Escherichia coli" or "g__Bacteroides".
Anything else is reported, with a suggestion where there is one, and not painted.

With fuzzy=True these are painted too, and reported:
    name       the taxon's own name matches but its higher ranks differ
    suffix     a species matches once GTDB's letter suffixes are ignored
               (Blautia obeum → Blautia_A obeum), if only one candidate fits
    ancestor   the closest named relative higher up the lineage, genus → phylum
"""

import re
from collections import defaultdict
from pathlib import Path

import polars as pl

from paint.palette import PALETTE_PATH, load_palette

RANKS = ["domain", "phylum", "class", "order", "family", "genus", "species"]
PREFIX_RANK = {rank[0]: rank for rank in RANKS}   # d__, p__, ... s__


def load(abundance_tsv: Path, palette_path: Path = PALETTE_PATH, fuzzy: bool = False) -> pl.DataFrame:
    """
    Returns a DataFrame with columns:
        lineage, rank, name, count, hue, saturation, lightness, brush_style
    Sorted by count descending. Inputs that match the same taxon are added together.
    """
    raw = _read_abundance(abundance_tsv)
    palette = load_palette(palette_path).drop("parent_lineage")
    matcher = _Matcher(palette)

    counts: dict[str, int] = {}
    how: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for taxon, count in raw.select("taxon", "count").iter_rows():
        lineage, method = matcher.match(taxon)
        how[method].append((taxon, lineage))
        if lineage and (fuzzy or method == "exact"):
            counts[lineage] = counts.get(lineage, 0) + count
    _report(how, fuzzy)

    matched = pl.DataFrame(
        {"lineage": list(counts), "count": list(counts.values())},
        schema={"lineage": pl.String, "count": pl.Int64},
    )
    return (
        matched
        .join(palette, on="lineage", how="inner", maintain_order="left")
        .select(["lineage", "rank", "name", "count", "hue", "saturation", "lightness", "brush_style"])
        .sort("count", descending=True, maintain_order=True)
    )


class _Matcher:
    def __init__(self, palette: pl.DataFrame):
        self.lineages = set(palette["lineage"].to_list())
        # (rank, name) and suffix-free species name → lineages; >1 entry = ambiguous
        self.by_name: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.by_plain_species: dict[str, list[str]] = defaultdict(list)
        for lineage, rank, name in palette.select("lineage", "rank", "name").iter_rows():
            self.by_name[rank, name].append(lineage)
            if rank == "species":
                self.by_plain_species[_strip_suffixes(name)].append(lineage)

    def match(self, taxon: str) -> tuple[str | None, str]:
        taxon = taxon.strip()
        trimmed = re.sub(r"(;\s*[a-z]__\s*)+$", "", taxon)   # drop blank trailing ranks
        if trimmed in self.lineages:
            return trimmed, "exact"

        parts = _parse(taxon)
        if not parts:
            return None, "unmatched"

        rank, name = parts[-1]
        if hit := self._unique(self.by_name.get((rank, name))):
            # A lone name states no higher ranks, so there is nothing to disagree with
            return hit, "name" if ";" in taxon else "exact"
        if rank == "species":
            if hit := self._unique(self.by_plain_species.get(_strip_suffixes(name))):
                return hit, "suffix"
            # A bare species name still tells us its genus
            parts = parts[:-1]
            if not parts and " " in name:
                parts = [("genus", name.split(" ")[0])]
        else:
            parts = parts[:-1]

        for rank, name in reversed(parts):
            # The domain is every bacterium, so it says nothing about the taxon
            if rank != "domain" and (hit := self._unique(self.by_name.get((rank, name)))):
                return hit, "ancestor"
        return None, "unmatched"

    @staticmethod
    def _unique(hits: list[str] | None) -> str | None:
        return hits[0] if hits and len(hits) == 1 else None


def _parse(taxon: str) -> list[tuple[str, str]]:
    """Split into (rank, name), dropping blank ranks. A bare name is taken as a species."""
    out = []
    for part in taxon.split(";"):
        prefix, sep, name = part.strip().partition("__")
        if not sep:
            prefix, name = "s", part.strip()
        if name and prefix in PREFIX_RANK:
            out.append((PREFIX_RANK[prefix], name))
    return out


def _strip_suffixes(name: str) -> str:
    """Blautia_A obeum_B → Blautia obeum"""
    return re.sub(r"_[A-Z]+(?= |$)", "", name)


def _report(how: dict[str, list[tuple[str, str | None]]], fuzzy: bool) -> None:
    labels = {
        "name": "same name, different lineage",
        "suffix": "similar name, may not be the same species",
        "ancestor": "not in GTDB, closest relative",
        "unmatched": "not in GTDB, no suggestion",
    }
    rows = [(method, row) for method in labels for row in how.get(method, [])]
    if not rows:
        return
    if fuzzy:
        print(f"  Warning: {len(rows)} taxa are not exact GTDB names:")
    else:
        print(f"  Warning: {len(rows)} taxa are not exact GTDB names and will not be painted")
        print("  (use --fuzzy to paint the suggestions instead):")
    for method, (taxon, lineage) in rows:
        print(f"    {taxon}")
        print(f"      {labels[method]}{': ' + lineage if lineage else ''}")


def _read_abundance(path: Path) -> pl.DataFrame:
    raw = pl.read_csv(path, separator="\t", has_header=False, new_columns=["taxon", "count"])

    # If first row looks like a header, drop it
    if raw["count"].dtype == pl.String:
        raw = raw.slice(1)
        raw = raw.with_columns(pl.col("count").cast(pl.Int64))
    else:
        raw = raw.with_columns(pl.col("count").cast(pl.Int64))

    return raw.filter(pl.col("count") > 0)
