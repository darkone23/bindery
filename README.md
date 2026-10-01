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
- **M1 — 20-page physical proof** (HOL-253): `just proof` takes archive pages
  400–419 through assemble → trim → impose and emits `build/press.pdf`
  (5 duplex Letter sheets: signatures 8+8+4, long-edge flip, creep
  compensation, crop/fold marks, registration block) plus
  `build/proof-screen.pdf` (reading-order screen proof). See `PRINTING.md`.
- **M2 — structure mining** (HOL-255): `just structure` runs the docling
  layout pass (2.118.0) + tesseract OCR over every archive page — each page
  processed individually and cached — and derives per-page structure
  records, `sarga-map.json` (kanda/sarga → archive page ranges),
  `toc-draft.md` and `fidelity-report.md`. Any single page is inspectable
  on its own: `just page N` answers "what does page N contain?".
  Boundaries only — no verbatim retype. The impure/unfree tooling (docling
  deps, model download) is confined to the stage's devenv
  (`devenv.nix`/`devenv.yaml`, run via `devenv shell`).
- **M3 — full volume + apparatus** (HOL-256): `just enhance` (profile-driven
  per-page ops; near-no-op on the clean vector body, per-page diffs in the
  enhanced manifest), `bindery apparatus` (preface / ToC / errata leaves
  typeset at trim geometry), `[order] full` (the complete-volume order from
  the sarga map, apparatus leaves inserted first), and 16-page-signature
  imposition: `just impose --full` / `just full`.
- **M3 board rev — targeted supplement**: the board narrowed the deliverable
  to the pages actually missing from the 1970s edition: `book.toml` is the
  supplement profile — `[order] sarga_range` (ToC + Uttara-kanda sargas
  42–111, archive pages 2159–2303), `apparatus_kinds = ["toc"]` (the
  supplement renders the ToC only; preface/errata stay one config flip
  away). `just supplement` / `just impose --full` builds it. The
  full-volume profile remains available in code (full mode).
- Next: M4 splice of Tommy's scans
  (see the plan).

## Interface

Everything goes through `just` recipes:

```sh
just build            # nix build (packages.default = bindery CLI)
just ingest-fixture   # pytest suite (ingest fixture + M1 trim/impose fixture)
just dataset-fetch    # fetch the Ramayana PDF into gitignored dataset/
just ingest           # 600 dpi render of dataset/ PDF into archive/ + manifest
just verify           # recheck archive/ against its manifest
just structure        # M2: docling layout + tesseract OCR -> sarga map/ToC/fidelity
just page N           # "what does page N contain?" from the per-page records
just structure-fixture # pytest for the structure stage (pure units + 7-page slice)
just enhance          # M3: profile-driven per-page ops -> build/enhance/
just apparatus        # M3: preface/ToC/errata leaves -> build/apparatus/
just supplement       # M3 chain (board rev): enhance -> apparatus -> assemble -> trim -> impose
just assemble         # book.toml slice -> build/order.json (manifest-validated)
just trim             # crop to the trim profile -> build/trim/ + trim.json
just impose           # duplex Letter imposition -> build/press.pdf + proof
just proof            # the full M1 chain
```

## Layout

- `bindery.py` — the CLI (stdlib only; renders via poppler `pdftoppm`/`pdfinfo`)
- `structure.py` — the M2 structure stage (docling + tesseract; heavy imports
  are lazy so the pure flake never needs them; run via `just structure`)
- `tests/` — pytest suite; `tests/fixtures/fixture3.pdf` is a committed 3-page
  fixture so the ingest stage is provable without the 2303-page run;
  `tests/fixtures/structure-slice/` is a committed 7-page archive slice
  (archive pages 283–289) so the structure stage is provable end-to-end
- `dataset/` — downloaded sources (gitignored, never in git)
- `archive/` — ingest output (gitignored; reproducible from dataset + manifest)
- `build/` — stage outputs (gitignored), incl. `build/structure/`
- `devenv.nix` / `devenv.yaml` — the structure stage's devenv
  (`devenv shell`): docling-slim + tesseract + poppler; the only
  impure/unfree environment (allowUnfree scoped in devenv.yaml)
- `flake.nix` — `packages.default` (CLI with poppler on PATH),
  `devShells.default`, `checks.default` (pytest; stays unfree-clean)

## House rules

- Deps from nixpkgs only. No secrets. Sources are public domain / public URL.
- Just recipes are the only interface; nothing is hand-done twice.
- GitHub pushes to this repo (darkone23/bindery) run through
  `GITHUB_DARKONE23_ADMIN_PAT` via the repo-local env-reading credential
  helper (`git config --local --get 'credential.https://github.com/darkone23.helper'`);
  the org-wide chipnet helper is scoped to holycharisma repos only
  (chipnet branch `fix/gh-credential-org-scope`).
