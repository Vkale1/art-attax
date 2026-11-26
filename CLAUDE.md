# GTDB Art — Claude Code Context

## Scope rules
- Only read and edit files within this repository
- Do not access files outside this directory
- Do not read ~/.ssh, ~/.env, or any file outside this project folder
- Do not execute network commands unless explicitly asked
- Never read or modify any .env file

---

## Project overview
A generative art tool that creates abstract paintings driven by microbial abundance data.
The taxonomy backbone is the GTDB (Genome Taxonomy Database) bacterial tree.
Each taxon is assigned a colour, then an input abundance file drives the composition
of a final painting in an abstract, flat-brush / palette-knife style
(see `example.jpg` for the target look).

The core idea: similar taxa get similar colours (derived from their position in the
phylogenetic tree), and abundance determines how prominently each taxon appears
in the painting.

---

## Architecture

### Two phases

**Phase 1 — Palette** (`palette/`, maintainer only: `main.py build-palette --release N`)
- `build.py` downloads `bac120_taxonomy_r<N>.tsv.gz` from GTDB into a temporary folder,
  splits lineages into one row per unique taxon (domain → species), colours them, writes
  `palette/gtdb_r<N>_colours.parquet`, rebuilds the app, then deletes the download.
  `--taxonomy FILE` builds from a local file instead (kept)
- No database: the taxa table (~234k rows) is built in memory with polars
- `colours.py` walks the taxonomy tree directly; deterministic, no training
- Each taxon owns a slice of hues that its children divide, weighted by sqrt(species count);
  hue = middle of the slice. Big phyla are scattered around the wheel
- Class/order/family shift lightness and saturation; descendants inherit the shift
- A `brush_style` per rank is also written, but the current painter no longer uses it
- The palette parquet **is** committed; users paint from it. `paint/palette.py` picks the
  newest `gtdb_r*_colours.parquet`
- The palette is CC BY-SA 4.0 (derived from GTDB), unlike the MIT code
- Rebuilding R232 reproduces the committed palette's data exactly

**Phase 2 — Painting** (`paint/`)
- `loader.py` reads an abundance TSV (full lineage or species name + any non-negative abundance; only proportions matter) and joins
  to the palette (`palette.py`; override with env var `GTDB_PALETTE_PATH`, e.g. via `docker-compose run -e`); exact GTDB names only;
  others are reported, not painted, unless `--fuzzy` (name → suffix → ancestor)
- `spread.py` optionally stretches a sample's hues apart (`--spread`, off by default)
- `composer.py` plans the strokes:
  - underpainting grid of big translucent blocks so no bare canvas shows
  - stroke budget split by abundance; abundant taxa also get *bigger* strokes
    (higher ranks slightly bigger still)
  - strokes mostly vertical/horizontal, clustered around per-taxon anchor points
    so colours form blocks; tone jitter + occasional dark accents
  - painted big-to-small
- `brushes.py` renders with py5: each stroke is a solid paint body plus many
  parallel bristles (streaks, ragged ends, dry-brush dropout), then a faint canvas weave.
  Starts Xvfb automatically when headless
- `key.py` draws a sunburst colour key (phylum/class/order) → `outputs/colour_key.png`
- Output is a PNG

### Key design decisions
- No DuckDB: one in-memory pass over the GTDB file is enough; the only output is the parquet
- Direct tree colouring over Poincaré embeddings: the trained embeddings never left the
  centre of the disk, so species hues were close to random
- py5 for painting: designed for generative art, expressive brushstroke control
- Hue is the taxon's identity — the painter jitters tone but never changes hue
  (except the opt-in `--spread`)
- No metadata enrichment: the tool is deliberately scoped to taxonomy + abundance only

**App** (`app/`)
- `template.html` is a JavaScript port of loader + composer + brushes (canvas 2D); a
  SETTINGS block at the top mirrors the Python constants
- `build.py` (`main.py build-app`) packs the palette (depth-first, gzip + base64) and the
  example into `app/art-attax.html`, a ~2 MB single file that works offline
