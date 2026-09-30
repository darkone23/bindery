# bindery

Book-reprint toolkit for the Holy Charisma household org: turns digital-commons-era
PDFs and home scans into press-ready, cut-and-bind book blocks.

**Design & plan:** Paperclip issue [HOL-250](/HOL/issues/HOL-250) — plan doc:
[HOL-250 plan](/HOL/issues/HOL-250#document-plan). First delivery: HOL-251 (M0:
repo scaffold + ingest of the Gita Press *Valmiki-Ramayana* PDF).

## Status

- **M0 — ingest**: done. `bindery ingest` renders every PDF page to a 600 dpi
  archival raster (PNG) under `archive/` plus a `manifest.json` sidecar
  (source URL + checksum, render dpi, sha256 per page). Originals are never
  mutated.
- Next: M1 20-page physical proof, M2 structure mining (docling), M3+ assembly /
  trim / imposition (see the plan).

## Interface

Everything goes through `just` recipes:

```sh
just build            # nix build (packages.default = bindery CLI)
just ingest-fixture   # pytest suite on a tiny committed fixture PDF
just dataset-fetch    # fetch the Ramayana PDF into gitignored dataset/
just ingest           # 600 dpi render of dataset/ PDF into archive/ + manifest
just verify           # recheck archive/ against its manifest
```

## Layout

- `bindery.py` — the CLI (stdlib only; renders via poppler `pdftoppm`/`pdfinfo`)
- `tests/` — pytest suite; `tests/fixtures/fixture3.pdf` is a committed 3-page
  fixture so the ingest stage is provable without the 2303-page run
- `dataset/` — downloaded sources (gitignored, never in git)
- `archive/` — ingest output (gitignored; reproducible from dataset + manifest)
- `flake.nix` — `packages.default` (CLI with poppler on PATH),
  `devShells.default`, `checks.default` (pytest)

## House rules

- Deps from nixpkgs only. No secrets. Sources are public domain / public URL.
- Just recipes are the only interface; nothing is hand-done twice.
