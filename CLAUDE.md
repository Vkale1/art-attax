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

### Three phases

**Phase 1 — Data** (`db/build_db.py`)
- Source: GTDB R232 bacterial taxonomy TSV — **not downloaded automatically**.
  Download it manually and save it as `data/bac120_taxonomy.tsv.gz` (no `_r232` suffix;
  path is hard-coded in `build_db.py`)
- Parses each lineage into its 7 ranks and builds a DuckDB database
- Two tables: `taxa` (one row per unique taxon) and `genomes` (one row per genome)
- A flat Parquet export (`data/taxa.parquet`) is also written for fast bulk reads

**Phase 2 — Colour assignment** (`db/assign_colours.py`)
- Walks the taxonomy tree directly; deterministic, no training
- Each taxon owns a slice of hues that its children divide, weighted by sqrt(species count);
  hue = middle of the slice. Big phyla are scattered around the wheel
- Class/order/family shift lightness and saturation; descendants inherit the shift
- A `brush_style` per rank is also written, but the current painter no longer uses it
- Colour values are written back into the DuckDB taxa table and Parquet is refreshed
- `db/export_palette.py` then writes `palette/gtdb_r232_colours.parquet`, which **is**
  committed. Users paint from it, so phases 1–2 are maintainer-only
- The palette is CC BY-SA 4.0 (derived from GTDB), unlike the MIT code

**Phase 3 — Painting** (`paint/`)
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
- DuckDB over SQLite: better analytical query performance at GTDB scale
- Parquet alongside DuckDB: fast flat reads during painting without loading full DB
- Direct tree colouring over Poincaré embeddings: the trained embeddings never left the
  centre of the disk, so species hues were close to random
- py5 for painting: designed for generative art, expressive brushstroke control
- Hue is the taxon's identity — the painter jitters tone but never changes hue
  (except the opt-in `--spread`)
- No metadata enrichment: the tool is deliberately scoped to taxonomy + abundance only

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
├── db/
│   ├── build_db.py         ← Phase 1: parse GTDB TSV → DuckDB + Parquet
│   ├── assign_colours.py   ← Phase 2: taxonomy tree → colour map
│   └── export_palette.py   ← write the committed palette
├── palette/                ← prebuilt colours, committed
├── paint/
│   ├── palette.py          ← locate + load the palette
│   ├── loader.py           ← Phase 3: load abundance TSV, join to palette
│   ├── spread.py           ← optional hue spreading
│   ├── composer.py         ← Phase 3: stroke planning / canvas layout
│   ├── brushes.py          ← Phase 3: flat-brush stroke rendering with py5
│   └── key.py              ← sunburst colour key
├── tests/fixtures/
│   └── gut_microbiome_r232.tsv  ← example abundance input
├── main.py                 ← CLI entry point (Typer)
├── data/                   ← mounted volume, not committed
│   ├── bac120_taxonomy.tsv.gz
│   ├── gtdb_r232.duckdb
│   └── taxa.parquet
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

# Maintainer only: rebuild the palette for a new GTDB release
docker-compose run --rm art-attax python main.py build-db         # Phase 1
docker-compose run --rm art-attax python main.py assign-colours   # Phase 2
docker-compose run --rm art-attax python main.py export-palette
```
`paint` options: `--output`, `--width` (2400), `--height` (3200), `--strokes` (400), `--spread` (0), `--fuzzy` (off).
Use e.g. `--width 3200 --height 1800` for a landscape canvas like `example.jpg`.

---

## Stack
| Concern | Library |
|---|---|
| Database | DuckDB |
| Flat data | Parquet (via DuckDB / polars) |
| Painting | py5 |
| Colour key | matplotlib |
| CLI | Typer |
| Input parsing | polars |

ETE4 and colorspacious are in `requirements.txt` but not currently used.

---

## Current status
- [x] Architecture designed
- [x] Docker + Colima setup
- [x] build_db.py — working; DB + Parquet built in `data/`
- [x] assign_colours.py — working
- [x] paint/ modules — working; abstract flat-brush style
- [x] main.py CLI — `build-db`, `assign-colours`, `export-palette`, `paint`
- [x] Colour key (`paint/key.py`)

## Known issues / next steps
- Palette is entirely data-driven (muted, full wheel); an optional palette
  shift (e.g. warm, like `example.jpg`) that preserves relative hue relationships could be added.
- `key.py` is not exposed as a CLI command.

---

## GTDB notes
- Release: R232
- Taxonomy file: `bac120_taxonomy_r232.tsv.gz` (save locally as `data/bac120_taxonomy.tsv.gz`)
- Download URL: `https://data.gtdb.aau.ecogenomic.org/releases/release232/232.0/bac120_taxonomy_r232.tsv.gz`
- Format: `genome_accession\td__Bacteria;p__...;s__...`
- Uniqueness key for taxa is the full lineage string, not just the name
  (homonymous names exist across different clades)