- Edit the template, never `art-attax.html`; rebuild after palette changes
- Matching must stay identical to `paint/loader.py`; it was checked on 5,154 names
- App-only (not in the Python painter): styles in `STYLES` — `brush`, `ink` (tapering
  calligraphic strokes + dry bristles), `watercolour` (deformed-polygon glazes, multiply),
  `pointillism` (dots weighted by distance to each taxon's anchors), `splatter` (pours,
  splats, flicks), `glass` (power-diagram panes, bigger for abundant taxa), `petri` (quadrant streak plate,
  one colony per pick by abundance). Mark counts are shared out by abundance (`layout`,
  `share`, `near` helpers). The Coverage slider (`fill`, 0–1) works in every style; several
  add a `ground` layer on a jittered grid. `STYLE_NOTES` holds the on-page explanations.
  `spreadHues()` ports `paint/spread.py` (Spread slider, GTDB wheel only);
  and colour schemes (`COLOUR_MAPS`, matplotlib stops). `recolour()` cuts the sample's hues
  at their widest gap and stretches them over the scheme, keeping GTDB tone offsets
- Speed: the screen shows a preview drawn at screen size; Download redraws at full size.
  Bristles are batched into ~20 tones per stroke (one Path2D each) and the canvas weave
  into 8 paths, so a repaint is a few thousand draw calls, not ~25k

---

## File structure
```
art-attax/
├── CLAUDE.md               ← you are here
├── .claudeignore
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── example.jpg             ← style reference for the painting look
├── palette/
│   ├── build.py            ← Phase 1: download GTDB → palette parquet + app
│   ├── colours.py          ← taxonomy tree → colours
│   └── gtdb_r232_colours.parquet  ← committed palette
├── app/
│   ├── template.html       ← the app source (HTML + JavaScript)
│   ├── build.py            ← builds art-attax.html
│   └── art-attax.html      ← GENERATED standalone app, committed
├── paint/
│   ├── palette.py          ← locate + load the palette
│   ├── loader.py           ← Phase 2: load abundance TSV, join to palette
│   ├── spread.py           ← optional hue spreading
│   ├── composer.py         ← Phase 2: stroke planning / canvas layout
│   ├── brushes.py          ← Phase 2: flat-brush stroke rendering with py5
│   └── key.py              ← sunburst colour key
├── tests/fixtures/
│   └── gut_microbiome_r232.tsv  ← example abundance input
├── main.py                 ← CLI entry point (Typer)
└── outputs/                ← paintings saved here, not committed
```

---

## Environment
- OS: macOS
- Container runtime: Colima (not Docker Desktop)
- Compose: standalone `docker-compose` (hyphenated) — the `docker compose` plugin is not installed
- IDE: PyCharm (JetBrains)
- Claude Code: terminal CLI + JetBrains plugin

Start Colima before any Docker commands:
```bash
colima start
docker-compose build         # first time / after requirements change
```

Run the pipeline inside the container:
```bash
docker-compose run --rm art-attax python main.py paint tests/fixtures/gut_microbiome_r232.tsv
docker-compose run --rm art-attax python -m paint.key             # colour key

# Maintainer only: palette for a new GTDB release (downloads, then deletes the download)
docker-compose run --rm art-attax python main.py build-palette --release 232
```
`paint` options: `--output`, `--width` (2400), `--height` (3200), `--strokes` (400), `--spread` (0), `--fuzzy` (off).
Use e.g. `--width 3200 --height 1800` for a landscape canvas like `example.jpg`.

---

## Stack
| Concern | Library |
|---|---|
| Flat data | Parquet (via polars) |
| Painting | py5 |
| Colour key | matplotlib |
| CLI | Typer |
| Input parsing | polars |

---

## Current status
- [x] Architecture designed
- [x] Docker + Colima setup
- [x] palette/build.py — one command: download → colour → palette + app
- [x] paint/ modules — working; abstract flat-brush style
- [x] main.py CLI — `build-palette`, `build-app`, `paint`
- [x] Colour key (`paint/key.py`)
- [x] Standalone app (`app/`) — styles, colour schemes, screen-size preview

## Known issues / next steps
- Colour schemes and extra styles exist only in the app; the Python painter is brush + GTDB wheel
- No automated tests yet (only the example fixture)
- `key.py` is not exposed as a CLI command.

---

## GTDB notes
- Release: R232
- Taxonomy file: `bac120_taxonomy_r232.tsv.gz` (downloaded by `build-palette`)
- Download URL pattern: `https://data.gtdb.aau.ecogenomic.org/releases/release{N}/{N}.0/bac120_taxonomy_r{N}.tsv.gz`
- Format: `genome_accession\td__Bacteria;p__...;s__...`
- Uniqueness key for taxa is the full lineage string, not just the name
  (homonymous names exist across different clades)
