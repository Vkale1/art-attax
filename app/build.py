#!/usr/bin/env python3
"""
Build the standalone app: app/template.html + palette + example → app/art-attax.html
Runs automatically at the end of build-palette; run it alone after editing the template.

The palette is packed as one taxon per line, parents before children:
    <depth 0-6><name>\t<hue>\t<saturation>\t<lightness>
A taxon's parent is the closest line above it with depth one less, so full
lineages never need to be stored. The text is gzipped and base64-encoded.
"""

import base64
import gzip
import json
from pathlib import Path

from paint.palette import PALETTE_PATH, load_palette, release_of

APP_DIR = Path(__file__).resolve().parent
TEMPLATE = APP_DIR / "template.html"
OUTPUT = APP_DIR / "art-attax.html"
EXAMPLE = APP_DIR.parent / "tests" / "fixtures" / "gut_microbiome_r232.tsv"


def pack_palette(path: Path) -> str:
    df = load_palette(path).select("lineage", "hue", "saturation", "lightness")
    rows = [
        (lineage.split(";"), h, s, l)
        for lineage, h, s, l in df.iter_rows()
    ]
    # Depth-first order: sorting on the list of parts puts every parent right
    # before its children (sorting the raw string would not, e.g. "-" < ";")
    rows.sort(key=lambda r: r[0])

    lines = []
    for parts, h, s, l in rows:
        name = parts[-1].split("__", 1)[1]
        lines.append(f"{len(parts) - 1}{name}\t{h:.1f}\t{s:.3f}\t{l:.3f}")
    packed = gzip.compress("\n".join(lines).encode(), compresslevel=9, mtime=0)
    return base64.b64encode(packed).decode()


def main(palette: Path = PALETTE_PATH) -> None:
    release = release_of(palette)
    if release is None:
        raise SystemExit(f"ERROR: can't tell the GTDB release from {palette.name}")

    html = TEMPLATE.read_text()
    for placeholder in ('"__PALETTE_B64__"', "__EXAMPLE_JSON__"):
        if html.count(placeholder) != 1:
            raise SystemExit(f"ERROR: {placeholder} should appear exactly once in {TEMPLATE}")

    html = html.replace('"__PALETTE_B64__"', json.dumps(pack_palette(palette)))
    html = html.replace("__EXAMPLE_JSON__", json.dumps(EXAMPLE.read_text()))
    html = html.replace("__RELEASE__", f"R{release}")
    OUTPUT.write_text(html)
    print(f"Wrote {OUTPUT} with the R{release} palette ({OUTPUT.stat().st_size / 1e6:.1f} MB)")

if __name__ == "__main__":
    main()
