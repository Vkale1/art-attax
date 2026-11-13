# GTDB Art — Claude Code Context

## Scope rules
- Only read and edit files within this repository
- Do not access files outside this directory
- Do not read ~/.ssh, ~/.env, or any file outside this project folder
- Do not execute network commands unless explicitly asked
- Never read or modify .env — use env.example to understand the variable names only

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

**Phase 2 — AI (colour assignment)** (`db/assign_colours.py`)
- Trains 2D Poincaré embeddings on the child→parent edges using `geoopt`
- Hyperbolic space naturally represents hierarchies — taxa close in the tree land
  close together, root near the centre, species near the boundary
- Disk coordinates → colour: angle = hue, radius = saturation, lightness fixed at 0.5
- A `brush_style` per rank is also written, but the current painter no longer uses it
- Colour values are written back into the DuckDB taxa table and Parquet is refreshed

**Phase 3 — Painting** (`paint/`)
- `loader.py` reads an abundance TSV (full lineage or species name + count) and joins
  to the DB; exact lineage match first, species-name fallback, unmatched rows dropped
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
- Poincaré embeddings over hand-crafted colour rules: mathematically principled,
  phylogenetic distance maps cleanly to colour distance
- py5 for painting: designed for generative art, expressive brushstroke control
- Hue is the taxon's identity — the painter jitters tone but never changes hue
- No metadata enrichment: the tool is deliberately scoped to taxonomy + abundance only

---

## File structure
```
art-attax/
├── CLAUDE.md               ← you are here
├── .claudeignore
├── env.example             ← copy to ../.env (one level ABOVE the repo)
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── example.jpg             ← style reference for the painting look
├── db/
│   ├── build_db.py         ← Phase 1: parse GTDB TSV → DuckDB + Parquet
│   └── assign_colours.py   ← Phase 2: Poincaré embeddings → colour map
├── paint/
│   ├── loader.py           ← Phase 3: load abundance TSV, join to DB
│   ├── composer.py         ← Phase 3: stroke planning / canvas layout
│   ├── brushes.py          ← Phase 3: flat-brush stroke rendering with py5
│   └── key.py              ← sunburst colour key
├── tests/fixtures/
│   └── gut_microbiome.tsv  ← example abundance input
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

Start Colima before any Docker commands, and make sure `../.env` exists
(compose fails without it):
```bash
colima start
cp env.example ../.env       # first time only
docker-compose build         # first time / after requirements change
```

Run the pipeline inside the container:
```bash
docker-compose run --rm art-attax python main.py build-db         # Phase 1
docker-compose run --rm art-attax python main.py assign-colours   # Phase 2
docker-compose run --rm art-attax python main.py paint tests/fixtures/gut_microbiome.tsv
docker-compose run --rm art-attax python -m paint.key             # colour key
```
`paint` options: `--output`, `--width` (2400), `--height` (3200), `--strokes` (400).
Use e.g. `--width 3200 --height 1800` for a landscape canvas like `example.jpg`.

---

## Stack
| Concern | Library |
|---|---|
| Database | DuckDB |
| Flat data | Parquet (via DuckDB / polars) |
| Hyperbolic embeddings | geoopt (PyTorch) |
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
- [x] main.py CLI — `build-db`, `assign-colours`, `paint`
- [x] Colour key (`paint/key.py`)

## Known issues / next steps
- Only 6 of 22 taxa in `tests/fixtures/gut_microbiome.tsv` match R232 — the fixture uses
  older names (e.g. `Firmicutes_A`). Update the fixture and/or make matching more forgiving.
- Palette is entirely data-driven (currently cool blues/olives); an optional palette
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
